package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Enqueue handoff failures and at-most-once ownership; no engine execution. */
public final class DispatchFixtureConsumer {
    private static int count;
    private static void require(boolean value){if(!value)throw new AssertionError("Dispatch case "+count);count++;}
    private interface Attempt {void run() throws Exception;}
    private static void fails(String code,Attempt attempt) throws Exception {
        try{attempt.run();throw new AssertionError("Accepted invalid dispatch");}
        catch(WireEnvelope.EnvelopeException expected){require(expected.code.equals(code) && expected.getMessage().equals(code));}
    }
    private static String outcome(GatewaySessionBoundary owner) throws Exception {return owner.receiptFor("first").getAsJsonObject("body").get("outcome").getAsString();}
    public static void run(GatewayHandshake.ViewerContext context,String offered,String request) throws Exception {
        count=0;
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);AtomicInteger calls=new AtomicInteger();
            GatewaySessionBoundary.Submission enqueue=value->{calls.incrementAndGet();require(value.get("message_id").getAsString().equals("first"));value.getAsJsonObject("body").addProperty("action_id","mutated");};
            require(owner.dispatch(request,enqueue).shouldSubmit);require(!owner.dispatch(request,enqueue).shouldSubmit);require(calls.get()==1);
            require(outcome(owner).equals("submitted"));require(owner.state()==GatewaySessionBoundary.State.ACTIVE);
            JsonObject wrong=WireMessages.parse(request);wrong.addProperty("message_id","other");wrong.getAsJsonObject("body").addProperty("action_id","unoffered");
            require(!owner.dispatch(wrong.toString(),enqueue).shouldSubmit);require(calls.get()==1);
            owner.recordOutcome("first","confirmed",null);require(!owner.dispatch(request,enqueue).shouldSubmit);require(calls.get()==1);
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);AtomicInteger effects=new AtomicInteger();
            fails("SESSION_DISPATCH_FAILED",()->owner.dispatch(request,value->{effects.incrementAndGet();throw new IOException("private callback details");}));
            require(effects.get()==1);require(owner.state()==GatewaySessionBoundary.State.FAULTED);require(outcome(owner).equals("uncertain"));
            fails("SESSION_CLOSED",()->owner.dispatch(request,value->effects.incrementAndGet()));require(effects.get()==1);
            require(owner.recordOutcome("first","confirmed",null).getAsJsonObject("body").get("outcome").getAsString().equals("confirmed"));
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);
            fails("SESSION_DISPATCH_FAILED",()->owner.dispatch(request,value->{throw new InterruptedException("private");}));
            try{require(Thread.currentThread().isInterrupted());require(outcome(owner).equals("uncertain"));}finally{Thread.interrupted();}
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);try{owner.dispatch(request,null);throw new AssertionError();}catch(IllegalArgumentException expected){require(owner.state()==GatewaySessionBoundary.State.ACTIVE);}
            require(owner.dispatch(request,value->{
                fails("SESSION_REENTRANT",()->owner.prepare(request));fails("SESSION_REENTRANT",()->owner.observe(offered));
                fails("SESSION_REENTRANT",()->owner.recordOutcome("first","confirmed",null));fails("SESSION_REENTRANT",()->owner.disconnected());
                fails("SESSION_REENTRANT",()->owner.receiptFor("first"));
                try{owner.close();throw new AssertionError();}catch(IllegalStateException expected){require(expected.getMessage().equals("SESSION_REENTRANT"));}
            }).shouldSubmit);require(outcome(owner).equals("submitted"));
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);AssertionError original=new AssertionError("fixture fatal callback");
            try{owner.dispatch(request,value->{throw original;});throw new AssertionError("Swallowed fatal error");}
            catch(AssertionError expected){require(expected==original);}
            require(owner.state()==GatewaySessionBoundary.State.FAULTED);require(outcome(owner).equals("uncertain"));
        }
        ExecutorService workers=Executors.newFixedThreadPool(2);
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);AtomicInteger calls=new AtomicInteger();CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);
            Callable<Boolean> submit=()->{ready.countDown();if(!go.await(2,TimeUnit.SECONDS))throw new AssertionError();return owner.dispatch(request,value->calls.incrementAndGet()).shouldSubmit;};
            Future<Boolean> a=workers.submit(submit),b=workers.submit(submit);require(ready.await(2,TimeUnit.SECONDS));go.countDown();
            require(a.get(2,TimeUnit.SECONDS)^b.get(2,TimeUnit.SECONDS));require(calls.get()==1);
        }finally{workers.shutdownNow();require(workers.awaitTermination(3,TimeUnit.SECONDS));}
        System.out.println("Java submission dispatch handoff: "+count+" checks passed");
    }
}

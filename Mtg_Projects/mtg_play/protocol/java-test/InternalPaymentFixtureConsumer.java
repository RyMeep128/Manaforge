package manaforge.protocol;

import com.google.gson.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import manaforge.payment.PaymentCoordinator;
import manaforge.payment.PaymentCoordinator.*;
import manaforge.payment.gateway.GatewayPaymentPort;

/** Shared admission checks with synthetic native callbacks. No live XMage execution. */
public final class InternalPaymentFixtureConsumer {
    private static int count;
    private static void check(boolean condition){count++;if(!condition)throw new AssertionError("PAYMENT_ADMISSION_"+count);}
    private static String command(JsonObject request,String id){JsonObject copy=request.deepCopy();copy.addProperty("message_id",id);return copy.toString();}
    private static final class Native implements EnginePort {
        int calls,currentChecks,failCurrentAt;boolean current=true,throwing,fatal;Submission result=Submission.ENQUEUED;final AssertionError fatalFailure=new AssertionError("native fatal fixture");Runnable onEnqueue=()->{};
        public boolean isCurrent(Context context){if(++currentChecks==failCurrentAt)throw new IllegalStateException("private preflight detail");return current;}
        public Assessment inspect(Context context){return new Assessment(Safety.VERIFIED_ORDINARY_EQUIVALENT,Arrays.asList("native-step"));}
        public Submission enqueue(Attempt attempt){calls++;onEnqueue.run();if(throwing)throw new IllegalStateException("private native detail");if(fatal)throw fatalFailure;return result;}
    }
    public static void run(GatewayHandshake.ViewerContext auth,String original,String request) throws Exception {
        count=0;JsonObject snapshot=JsonParser.parseString(original).getAsJsonObject();
        JsonObject decision=snapshot.getAsJsonObject("body").getAsJsonObject("snapshot").getAsJsonObject("decision");decision.addProperty("family","mana");
        String offered=snapshot.toString();JsonObject manual=WireMessages.parse(request);JsonObject body=manual.getAsJsonObject("body");
        body.remove("action_id");body.addProperty("operation","select_mana_source");body.addProperty("object_id","fixture-0002");
        String session=auth.sessionId,viewer=auth.viewerId,decisionId=body.get("decision_id").getAsString();long revision=body.get("revision").getAsLong();
        Context context=new Context(session,viewer,"payment",decisionId,revision);
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);check(owner.reserveInternal(session,"other",revision,decisionId)==null);check(owner.reserveInternal(session,viewer,revision-1,decisionId)==null);
            GatewaySessionBoundary.InternalReservation lease=owner.reserveInternal(session,viewer,revision,decisionId);check(lease!=null && owner.internalCurrent(lease));check(owner.reserveInternal(session,viewer,revision,decisionId)==null);
            AtomicInteger calls=new AtomicInteger();SubmissionLedger.Prepared blocked=owner.dispatch(command(manual,"blocked"),value->calls.incrementAndGet());check(!blocked.shouldSubmit && calls.get()==0);check(blocked.receipt().getAsJsonObject("body").get("code").getAsString().equals("COMMAND_PENDING"));
            check(owner.settleInternal(lease,false));check(!owner.internalCurrent(lease));check(owner.reserveInternal(session,viewer,revision,decisionId)==null);
            check(owner.settleInternal(lease,true));check(!owner.settleInternal(lease,true));check(owner.dispatch(command(manual,"manual-after"),value->calls.incrementAndGet()).shouldSubmit);check(calls.get()==1);
            check(!owner.dispatch(command(manual,"blocked"),value->calls.incrementAndGet()).shouldSubmit);check(calls.get()==1);
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);owner.dispatch(command(manual,"manual-first"),value->{});Native engine=new Native();
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);check(coordinator.consider()==null);check(engine.calls==0 && coordinator.state()==State.REJECTED);coordinator.close();
            }
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);Native engine=new Native();
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);Attempt attempt=coordinator.consider();check(attempt!=null && engine.calls==1);
                check(!owner.dispatch(command(manual,"overlap"),value->{throw new AssertionError();}).shouldSubmit);
                check(port.enqueue(attempt)==Submission.UNCERTAIN && engine.calls==1);check(port.observe(attempt,Observation.PROGRESS));check(coordinator.observe(attempt,Observation.PROGRESS));check(coordinator.consider()==null);
                check(!port.observe(attempt,Observation.COMPLETE));check(owner.dispatch(command(manual,"explicit-manual"),value->{check(coordinator.claimManual(context));}).shouldSubmit);coordinator.close();
            }
        }
        for(boolean disconnect:new boolean[]{false,true})try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);Native engine=new Native();
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);Attempt attempt=coordinator.consider();
                if(disconnect)owner.disconnected();else {
                    JsonObject next=snapshot.deepCopy();next.addProperty("message_id","replaced-payment");next.getAsJsonObject("body").getAsJsonObject("snapshot").addProperty("revision",revision+1);owner.observe(next.toString());
                    check(owner.reserveInternal(session,viewer,revision+1,decisionId)==null);
                }
                check(!port.isCurrent(context));check(coordinator.consider()==null && engine.calls==1);check(port.observe(attempt,Observation.COMPLETE));check(coordinator.observe(attempt,Observation.COMPLETE));coordinator.close();
            }
        }
        for(int kind=0;kind<3;kind++)try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);Native engine=new Native();engine.throwing=kind==0;engine.fatal=kind==1;engine.result=null;
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);
                boolean escaped=false;try{coordinator.consider();}catch(AssertionError expected){check(expected==engine.fatalFailure);escaped=true;}check(escaped==(kind==1));
                check(coordinator.state()==State.UNCERTAIN && engine.calls==1);check(!owner.dispatch(command(manual,"failed-native"),value->{throw new AssertionError();}).shouldSubmit);coordinator.close();
            }
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32);GatewaySessionBoundary foreign=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);foreign.observe(offered);GatewaySessionBoundary.InternalReservation lease=owner.reserveInternal(session,viewer,revision,decisionId);
            check(!foreign.internalCurrent(lease));check(!foreign.settleInternal(lease,true));owner.close();check(!owner.internalCurrent(lease));
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);Native engine=new Native();engine.failCurrentAt=4;
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);check(coordinator.consider()==null);check(engine.calls==0 && coordinator.state()==State.REJECTED);
                check(owner.dispatch(command(manual,"manual-after-preflight"),value->{}).shouldSubmit);coordinator.close();
            }
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);Native engine=new Native();engine.result=Submission.REJECTED;
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);check(coordinator.consider()==null);check(engine.calls==1 && coordinator.state()==State.REJECTED);
                check(owner.dispatch(command(manual,"manual-after-definite-rejection"),value->{}).shouldSubmit);coordinator.close();
            }
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);check(owner.dispatch(command(manual,"old-manual"),value->{}).shouldSubmit);owner.recordOutcome("old-manual","confirmed",null);
            GatewaySessionBoundary.InternalReservation lease=owner.reserveInternal(session,viewer,revision,decisionId);check(lease!=null);owner.recordOutcome("old-manual","confirmed",null);
            check(owner.internalCurrent(lease));check(!owner.dispatch(command(manual,"new-manual-blocked"),value->{throw new AssertionError();}).shouldSubmit);
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);Native engine=new Native();
            try(GatewayPaymentPort port=new GatewayPaymentPort(owner,engine)) {
                engine.onEnqueue=()->{try{port.close();}catch(java.io.IOException failure){throw new RuntimeException(failure);}};
                PaymentCoordinator coordinator=new PaymentCoordinator(session,viewer,true,port);coordinator.offer(context);coordinator.consider();check(coordinator.state()==State.UNCERTAIN && engine.calls==1);check(coordinator.consider()==null);
                check(!owner.dispatch(command(manual,"no-reentrant-release"),value->{throw new AssertionError();}).shouldSubmit);coordinator.close();
            }
        }
        ExecutorService workers=Executors.newFixedThreadPool(2);
        try {for(int round=0;round<16;round++)try(GatewaySessionBoundary owner=new GatewaySessionBoundary(auth,true,32)) {
            owner.observe(offered);CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);AtomicInteger calls=new AtomicInteger();
            Future<Boolean> automatic=workers.submit(()->{ready.countDown();if(!go.await(2,TimeUnit.SECONDS))throw new AssertionError();return owner.reserveInternal(session,viewer,revision,decisionId)!=null;});
            Future<Boolean> user=workers.submit(()->{ready.countDown();if(!go.await(2,TimeUnit.SECONDS))throw new AssertionError();return owner.dispatch(command(manual,"racing-manual"),value->calls.incrementAndGet()).shouldSubmit;});
            check(ready.await(2,TimeUnit.SECONDS));go.countDown();boolean auto=automatic.get(2,TimeUnit.SECONDS),human=user.get(2,TimeUnit.SECONDS);check(auto^human);check(calls.get()==(human?1:0));
        }}finally{workers.shutdownNow();check(workers.awaitTermination(3,TimeUnit.SECONDS));}
        System.out.println("Java shared internal/manual payment admission: "+count+" synthetic checks passed; no live engine activation");
    }
}

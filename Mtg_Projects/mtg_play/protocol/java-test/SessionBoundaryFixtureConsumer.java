package manaforge.protocol;

import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public final class SessionBoundaryFixtureConsumer {
    private static int count;
    private static void require(boolean value){if(!value)throw new AssertionError("Session boundary case "+count);count++;}
    private interface Attempt {void run() throws Exception;}
    private static void fails(String code,Attempt attempt) throws Exception {
        try{attempt.run();throw new AssertionError("Accepted invalid session operation");}
        catch(WireEnvelope.EnvelopeException expected){require(expected.code.equals(code));}
    }
    private static JsonObject command(String id) {
        JsonObject b=new JsonObject();b.addProperty("session_id","fixture-session");b.addProperty("viewer_id","seat-one");b.addProperty("revision",7);b.addProperty("decision_id","fixture-decision");b.addProperty("operation","perform");b.addProperty("action_id","fixture-action");
        JsonObject e=new JsonObject();e.addProperty("wire_version",1);e.addProperty("message_type","command");e.addProperty("message_id",id);e.add("body",b);return e;
    }
    private static String outcome(JsonObject receipt){return receipt.getAsJsonObject("body").get("outcome").getAsString();}
    public static void run(GatewayHandshake.ViewerContext context,Path path) throws Exception {
        count=0;JsonObject snapshot=JsonParser.parseString(new String(Files.readAllBytes(path),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonObject("snapshot");
        snapshot.addProperty("viewer_id",context.viewerId);snapshot.getAsJsonObject("decision").addProperty("player_id",context.viewerId);
        JsonObject body=new JsonObject();body.addProperty("fixture_only",true);body.add("snapshot",snapshot);
        JsonObject update=new JsonObject();update.addProperty("wire_version",1);update.addProperty("message_type","snapshot");update.addProperty("message_id","s1");update.add("body",body);
        String offered=update.toString(),request=command("first").toString();
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);require(owner.prepare(request).shouldSubmit);require(!owner.prepare(request).shouldSubmit);
            require(owner.prepare(command("second").toString()).receipt().getAsJsonObject("body").get("code").getAsString().equals("COMMAND_PENDING"));
            JsonObject copy=owner.receiptFor("first");copy.getAsJsonObject("body").addProperty("outcome","confirmed");require(outcome(owner.receiptFor("first")).equals("submitted"));
            snapshot.addProperty("revision",8);snapshot.addProperty("status","finished");snapshot.addProperty("result","fixture_complete");snapshot.add("decision",JsonNull.INSTANCE);snapshot.add("actions",new JsonArray());
            update.addProperty("message_type","result");update.addProperty("message_id","r1");owner.observe(update.toString());
            require(outcome(owner.receiptFor("first")).equals("submitted"));require(!owner.prepare(request).shouldSubmit);
            owner.disconnected();require(owner.state()==GatewaySessionBoundary.State.DISCONNECTED);require(outcome(owner.receiptFor("first")).equals("uncertain"));
            fails("SESSION_CLOSED",()->owner.prepare(request));fails("SESSION_CLOSED",()->owner.observe(offered));
            require(outcome(owner.recordOutcome("first","confirmed",null)).equals("confirmed"));require(owner.state()==GatewaySessionBoundary.State.DISCONNECTED);
            owner.disconnected();require(outcome(owner.receiptFor("first")).equals("confirmed"));
            owner.close();owner.close();require(owner.state()==GatewaySessionBoundary.State.CLOSED);fails("SESSION_CLOSED",()->owner.receiptFor("first"));fails("SESSION_CLOSED",()->owner.recordOutcome("first","confirmed",null));
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);owner.prepare(request);JsonObject conflicting=command("first");conflicting.getAsJsonObject("body").addProperty("action_id","other");
            fails("COMMAND_ID_CONFLICT",()->owner.prepare(conflicting.toString()));require(owner.state()==GatewaySessionBoundary.State.FAULTED);require(outcome(owner.receiptFor("first")).equals("uncertain"));fails("SESSION_CLOSED",()->owner.prepare(request));
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);owner.prepare(request);fails("ENVELOPE_INVALID",()->owner.observe("{}"));require(owner.state()==GatewaySessionBoundary.State.FAULTED);require(outcome(owner.receiptFor("first")).equals("uncertain"));
        }
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,1)) {
            owner.observe(offered);owner.prepare(request);fails("COMMAND_HISTORY_FULL",()->owner.prepare(command("second").toString()));require(owner.state()==GatewaySessionBoundary.State.FAULTED);require(outcome(owner.receiptFor("first")).equals("uncertain"));
        }
        ExecutorService workers=Executors.newFixedThreadPool(2);
        try(GatewaySessionBoundary owner=new GatewaySessionBoundary(context,true,16)) {
            owner.observe(offered);CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);
            Callable<Boolean> submit=()->{ready.countDown();if(!go.await(2,TimeUnit.SECONDS))throw new AssertionError();return owner.prepare(request).shouldSubmit;};
            Future<Boolean> a=workers.submit(submit),b=workers.submit(submit);require(ready.await(2,TimeUnit.SECONDS));go.countDown();require(a.get(2,TimeUnit.SECONDS)^b.get(2,TimeUnit.SECONDS));require(outcome(owner.receiptFor("first")).equals("submitted"));
        }finally{workers.shutdownNow();require(workers.awaitTermination(3,TimeUnit.SECONDS));}
        System.out.println("Java viewer session boundary: "+count+" checks passed");
        DispatchFixtureConsumer.run(context,offered,request);
    }
}

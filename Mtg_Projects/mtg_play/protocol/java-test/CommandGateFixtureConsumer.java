package manaforge.protocol;

import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Objects;

/** Synthetic offered-decision tests; no engine or rules simulation. */
public final class CommandGateFixtureConsumer {
    private static int count;
    private static void require(boolean value){if(!value)throw new AssertionError("Command gate case "+count);count++;}
    private static JsonObject wrap(String type,String id,JsonObject body) {
        JsonObject e=new JsonObject();e.addProperty("wire_version",1);e.addProperty("message_type",type);e.addProperty("message_id",id);e.add("body",body);return e;
    }
    private static JsonObject update(JsonObject snapshot,String id) {
        JsonObject body=new JsonObject();body.addProperty("fixture_only",true);body.add("snapshot",snapshot.deepCopy());return wrap("snapshot",id,body);
    }
    private static JsonObject command(String operation,JsonElement value) {
        JsonObject b=new JsonObject();b.addProperty("session_id","fixture-session");b.addProperty("viewer_id","seat-one");b.addProperty("revision",7);b.addProperty("decision_id","fixture-decision");b.addProperty("operation",operation);
        String field=operation.equals("perform")?"action_id":operation.equals("choose")?"option_id":operation.equals("select_mana_source")?"object_id":operation.equals("choose_number")?"value":"values";
        if(value!=null)b.add(field,value);return wrap("command","command-1",b);
    }
    private static void check(GatewayCommandGate gate,JsonObject command,String expected) throws Exception {require(Objects.equals(gate.check(command.toString()),expected));}
    private static JsonObject range(long low,long high){JsonObject r=new JsonObject();r.addProperty("label","Fixture");r.addProperty("minimum",low);r.addProperty("maximum",high);r.add("default",JsonNull.INSTANCE);return r;}
    public static void run(GatewayHandshake.ViewerContext context,Path path) throws Exception {
        count=0;JsonObject snapshot=JsonParser.parseString(new String(Files.readAllBytes(path),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonObject("snapshot");
        snapshot.addProperty("viewer_id",context.viewerId);JsonObject decision=snapshot.getAsJsonObject("decision");decision.addProperty("player_id",context.viewerId);
        JsonObject action=command("perform",new JsonPrimitive("fixture-action"));
        try(GatewayCommandGate gate=new GatewayCommandGate(context,true,64)) {
            check(gate,action,"STALE_REVISION");gate.observe(update(snapshot,"s1").toString());check(gate,action,null);
            for(String field:new String[]{"session_id","viewer_id","revision","decision_id","action_id"}) {
                JsonObject wrong=action.deepCopy();wrong.getAsJsonObject("body").add(field,field.equals("revision")?new JsonPrimitive(6):new JsonPrimitive("other"));
                check(gate,wrong,field.equals("session_id")?"SESSION_MISMATCH":field.equals("viewer_id")?"VIEWER_MISMATCH":field.equals("revision")?"STALE_REVISION":field.equals("decision_id")?"STALE_DECISION":"ACTION_UNAVAILABLE");
            }
            gate.observe(update(snapshot,"s1").toString());check(gate,action,null);
            JsonObject option=new JsonObject();option.addProperty("option_id","option-1");option.addProperty("label","Fixture");option.add("object_id",JsonNull.INSTANCE);option.add("player_id",JsonNull.INSTANCE);option.addProperty("selected",false);
            decision.getAsJsonArray("options").add(option);decision.addProperty("can_finish",true);decision.addProperty("cancellable",true);
            gate.observe(update(snapshot,"s2").toString());
            check(gate,command("choose",new JsonPrimitive("option-1")),null);check(gate,command("choose",new JsonPrimitive("missing")),"ACTION_UNAVAILABLE");
            check(gate,command("finish_selection",null),null);check(gate,command("cancel",null),null);
            decision.addProperty("can_finish",false);decision.addProperty("cancellable",false);decision.addProperty("family","mana");gate.observe(update(snapshot,"s3").toString());
            check(gate,command("finish_selection",null),"ACTION_UNAVAILABLE");check(gate,command("cancel",null),"ACTION_UNAVAILABLE");
            check(gate,command("select_mana_source",new JsonPrimitive("fixture-0002")),null);check(gate,command("select_mana_source",new JsonPrimitive("missing")),"ACTION_UNAVAILABLE");
            decision.addProperty("family","number");decision.addProperty("minimum",-3);decision.addProperty("maximum",3);gate.observe(update(snapshot,"s4").toString());
            check(gate,command("select_mana_source",new JsonPrimitive("fixture-0002")),"ACTION_UNAVAILABLE");
            for(long value:new long[]{-3,0,3})check(gate,command("choose_number",new JsonPrimitive(value)),null);
            for(long value:new long[]{-4,4,Long.MAX_VALUE})check(gate,command("choose_number",new JsonPrimitive(value)),"ACTION_UNAVAILABLE");
            decision.add("minimum",JsonNull.INSTANCE);gate.observe(update(snapshot,"s5").toString());check(gate,command("choose_number",new JsonPrimitive(0)),"ACTION_UNAVAILABLE");
            decision.addProperty("family","amounts");decision.addProperty("minimum",1);decision.addProperty("maximum",1);JsonArray ranges=new JsonArray();ranges.add(range(-3,0));ranges.add(range(0,5));decision.add("amounts",ranges);gate.observe(update(snapshot,"s6").toString());
            check(gate,command("choose_amounts",JsonParser.parseString("[-2,3]")),null);
            for(String values:new String[]{"[-2,4]","[-4,5]","[1]"})check(gate,command("choose_amounts",JsonParser.parseString(values)),"ACTION_UNAVAILABLE");
            ranges=new JsonArray();ranges.add(range(0,Long.MAX_VALUE));ranges.add(range(0,Long.MAX_VALUE));decision.add("amounts",ranges);decision.addProperty("minimum",-2);decision.addProperty("maximum",-2);gate.observe(update(snapshot,"s7").toString());
            check(gate,command("choose_amounts",JsonParser.parseString("[9223372036854775807,9223372036854775807]")),"ACTION_UNAVAILABLE");
            JsonObject event=new JsonObject();event.addProperty("revision",8);event.addProperty("kind","fixture");event.addProperty("player_id",context.viewerId);event.add("code",JsonNull.INSTANCE);event.add("observations",new JsonArray());
            JsonObject body=new JsonObject();body.addProperty("fixture_only",true);body.addProperty("session_id",context.sessionId);body.addProperty("viewer_id",context.viewerId);body.add("event",event);
            gate.observe(wrap("event","e1",body).toString());JsonObject current=action.deepCopy();current.getAsJsonObject("body").addProperty("revision",8);check(gate,current,"STALE_DECISION");
            JsonObject old=JsonParser.parseString(new String(Files.readAllBytes(path),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonObject("snapshot");old.addProperty("viewer_id",context.viewerId);old.getAsJsonObject("decision").addProperty("player_id",context.viewerId);gate.observe(update(old,"s1").toString());check(gate,current,"STALE_DECISION");
            snapshot.addProperty("revision",8);snapshot.add("decision",JsonNull.INSTANCE);gate.observe(update(snapshot,"s8").toString());check(gate,current,"STALE_DECISION");
            snapshot.addProperty("status","finished");snapshot.addProperty("result","fixture_complete");
            JsonObject terminal=update(snapshot,"result-1");terminal.addProperty("message_type","result");gate.observe(terminal.toString());
            check(gate,action,"STALE_REVISION");check(gate,current,"STALE_DECISION");
            gate.close();try{gate.check(action.toString());throw new AssertionError();}catch(WireEnvelope.EnvelopeException expected){require(expected.code.equals("GATE_CLOSED"));}
        }
        try(GatewayCommandGate gate=new GatewayCommandGate(context,true,64)) {
            snapshot.addProperty("revision",7);snapshot.addProperty("status","active");snapshot.add("result",JsonNull.INSTANCE);snapshot.add("decision",decision);gate.observe(update(snapshot,"valid").toString());
            JsonObject wrong=snapshot.deepCopy();wrong.addProperty("viewer_id","other");
            try{gate.observe(update(wrong,"wrong").toString());throw new AssertionError();}catch(WireEnvelope.EnvelopeException expected){require(expected.code.equals("RECEIVE_VIEWER"));}
            try{gate.check(action.toString());throw new AssertionError();}catch(WireEnvelope.EnvelopeException expected){require(expected.code.equals("GATE_CLOSED"));}
        }
        System.out.println("Java authenticated command admission: "+count+" checks passed");
    }
}

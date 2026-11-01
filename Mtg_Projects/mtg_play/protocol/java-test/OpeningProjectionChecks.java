import com.google.gson.*;
import java.util.*;
import java.io.IOException;
import manaforge.protocol.PlayContracts.CardIdentity;
import manaforge.protocol.ReceiveMessages;

/** Synthetic privacy/shape checks; no engine installation or private deck fixture. */
public final class OpeningProjectionChecks {
    static int checks;
    static void check(boolean value){checks++;if(!value)throw new AssertionError("OPENING_PROJECTION_CHECK");}
    static JsonObject state() {
        return JsonParser.parseString("{\"game_id\":\"raw-game\",\"viewer\":\"raw-human\",\"cycle\":8,\"turn\":0,\"phase\":null,\"step\":null,\"active_player\":\"raw-name\",\"priority_player\":null,\"stack\":[],\"exile\":[],\"combat\":[],\"players\":[{\"id\":\"raw-human\",\"name\":\"raw-name\",\"life\":20,\"hand_count\":1,\"library_count\":59,\"left\":false,\"battlefield\":[],\"graveyard\":[],\"command\":[]},{\"id\":\"raw-ai\",\"name\":\"raw-opponent-name\",\"life\":20,\"hand_count\":7,\"library_count\":53,\"left\":false,\"battlefield\":[],\"graveyard\":[],\"command\":[],\"hand\":[{\"name\":\"OPPONENT_SECRET\"}]}],\"hand\":[{\"id\":\"raw-card\",\"hidden\":false,\"face_down\":false,\"name\":\"Forest\",\"set\":\"M10\",\"number\":\"248\",\"view_rules\":[\"Tap for mana\"]}]}").getAsJsonObject();
    }
    static JsonObject prompt(){return JsonParser.parseString("{\"kind\":\"GAME_ASK\",\"decision_id\":41,\"cycle\":8,\"message\":\"Keep?\"}").getAsJsonObject();}
    static ManaforgeOpeningProjection projection() {
        CardIdentity id=new CardIdentity();id.printing_id="exact-selected-printing";id.deck_entry_id="native-entry";
        Map<String,CardIdentity> bindings=new HashMap<>();bindings.put("M10/248",id);
        ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection("session","human","raw-human",bindings);
        id.printing_id="MUTATED_BINDING";return projection;
    }
    static void shape(JsonObject snapshot) throws Exception {
        JsonObject body=new JsonObject();body.addProperty("fixture_only",false);body.add("snapshot",snapshot);
        JsonObject envelope=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","opening");envelope.add("body",body);
        ReceiveMessages.parse(envelope.toString(),"session","human",1,false);check(true);
    }
    static void rejects(JsonObject raw,JsonObject request) throws Exception {
        try{projection().project(raw,request);throw new AssertionError("ACCEPTED_UNSUPPORTED_OPENING");}
        catch(IOException error){check(error.getMessage().equals("LIVE_OPENING_PROJECTION_UNSUPPORTED") && error.getCause()==null);}
    }

    static String choose(JsonObject snapshot,int index) {
        JsonObject envelope=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","command");envelope.addProperty("message_id","public-choice");
        JsonObject body=new JsonObject();body.add("session_id",snapshot.get("session_id"));body.add("viewer_id",snapshot.get("viewer_id"));body.add("revision",snapshot.get("revision"));body.addProperty("operation","choose");
        body.add("decision_id",snapshot.getAsJsonObject("decision").get("decision_id"));body.add("option_id",snapshot.getAsJsonObject("decision").getAsJsonArray("options").get(index).getAsJsonObject().get("option_id"));envelope.add("body",body);return envelope.toString();
    }
    static JsonObject claim(ManaforgeOpeningProjection projection,String command) throws Exception {
        return projection.claimBoolean(command,"session","human","raw-game","raw-human",41,8);
    }
    interface Attempt {void run() throws Exception;}
    static void fails(String code,Attempt attempt) throws Exception {
        try{attempt.run();throw new AssertionError("ACCEPTED_BAD_CHOICE");}catch(IOException failure){check(failure.getMessage().equals(code) && failure.getCause()==null);}
    }
    static void choiceChecks() throws Exception {
        for(int index=0;index<2;index++) {
            ManaforgeOpeningProjection p=projection();JsonObject snapshot=p.project(state(),prompt());String command=choose(snapshot,index);
            JsonObject nativeCommand=claim(p,command);check(nativeCommand.get("value").getAsBoolean()==(index==0));
            check(nativeCommand.get("game_id").getAsString().equals("raw-game") && nativeCommand.get("decision_id").getAsInt()==41 && nativeCommand.get("kind").getAsString().equals("boolean"));
            fails("STALE_DECISION",()->claim(p,command));
        }
        for(String field:new String[]{"session_id","viewer_id","revision","decision_id","option_id"}) {
            ManaforgeOpeningProjection p=projection();JsonObject snapshot=p.project(state(),prompt());String command=choose(snapshot,0);
            JsonObject bad=JsonParser.parseString(command).getAsJsonObject();
            if(field.equals("revision"))bad.getAsJsonObject("body").addProperty(field,0);else bad.getAsJsonObject("body").addProperty(field,"wrong");
            String code=field.equals("session_id")?"SESSION_MISMATCH":field.equals("viewer_id")?"VIEWER_MISMATCH":field.equals("revision")?"STALE_REVISION":field.equals("decision_id")?"STALE_DECISION":"ACTION_UNAVAILABLE";
            fails(code,()->claim(p,bad.toString()));check(claim(p,command).get("value").getAsBoolean());
        }
        for(int mode=0;mode<6;mode++) {
            final int value=mode;ManaforgeOpeningProjection p=projection();String command=choose(p.project(state(),prompt()),0);
            String code=mode==0?"SESSION_MISMATCH":(mode==1 || mode==5)?"VIEWER_MISMATCH":"STALE_DECISION";
            fails(code,()->p.claimBoolean(command,value==0?"wrong":"session",value==1?"wrong":"human",value==2?"wrong":"raw-game",value==5?"wrong":"raw-human",value==3?42:41,value==4?9:8));
            check(claim(p,command).get("value").getAsBoolean());
        }
        ManaforgeOpeningProjection shared=projection();String sharedCommand=choose(shared.project(state(),prompt()),0);
        java.util.concurrent.atomic.AtomicInteger claims=new java.util.concurrent.atomic.AtomicInteger(),rejected=new java.util.concurrent.atomic.AtomicInteger();
        java.util.concurrent.ExecutorService workers=java.util.concurrent.Executors.newFixedThreadPool(2);
        try {
            List<java.util.concurrent.Future<?>> results=new ArrayList<>();
            for(int i=0;i<2;i++)results.add(workers.submit(()->{try{claim(shared,sharedCommand);claims.incrementAndGet();}catch(Exception failure){if(!"STALE_DECISION".equals(failure.getMessage()))throw new RuntimeException(failure);rejected.incrementAndGet();}}));
            for(java.util.concurrent.Future<?> result:results)result.get(5,java.util.concurrent.TimeUnit.SECONDS);
            check(claims.get()==1 && rejected.get()==1);
        }finally{workers.shutdownNow();}
        ManaforgeOpeningProjection p=projection();String old=choose(p.project(state(),prompt()),0);p.project(state(),prompt());fails("STALE_REVISION",()->claim(p,old));
        String fresh=choose(p.project(state(),prompt()),0);p.invalidateDecision();fails("STALE_DECISION",()->claim(p,fresh));
        String beforeFailure=choose(p.project(state(),prompt()),0);JsonObject bad=prompt();bad.addProperty("kind","GAME_SELECT");
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->p.project(state(),bad));fails("STALE_DECISION",()->claim(p,beforeFailure));
    }
    static JsonObject priorityPrompt(){JsonObject result=prompt();result.addProperty("kind","GAME_SELECT");result.addProperty("is_priority",true);return result;}
    static JsonObject landState(){JsonObject result=state();result.addProperty("priority_player","raw-name");JsonArray playable=new JsonArray();playable.add("raw-card");result.add("playable",playable);JsonObject kinds=new JsonObject();kinds.addProperty("raw-card","play_land");result.add("action_kinds",kinds);return result;}
    static String perform(JsonObject snapshot){JsonObject out=JsonParser.parseString(chooseForAction(snapshot)).getAsJsonObject();return out.toString();}
    static String chooseForAction(JsonObject snapshot){JsonObject body=new JsonObject(),out=new JsonObject();out.addProperty("wire_version",1);out.addProperty("message_type","command");out.addProperty("message_id","land-action");for(String field:new String[]{"session_id","viewer_id","revision"})body.add(field,snapshot.get(field));body.addProperty("operation","perform");body.add("decision_id",snapshot.getAsJsonObject("decision").get("decision_id"));body.add("action_id",snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("action_id"));out.add("body",body);return out.toString();}
    static void landChecks() throws Exception {
        ManaforgeOpeningProjection passOwner=projection();JsonObject passSnapshot=passOwner.project(landState(),priorityPrompt(),true);
        JsonObject passAction=passSnapshot.getAsJsonArray("actions").get(1).getAsJsonObject();
        check(passAction.get("kind").getAsString().equals("pass") && passAction.get("object_id").isJsonNull());
        JsonObject passWire=JsonParser.parseString(perform(passSnapshot)).getAsJsonObject();passWire.getAsJsonObject("body").add("action_id",passAction.get("action_id"));
        JsonObject nativePass=passOwner.claimAction(passWire.toString(),"session","human","raw-game","raw-human",41,8);
        check(nativePass.get("kind").getAsString().equals("boolean") && !nativePass.get("value").getAsBoolean());
        fails("STALE_DECISION",()->passOwner.claimAction(passWire.toString(),"session","human","raw-game","raw-human",41,8));
        JsonObject empty=landState();empty.add("playable",new JsonArray());
        JsonObject onlyPass=projection().project(empty,priorityPrompt(),true);shape(onlyPass);
        check(onlyPass.getAsJsonArray("actions").size()==1 && onlyPass.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString().equals("pass"));
        check(projection().project(state(),prompt(),true).getAsJsonArray("actions").size()==0);
        for(String field:new String[]{"session_id","viewer_id","revision","decision_id","action_id"}) {
            ManaforgeOpeningProjection bound=projection();String valid=perform(bound.project(empty,priorityPrompt(),true));
            JsonObject bad=JsonParser.parseString(valid).getAsJsonObject();
            if(field.equals("revision"))bad.getAsJsonObject("body").addProperty(field,0);else bad.getAsJsonObject("body").addProperty(field,"wrong");
            String code=field.equals("session_id")?"SESSION_MISMATCH":field.equals("viewer_id")?"VIEWER_MISMATCH":field.equals("revision")?"STALE_REVISION":field.equals("decision_id")?"STALE_DECISION":"ACTION_UNAVAILABLE";
            fails(code,()->bound.claimAction(bad.toString(),"session","human","raw-game","raw-human",41,8));
            check(!bound.claimAction(valid,"session","human","raw-game","raw-human",41,8).get("value").getAsBoolean());
        }
        ManaforgeOpeningProjection fresh=projection();String previous=perform(fresh.project(landState(),priorityPrompt()));
        fresh.project(state(),prompt());fails("STALE_REVISION",()->fresh.claimAction(previous,"session","human","raw-game","raw-human",41,8));
        ManaforgeOpeningProjection p=projection();JsonObject snapshot=p.project(landState(),priorityPrompt());shape(snapshot);
        check(snapshot.getAsJsonArray("actions").size()==1 && snapshot.getAsJsonObject("decision").get("family").getAsString().equals("selection"));
        check(!snapshot.get("actions_complete").getAsBoolean() && snapshot.getAsJsonObject("decision").get("is_priority").getAsBoolean());
        String wire=perform(snapshot);JsonObject nativeCommand=p.claimAction(wire,"session","human","raw-game","raw-human",41,8);check(nativeCommand.get("kind").getAsString().equals("object") && nativeCommand.get("value").getAsString().equals("raw-card"));
        fails("STALE_DECISION",()->p.claimAction(wire,"session","human","raw-game","raw-human",41,8));
        JsonObject hidden=landState();hidden.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("hidden",true);check(projection().project(hidden,priorityPrompt()).getAsJsonArray("actions").size()==0);
        JsonObject unknown=landState();unknown.getAsJsonObject("action_kinds").addProperty("raw-card","activate");check(projection().project(unknown,priorityPrompt()).getAsJsonArray("actions").size()==0);
        JsonObject notOffered=landState();notOffered.add("playable",new JsonArray());check(projection().project(notOffered,priorityPrompt()).getAsJsonArray("actions").size()==0);
        JsonObject board=landState(),permanent=board.getAsJsonArray("hand").get(0).getAsJsonObject().deepCopy();permanent.addProperty("id","raw-permanent");permanent.addProperty("controller_name","raw-opponent-name");permanent.addProperty("owner_name","");permanent.addProperty("tapped",true);permanent.addProperty("damage",0);board.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").add(permanent);
        snapshot=projection().project(board,priorityPrompt());shape(snapshot);check(snapshot.getAsJsonArray("objects").size()==2 && !snapshot.toString().contains("raw-permanent"));
        check(snapshot.getAsJsonArray("objects").get(1).getAsJsonObject().get("tapped").getAsBoolean());
        check(snapshot.getAsJsonArray("objects").get(1).getAsJsonObject().get("card_identity").isJsonNull());
        JsonObject combat=priorityPrompt();combat.add("attackers",new JsonArray());rejects(landState(),combat);
        for(String priority:new String[]{null,"unknown","raw-opponent-name"}) {
            JsonObject wrong=landState();wrong.addProperty("priority_player",priority);rejects(wrong,priorityPrompt());
        }
        JsonObject concealed=landState();concealed.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("face_down",true);
        check(projection().project(concealed,priorityPrompt()).getAsJsonArray("actions").size()==0);
        for(String field:new String[]{"session_id","viewer_id","revision","decision_id","action_id"}) {
            ManaforgeOpeningProjection bound=projection();String valid=perform(bound.project(landState(),priorityPrompt()));
            JsonObject bad=JsonParser.parseString(valid).getAsJsonObject();
            if(field.equals("revision"))bad.getAsJsonObject("body").addProperty(field,0);else bad.getAsJsonObject("body").addProperty(field,"wrong");
            String code=field.equals("session_id")?"SESSION_MISMATCH":field.equals("viewer_id")?"VIEWER_MISMATCH":field.equals("revision")?"STALE_REVISION":field.equals("decision_id")?"STALE_DECISION":"ACTION_UNAVAILABLE";
            fails(code,()->bound.claimAction(bad.toString(),"session","human","raw-game","raw-human",41,8));
            check(bound.claimAction(valid,"session","human","raw-game","raw-human",41,8).get("value").getAsString().equals("raw-card"));
        }
        ManaforgeOpeningProjection stale=projection();String old=perform(stale.project(landState(),priorityPrompt()));
        stale.project(landState(),priorityPrompt());fails("STALE_REVISION",()->stale.claimAction(old,"session","human","raw-game","raw-human",41,8));
        String current=perform(stale.project(landState(),priorityPrompt()));JsonObject wrong=landState();wrong.addProperty("priority_player","raw-opponent-name");
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->stale.project(wrong,priorityPrompt()));
        fails("STALE_DECISION",()->stale.claimAction(current,"session","human","raw-game","raw-human",41,8));
    }
    public static void main(String[] args) throws Exception {
        ManaforgeOpeningProjection projection=projection();JsonObject raw=state(),request=prompt();JsonObject snapshot=projection.project(raw,request);shape(snapshot);
        String text=snapshot.toString();for(String secret:new String[]{"raw-human","raw-ai","raw-card","raw-name","raw-opponent-name","OPPONENT_SECRET","MUTATED_BINDING"})check(!text.contains(secret));
        check(snapshot.get("revision").getAsLong()==1);check(!snapshot.get("actions_complete").getAsBoolean());
        check(snapshot.getAsJsonArray("objects").size()==1 && snapshot.getAsJsonArray("actions").size()==0);
        JsonObject card=snapshot.getAsJsonArray("objects").get(0).getAsJsonObject();check(card.getAsJsonObject("card_identity").get("printing_id").getAsString().equals("exact-selected-printing"));
        check(snapshot.getAsJsonObject("decision").getAsJsonArray("options").size()==2);
        card.addProperty("zone","MUTATED_OUTPUT");JsonObject second=projection.project(raw,request);shape(second);
        check(second.get("revision").getAsLong()==2 && !second.toString().contains("MUTATED_OUTPUT"));
        check(!second.getAsJsonArray("objects").get(0).getAsJsonObject().get("object_id").equals(card.get("object_id")));
        for(String hiddenFlag:new String[]{"hidden","face_down"}) {
            raw=state();raw.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty(hiddenFlag,true);
            snapshot=projection().project(raw,prompt());shape(snapshot);text=snapshot.toString();
            check(!text.contains("Forest") && !text.contains("exact-selected-printing") && !text.contains("Tap for mana"));
        }
        raw=state();raw.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("set","UNKNOWN");
        check(projection().project(raw,prompt()).getAsJsonArray("objects").get(0).getAsJsonObject().get("card_identity").isJsonNull());
        raw=state();raw.addProperty("viewer","wrong-viewer");rejects(raw,prompt());
        request=prompt();request.addProperty("cycle",9);rejects(state(),request);
        request=prompt();request.addProperty("kind","GAME_SELECT");rejects(state(),request);
        raw=state();raw.getAsJsonArray("stack").add(new JsonObject());rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(new JsonObject());rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("hand").get(0).getAsJsonObject().remove("hidden");rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("players").add(raw.getAsJsonArray("players").get(0).deepCopy());rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("life",true);rejects(raw,prompt());
        request=prompt();request.addProperty("message","Use 12345678-abcd-1234-abcd-123456789abc");check(!projection().project(state(),request).toString().contains("12345678-abcd-1234-abcd-123456789abc"));
        choiceChecks();landChecks();
        System.out.println("Opening projection: "+checks+" privacy, schema, isolation and fail-closed checks passed");
    }
}

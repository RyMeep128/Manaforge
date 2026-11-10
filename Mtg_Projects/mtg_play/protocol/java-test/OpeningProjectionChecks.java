import com.google.gson.*;
import java.util.*;
import java.io.IOException;
import manaforge.protocol.PlayContracts.CardIdentity;
import manaforge.protocol.LaunchContracts.NativeLaunchEntry;
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
    static JsonObject attackState() {
        JsonObject raw=landState(),card=raw.getAsJsonArray("hand").get(0).getAsJsonObject().deepCopy();card.addProperty("controller_name","raw-name");card.addProperty("owner_name","raw-name");
        raw.add("hand",new JsonArray());raw.add("priority_player",JsonNull.INSTANCE);raw.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("hand_count",0);raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(card);return raw;
    }
    static JsonObject attackPrompt(){JsonObject request=priorityPrompt();request.addProperty("is_priority",false);JsonArray candidates=new JsonArray();candidates.add("raw-card");request.add("attackers",candidates);return request;}
    static JsonObject attackMetadata(boolean priority){return JsonParser.parseString("{\"status\":\"ok\",\"cycle\":8,\"priority_open\":"+priority+",\"objects\":{\"raw-card\":{\"incarnation\":4,\"owner\":\"raw-human\",\"controller\":\"raw-human\"}}}").getAsJsonObject();}
    static void combatEntryChecks() throws Exception {
        JsonObject before=attackState(),prompt=priorityPrompt();before.addProperty("priority_player","raw-name");before.addProperty("phase","PRECOMBAT_MAIN");before.addProperty("step","PRECOMBAT_MAIN");ManaforgeOpeningProjection projection=projection();JsonObject offered=projection.projectTurnCombat(before,prompt,false,false);JsonObject command=projection.claimAction(perform(offered),"session","human","raw-game","raw-human",41,8);
        JsonObject after=before.deepCopy(),next=attackPrompt(),accepted=new JsonObject();after.addProperty("phase","COMBAT");after.addProperty("step","DECLARE_ATTACKERS");after.add("priority_player",JsonNull.INSTANCE);next.addProperty("decision_id",42);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
        NativeCastCorrelation.PriorityEvidence proof=NativeCastCorrelation.combatEntryEvidence(before,prompt,command,attackMetadata(true),accepted,after,next,attackMetadata(false),"raw-card");check(proof!=null && proof.matchesCommand(command));
        for(int mode=0;mode<7;mode++){JsonObject bad=after.deepCopy(),badNext=next.deepCopy(),badAccepted=accepted.deepCopy(),metadata=attackMetadata(false);if(mode==0)badNext.add("attackers",new JsonArray());if(mode==1)metadata.addProperty("priority_open",true);if(mode==2)metadata.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);if(mode==3)badAccepted.addProperty("request_id","wrong");if(mode==4)bad.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);if(mode==5)badNext.addProperty("decision_id",41);if(mode==6)bad.addProperty("turn",1);check(NativeCastCorrelation.combatEntryEvidence(before,prompt,command,attackMetadata(true),badAccepted,bad,badNext,metadata,"raw-card")==null);}
        JsonObject selection=projection.projectSingleTurnAttacker(after,next,"raw-card");shape(selection);check(selection.getAsJsonArray("actions").size()==1 && "declare_attacker".equals(selection.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString()));JsonObject selected=projection.claimAction(perform(selection),"session","human","raw-game","raw-human",42,8);check("raw-card".equals(selected.get("value").getAsString()));
    }
    static void repeatedCombatChecks() throws Exception {
        JsonObject before=attackState();before.addProperty("phase","PRECOMBAT_MAIN");before.addProperty("step","PRECOMBAT_MAIN");before.addProperty("priority_player","raw-name");before.addProperty("turn",6);JsonObject original=before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();original.addProperty("name","Memnite");original.addProperty("power","1");original.addProperty("toughness","1");original.addProperty("damage",0);original.addProperty("tapped",false);JsonObject added=original.deepCopy();added.addProperty("id","cast-next");before.getAsJsonArray("hand").add(added);
        JsonObject discarded=added.deepCopy();discarded.addProperty("id","old-discard");before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("graveyard").add(discarded);
        JsonObject after=before.deepCopy(),metadata=attackMetadata(true);after.addProperty("cycle",9);after.addProperty("phase","POSTCOMBAT_MAIN");after.addProperty("step","POSTCOMBAT_MAIN");after.getAsJsonArray("hand").remove(0);JsonObject human=after.getAsJsonArray("players").get(0).getAsJsonObject();human.getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",true);human.getAsJsonArray("battlefield").add(added.deepCopy());after.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);metadata.addProperty("cycle",9);metadata.getAsJsonObject("objects").add("cast-next",JsonParser.parseString("{\"incarnation\":6,\"owner\":\"raw-human\",\"controller\":\"raw-human\"}"));
        check(NativeCastCorrelation.observesRepeatedCombat(before,attackMetadata(true),after,metadata,"raw-card","cast-next"));
        for(int mode=0;mode<11;mode++){JsonObject bad=after.deepCopy(),badMeta=metadata.deepCopy();JsonObject player=bad.getAsJsonArray("players").get(0).getAsJsonObject();if(mode==0)bad.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",20);if(mode==1)player.addProperty("life",19);if(mode==2)player.getAsJsonArray("battlefield").remove(1);if(mode==3)badMeta.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);if(mode==4)badMeta.getAsJsonObject("objects").getAsJsonObject("cast-next").addProperty("owner","raw-ai");if(mode==5)bad.addProperty("turn",7);if(mode==6)bad.getAsJsonArray("combat").add(new JsonObject());if(mode==7)player.getAsJsonArray("graveyard").remove(0);if(mode==8)player.addProperty("library_count",58);if(mode==9)player.getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",false);if(mode==10)badMeta.addProperty("priority_open",false);check(!NativeCastCorrelation.observesRepeatedCombat(before,attackMetadata(true),bad,badMeta,"raw-card","cast-next"));}
        JsonObject matureBefore=after.deepCopy(),matureMetadata=metadata.deepCopy();matureBefore.addProperty("phase","PRECOMBAT_MAIN");matureBefore.addProperty("step","PRECOMBAT_MAIN");matureBefore.addProperty("turn",8);matureBefore.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",false);JsonObject matureAfter=matureBefore.deepCopy(),lastMetadata=matureMetadata.deepCopy();matureAfter.addProperty("phase","POSTCOMBAT_MAIN");matureAfter.addProperty("step","POSTCOMBAT_MAIN");matureAfter.addProperty("cycle",10);lastMetadata.addProperty("cycle",10);matureAfter.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(1).getAsJsonObject().addProperty("tapped",true);matureAfter.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",18);
        check(NativeCastCorrelation.observesExistingCombat(matureBefore,matureMetadata,matureAfter,lastMetadata,"cast-next"));
        for(int mode=0;mode<12;mode++){JsonObject bad=matureAfter.deepCopy(),guard=lastMetadata.deepCopy(),player=bad.getAsJsonArray("players").get(0).getAsJsonObject();if(mode==0)bad.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);if(mode==1)player.addProperty("life",19);if(mode==2)player.getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("id","replacement");if(mode==3)guard.getAsJsonObject("objects").getAsJsonObject("cast-next").addProperty("incarnation",7);if(mode==4)bad.getAsJsonArray("hand").add(added.deepCopy());if(mode==5)bad.addProperty("turn",10);if(mode==6)bad.getAsJsonArray("stack").add(new JsonObject());if(mode==7)player.getAsJsonArray("graveyard").remove(0);if(mode==8)player.addProperty("library_count",58);if(mode==9)player.getAsJsonArray("battlefield").get(1).getAsJsonObject().addProperty("tapped",false);if(mode==10)guard.addProperty("priority_open",false);if(mode==11)bad.addProperty("active_player","raw-opponent-name");check(!NativeCastCorrelation.observesExistingCombat(matureBefore,matureMetadata,bad,guard,"cast-next"));}
        JsonObject legal=attackPrompt();legal.addProperty("cycle",9);legal.getAsJsonArray("attackers").add("cast-next");JsonObject selection=matureBefore.deepCopy();selection.addProperty("phase","COMBAT");selection.add("priority_player",JsonNull.INSTANCE);ManaforgeOpeningProjection selecting=projection();JsonObject offered=selecting.projectSingleTurnAttacker(selection,legal,"cast-next");shape(offered);check(offered.getAsJsonArray("actions").size()==1);check("cast-next".equals(selecting.claimAction(perform(offered),"session","human","raw-game","raw-human",41,9).get("value").getAsString()));
        JsonObject prompt=attackPrompt(),combatState=before.deepCopy();combatState.add("priority_player",JsonNull.INSTANCE);JsonObject attack=projection().projectTurnCombat(combatState,prompt,true,false);shape(attack);check(attack.getAsJsonArray("actions").size()==2 && !attack.toString().contains("old-discard"));
    }
    static void turnContinuationChecks() throws Exception {
        JsonObject raw=attackState(),prompt=priorityPrompt();raw.addProperty("priority_player","raw-name");raw.addProperty("phase","END");raw.addProperty("step","CLEANUP");prompt.addProperty("kind","GAME_TARGET");prompt.addProperty("is_priority",false);JsonArray hand=new JsonArray(),targets=new JsonArray();
        for(int index=0;index<8;index++){JsonObject card=state().getAsJsonArray("hand").get(0).getAsJsonObject().deepCopy();card.addProperty("id","discard-"+index);hand.add(card);targets.add("discard-"+index);}raw.add("hand",hand);raw.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("hand_count",8);prompt.add("targets",targets);
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectTurnContinuation(raw,prompt);shape(snapshot);check(snapshot.getAsJsonArray("actions").size()==8 && snapshot.getAsJsonObject("decision").getAsJsonArray("options").size()==0 && !snapshot.toString().contains("discard-0") && !snapshot.toString().contains("OPPONENT_SECRET"));
        String wire=perform(snapshot);JsonObject command=projection.claimAction(wire,"session","human","raw-game","raw-human",41,8);check("object".equals(command.get("kind").getAsString()) && "discard-0".equals(command.get("value").getAsString()));fails("STALE_DECISION",()->projection.claimAction(wire,"session","human","raw-game","raw-human",41,8));
        for(int mode=0;mode<4;mode++){JsonObject bad=raw.deepCopy(),badPrompt=prompt.deepCopy();if(mode==0)badPrompt.getAsJsonArray("targets").add("foreign");if(mode==1)badPrompt.getAsJsonArray("targets").add("discard-0");if(mode==2)bad.addProperty("step","END_TURN");if(mode==3)bad.addProperty("active_player","raw-opponent-name");fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection.projectTurnContinuation(bad,badPrompt));}
        JsonObject discardBefore=raw.deepCopy();
        JsonObject grave=hand.get(0).getAsJsonObject().deepCopy();raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("graveyard").add(grave);hand.remove(0);raw.addProperty("phase","PRECOMBAT_MAIN");raw.addProperty("step","PRECOMBAT_MAIN");JsonObject priority=priorityPrompt();snapshot=projection.projectTurnContinuation(raw,priority);shape(snapshot);check(snapshot.getAsJsonArray("objects").size()==9 && snapshot.getAsJsonArray("actions").size()==1 && !snapshot.toString().contains("discard-0"));
        priority.addProperty("decision_id",42);JsonObject acceptedDiscard=new JsonObject();acceptedDiscard.addProperty("event","response_sent");acceptedDiscard.addProperty("accepted",true);acceptedDiscard.add("request_id",command.get("request_id"));NativeCastCorrelation.TurnDecisionEvidence discardProof=NativeCastCorrelation.turnDecisionEvidence(discardBefore,prompt,command,attackMetadata(false),acceptedDiscard,raw,priority,attackMetadata(true),"raw-card");check(discardProof!=null && discardProof.matchesCommand(command));JsonObject wrongDiscard=acceptedDiscard.deepCopy();wrongDiscard.addProperty("request_id","other");check(NativeCastCorrelation.turnDecisionEvidence(discardBefore,prompt,command,attackMetadata(false),wrongDiscard,raw,priority,attackMetadata(true),"raw-card")==null);
        raw.add("playable",JsonParser.parseString("[\"discard-1\"]"));raw.getAsJsonObject("action_kinds").addProperty("discard-1","cast_spell");JsonObject ready=projection.projectTurnContinuation(raw,priority,true);shape(ready);check(ready.getAsJsonArray("actions").size()==2 && "cast_spell".equals(ready.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString()));
        JsonObject before=attackState();before.addProperty("turn",4);before.addProperty("phase","POSTCOMBAT_MAIN");before.addProperty("step","POSTCOMBAT_MAIN");before.addProperty("priority_player","raw-name");before.add("hand",new JsonArray());before.getAsJsonArray("hand").add(grave.deepCopy());JsonObject second=grave.deepCopy();second.addProperty("id","kept-card");before.getAsJsonArray("hand").add(second);before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",true);
        JsonObject after=before.deepCopy(),afterMetadata=attackMetadata(true),next=priorityPrompt();after.addProperty("cycle",9);after.addProperty("turn",6);after.addProperty("phase","PRECOMBAT_MAIN");after.addProperty("step","PRECOMBAT_MAIN");after.getAsJsonArray("hand").remove(0);JsonObject drawn=grave.deepCopy();drawn.addProperty("id","drawn-card");after.getAsJsonArray("hand").add(drawn);JsonObject human=after.getAsJsonArray("players").get(0).getAsJsonObject();human.addProperty("library_count",58);human.getAsJsonArray("graveyard").add(grave.deepCopy());human.getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",false);next.addProperty("cycle",9);next.addProperty("decision_id",50);afterMetadata.addProperty("cycle",9);Set<String> discarded=new HashSet<>(Arrays.asList("discard-0"));
        check(NativeCastCorrelation.observesNextHumanTurn(before,attackMetadata(true),after,next,afterMetadata,"raw-card",discarded));
        JsonObject secondBefore=before.deepCopy(),secondAfter=after.deepCopy();JsonObject permanent=before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().deepCopy();permanent.addProperty("id","second-creature");secondBefore.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(permanent);permanent=permanent.deepCopy();permanent.addProperty("tapped",false);secondAfter.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(permanent);
        JsonObject oldGrave=grave.deepCopy();oldGrave.addProperty("id","old-grave");secondBefore.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("graveyard").add(oldGrave);secondAfter.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("graveyard").add(oldGrave.deepCopy());
        check(NativeCastCorrelation.observesNextHumanTurn(secondBefore,attackMetadata(true),secondAfter,next,afterMetadata,"raw-card",discarded));
        for(int mode=0;mode<5;mode++){JsonObject bad=secondAfter.deepCopy(),card=bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(1).getAsJsonObject();if(mode==0)card.addProperty("id","replacement");if(mode==1)card.addProperty("tapped",true);if(mode==2)card.addProperty("controller_name","raw-opponent-name");if(mode==3)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").remove(1);if(mode==4)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("graveyard").get(1).getAsJsonObject().addProperty("id","replacement-grave");check(!NativeCastCorrelation.observesNextHumanTurn(secondBefore,attackMetadata(true),bad,next,afterMetadata,"raw-card",discarded));}

        for(int mode=0;mode<7;mode++){JsonObject bad=after.deepCopy(),badMeta=afterMetadata.deepCopy();if(mode==0)bad.addProperty("turn",5);if(mode==1)bad.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("library_count",59);if(mode==2)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("graveyard").get(0).getAsJsonObject().addProperty("id","wrong");if(mode==3)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",true);if(mode==4)badMeta.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);if(mode==5)bad.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);if(mode==6)bad.addProperty("active_player","raw-opponent-name");check(!NativeCastCorrelation.observesNextHumanTurn(before,attackMetadata(true),bad,next,badMeta,"raw-card",discarded));}
    }
    static void blockedDamageChecks() throws Exception {
        JsonObject before=attackState(),prompt=priorityPrompt();before.addProperty("priority_player","raw-name");before.addProperty("phase","COMBAT");before.addProperty("step","DECLARE_BLOCKERS");prompt.addProperty("decision_id",44);
        before.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[\"raw-blocker\"],\"defender\":\"raw-ai\",\"blocked\":true}]"));JsonObject attacker=before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();attacker.addProperty("name","Memnite");attacker.addProperty("power","1");attacker.addProperty("toughness","1");attacker.addProperty("damage",0);
        JsonObject blocker=attacker.deepCopy();blocker.addProperty("id","raw-blocker");blocker.addProperty("name","Ornithopter");blocker.addProperty("power","0");blocker.addProperty("toughness","2");blocker.addProperty("controller_name","raw-opponent-name");blocker.addProperty("owner_name","raw-opponent-name");before.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").add(blocker);
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectBlockedAttackPriority(before,prompt);shape(snapshot);check(snapshot.getAsJsonArray("actions").size()==1 && !snapshot.toString().contains("raw-blocker"));String wire=perform(snapshot);JsonObject command=projection.claimAction(wire,"session","human","raw-game","raw-human",44,8);fails("STALE_DECISION",()->projection.claimAction(wire,"session","human","raw-game","raw-human",44,8));
        JsonObject after=before.deepCopy(),next=priorityPrompt(),accepted=new JsonObject(),metadata=attackMetadata(true);after.addProperty("step","COMBAT_DAMAGE");after.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("damage",1);next.addProperty("decision_id",45);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));metadata.getAsJsonObject("objects").add("raw-blocker",JsonParser.parseString("{\"incarnation\":7,\"owner\":\"raw-ai\",\"controller\":\"raw-ai\"}"));
        NativeCastCorrelation.PriorityEvidence proof=NativeCastCorrelation.blockedDamageEvidence(before,prompt,command,metadata,accepted,after,next,metadata,"raw-card");check(proof!=null && proof.matchesCommand(command));
        for(int mode=0;mode<17;mode++) {
            JsonObject badBefore=before.deepCopy(),badAfter=after.deepCopy(),badAccepted=accepted.deepCopy(),badNext=next.deepCopy(),badMeta=metadata.deepCopy();JsonObject badBlocker=badAfter.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();
            if(mode==0)badBlocker.addProperty("damage",0);
            if(mode==1)badBlocker.addProperty("damage",2);
            if(mode==2)badMeta.getAsJsonObject("objects").getAsJsonObject("raw-blocker").addProperty("incarnation",8);
            if(mode==3)badMeta.getAsJsonObject("objects").remove("raw-blocker");
            if(mode==4)badAfter.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("life",19);
            if(mode==5)badAfter.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);
            if(mode==6)badBlocker.addProperty("name","Other creature");
            if(mode==7)badBlocker.addProperty("power","1");
            if(mode==8)badBlocker.addProperty("toughness","1");
            if(mode==9)badAfter.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("damage",1);
            if(mode==10)badAfter.addProperty("step","DECLARE_BLOCKERS");
            if(mode==11)badAfter.getAsJsonArray("stack").add(new JsonObject());
            if(mode==12)badAccepted.addProperty("accepted",false);
            if(mode==13)badNext.addProperty("decision_id",44);
            if(mode==14)badMeta.addProperty("priority_open",false);
            if(mode==15)badBlocker.addProperty("hidden",true);
            if(mode==16)badMeta.getAsJsonObject("objects").getAsJsonObject("raw-blocker").addProperty("controller","raw-human");
            check(NativeCastCorrelation.blockedDamageEvidence(badBefore,prompt,command,metadata,badAccepted,badAfter,badNext,badMeta,"raw-card")==null);
        }
    }
    static void combatCleanupChecks() throws Exception {
        {
            JsonObject before=attackState(),prompt=priorityPrompt();before.addProperty("priority_player","raw-name");before.addProperty("phase","COMBAT");before.addProperty("step","COMBAT_DAMAGE");prompt.addProperty("decision_id",45);
            before.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectDeclaredAttackPriority(before,prompt);String wire=perform(snapshot);JsonObject command=projection.claimAction(wire,"session","human","raw-game","raw-human",45,8);
            JsonObject after=before.deepCopy(),next=priorityPrompt(),accepted=new JsonObject();after.addProperty("phase","POSTCOMBAT_MAIN");after.addProperty("step","POSTCOMBAT_MAIN");after.add("combat",new JsonArray());next.addProperty("decision_id",46);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
            NativeCastCorrelation.PriorityEvidence proof=NativeCastCorrelation.combatCleanupEvidence(before,prompt,command,attackMetadata(true),accepted,after,next,attackMetadata(true),"raw-card");check(proof!=null && proof.matchesCommand(command));
            for(int mode=0;mode<10;mode++) {
                JsonObject badBefore=before.deepCopy(),badAfter=after.deepCopy(),badNext=next.deepCopy(),badAccepted=accepted.deepCopy(),metadata=attackMetadata(true);
                if(mode==0)badAfter.addProperty("step","COMBAT_DAMAGE");
                if(mode==1)badAfter.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);
                if(mode==2)badAfter.getAsJsonArray("stack").add(new JsonObject());
                if(mode==3)metadata.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
                if(mode==4)badAccepted.addProperty("request_id","wrong");
                if(mode==5)badNext.addProperty("decision_id",45);
                if(mode==6)badAfter.addProperty("turn",1);
                if(mode==7)badBefore.getAsJsonArray("combat").get(0).getAsJsonObject().getAsJsonArray("blockers").add("unknown");
                if(mode==8)badBefore.getAsJsonArray("combat").get(0).getAsJsonObject().addProperty("defender","unknown");
                if(mode==9)metadata.addProperty("priority_open",false);
                check(NativeCastCorrelation.combatCleanupEvidence(badBefore,prompt,command,attackMetadata(true),badAccepted,badAfter,badNext,metadata,"raw-card")==null);
            }
            JsonObject cleared=before.deepCopy();cleared.add("combat",new JsonArray());check(NativeCastCorrelation.combatCleanupEvidence(cleared,prompt,command,attackMetadata(true),accepted,after,next,attackMetadata(true),"raw-card")==null);
        }
    }
    static void combatDamageChecks() throws Exception {
        JsonObject before=attackState(),prompt=priorityPrompt();before.addProperty("priority_player","raw-name");before.addProperty("phase","COMBAT");before.addProperty("step","DECLARE_BLOCKERS");prompt.addProperty("decision_id",44);
        before.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));JsonObject source=before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();source.addProperty("name","Memnite");source.addProperty("power","1");source.addProperty("toughness","1");
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectDeclaredAttackPriority(before,prompt);String wire=perform(snapshot);JsonObject command=projection.claimAction(wire,"session","human","raw-game","raw-human",44,8);
        JsonObject after=before.deepCopy(),next=priorityPrompt(),accepted=new JsonObject();after.addProperty("step","COMBAT_DAMAGE");after.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);next.addProperty("decision_id",45);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
        NativeCastCorrelation.PriorityEvidence proof=NativeCastCorrelation.combatDamageEvidence(before,prompt,command,attackMetadata(true),accepted,after,next,attackMetadata(true),"raw-card");check(proof!=null && proof.matchesCommand(command));
        for(int mode=0;mode<12;mode++) {
            JsonObject badBefore=before.deepCopy(),badAfter=after.deepCopy(),badAccepted=accepted.deepCopy(),badNext=next.deepCopy(),metadata=attackMetadata(true);
            if(mode==0)badAfter.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",20);
            if(mode==1)badAfter.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",18);
            if(mode==2)badAfter.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("life",19);
            if(mode==3)badAfter.addProperty("step","DECLARE_BLOCKERS");
            if(mode==4)badAfter.addProperty("phase","POSTCOMBAT_MAIN");
            if(mode==5)badBefore.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("power","2");
            if(mode==6)badBefore.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("name","Other creature");
            if(mode==7)metadata.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
            if(mode==8)badAccepted.addProperty("accepted",false);
            if(mode==9)badNext.addProperty("decision_id",44);
            if(mode==10)badAfter.getAsJsonArray("stack").add(new JsonObject());
            if(mode==11){badBefore.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",1);badAfter.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",0);}
            check(NativeCastCorrelation.combatDamageEvidence(badBefore,prompt,command,attackMetadata(true),badAccepted,badAfter,badNext,metadata,"raw-card")==null);
        }
    }
    static void declaredPriorityChecks() throws Exception {
        JsonObject before=attackState(),prompt=priorityPrompt();prompt.addProperty("decision_id",43);before.addProperty("priority_player","raw-name");
        before.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectDeclaredAttackPriority(before,prompt);shape(snapshot);
        check(snapshot.getAsJsonArray("actions").size()==1 && "pass".equals(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString()));
        String wire=perform(snapshot);JsonObject command=projection.claimAction(wire,"session","human","raw-game","raw-human",43,8);fails("STALE_DECISION",()->projection.claimAction(wire,"session","human","raw-game","raw-human",43,8));
        JsonObject after=before.deepCopy(),next=priorityPrompt(),accepted=new JsonObject();next.addProperty("decision_id",44);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
        NativeCastCorrelation.PriorityEvidence proof=NativeCastCorrelation.declaredPriorityEvidence(before,prompt,command,attackMetadata(true),accepted,after,next,attackMetadata(true),"raw-card");check(proof!=null && proof.matchesCommand(command));
        JsonObject blocker=before.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().deepCopy();blocker.addProperty("id","raw-blocker");blocker.addProperty("controller_name","raw-opponent-name");
        after.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").add(blocker);after.getAsJsonArray("combat").get(0).getAsJsonObject().getAsJsonArray("blockers").add("raw-blocker");after.getAsJsonArray("combat").get(0).getAsJsonObject().addProperty("blocked",true);
        check(NativeCastCorrelation.declaredPriorityEvidence(before,prompt,command,attackMetadata(true),accepted,after,next,attackMetadata(true),"raw-card")!=null);
        JsonObject observed=projection.projectReadOnlyPostDeclaredPriority(after,next);shape(observed);check(observed.get("decision").isJsonNull() && observed.getAsJsonArray("actions").size()==0 && observed.getAsJsonArray("combat").get(0).getAsJsonObject().getAsJsonArray("blockers").size()==1 && !observed.toString().contains("raw-blocker"));
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection.projectReadOnlyDeclaredAttack(after,next));

        for(int mode=0;mode<12;mode++) {
            JsonObject bad=after.deepCopy(),badNext=next.deepCopy(),badAccepted=accepted.deepCopy(),badCommand=command.deepCopy(),metadata=attackMetadata(true);JsonObject group=bad.getAsJsonArray("combat").get(0).getAsJsonObject();
            if(mode==0)group.addProperty("defender","raw-human");
            if(mode==1)group.getAsJsonArray("blockers").add("raw-blocker");
            if(mode==2)group.getAsJsonArray("blockers").add("unknown");
            if(mode==3)bad.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("hidden",true);
            if(mode==4)metadata.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
            if(mode==5)metadata.addProperty("priority_open",false);
            if(mode==6)badAccepted.addProperty("request_id","other");
            if(mode==7)badAccepted.addProperty("accepted",false);
            if(mode==8)badNext.addProperty("decision_id",43);
            if(mode==9)badCommand.addProperty("value",true);
            if(mode==10)bad.getAsJsonArray("stack").add(new JsonObject());
            if(mode==11)bad.add("combat",new JsonArray());
            check(NativeCastCorrelation.declaredPriorityEvidence(before,prompt,badCommand,attackMetadata(true),badAccepted,bad,badNext,metadata,"raw-card")==null);
        }
    }
    static void declaredAttackChecks() throws Exception {
        JsonObject before=attackState(),prompt=attackPrompt();prompt.addProperty("decision_id",42);
        before.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectSelectedAttackFinish(before,prompt);shape(snapshot);
        check(snapshot.getAsJsonArray("actions").size()==1 && "Finish attacks".equals(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("label").getAsString()));
        check(!snapshot.toString().contains("raw-card") && !snapshot.toString().contains("raw-ai"));
        String wire=perform(snapshot);final JsonObject command=projection.claimAction(wire,"session","human","raw-game","raw-human",42,8);
        fails("STALE_DECISION",()->projection.claimAction(wire,"session","human","raw-game","raw-human",42,8));
        JsonObject after=before.deepCopy(),next=priorityPrompt(),accepted=new JsonObject();next.addProperty("decision_id",43);after.addProperty("priority_player","raw-name");
        accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
        NativeCastCorrelation.DeclaredAttackEvidence proof=NativeCastCorrelation.declaredAttackEvidence(before,prompt,command,attackMetadata(false),accepted,after,next,attackMetadata(true),"raw-card");
        check(proof!=null && proof.matchesCommand(command));
        check(NativeCastCorrelation.turnDeclaredEvidence(proof,command)!=null);
        JsonObject declared=projection.projectReadOnlyDeclaredAttack(after,next);shape(declared);check(declared.get("decision").isJsonNull() && declared.getAsJsonArray("actions").size()==0 && declared.getAsJsonArray("combat").size()==1 && !declared.toString().contains("raw-card"));
        JsonObject original=command.deepCopy();command.addProperty("value",true);check(proof.matchesCommand(original) && !proof.matchesCommand(command));command.addProperty("value",false);
        for(int mode=0;mode<13;mode++) {
            JsonObject badBefore=before.deepCopy(),badAfter=after.deepCopy(),badNext=next.deepCopy(),badAccepted=accepted.deepCopy(),badCommand=command.deepCopy(),metadata=attackMetadata(true);
            if(mode==0)badAfter.add("combat",new JsonArray());
            if(mode==1)badAfter.getAsJsonArray("combat").get(0).getAsJsonObject().addProperty("defender","raw-human");
            if(mode==2){badBefore.getAsJsonArray("combat").get(0).getAsJsonObject().addProperty("defender","unknown");badAfter.add("combat",badBefore.get("combat").deepCopy());}
            if(mode==3)metadata.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
            if(mode==4)metadata.addProperty("priority_open",false);
            if(mode==5)badAccepted.addProperty("accepted",false);
            if(mode==6)badAccepted.addProperty("request_id","other");
            if(mode==7)badNext.addProperty("decision_id",42);
            if(mode==8)badNext.addProperty("is_priority",false);
            if(mode==9)badCommand.addProperty("value",true);
            if(mode==10)badBefore.addProperty("active_player","raw-opponent-name");
            if(mode==11)badAfter.addProperty("turn",1);
            if(mode==12)badAfter.getAsJsonArray("stack").add(new JsonObject());
            check(NativeCastCorrelation.declaredAttackEvidence(badBefore,prompt,badCommand,attackMetadata(false),badAccepted,badAfter,badNext,metadata,"raw-card")==null);
        }
    }
    static void attackerSelectionChecks() throws Exception {
        JsonObject before=attackState(),prompt=attackPrompt();ManaforgeOpeningProjection projection=projection();
        JsonObject snapshot=projection.projectAttackSelection(before,prompt);shape(snapshot);
        check(snapshot.getAsJsonArray("actions").size()==2 && !snapshot.toString().contains("raw-card") && !snapshot.toString().contains("OPPONENT_SECRET"));
        check("declare_attacker".equals(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString()));
        String choice=perform(snapshot);JsonObject command=projection.claimAction(choice,"session","human","raw-game","raw-human",41,8);
        check("object".equals(command.get("kind").getAsString()) && "raw-card".equals(command.get("value").getAsString()));
        fails("STALE_DECISION",()->projection.claimAction(choice,"session","human","raw-game","raw-human",41,8));
        JsonObject after=before.deepCopy(),next=attackPrompt(),accepted=new JsonObject();next.addProperty("decision_id",42);
        after.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));
        accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
        check(NativeCastCorrelation.observesAttackerSelection(before,prompt,command,attackMetadata(false),accepted,after,next,attackMetadata(false),"raw-card"));
        check(NativeCastCorrelation.turnAttackerEvidence(NativeCastCorrelation.attackerSelectionEvidence(before,prompt,command,attackMetadata(false),accepted,after,next,attackMetadata(false),"raw-card"),command)!=null);
        JsonObject observed=projection.projectReadOnlyAttackAssignment(after,next);shape(observed);
        check(observed.get("decision").isJsonNull() && observed.getAsJsonArray("actions").size()==0 && observed.getAsJsonArray("combat").size()==1);
        check(!observed.toString().contains("raw-card") && !observed.toString().contains("raw-ai") && !observed.toString().contains("OPPONENT_SECRET"));
        check(observed.getAsJsonArray("combat").get(0).getAsJsonObject().getAsJsonArray("attackers").get(0).equals(observed.getAsJsonArray("objects").get(0).getAsJsonObject().get("object_id")));
        fails("STALE_DECISION",()->projection.claimAction(choice,"session","human","raw-game","raw-human",42,8));
        for(int mode=0;mode<5;mode++) {
            JsonObject bad=after.deepCopy();JsonObject group=bad.getAsJsonArray("combat").get(0).getAsJsonObject();
            if(mode==0)group.addProperty("defender","unknown");
            if(mode==1)group.addProperty("defender","raw-human");
            if(mode==2)group.getAsJsonArray("blockers").add("unknown");
            if(mode==3)group.addProperty("blocked",true);
            if(mode==4)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("hidden",true);
            fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection.projectReadOnlyAttackAssignment(bad,next));
        }

        for(int mode=0;mode<9;mode++) {
            JsonObject bad=after.deepCopy(),badNext=next.deepCopy(),badAccepted=accepted.deepCopy(),metadata=attackMetadata(false);JsonObject group=bad.getAsJsonArray("combat").get(0).getAsJsonObject();
            if(mode==0)group.addProperty("defender","raw-human");
            if(mode==1)group.addProperty("defender","unknown");
            if(mode==2)group.getAsJsonArray("attackers").add("raw-card");
            if(mode==3)group.getAsJsonArray("blockers").add("unknown");
            if(mode==4)metadata.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
            if(mode==5)badNext.addProperty("decision_id",41);
            if(mode==6)badNext.addProperty("is_priority",true);
            if(mode==7)badAccepted.addProperty("accepted",false);
            if(mode==8)badAccepted.addProperty("request_id","other");
            check(!NativeCastCorrelation.observesAttackerSelection(before,prompt,command,attackMetadata(false),badAccepted,bad,badNext,metadata,"raw-card"));
            check(NativeCastCorrelation.attackerSelectionEvidence(before,prompt,command,attackMetadata(false),badAccepted,bad,badNext,metadata,"raw-card")==null);
        }
    }
    static void attackFinishChecks() throws Exception {
        JsonObject raw=attackState(),request=attackPrompt();ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectAttackFinish(raw,request);shape(snapshot);
        check(snapshot.getAsJsonArray("actions").size()==1 && "Finish attacks".equals(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("label").getAsString()));
        check(!snapshot.getAsJsonObject("decision").get("is_priority").getAsBoolean() && snapshot.getAsJsonObject("decision").getAsJsonArray("options").size()==0 && !snapshot.get("actions_complete").getAsBoolean());
        check(!snapshot.toString().contains("raw-card") && !snapshot.toString().contains("OPPONENT_SECRET"));
        String finish=perform(snapshot);JsonObject nativeFinish=projection.claimAction(finish,"session","human","raw-game","raw-human",41,8);check("boolean".equals(nativeFinish.get("kind").getAsString()) && new JsonPrimitive(false).equals(nativeFinish.get("value")));
        JsonObject after=raw.deepCopy(),next=priorityPrompt(),accepted=new JsonObject();after.addProperty("priority_player","raw-name");next.addProperty("decision_id",42);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",nativeFinish.get("request_id").deepCopy());
        NativeCastCorrelation.AttackFinishEvidence proof=NativeCastCorrelation.attackFinishEvidence(raw,request,nativeFinish,attackMetadata(false),accepted,after,next,attackMetadata(true),"raw-card");
        check(proof!=null && proof.matchesCommand(nativeFinish));JsonObject different=nativeFinish.deepCopy();different.addProperty("request_id","other");check(!proof.matchesCommand(different));
        JsonObject phaseBefore=after.deepCopy(),phaseAfter=after.deepCopy(),pass=nativeFinish.deepCopy(),passAccepted=accepted.deepCopy(),phaseNext=next.deepCopy();
        phaseBefore.addProperty("phase","COMBAT");phaseBefore.addProperty("step","END_COMBAT");phaseAfter.addProperty("phase","POSTCOMBAT_MAIN");phaseAfter.addProperty("step","POSTCOMBAT_MAIN");
        pass.addProperty("decision_id",42);pass.addProperty("request_id","combat-pass");passAccepted.addProperty("request_id","combat-pass");phaseNext.addProperty("decision_id",43);
        NativeCastCorrelation.PriorityEvidence phaseProof=proof.phasePriorityEvidence(phaseBefore,next,pass,attackMetadata(true),passAccepted,phaseAfter,phaseNext,attackMetadata(true));check(phaseProof!=null && phaseProof.matchesCommand(pass));
        for(int mode=0;mode<12;mode++) {
            JsonObject badAfter=phaseAfter.deepCopy(),badPass=pass.deepCopy(),badAccepted=passAccepted.deepCopy(),badNext=phaseNext.deepCopy(),beforeMeta=attackMetadata(true),afterMeta=attackMetadata(true);
            if(mode==0 || mode==1){badAfter.addProperty("phase","COMBAT");badAfter.addProperty("step","END_COMBAT");}
            if(mode==1){badAfter.addProperty("cycle",9);badNext.addProperty("cycle",9);afterMeta.addProperty("cycle",9);}
            if(mode==2)beforeMeta.addProperty("priority_open",false);
            if(mode==3)afterMeta.addProperty("priority_open",false);
            if(mode==4)badAccepted.addProperty("request_id","wrong");
            if(mode==5)badAccepted.addProperty("accepted",false);
            if(mode==6)badNext.addProperty("decision_id",42);
            if(mode==7)afterMeta.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
            if(mode==8)badAfter.add("phase",JsonNull.INSTANCE);
            if(mode==9)badAfter.addProperty("viewer","wrong");
            if(mode==10)badPass.addProperty("value",true);
            if(mode==11)badNext.addProperty("kind","GAME_TARGET");
            check(proof.phasePriorityEvidence(phaseBefore,next,badPass,beforeMeta,badAccepted,badAfter,badNext,afterMeta)==null);
        }
        for(int mode=0;mode<20;mode++) {
            JsonObject badBefore=raw.deepCopy(),badAfter=after.deepCopy(),badPrompt=request.deepCopy(),badNext=next.deepCopy(),badCommand=nativeFinish.deepCopy(),badAccepted=accepted.deepCopy(),beforeMeta=attackMetadata(false),afterMeta=attackMetadata(true);
            if(mode==0)badCommand.addProperty("value",true);
            if(mode==1)badCommand.addProperty("game_id","other");
            if(mode==2)badCommand.addProperty("decision_id",40);
            if(mode==3)badPrompt.add("attackers",new JsonArray());
            if(mode==4)badPrompt.getAsJsonArray("attackers").add("raw-card");
            if(mode==5)beforeMeta.addProperty("priority_open",true);
            if(mode==6)afterMeta.addProperty("priority_open",false);
            if(mode==7)badAccepted.addProperty("accepted",false);
            if(mode==8)badAccepted.addProperty("request_id","wrong");
            if(mode==9)afterMeta.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",5);
            if(mode==10)badAfter.getAsJsonArray("combat").add(new JsonObject());
            if(mode==11)badAfter.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("hidden",true);
            if(mode==12)badNext.addProperty("decision_id",41);
            if(mode==13)badNext.addProperty("is_priority",false);
            if(mode==14)badAfter.addProperty("game_id","other");
            if(mode==15)badBefore.addProperty("active_player","raw-opponent-name");
            if(mode==16)badAfter.addProperty("viewer","other");
            if(mode==17)badPrompt.addProperty("kind","GAME_TARGET");
            if(mode==18)badNext.addProperty("cycle",9);
            if(mode==19)afterMeta.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("controller","raw-ai");
            check(NativeCastCorrelation.attackFinishEvidence(badBefore,badPrompt,badCommand,beforeMeta,badAccepted,badAfter,badNext,afterMeta,"raw-card")==null);
        }
        fails("STALE_DECISION",()->projection.claimAction(finish,"session","human","raw-game","raw-human",41,8));
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().project(raw,request,true));
        for(int mode=0;mode<16;mode++) {
            JsonObject bad=raw.deepCopy(),prompt=request.deepCopy();JsonObject card=bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();
            if(mode==0)prompt.addProperty("kind","GAME_ASK");
            if(mode==1)prompt.addProperty("is_priority",true);
            if(mode==2)prompt.remove("attackers");
            if(mode==3)prompt.add("attackers",new JsonObject());
            if(mode==4)prompt.add("blockers",new JsonArray());
            if(mode==5)bad.addProperty("active_player","raw-opponent-name");
            if(mode==6){bad.getAsJsonArray("hand").add(card.deepCopy());bad.getAsJsonArray("players").get(0).getAsJsonObject().add("battlefield",new JsonArray());}
            if(mode==7)card.addProperty("controller_name","raw-opponent-name");
            if(mode==8)card.addProperty("hidden",true);
            if(mode==9)card.addProperty("face_down",true);
            if(mode==10)card.remove("face_down");
            if(mode==11)prompt.getAsJsonArray("attackers").add("raw-card");
            if(mode==12){prompt.add("attackers",new JsonArray());prompt.getAsJsonArray("attackers").add("unknown");}
            if(mode==13)prompt.addProperty("cycle",9);
            if(mode==14)bad.getAsJsonArray("combat").add(new JsonObject());
            if(mode==15)bad.getAsJsonArray("stack").add(new JsonObject());
            ManaforgeOpeningProjection stale=projection();String previous=perform(stale.projectAttackFinish(raw,request));
            fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->stale.projectAttackFinish(bad,prompt));
            fails("STALE_DECISION",()->stale.claimAction(previous,"session","human","raw-game","raw-human",41,8));
        }
    }
    static void landChecks() throws Exception {
        JsonObject spell=landState();spell.getAsJsonObject("action_kinds").addProperty("raw-card","cast_spell");
        check(projection().project(spell,priorityPrompt()).getAsJsonArray("actions").size()==0);
        ManaforgeOpeningProjection caster=projection();JsonObject castSnapshot=caster.project(spell,priorityPrompt(),false,true);shape(castSnapshot);
        check(castSnapshot.getAsJsonArray("actions").size()==1 && castSnapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString().equals("cast_spell"));
        String castWire=perform(castSnapshot);JsonObject castCommand=caster.claimAction(castWire,"session","human","raw-game","raw-human",41,8);
        check(castCommand.get("kind").getAsString().equals("object") && castCommand.get("value").getAsString().equals("raw-card"));
        fails("STALE_DECISION",()->caster.claimAction(castWire,"session","human","raw-game","raw-human",41,8));
        for(String hidden:new String[]{"hidden","face_down"}) {
            JsonObject concealedSpell=spell.deepCopy();concealedSpell.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty(hidden,true);
            check(projection().project(concealedSpell,priorityPrompt(),false,true).getAsJsonArray("actions").size()==0);
        }
        JsonObject notPlayable=spell.deepCopy();notPlayable.add("playable",new JsonArray());check(projection().project(notPlayable,priorityPrompt(),false,true).getAsJsonArray("actions").size()==0);
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
    static void abilityChecks() throws Exception {
        String nativeId="12345678-abcd-1234-abcd-123456789abc";
        JsonObject prompt=priorityPrompt();prompt.addProperty("kind","GAME_CHOOSE_ABILITY");prompt.addProperty("is_priority",false);
        JsonObject choices=new JsonObject();choices.addProperty(nativeId,"Cast creature "+nativeId);prompt.add("key_choices",choices);
        rejects(landState(),prompt);
        ManaforgeOpeningProjection owner=projection();JsonObject snapshot=owner.project(landState(),prompt,false,true);shape(snapshot);
        check(!snapshot.toString().contains(nativeId) && snapshot.getAsJsonArray("actions").size()==0);
        check(snapshot.getAsJsonObject("decision").getAsJsonArray("options").size()==1);
        String wire=choose(snapshot,0);JsonObject command=claim(owner,wire);
        check(command.get("kind").getAsString().equals("object") && command.get("value").getAsString().equals(nativeId));
        fails("STALE_DECISION",()->claim(owner,wire));
        for(String field:new String[]{"session_id","viewer_id","revision","decision_id","option_id"}) {
            ManaforgeOpeningProjection bound=projection();String valid=choose(bound.project(landState(),prompt,false,true),0);
            JsonObject bad=JsonParser.parseString(valid).getAsJsonObject();
            if(field.equals("revision"))bad.getAsJsonObject("body").addProperty(field,0);else bad.getAsJsonObject("body").addProperty(field,"wrong");
            String code=field.equals("session_id")?"SESSION_MISMATCH":field.equals("viewer_id")?"VIEWER_MISMATCH":field.equals("revision")?"STALE_REVISION":field.equals("decision_id")?"STALE_DECISION":"ACTION_UNAVAILABLE";
            fails(code,()->claim(bound,bad.toString()));check(claim(bound,valid).get("value").getAsString().equals(nativeId));
        }
        for(int mode=0;mode<4;mode++) {
            JsonObject bad=prompt.deepCopy();JsonObject invalid=new JsonObject();
            if(mode==0)invalid.addProperty("not-an-id","Cast");
            if(mode==1)invalid.addProperty(nativeId,42);
            if(mode==3)for(int i=0;i<33;i++)invalid.addProperty(UUID.randomUUID().toString(),"Cast");
            bad.add("key_choices",invalid);ManaforgeOpeningProjection bound=projection();String old=choose(bound.project(landState(),prompt,false,true),0);
            fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->bound.project(landState(),bad,false,true));fails("STALE_DECISION",()->claim(bound,old));
        }
    }
    static void stackPriorityChecks() throws Exception {
        JsonObject raw=landState(),stack=new JsonObject();stack.addProperty("id","PRIVATE_STACK_ID");stack.addProperty("name","PRIVATE_STACK_NAME");raw.getAsJsonArray("stack").add(stack);
        rejects(raw,priorityPrompt());
        ManaforgeOpeningProjection owner=projection();JsonObject snapshot=owner.projectPriorityWithoutStack(raw,priorityPrompt());shape(snapshot);
        check(!snapshot.toString().contains("PRIVATE_STACK") && raw.getAsJsonArray("stack").size()==1);
        check(snapshot.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("stack")));
        check(!snapshot.get("actions_complete").getAsBoolean() && snapshot.getAsJsonArray("actions").size()==1);
        check(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString().equals("pass"));
        String wire=perform(snapshot);JsonObject command=owner.claimAction(wire,"session","human","raw-game","raw-human",41,8);
        check(command.get("kind").getAsString().equals("boolean") && !command.get("value").getAsBoolean());
        fails("STALE_DECISION",()->owner.claimAction(wire,"session","human","raw-game","raw-human",41,8));
        for(int mode=0;mode<4;mode++) {
            ManaforgeOpeningProjection bound=projection();String previous=perform(bound.projectPriorityWithoutStack(raw,priorityPrompt()));
            JsonObject bad=raw.deepCopy(),request=priorityPrompt();
            if(mode==0)bad.add("stack",new JsonArray());
            if(mode==1)request.addProperty("is_priority",false);
            if(mode==2)bad.addProperty("priority_player","raw-opponent-name");
            if(mode==3)request.addProperty("cycle",9);
            fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->bound.projectPriorityWithoutStack(bad,request));
            fails("STALE_DECISION",()->bound.claimAction(previous,"session","human","raw-game","raw-human",41,8));
        }
    }
    static void castCorrelationChecks() throws Exception {
        String source="12345678-abcd-1234-abcd-123456789abc",ability="87654321-abcd-1234-abcd-123456789abc";
        JsonObject raw=JsonParser.parseString(landState().toString().replace("raw-card",source)).getAsJsonObject();
        raw.getAsJsonObject("action_kinds").addProperty(source,"cast_spell");JsonObject ids=new JsonObject();JsonArray offered=new JsonArray();offered.add(ability);ids.add(source,offered);raw.add("casting_ability_ids",ids);
        JsonObject command=new JsonObject();command.addProperty("command","respond");command.addProperty("game_id","raw-game");command.addProperty("decision_id",41);command.addProperty("kind","object");command.addProperty("value",source);
        JsonObject prompt=priorityPrompt(),choice=priorityPrompt();choice.addProperty("kind","GAME_CHOOSE_ABILITY");choice.addProperty("decision_id",42);choice.addProperty("is_priority",false);JsonObject options=new JsonObject();options.addProperty(ability,"Cast");choice.add("key_choices",options);
        NativeCastCorrelation ticket=NativeCastCorrelation.capture(raw,prompt,command);check(ticket!=null && ticket.matches(raw,choice));
        JsonObject projected=projection().project(raw,prompt,false,true);shape(projected);check(!projected.toString().contains(source) && !projected.toString().contains(ability));
        for(int mode=0;mode<13;mode++) {
            JsonObject bad=raw.deepCopy(),request=prompt.deepCopy(),submission=command.deepCopy();
            if(mode==0)submission.addProperty("game_id","wrong");
            if(mode==1)submission.addProperty("decision_id",40);
            if(mode==2)request.addProperty("cycle",9);
            if(mode==3)submission.addProperty("kind","boolean");
            if(mode==4)bad.getAsJsonObject("action_kinds").addProperty(source,"play_land");
            if(mode==5)bad.add("playable",new JsonArray());
            if(mode==6)bad.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("hidden",true);
            if(mode==7)bad.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("face_down",true);
            if(mode==8)bad.getAsJsonObject("casting_ability_ids").add(source,new JsonArray());
            if(mode==9)bad.getAsJsonObject("casting_ability_ids").getAsJsonArray(source).add(ability);
            if(mode==10)bad.getAsJsonObject("casting_ability_ids").getAsJsonArray(source).add("invalid-id");
            if(mode==11)bad.add("cycle",JsonParser.parseString("18446744073709551616"));
            if(mode==12)request.addProperty("is_priority",false);
            check(NativeCastCorrelation.capture(bad,request,submission)==null);
        }
        for(int mode=0;mode<10;mode++) {
            JsonObject bad=raw.deepCopy(),request=choice.deepCopy();
            if(mode==0)bad.addProperty("game_id","wrong");
            if(mode==1)bad.addProperty("viewer","wrong");
            if(mode==2){bad.addProperty("cycle",7);request.addProperty("cycle",7);}
            if(mode==3)request.addProperty("cycle",9);
            if(mode==4)request.addProperty("decision_id",41);
            if(mode==5)request.addProperty("kind","GAME_SELECT");
            if(mode==6)request.getAsJsonObject("key_choices").addProperty(source,"Other");
            if(mode==7){JsonObject wrong=new JsonObject();wrong.addProperty(source,"Other");request.add("key_choices",wrong);}
            if(mode==8)bad.add("hand",new JsonArray());
            if(mode==9)request.getAsJsonObject("key_choices").addProperty(ability,42);
            check(!ticket.matches(bad,request));
        }
        raw.getAsJsonObject("casting_ability_ids").getAsJsonArray(source).remove(0);check(ticket.matches(raw,choice));
        JsonObject after=raw.deepCopy();after.add("hand",new JsonArray());JsonObject stacked=new JsonObject();stacked.addProperty("id",ability);stacked.addProperty("hidden",false);stacked.addProperty("face_down",false);after.getAsJsonArray("stack").add(stacked);
        JsonObject metadata=new JsonObject(),objects=new JsonObject(),entry=new JsonObject();metadata.addProperty("status","ok");metadata.addProperty("cycle",8);entry.addProperty("source",source);entry.addProperty("owner","raw-human");entry.addProperty("controller","raw-human");entry.addProperty("incarnation",1);objects.add(ability,entry);metadata.add("objects",objects);
        check(ticket.matchesStack(after,metadata));
        JsonObject before=new JsonObject(),beforeObjects=new JsonObject(),beforeEntry=new JsonObject();before.addProperty("status","ok");before.addProperty("cycle",8);beforeEntry.addProperty("owner","raw-human");beforeEntry.addProperty("incarnation",2);beforeObjects.add(source,beforeEntry);before.add("objects",beforeObjects);
        NativeCastCorrelation instance=ticket.withSourceMetadata(before);check(instance!=null);
        JsonObject selectionCommand=command.deepCopy(),selectionAccepted=new JsonObject(),selectionBefore=before.deepCopy(),selectionAfter=before.deepCopy();selectionCommand.addProperty("request_id","cast-selection");selectionAccepted.addProperty("event","response_sent");selectionAccepted.addProperty("accepted",true);selectionAccepted.addProperty("request_id","cast-selection");selectionBefore.addProperty("priority_open",true);selectionAfter.addProperty("priority_open",false);
        NativeCastCorrelation.TurnDecisionEvidence selectionProof=instance.selectionEvidence(raw,selectionBefore,selectionCommand,selectionAccepted,raw,choice,selectionAfter);check(selectionProof!=null && selectionProof.matchesCommand(selectionCommand));
        for(int mode=0;mode<10;mode++){JsonObject badBefore=selectionBefore.deepCopy(),badAfter=selectionAfter.deepCopy(),badCommand=selectionCommand.deepCopy(),badAccepted=selectionAccepted.deepCopy(),badState=raw.deepCopy(),badChoice=choice.deepCopy();if(mode==0)badBefore.addProperty("priority_open",false);if(mode==1)badAfter.addProperty("priority_open",true);if(mode==2)badAccepted.addProperty("accepted",false);if(mode==3)badAccepted.addProperty("request_id","other");if(mode==4)badAfter.getAsJsonObject("objects").getAsJsonObject(source).addProperty("incarnation",3);if(mode==5)badState.add("hand",new JsonArray());if(mode==6)badChoice.addProperty("decision_id",41);if(mode==7)badCommand.addProperty("value",ability);if(mode==8)badBefore.getAsJsonObject("objects").getAsJsonObject(source).addProperty("owner","other");if(mode==9)badAfter.getAsJsonObject("objects").getAsJsonObject(source).addProperty("owner","other");check(instance.selectionEvidence(raw,badBefore,badCommand,badAccepted,badState,badChoice,badAfter)==null);}

        entry.addProperty("source_incarnation",3);JsonArray spellIds=new JsonArray();spellIds.add(ability);entry.add("spell_ability_ids",spellIds);
        check(instance.matchesStackInstance(after,metadata,ability));check(!ticket.matchesStackInstance(after,metadata,ability));
        JsonObject abilityCommand=command.deepCopy();abilityCommand.addProperty("value",ability);abilityCommand.addProperty("decision_id",42);abilityCommand.addProperty("request_id","ability-receipt");
        NativeCastCorrelation.AbilityEvidence evidence=instance.abilityEvidence(raw,choice,abilityCommand,after,metadata);
        check(evidence!=null && evidence.matchesCommand(abilityCommand));
        check(NativeCastCorrelation.turnAbilityEvidence(evidence,abilityCommand)!=null);JsonObject wrongAbilityCommand=abilityCommand.deepCopy();wrongAbilityCommand.addProperty("request_id","other");check(NativeCastCorrelation.turnAbilityEvidence(evidence,wrongAbilityCommand)==null && NativeCastCorrelation.turnAbilityEvidence(null,abilityCommand)==null);

        JsonObject resolved=after.deepCopy();resolved.add("stack",new JsonArray());
        JsonObject permanent=raw.getAsJsonArray("hand").get(0).getAsJsonObject().deepCopy();
        permanent.addProperty("controller_name","raw-name");permanent.addProperty("owner_name","raw-name");
        resolved.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(permanent);
        JsonObject resolvedMetadata=new JsonObject(),resolvedObjects=new JsonObject(),resolvedEntry=new JsonObject();
        resolvedMetadata.addProperty("status","ok");resolvedMetadata.addProperty("cycle",8);resolvedEntry.addProperty("incarnation",4);
        resolvedEntry.addProperty("owner","raw-human");resolvedEntry.addProperty("controller","raw-human");resolvedObjects.add(source,resolvedEntry);resolvedMetadata.add("objects",resolvedObjects);
        check(evidence.observesBattlefieldTransition(resolved,resolvedMetadata));
        for(int mode=0;mode<12;mode++) {
            JsonObject bad=resolved.deepCopy(),badMetadata=resolvedMetadata.deepCopy();
            JsonObject card=bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();
            if(mode==0)bad.addProperty("game_id","wrong");
            if(mode==1)bad.addProperty("viewer","wrong");
            if(mode==2)card.addProperty("hidden",true);
            if(mode==3)card.addProperty("face_down",true);
            if(mode==4)card.addProperty("id",ability);
            if(mode==5)bad.getAsJsonArray("hand").add(card.deepCopy());
            if(mode==6)badMetadata.getAsJsonObject("objects").getAsJsonObject(source).addProperty("incarnation",3);
            if(mode==7)badMetadata.getAsJsonObject("objects").getAsJsonObject(source).addProperty("incarnation",5);
            if(mode==8)badMetadata.addProperty("cycle",9);
            if(mode==9)badMetadata.getAsJsonObject("objects").getAsJsonObject(source).addProperty("controller","wrong");
            if(mode==10)bad.getAsJsonArray("stack").add(stacked.deepCopy());
            if(mode==11)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(card.deepCopy());
            check(!evidence.observesBattlefieldTransition(bad,badMetadata));
        }
        ManaforgeOpeningProjection readOnly=projection();JsonObject nextPriority=priorityPrompt();nextPriority.addProperty("decision_id",43);
        JsonObject priorOffer=readOnly.project(resolved,nextPriority,true);String priorPass=perform(priorOffer);
        JsonObject observation=readOnly.projectReadOnlyPriority(resolved,nextPriority);shape(observation);
        check(observation.get("decision").isJsonNull() && observation.getAsJsonArray("actions").size()==0 && !observation.get("actions_complete").getAsBoolean());
        check(!observation.toString().contains(source) && !observation.toString().contains(ability));
        JsonObject passCommand=new JsonObject();passCommand.addProperty("command","respond");passCommand.addProperty("game_id","raw-game");passCommand.addProperty("decision_id",43);passCommand.addProperty("kind","boolean");passCommand.addProperty("value",false);passCommand.addProperty("request_id","priority-receipt");
        JsonObject openMetadata=metadata.deepCopy(),closedMetadata=resolvedMetadata.deepCopy(),accepted=new JsonObject(),laterPriority=nextPriority.deepCopy();
        openMetadata.addProperty("priority_open",true);closedMetadata.addProperty("priority_open",true);laterPriority.addProperty("decision_id",44);
        accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.addProperty("request_id","priority-receipt");
        NativeCastCorrelation.PriorityEvidence passEvidence=evidence.priorityEvidence(after,nextPriority,passCommand,openMetadata,accepted,resolved,laterPriority,closedMetadata);
        check(passEvidence!=null && passEvidence.matchesCommand(passCommand));
        JsonObject differentPass=passCommand.deepCopy();differentPass.addProperty("request_id","other-priority");check(!passEvidence.matchesCommand(differentPass));
        for(int mode=0;mode<15;mode++) {
            JsonObject badPass=passCommand.deepCopy(),badBefore=after.deepCopy(),badPrompt=nextPriority.deepCopy(),badOpen=openMetadata.deepCopy(),badAccepted=accepted.deepCopy(),badNext=laterPriority.deepCopy(),badClosed=closedMetadata.deepCopy();
            if(mode==0)badPass.addProperty("value",true);
            if(mode==1)badPass.addProperty("kind","object");
            if(mode==2)badPass.addProperty("game_id","wrong");
            if(mode==3)badPass.addProperty("decision_id",42);
            if(mode==4)badPrompt.addProperty("cycle",9);
            if(mode==5)badOpen.addProperty("priority_open",false);
            if(mode==6)badAccepted.addProperty("accepted",false);
            if(mode==7)badAccepted.addProperty("request_id","wrong");
            if(mode==8)badNext.addProperty("decision_id",43);
            if(mode==9)badClosed.addProperty("priority_open",false);
            if(mode==10)badClosed.getAsJsonObject("objects").getAsJsonObject(source).addProperty("incarnation",3);
            if(mode==11)badBefore.getAsJsonArray("stack").get(0).getAsJsonObject().addProperty("id",source);
            if(mode==12)badOpen.getAsJsonObject("objects").getAsJsonObject(ability).addProperty("source_incarnation",4);
            if(mode==13)badAccepted.addProperty("event","game_state");
            if(mode==14)badNext.addProperty("is_priority",false);
            check(evidence.priorityEvidence(badBefore,badPrompt,badPass,badOpen,badAccepted,resolved,badNext,badClosed)==null);
        }
        JsonObject phaseBefore=resolved.deepCopy(),phaseAfter=resolved.deepCopy(),phasePass=passCommand.deepCopy(),phaseAccepted=accepted.deepCopy(),phaseNext=laterPriority.deepCopy();
        phaseBefore.addProperty("turn",1);phaseBefore.addProperty("phase","PRECOMBAT_MAIN");phaseBefore.addProperty("step","PRECOMBAT_MAIN");
        phaseAfter.addProperty("turn",1);phaseAfter.addProperty("phase","COMBAT");phaseAfter.addProperty("step","BEGIN_COMBAT");
        phasePass.addProperty("decision_id",44);phasePass.addProperty("request_id","phase-receipt");phaseAccepted.addProperty("request_id","phase-receipt");phaseNext.addProperty("decision_id",45);
        NativeCastCorrelation.PriorityEvidence phaseProof=evidence.phasePriorityEvidence(phaseBefore,laterPriority,phasePass,closedMetadata,phaseAccepted,phaseAfter,phaseNext,closedMetadata);
        check(phaseProof!=null && phaseProof.matchesCommand(phasePass));
        for(int mode=0;mode<12;mode++) {
            JsonObject badAfter=phaseAfter.deepCopy(),badPass=phasePass.deepCopy(),badAccepted=phaseAccepted.deepCopy(),badNext=phaseNext.deepCopy(),badOpen=closedMetadata.deepCopy(),badClosed=closedMetadata.deepCopy();
            if(mode==0 || mode==1){badAfter.addProperty("phase","PRECOMBAT_MAIN");badAfter.addProperty("step","PRECOMBAT_MAIN");}
            if(mode==1){badAfter.addProperty("cycle",9);badNext.addProperty("cycle",9);badClosed.addProperty("cycle",9);}
            if(mode==2)badOpen.addProperty("priority_open",false);
            if(mode==3)badClosed.addProperty("priority_open",false);
            if(mode==4)badAccepted.addProperty("request_id","wrong");
            if(mode==5)badAccepted.addProperty("accepted",false);
            if(mode==6)badNext.addProperty("decision_id",44);
            if(mode==7)badClosed.getAsJsonObject("objects").getAsJsonObject(source).addProperty("incarnation",5);
            if(mode==8)badAfter.add("phase",JsonNull.INSTANCE);
            if(mode==9)badAfter.addProperty("turn",0);
            if(mode==10)badPass.addProperty("value",true);
            if(mode==11)badNext.addProperty("kind","GAME_TARGET");
            check(evidence.phasePriorityEvidence(phaseBefore,laterPriority,badPass,badOpen,badAccepted,badAfter,badNext,badClosed)==null);
        }
        fails("STALE_DECISION",()->readOnly.claimAction(priorPass,"session","human","raw-game","raw-human",43,8));
        OpeningSessionChecks.confirmationChecks(raw,choice,instance,after,metadata);
        JsonObject other=abilityCommand.deepCopy();other.addProperty("request_id","other-receipt");check(!evidence.matchesCommand(other));
        other=abilityCommand.deepCopy();other.addProperty("decision_id",43);check(!evidence.matchesCommand(other));
        check(ticket.abilityEvidence(raw,choice,abilityCommand,after,metadata)==null);
        for(int mode=0;mode<8;mode++) {
            JsonObject bad=abilityCommand.deepCopy(),badPrompt=choice.deepCopy(),badAfter=after.deepCopy(),badMetadata=metadata.deepCopy();
            if(mode==0)bad.addProperty("value",source);
            if(mode==1)bad.addProperty("decision_id",41);
            if(mode==2)bad.addProperty("game_id","other-game");
            if(mode==3)bad.addProperty("kind","boolean");
            if(mode==4)bad.remove("request_id");
            if(mode==5)badPrompt.addProperty("cycle",9);
            if(mode==6)badMetadata.getAsJsonObject("objects").getAsJsonObject(ability).addProperty("source_incarnation",2);
            if(mode==7){badAfter.addProperty("cycle",7);badMetadata.addProperty("cycle",7);}
            check(instance.abilityEvidence(raw,badPrompt,bad,badAfter,badMetadata)==null);
        }
        abilityCommand.addProperty("value",source);check(!evidence.matchesCommand(abilityCommand));
        beforeEntry.addProperty("incarnation",99);check(instance.matchesStackInstance(after,metadata,ability));
        check(instance.withSourceMetadata(before)==null);
        for(int mode=0;mode<7;mode++) {
            JsonObject bad=metadata.deepCopy();JsonObject badEntry=bad.getAsJsonObject("objects").getAsJsonObject(ability);
            if(mode==0)badEntry.addProperty("source_incarnation",2);
            if(mode==1)badEntry.addProperty("source_incarnation",1);
            if(mode==2)badEntry.remove("source_incarnation");
            if(mode==3)badEntry.getAsJsonArray("spell_ability_ids").add(ability);
            if(mode==4)badEntry.add("spell_ability_ids",new JsonArray());
            if(mode==5){JsonArray wrong=new JsonArray();wrong.add(source);badEntry.add("spell_ability_ids",wrong);}
            if(mode==6)badEntry.addProperty("source_incarnation",true);
            check(!instance.matchesStackInstance(after,bad,ability));
        }
        check(!instance.matchesStackInstance(after,metadata,source));
        for(int mode=0;mode<4;mode++) {
            JsonObject bad=before.deepCopy();JsonObject badEntry=bad.getAsJsonObject("objects").getAsJsonObject(source);
            if(mode==0)bad.addProperty("cycle",9);
            if(mode==1)bad.addProperty("status","retry");
            if(mode==2)badEntry.addProperty("owner","wrong");
            if(mode==3)badEntry.addProperty("incarnation",-1);
            check(ticket.withSourceMetadata(bad)==null);
        }
        for(String field:new String[]{"source","owner","controller","incarnation"}) {
            JsonObject bad=metadata.deepCopy();bad.getAsJsonObject("objects").getAsJsonObject(ability).addProperty(field,"wrong");check(!ticket.matchesStack(after,bad));
        }
        JsonObject stale=metadata.deepCopy();stale.addProperty("cycle",9);check(!ticket.matchesStack(after,stale));
        JsonObject hidden=after.deepCopy();hidden.getAsJsonArray("stack").get(0).getAsJsonObject().addProperty("hidden",true);check(!ticket.matchesStack(hidden,metadata));
        check(!ticket.matchesStack(raw,metadata));metadata.addProperty("status","retry");check(!ticket.matchesStack(after,metadata));
    }
    static void combatCounterChecks() throws Exception {
        JsonObject raw=attackState(),prompt=priorityPrompt(),card=raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();raw.addProperty("priority_player","raw-name");card.add("counters",JsonParser.parseString("[[\"-0/-1\",1]]"));card.add("loyalty",JsonNull.INSTANCE);card.add("defense",JsonNull.INSTANCE);JsonObject snapshot=projection().projectCoreCombat(raw,prompt);shape(snapshot);JsonObject publicCard=null;for(JsonElement value:snapshot.getAsJsonArray("objects"))if("battlefield".equals(value.getAsJsonObject().get("zone").getAsString()))publicCard=value.getAsJsonObject();check(publicCard!=null && publicCard.getAsJsonObject("characteristics").getAsJsonArray("counters").get(0).getAsJsonArray().get(1).getAsInt()==1);card.getAsJsonArray("counters").get(0).getAsJsonArray().set(1,new JsonPrimitive(2));check(publicCard.getAsJsonObject("characteristics").getAsJsonArray("counters").get(0).getAsJsonArray().get(1).getAsInt()==1);
        for(String invalid:new String[]{"[[\"-0/-1\",-1]]","[[\"-0/-1\",1.5]]","[[\"-0/-1\",2147483648]]","[[\"-0/-1\",1],[\"-0/-1\",2]]","[[\"-0/-1\"]]","{}"}){JsonObject bad=raw.deepCopy();bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().add("counters",JsonParser.parseString(invalid));fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(bad,prompt));}
    }
    static void coreChoiceChecks() throws Exception {
        JsonObject raw=attackState(),prompt=priorityPrompt();prompt.addProperty("is_priority",false);prompt.addProperty("kind","GAME_GET_AMOUNT");prompt.addProperty("min",1);prompt.addProperty("max",3);ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectCoreCombat(raw,prompt);shape(snapshot);check("number".equals(snapshot.getAsJsonObject("decision").get("family").getAsString()));
        JsonObject wire=JsonParser.parseString(choose(projection().project(state(),OpeningProjectionChecks.prompt()),0)).getAsJsonObject(),body=wire.getAsJsonObject("body");body.add("revision",snapshot.get("revision"));body.add("decision_id",snapshot.getAsJsonObject("decision").get("decision_id"));body.addProperty("operation","choose_number");body.remove("option_id");body.addProperty("value",4);String invalid=wire.toString();fails("ACTION_UNAVAILABLE",()->projection.claimOperation(invalid,"session","human","raw-game","raw-human",41,8));body.addProperty("value",2);JsonObject nativeNumber=projection.claimOperation(wire.toString(),"session","human","raw-game","raw-human",41,8);check("integer".equals(nativeNumber.get("kind").getAsString()) && nativeNumber.get("value").getAsInt()==2 && NativeCombatChoices.matchesResponse(prompt,nativeNumber));String stale=wire.toString();fails("STALE_DECISION",()->projection.claimOperation(stale,"session","human","raw-game","raw-human",41,8));
        prompt.addProperty("kind","GAME_GET_MULTI_AMOUNT");prompt.add("message",JsonNull.INSTANCE);prompt.addProperty("min",3);prompt.addProperty("max",3);prompt.add("amounts",JsonParser.parseString("[{\"message\":\"First blocker\",\"min\":0,\"max\":3,\"default\":1},{\"message\":\"Second blocker\",\"min\":0,\"max\":3,\"default\":2}]"));snapshot=projection.projectCoreCombat(raw,prompt);shape(snapshot);body.add("revision",snapshot.get("revision"));body.add("decision_id",snapshot.getAsJsonObject("decision").get("decision_id"));body.addProperty("operation","choose_amounts");body.remove("value");body.add("values",JsonParser.parseString("[1,2]"));JsonObject amounts=projection.claimOperation(wire.toString(),"session","human","raw-game","raw-human",41,8);check("1 2".equals(amounts.get("value").getAsString()) && NativeCombatChoices.matchesResponse(prompt,amounts));
        for(String values:new String[]{"[1,1]","[4,-1]","[3]","[1,2.5]","[2147483648,0]"}){JsonObject bad=body.deepCopy();bad.add("values",JsonParser.parseString(values));try{NativeCombatChoices.numericResponse(prompt,bad);throw new AssertionError("BAD_DAMAGE_ALLOCATION");}catch(IllegalArgumentException expected){check(true);}}
        prompt.addProperty("kind","GAME_CHOOSE_CHOICE");prompt.add("key_choices",JsonParser.parseString("{\"native-first\":\"First blocker\",\"native-second\":\"Second blocker\"}"));snapshot=projection.projectCoreCombat(raw,prompt);shape(snapshot);check(!snapshot.toString().contains("native-first"));JsonObject chosen=projection.claimBoolean(choose(snapshot,1),"session","human","raw-game","raw-human",41,8);check("string".equals(chosen.get("kind").getAsString()) && "native-second".equals(chosen.get("value").getAsString()) && NativeCombatChoices.matchesResponse(prompt,chosen));chosen.addProperty("value","foreign");check(!NativeCombatChoices.matchesResponse(prompt,chosen));
    }
    static void terminalCombatChecks() throws Exception {
        terminalGameplayChecks();
        JsonObject before=attackState(),prompt=priorityPrompt(),guard=attackMetadata(true),command=JsonParser.parseString("{\"command\":\"respond\",\"kind\":\"boolean\",\"value\":false,\"game_id\":\"raw-game\",\"decision_id\":41,\"request_id\":\"terminal-input\"}").getAsJsonObject(),accepted=JsonParser.parseString("{\"event\":\"response_sent\",\"accepted\":true,\"request_id\":\"terminal-input\"}").getAsJsonObject();
        for(String outcome:new String[]{"win","loss","draw"}){JsonObject terminal=new JsonObject(),callback=new JsonObject();terminal.addProperty("status","finished");terminal.addProperty("outcome",outcome);terminal.addProperty("game_id","raw-game");terminal.addProperty("viewer","raw-human");callback.addProperty("event","game_result");callback.addProperty("won","win".equals(outcome));callback.addProperty("game_id","raw-game");callback.addProperty("viewer","raw-human");NativeCastCorrelation.TurnDecisionEvidence proof=NativeCastCorrelation.terminalCombatEvidence(before,prompt,command,guard,accepted,terminal,callback);check(proof!=null && proof.matchesCommand(command));
            for(int mode=0;mode<7;mode++){JsonObject bad=terminal.deepCopy(),badCallback=callback.deepCopy(),badCommand=command.deepCopy();if(mode==0)bad.remove("outcome");if(mode==1)bad.addProperty("status","retry");if(mode==2)bad.addProperty("viewer","other");if(mode==3)badCallback.addProperty("won",!"win".equals(outcome));if(mode==4)badCallback.addProperty("event","game_over");if(mode==5)badCommand.addProperty("value",true);if(mode==6)badCommand.addProperty("decision_id",42);check(NativeCastCorrelation.terminalCombatEvidence(before,prompt,badCommand,guard,accepted,bad,badCallback)==null);}
            ManaforgeOpeningProjection projection=projection();JsonObject result=projection.projectCombatResult(before,outcome);shape(result);check("finished".equals(result.get("status").getAsString()) && outcome.equals(result.get("result").getAsString()) && result.get("decision").isJsonNull() && result.getAsJsonArray("actions").size()==0);fails("STALE_DECISION",()->projection.claimAction("{}","session","human","raw-game","raw-human",41,8));
        }
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCombatResult(before,"unknown"));
    }
    static void terminalGameplayChecks() throws Exception {
        JsonObject before=attackState(),prompt=priorityPrompt(),guard=attackMetadata(false),command=new JsonObject(),accepted=new JsonObject();
        command.addProperty("command","respond");command.addProperty("game_id","raw-game");command.addProperty("decision_id",41);command.addProperty("request_id","terminal-cost");command.addProperty("kind","integer");command.addProperty("value",2);
        prompt.addProperty("kind","GAME_GET_AMOUNT");prompt.addProperty("is_priority",false);prompt.addProperty("min",0);prompt.addProperty("max",2);
        accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.addProperty("request_id","terminal-cost");
        JsonObject terminal=JsonParser.parseString("{\"status\":\"finished\",\"outcome\":\"loss\",\"game_id\":\"raw-game\",\"viewer\":\"raw-human\"}").getAsJsonObject(),callback=JsonParser.parseString("{\"event\":\"game_result\",\"won\":false,\"game_id\":\"raw-game\",\"viewer\":\"raw-human\"}").getAsJsonObject();
        check(NativeCastCorrelation.terminalGameplayEvidence(before,prompt,command,guard,accepted,terminal,callback)!=null);
        check(NativeCastCorrelation.terminalCombatEvidence(before,prompt,command,guard,accepted,terminal,callback)==null);
        for(int mode=0;mode<7;mode++){JsonObject bad=command.deepCopy(),badGuard=guard.deepCopy(),badAccepted=accepted.deepCopy(),badTerminal=terminal.deepCopy(),badCallback=callback.deepCopy();if(mode==0)bad.addProperty("value",3);if(mode==1)bad.addProperty("decision_id",42);if(mode==2)badGuard.addProperty("priority_open",true);if(mode==3)badGuard.addProperty("cycle",9);if(mode==4)badAccepted.addProperty("request_id","other");if(mode==5)badTerminal.addProperty("viewer","other");if(mode==6)badCallback.addProperty("won",true);check(NativeCastCorrelation.terminalGameplayEvidence(before,prompt,bad,badGuard,badAccepted,badTerminal,badCallback)==null);}
        prompt.addProperty("kind","GAME_TARGET");prompt.add("targets",JsonParser.parseString("[\"raw-card\"]"));command.addProperty("kind","object");command.addProperty("value","raw-card");check(NativeCastCorrelation.terminalGameplayEvidence(before,prompt,command,guard,accepted,terminal,callback)!=null);command.addProperty("value","foreign");check(NativeCastCorrelation.terminalGameplayEvidence(before,prompt,command,guard,accepted,terminal,callback)==null);
    }
    static void coreResponseChecks() throws Exception {
        JsonObject before=attackState(),after=before.deepCopy(),prompt=attackPrompt(),next=attackPrompt(),guard=attackMetadata(false),command=new JsonObject(),accepted=new JsonObject();next.addProperty("decision_id",42);command.addProperty("command","respond");command.addProperty("game_id","raw-game");command.addProperty("decision_id",41);command.addProperty("request_id","core-input");command.addProperty("kind","object");command.addProperty("value","raw-card");accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.addProperty("request_id","core-input");
        NativeCastCorrelation.TurnDecisionEvidence proof=NativeCastCorrelation.coreCombatResponseEvidence(before,prompt,command,guard,accepted,after,next,guard);check(proof!=null && proof.matchesCommand(command));
        for(int mode=0;mode<8;mode++){JsonObject bad=command.deepCopy(),badNext=next.deepCopy(),badGuard=guard.deepCopy(),badAccepted=accepted.deepCopy();if(mode==0)bad.addProperty("value","foreign");if(mode==1)bad.addProperty("decision_id",40);if(mode==2)badAccepted.addProperty("request_id","different");if(mode==3)badNext.addProperty("decision_id",41);if(mode==4)badGuard.addProperty("priority_open",true);if(mode==5)badGuard.addProperty("cycle",9);if(mode==6)badAccepted.addProperty("accepted",false);if(mode==7)bad.addProperty("kind","string");check(NativeCastCorrelation.coreCombatResponseEvidence(before,prompt,bad,guard,badAccepted,after,badNext,badGuard)==null);}
    }
    static void coreCombatChecks() throws Exception {
        departedCombatChecks();
        JsonObject raw=attackState(),prompt=attackPrompt();JsonObject human=raw.getAsJsonArray("players").get(0).getAsJsonObject(),ai=raw.getAsJsonArray("players").get(1).getAsJsonObject();JsonObject original=human.getAsJsonArray("battlefield").get(0).getAsJsonObject(),second=original.deepCopy();second.addProperty("id","raw-second");human.getAsJsonArray("battlefield").add(second);prompt.getAsJsonArray("attackers").add("raw-second");
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectCoreCombat(raw,prompt);shape(snapshot);check(snapshot.getAsJsonArray("actions").size()==3);check(!snapshot.toString().contains("raw-second") && !snapshot.toString().contains("OPPONENT_SECRET"));
        JsonObject group=JsonParser.parseString("{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}").getAsJsonObject();raw.getAsJsonArray("combat").add(group);JsonObject another=group.deepCopy();another.add("attackers",JsonParser.parseString("[\"raw-second\"]"));raw.getAsJsonArray("combat").add(another);snapshot=projection.projectCoreCombat(raw,prompt);shape(snapshot);check(snapshot.getAsJsonArray("combat").size()==2);
        for(String type:new String[]{"Planeswalker","Battle"}){JsonObject defended=original.deepCopy();defended.addProperty("id","public-defender");defended.addProperty("name","Public "+type);defended.addProperty("type",type);defended.addProperty("controller_name","raw-opponent-name");ai.getAsJsonArray("battlefield").add(defended);another.addProperty("defender","public-defender");snapshot=projection.projectCoreCombat(raw,prompt);shape(snapshot);String reference=snapshot.getAsJsonArray("combat").get(1).getAsJsonObject().get("defender_id").getAsString();check(snapshot.getAsJsonArray("objects").asList().stream().anyMatch(row->row.getAsJsonObject().get("object_id").getAsString().equals(reference)));ai.getAsJsonArray("battlefield").remove(ai.getAsJsonArray("battlefield").size()-1);}another.addProperty("defender","raw-ai");
        JsonObject target=prompt.deepCopy();target.addProperty("kind","GAME_TARGET");target.remove("attackers");target.add("targets",JsonParser.parseString("[\"raw-ai\",\"raw-second\"]"));target.addProperty("can_finish",false);snapshot=projection.projectCoreCombat(raw,target);shape(snapshot);check(snapshot.getAsJsonObject("decision").getAsJsonArray("options").size()==2);check("raw-ai".equals(projection.claimBoolean(choose(snapshot,0),"session","human","raw-game","raw-human",41,8).get("value").getAsString()));String stale=choose(snapshot,0);fails("STALE_DECISION",()->projection.claimBoolean(stale,"session","human","raw-game","raw-human",41,8));
        JsonObject blocked=raw.deepCopy(),blockPrompt=prompt.deepCopy();blocked.addProperty("active_player","raw-opponent-name");blocked.add("combat",new JsonArray());JsonObject enemy=original.deepCopy();enemy.addProperty("id","enemy-attacker");enemy.addProperty("controller_name","raw-opponent-name");blocked.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").add(enemy);JsonObject enemyGroup=group.deepCopy();enemyGroup.add("attackers",JsonParser.parseString("[\"enemy-attacker\"]"));enemyGroup.addProperty("defender","raw-human");blocked.getAsJsonArray("combat").add(enemyGroup);blockPrompt.remove("attackers");blockPrompt.add("blockers",JsonParser.parseString("[\"raw-card\",\"raw-second\"]"));snapshot=projection.projectCoreCombat(blocked,blockPrompt);shape(snapshot);check("declare_blocker".equals(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString()));check("raw-card".equals(projection.claimAction(perform(snapshot),"session","human","raw-game","raw-human",41,8).get("value").getAsString()));
        String uuid="13572468-1234-4567-89ab-123456789abc";JsonObject uuidState=JsonParser.parseString(raw.toString().replace("raw-ai",uuid)).getAsJsonObject();JsonObject uuidView=projection().projectCoreCombat(uuidState,prompt);shape(uuidView);check(uuidView.getAsJsonArray("combat").get(0).getAsJsonObject().get("defender_id").getAsString().startsWith("mf-"));check(!uuidView.toString().contains(uuid));
        JsonObject departed=raw.deepCopy();departed.getAsJsonArray("combat").get(1).getAsJsonObject().add("defender",JsonNull.INSTANCE);JsonObject departedView=projection().projectCoreCombat(departed,prompt);shape(departedView);check(departedView.getAsJsonArray("combat").get(1).getAsJsonObject().get("defender_id").isJsonNull());check(departedView.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("combat_defender_lki")));
        for(int mode=0;mode<6;mode++){JsonObject bad=raw.deepCopy(),badPrompt=prompt.deepCopy();if(mode==0)badPrompt.getAsJsonArray("attackers").add("raw-card");if(mode==1)badPrompt.getAsJsonArray("attackers").add("foreign");if(mode==2)bad.getAsJsonArray("combat").get(1).getAsJsonObject().add("attackers",JsonParser.parseString("[\"raw-card\"]"));if(mode==3)bad.getAsJsonArray("combat").get(1).getAsJsonObject().addProperty("defender","foreign");if(mode==4)bad.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(1).getAsJsonObject().addProperty("hidden",true);if(mode==5)badPrompt.add("blockers",new JsonArray());fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(bad,badPrompt));}
    }
    static void departedCombatChecks() throws Exception {
        ManaforgeOpeningProjection projection=projection();JsonObject state=attackState(),prompt=attackPrompt();
        projection.projectCoreCombat(state,prompt);
        JsonObject priority=prompt.deepCopy();priority.remove("attackers");priority.addProperty("is_priority",true);state.add("priority_player",state.get("active_player"));
        state.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));
        state.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").remove(0);
        JsonObject view=projection.projectCoreCombat(state,priority);shape(view);
        check(view.getAsJsonArray("combat").size()==0);
        check(view.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("combat_lki")));
        check(view.getAsJsonArray("actions").size()>0);
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(state,priority));
    }
    static void combatCaseEvidenceChecks() throws Exception {
        NativeCombatCase scenario=new NativeCombatCase("trample");JsonObject raw=attackState(),prompt=attackPrompt(),command=new JsonObject();raw.addProperty("turn",1);raw.getAsJsonArray("hand").add(raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).deepCopy());raw.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("name","Garruk's Companion");prompt.remove("attackers");prompt.addProperty("is_priority",true);command.addProperty("kind","object");command.addProperty("value","raw-card");scenario.before(raw,prompt,command);raw.add("hand",new JsonArray());
        JsonObject actor=raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();actor.addProperty("name","Garruk's Companion");actor.addProperty("power","3");actor.addProperty("toughness","2");
        JsonObject opponent=actor.deepCopy();opponent.addProperty("id","blocker");opponent.addProperty("name","Ornithopter");raw.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").add(opponent);raw.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[\"blocker\"],\"defender\":\"raw-ai\",\"blocked\":true}]"));
        NativeCombatCase.Metadata metadata=(state,ids)->{JsonObject result=new JsonObject(),objects=new JsonObject(),entry=new JsonObject();result.addProperty("status","ok");result.add("cycle",state.get("cycle"));entry.addProperty("owner","raw-human");entry.addProperty("controller","raw-human");entry.addProperty("incarnation",2);entry.add("live_abilities",JsonParser.parseString("[\"Trample\"]"));objects.add("raw-card",entry);result.add("objects",objects);return result;};
        raw.addProperty("step","DECLARE_BLOCKERS");check(!scenario.observe(raw,prompt,metadata));raw.addProperty("step","COMBAT_DAMAGE");check(!scenario.observe(raw,prompt,metadata));check(!scenario.report().get("native_combat_case_damage_verified").getAsBoolean());raw.getAsJsonArray("players").get(1).getAsJsonObject().addProperty("life",19);check(!scenario.observe(raw,prompt,metadata));check(scenario.report().get("native_combat_case_damage_verified").getAsBoolean());raw.addProperty("phase","POSTCOMBAT_MAIN");check(scenario.observe(raw,prompt,metadata));
        NativeCombatCase.Metadata changed=(state,ids)->{JsonObject result=metadata.read(state,ids);result.getAsJsonObject("objects").getAsJsonObject("raw-card").addProperty("incarnation",3);return result;};fails("COMBAT_CASE_ACTOR_CHANGED",()->scenario.observe(raw,prompt,changed));
        NativeCombatCase draw=new NativeCombatCase("draw");fails("COMBAT_CASE_RESULT_UNPROVEN",()->{draw.terminal("draw");return;});
    }
    static final class SessionEngine implements ManaforgeGameplaySession.Engine {
        JsonObject state=OpeningProjectionChecks.state(),next=prompt();int submissions;boolean accepted=true,badCycle;Long authoritativeLife;
        SessionEngine(){next.addProperty("decision_id",42);}
        public JsonObject metadata(JsonObject state,String... ids){JsonObject result=attackMetadata(false);if(authoritativeLife!=null){JsonArray seats=new JsonArray();for(JsonElement player:state.getAsJsonArray("players")){JsonObject row=new JsonObject();row.add("id",player.getAsJsonObject().get("id"));row.addProperty("life",authoritativeLife);seats.add(row);}result.add("players",seats);}if(badCycle)result.addProperty("cycle",9);return result;}
        public JsonObject submit(JsonObject command){submissions++;JsonObject result=new JsonObject();result.addProperty("event","response_sent");result.addProperty("accepted",accepted);result.add("request_id",command.get("request_id"));return result;}
        public ManaforgeGameplaySession.Advance advance(long previous){return new ManaforgeGameplaySession.Advance(state,next,null);}
        public JsonObject terminalMetadata(JsonObject state){throw new AssertionError("UNEXPECTED_TERMINAL_READ");}
    }
    static ManaforgeUnityOpening.TurnSubmit nativeSubmit(ManaforgeUnityOpening.TurnOffer offer) throws Exception {java.lang.reflect.Field field=offer.getClass().getDeclaredField("submit");field.setAccessible(true);return (ManaforgeUnityOpening.TurnSubmit)field.get(offer);}
    static JsonObject sessionCommand(ManaforgeOpeningProjection projection,ManaforgeUnityOpening.TurnOffer offer) throws Exception {JsonObject view=offer.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot");return projection.claimBoolean(choose(view,0),"session","human","raw-game","raw-human",41,8);}
    static void gameplaySessionChecks() throws Exception {
        SessionEngine lifeEngine=new SessionEngine();lifeEngine.authoritativeLife=28L;
        String originalLife=lifeEngine.state.getAsJsonArray("players").get(0).getAsJsonObject().get("life").toString();
        ManaforgeGameplaySession lifeSession=new ManaforgeGameplaySession(projection(),lifeEngine,null,true);
        JsonObject lifeOffer=lifeSession.offer(lifeEngine.state,prompt()).snapshot().getAsJsonObject("body").getAsJsonObject("snapshot");shape(lifeOffer);
        for(JsonElement seat:lifeOffer.getAsJsonArray("players"))check(seat.getAsJsonObject().get("life").getAsLong()==28);
        check(originalLife.equals(lifeEngine.state.getAsJsonArray("players").get(0).getAsJsonObject().get("life").toString()));lifeSession.close();
        SessionEngine engine=new SessionEngine();ManaforgeOpeningProjection projection=projection();ManaforgeGameplaySession session=new ManaforgeGameplaySession(projection,engine,new ManaforgeGameplaySession.Observer(){public boolean after(JsonObject state,JsonObject prompt){state.addProperty("viewer","MUTATED");return true;}},true);
        ManaforgeUnityOpening.TurnOffer offer=session.offer(engine.state,prompt());shape(offer.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot"));JsonObject command=sessionCommand(projection,offer);nativeSubmit(offer).submit(command);check(engine.submissions==1 && "raw-human".equals(engine.state.get("viewer").getAsString()));try{nativeSubmit(offer).submit(command);throw new AssertionError("REPLAY");}catch(IllegalStateException expected){check(engine.submissions==1);}session.close();
        engine=new SessionEngine();engine.accepted=false;projection=projection();session=new ManaforgeGameplaySession(projection,engine,null,true);offer=session.offer(engine.state,prompt());command=sessionCommand(projection,offer);final ManaforgeUnityOpening.TurnSubmit rejected=nativeSubmit(offer);final JsonObject rejectedCommand=command;fails("GAMEPLAY_RESPONSE_REJECTED",()->rejected.submit(rejectedCommand));check(engine.submissions==1);fails("STALE_DECISION",()->rejected.submit(rejectedCommand));session.close();
        engine=new SessionEngine();projection=projection();session=new ManaforgeGameplaySession(projection,engine,null,true);offer=session.offer(engine.state,prompt());command=sessionCommand(projection,offer);engine.badCycle=true;final ManaforgeUnityOpening.TurnSubmit stale=nativeSubmit(offer);final JsonObject staleCommand=command;fails("GAMEPLAY_RESPONSE_UNPROVEN",()->stale.submit(staleCommand));session.close();
        engine=new SessionEngine();projection=projection();session=new ManaforgeGameplaySession(projection,engine,null,true);offer=session.offer(engine.state,prompt());command=sessionCommand(projection,offer);session.close();try{nativeSubmit(offer).submit(command);throw new AssertionError("CLOSED");}catch(IllegalStateException expected){check(engine.submissions==0);}
    }
    static final class RequestEngine implements ManaforgeGameplaySession.Engine {
        JsonObject state=OpeningProjectionChecks.state(),choice=prompt(),pending;int replies;
        public JsonObject metadata(JsonObject view,String... ids){JsonObject guard=attackMetadata(false);guard.add("cycle",view.get("cycle"));return guard;}
        public JsonObject submit(JsonObject command){replies++;JsonObject reply=new JsonObject();reply.addProperty("event","response_sent");reply.addProperty("accepted",true);reply.addProperty("request_consumed",true);reply.add("request_id",command.get("request_id"));reply.add("session_request_id",command.get("session_request_id"));pending=null;return reply;}
        public ManaforgeGameplaySession.Advance advance(long previous){throw new AssertionError("PERMISSION_CONSUMED_GAMEPLAY_DECISION");}
        public JsonObject terminalMetadata(JsonObject before){throw new AssertionError("UNEXPECTED_TERMINAL");}
        public JsonObject pollRequest(){return pending;}
        public boolean requestCurrent(String id){return pending!=null && id.equals(pending.get("session_request_id").getAsString());}
        public ManaforgeGameplaySession.Advance refresh(){return new ManaforgeGameplaySession.Advance(state,choice,null);}
    }
    static JsonObject permissionRequest(String kind){JsonObject request=new JsonObject();request.addProperty("kind","USER_REQUEST_DIALOG");request.addProperty("decision_id",77);request.addProperty("request_kind",kind);request.addProperty("session_request_id","native-private-request");request.addProperty("message","Permission request");JsonObject choices=new JsonObject();choices.addProperty("0","Accept");choices.addProperty("1","Deny");request.add("key_choices",choices);return request;}
    static void sessionRequestChecks() throws Exception {
        for(String kind:new String[]{"hand_visibility","rollback"})for(int option=0;option<2;option++){
            RequestEngine engine=new RequestEngine();ManaforgeOpeningProjection projection=projection();ManaforgeGameplaySession session=new ManaforgeGameplaySession(projection,engine,null,true);
            ManaforgeUnityOpening.TurnOffer gameplay=session.offer(engine.state,engine.choice);JsonObject oldView=gameplay.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot");String oldWire=choose(oldView,0);
            engine.pending=permissionRequest(kind);ManaforgeUnityOpening.TurnOffer modal=gameplay.poll();check(modal!=null && engine.replies==0);
            JsonObject view=modal.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot");shape(view);check(view.getAsJsonObject("decision").getAsJsonObject("request").get("kind").getAsString().equals(kind));check(!view.toString().contains("native-private-request"));
            fails("STALE_DECISION",()->projection.claimBoolean(oldWire,"session","human","raw-game","raw-human",41,8));
            JsonObject response=projection.claimBoolean(choose(view,option),"session","human","raw-game","raw-human",77,8);check("respond_request".equals(response.get("command").getAsString()) && Integer.toString(option).equals(response.get("value").getAsString()));
            ManaforgeUnityOpening.TurnResult result=nativeSubmit(modal).submit(response);java.lang.reflect.Field next=result.getClass().getDeclaredField("next");next.setAccessible(true);ManaforgeUnityOpening.TurnOffer resumed=(ManaforgeUnityOpening.TurnOffer)next.get(result);
            check(engine.replies==1 && resumed!=null);JsonObject restored=resumed.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot");shape(restored);check(!restored.getAsJsonObject("decision").has("request"));
            fails("STALE_SESSION_REQUEST",()->nativeSubmit(modal).submit(response));session.close();
        }
        RequestEngine changed=new RequestEngine();changed.pending=permissionRequest("rollback");ManaforgeOpeningProjection projection=projection();ManaforgeGameplaySession changing=new ManaforgeGameplaySession(projection,changed,null,true);ManaforgeUnityOpening.TurnOffer consent=changing.offer(changed.state,changed.choice);
        JsonObject view=consent.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot"),response=projection.claimBoolean(choose(view,1),"session","human","raw-game","raw-human",77,8);
        changed.state.addProperty("cycle",9);changed.choice.addProperty("cycle",9);changed.choice.addProperty("decision_id",88);ManaforgeUnityOpening.TurnResult continued=nativeSubmit(consent).submit(response);check(continued!=null && changed.replies==1);changing.close();
        RequestEngine engine=new RequestEngine();engine.pending=permissionRequest("hand_visibility");ManaforgeGameplaySession session=new ManaforgeGameplaySession(projection(),engine,null,true);ManaforgeUnityOpening.TurnOffer modal=session.offer(engine.state,engine.choice);engine.pending=null;check(modal.poll()!=null && engine.replies==0);session.close();
    }
    static void genericSelectionChecks() throws Exception {
        JsonObject raw=attackState(),prompt=attackPrompt();prompt.remove("attackers");prompt.add("targets",JsonParser.parseString("[\"raw-ai\",\"raw-card\"]"));
        ManaforgeOpeningProjection projection=projection();JsonObject view=projection.projectCoreCombat(raw,prompt,true);shape(view);check(view.getAsJsonObject("decision").getAsJsonArray("options").size()==2);
        JsonObject response=projection.claimBoolean(choose(view,0),"session","human","raw-game","raw-human",41,8);check("object".equals(response.get("kind").getAsString()) && "raw-ai".equals(response.get("value").getAsString()));
        prompt.add("targets",new JsonArray());fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection.projectCoreCombat(raw,prompt,true));
    }
    static void pileChoiceChecks() throws Exception {
        for(int selected=0;selected<2;selected++){
            JsonObject raw=attackState(),prompt=attackPrompt();prompt.addProperty("kind","GAME_CHOOSE_PILE");prompt.remove("attackers");
            JsonObject card=state().getAsJsonArray("hand").get(0).getAsJsonObject().deepCopy();card.addProperty("name","Same visible name");
            JsonArray first=new JsonArray();first.add(card);first.add(card.deepCopy());JsonObject hidden=card.deepCopy();hidden.addProperty("hidden",true);hidden.addProperty("name","SECRET_PILE_CARD");first.add(hidden);
            prompt.add("cards",first);prompt.add("second_pile",new JsonArray());ManaforgeOpeningProjection projection=projection();
            JsonObject view=projection.projectCoreCombat(raw,prompt,true);shape(view);String text=view.toString();check(!text.contains("SECRET_PILE_CARD") && !text.contains("raw-card"));
            JsonArray groups=view.getAsJsonObject("decision").getAsJsonArray("groups");check(groups.size()==2 && groups.get(0).getAsJsonObject().getAsJsonArray("cards").size()==3 && groups.get(1).getAsJsonObject().getAsJsonArray("cards").size()==0);
            String wire=choose(view,selected);JsonObject response=projection.claimBoolean(wire,"session","human","raw-game","raw-human",41,8);
            check(response.get("value").getAsBoolean()==(selected==0));fails("STALE_DECISION",()->projection.claimBoolean(wire,"session","human","raw-game","raw-human",41,8));
            JsonObject broken=view.deepCopy();broken.getAsJsonObject("decision").getAsJsonArray("groups").get(0).getAsJsonObject().addProperty("option_id","unoffered");
            try{shape(broken);throw new AssertionError("UNBOUND_PILE_ACCEPTED");}catch(java.io.IOException expected){check("RECEIVE_CONTEXT".equals(expected.getMessage()));}
        }
    }
    static void emptyOptionalTargetChecks() throws Exception {
        JsonObject raw=attackState(),target=attackPrompt();target.addProperty("kind","GAME_TARGET");target.remove("attackers");
        target.add("targets",new JsonArray());target.addProperty("can_finish",true);
        ManaforgeOpeningProjection projection=projection();JsonObject view=projection.projectCoreCombat(raw,target,true);shape(view);
        check(view.getAsJsonObject("decision").getAsJsonArray("options").size()==0);
        check(view.getAsJsonArray("actions").size()==1);
        JsonObject response=projection.claimAction(perform(view),"session","human","raw-game","raw-human",41,8);
        check("boolean".equals(response.get("kind").getAsString()) && !response.get("value").getAsBoolean());
        target.addProperty("can_finish",false);
        fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection.projectCoreCombat(raw,target,true));
        check("UNSUPPORTED_GAME_TARGET_OPTIONS".equals(projection.unsupportedCode()));
    }
    static void manualManaChecks() throws Exception {
        JsonObject raw=attackState(),prompt=priorityPrompt();raw.addProperty("priority_player","raw-name");raw.getAsJsonObject("action_kinds").addProperty("raw-card","activate");for(JsonElement player:raw.getAsJsonArray("players"))player.getAsJsonObject().add("mana",JsonParser.parseString("[[\"green\",2],[\"colorless\",1]]"));ManaforgeOpeningProjection projection=projection();JsonObject view=projection.projectCoreCombat(raw,prompt,true);shape(view);check("Activate: Forest".equals(view.getAsJsonArray("actions").get(0).getAsJsonObject().get("label").getAsString()));check(view.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("mana").size()==2);check(!view.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("mana")));check("raw-card".equals(projection.claimAction(perform(view),"session","human","raw-game","raw-human",41,8).get("value").getAsString()));
        JsonObject mana=prompt.deepCopy();mana.addProperty("kind","GAME_PLAY_MANA");mana.addProperty("is_priority",false);projection=projection();JsonObject poolView=projection.projectCoreCombat(raw,mana,true);shape(poolView);JsonObject poolWire=JsonParser.parseString(perform(poolView)).getAsJsonObject();poolWire.getAsJsonObject("body").add("action_id",poolView.getAsJsonArray("actions").get(1).getAsJsonObject().get("action_id"));JsonObject poolCommand=projection.claimAction(poolWire.toString(),"session","human","raw-game","raw-human",41,8);check("mana_type".equals(poolCommand.get("kind").getAsString()) && "GREEN".equals(poolCommand.get("value").getAsString()) && "raw-human".equals(poolCommand.get("player_id").getAsString()));
        JsonObject next=mana.deepCopy(),accepted=new JsonObject();next.addProperty("decision_id",42);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",poolCommand.get("request_id"));check(NativeCastCorrelation.coreCombatResponseEvidence(raw,mana,poolCommand,attackMetadata(false),accepted,raw,next,attackMetadata(false))!=null);JsonObject foreign=poolCommand.deepCopy();foreign.addProperty("player_id","raw-ai");check(NativeCastCorrelation.coreCombatResponseEvidence(raw,mana,foreign,attackMetadata(false),accepted,raw,next,attackMetadata(false))==null);
        for(String bad:new String[]{"[[\"green\",-1]]","[[\"unknown\",1]]","[[\"green\",1],[\"green\",2]]","[[\"green\",1.5]]","[[\"green\",2147483648]]"}){JsonObject invalid=raw.deepCopy();invalid.getAsJsonArray("players").get(0).getAsJsonObject().add("mana",JsonParser.parseString(bad));fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(invalid,prompt,true));}
    }
    static void automaticPaymentChecks() throws Exception {
        JsonObject state=attackState(),prompt=attackPrompt(),guard=attackMetadata(false);prompt.remove("attackers");prompt.addProperty("kind","GAME_PLAY_MANA");JsonObject assessment=JsonParser.parseString("{\"safety\":\"VERIFIED_ORDINARY_EQUIVALENT\",\"sequence\":1,\"paying_source\":\"spell\",\"unpaid_count\":1,\"steps\":[{\"source\":\"raw-card\",\"incarnation\":4}]}").getAsJsonObject();assessment.addProperty("plan_token","private-plan");guard.add("ordinary_payment",assessment);
        JsonObject receipt=new JsonObject();receipt.addProperty("sequence",1);receipt.addProperty("plan_token","private-plan");receipt.addProperty("source","raw-card");receipt.addProperty("activated",true);receipt.addProperty("completed",false);guard.add("payment_execution",receipt);
        for(manaforge.payment.PaymentCoordinator.Mode mode:manaforge.payment.PaymentCoordinator.Mode.values()){
            NativeAutomaticPayment payment=new NativeAutomaticPayment("session","raw-human",mode);JsonObject command=payment.prepare(state,prompt,guard);check((command!=null)==(mode==manaforge.payment.PaymentCoordinator.Mode.AUTO));if(command!=null){check(payment.revalidate(guard));JsonObject changed=guard.deepCopy();changed.addProperty("cycle",9);check(!payment.revalidate(changed));changed=guard.deepCopy();changed.getAsJsonObject("ordinary_payment").getAsJsonArray("steps").get(0).getAsJsonObject().addProperty("incarnation",5);check(!payment.revalidate(changed));check(payment.prepare(state,prompt,guard)==null);payment.uncertain();}check(payment.report().get("native_auto_payment_steps").getAsInt()==0);payment.close();
        }
        NativeAutomaticPayment progress=new NativeAutomaticPayment("session","raw-human",manaforge.payment.PaymentCoordinator.Mode.AUTO);JsonObject command=progress.prepare(state,prompt,guard),after=state.deepCopy(),next=attackPrompt(),accepted=new JsonObject();after.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().addProperty("tapped",true);next.addProperty("decision_id",42);accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));progress.observed(state,prompt,command,guard,accepted,after,next,guard);check(progress.report().get("native_auto_payment_steps").getAsInt()==1);check(progress.report().get("native_auto_payment_completed").getAsInt()==0);check(progress.prepare(state,prompt,guard)==null);progress.close();
        NativeAutomaticPayment uncertain=new NativeAutomaticPayment("session","raw-human",manaforge.payment.PaymentCoordinator.Mode.AUTO);JsonObject attempted=uncertain.prepare(state,prompt,guard),badMetadata=guard.deepCopy();badMetadata.getAsJsonObject("payment_execution").addProperty("plan_token","foreign-plan");accepted.add("request_id",attempted.get("request_id"));fails("AUTO_PAYMENT_EXECUTION_UNPROVEN",()->uncertain.observed(state,prompt,attempted,guard,accepted,after,next,badMetadata));check(uncertain.prepare(state,prompt,guard)==null);uncertain.close();
        SessionEngine engine=new SessionEngine();engine.next=prompt;NativeAutomaticPayment stopped=new NativeAutomaticPayment("session","raw-human",manaforge.payment.PaymentCoordinator.Mode.AUTO);ManaforgeAutomaticEngine wrapper=new ManaforgeAutomaticEngine(engine,stopped,()->true);fails("AUTO_PAYMENT_CANCELLED",()->wrapper.advance(40));check(engine.submissions==0);stopped.close();
        for(String safety:new String[]{"UNKNOWN","STRATEGIC","UNSUPPORTED"}){JsonObject manual=guard.deepCopy();manual.getAsJsonObject("ordinary_payment").addProperty("safety",safety);NativeAutomaticPayment payment=new NativeAutomaticPayment("session","raw-human",manaforge.payment.PaymentCoordinator.Mode.AUTO);check(payment.prepare(state,prompt,manual)==null);payment.close();}
    }
    static void nativeLaunchChecks() throws Exception {
        commanderProjectionChecks();attachmentProjectionChecks();
        manaforge.protocol.LaunchContracts.LaunchManifest manifest=new manaforge.protocol.LaunchContracts.LaunchManifest();manifest.manifest_id="saved-session";manifest.format="freeform";manifest.seats=new manaforge.protocol.LaunchContracts.LaunchSeat[2];
        for(int i=0;i<2;i++){manaforge.protocol.LaunchContracts.LaunchSeat seat=new manaforge.protocol.LaunchContracts.LaunchSeat();seat.seat_id="seat-"+i;seat.controller=i==0?"local_human":"engine_ai";seat.document=new manaforge.protocol.LaunchContracts.NativeLaunchDocument();seat.document.deck=new manaforge.protocol.LaunchContracts.NativeLaunchDeck();seat.document.deck.commander_entry_ids=new String[0];manaforge.protocol.LaunchContracts.NativeLaunchEntry entry=new manaforge.protocol.LaunchContracts.NativeLaunchEntry();entry.entry_id="entry-"+i;entry.name="Forest";entry.set_code="TRK";entry.collector_number="325";entry.section="mainboard";entry.quantity=60L;entry.card_id="print-"+i;seat.document.deck.entries=new manaforge.protocol.LaunchContracts.NativeLaunchEntry[]{entry};manifest.seats[i]=seat;}
        NativeGameLaunch launch=new NativeGameLaunch(manifest);check(launch.session().equals("saved-session") && launch.viewer().equals("seat-0"));check(launch.cards(false,false).get(0).getAsJsonObject().get("quantity").getAsLong()==60);check(launch.cards(true,true).size()==0);check(launch.bindings().get("TRK/325").printing_id.equals("print-0"));check(!launch.bindings().get("TRK/325").printing_id.equals("print-1"));
        manaforge.protocol.LaunchContracts.LaunchManifest commander=new Gson().fromJson(new Gson().toJson(manifest),manaforge.protocol.LaunchContracts.LaunchManifest.class);commander.format="commander";
        for(manaforge.protocol.LaunchContracts.LaunchSeat seat:commander.seats){manaforge.protocol.LaunchContracts.NativeLaunchEntry land=seat.document.deck.entries[0],designated=new Gson().fromJson(new Gson().toJson(land),manaforge.protocol.LaunchContracts.NativeLaunchEntry.class);land.quantity=99L;designated.entry_id="designated";designated.name="Public commander";designated.set_code="SYN";designated.collector_number="1";designated.quantity=1L;seat.document.deck.commander_entry_ids=new String[]{"designated"};seat.document.deck.entries=new manaforge.protocol.LaunchContracts.NativeLaunchEntry[]{land,designated};}
        NativeGameLaunch nativeCommander=new NativeGameLaunch(commander);check(nativeCommander.cards(false,false).size()==1 && nativeCommander.cards(false,true).size()==1);check(nativeCommander.cards(false,false).get(0).getAsJsonObject().get("quantity").getAsLong()==99);check(nativeCommander.bindings().containsKey("SYN/1"));
        JsonObject roster=JsonParser.parseString("{\"priority_open\":true,\"commander_metadata_complete\":true,\"commanders\":[{\"owner\":\"raw-human\",\"name\":\"Public commander\",\"set\":\"SYN\",\"number\":\"1\"},{\"owner\":\"raw-ai\",\"name\":\"Public commander\",\"set\":\"SYN\",\"number\":\"1\"}]}").getAsJsonObject();nativeCommander.verifyCommanders(attackState(),roster);check(true);roster.getAsJsonArray("commanders").get(0).getAsJsonObject().addProperty("number","2");fails("UNITY_GAME_COMMANDERS_MISMATCH",()->nativeCommander.verifyCommanders(attackState(),roster));
        NativeLaunchEntry original = manifest.seats[0].document.deck.entries[0];
        NativeLaunchEntry duplicate = new Gson().fromJson(new Gson().toJson(original), NativeLaunchEntry.class);
        duplicate.entry_id = "same-rules-different-art"; duplicate.card_id = "another-print";
        manifest.seats[0].document.deck.entries = new NativeLaunchEntry[]{original, duplicate};
        check(new NativeGameLaunch(manifest).bindings().get("TRK/325").printing_id.equals("another-print"));
        check(new NativeGameLaunch(manifest).bindings().get("TRK/325").deck_entry_id==null);
        check(new NativeGameLaunch(manifest).bindings().containsKey("opponent/TRK/325"));
        check(new NativeGameLaunch(manifest).bindings().get("opponent/TRK/325").deck_entry_id==null);
        duplicate.oracle_id="different-oracle";check(!new NativeGameLaunch(manifest).bindings().containsKey("TRK/325"));duplicate.oracle_id=original.oracle_id;
        duplicate.card_id = original.card_id;
        check(new NativeGameLaunch(manifest).bindings().get("TRK/325").printing_id.equals(original.card_id));
        check(new NativeGameLaunch(manifest).bindings().get("TRK/325").deck_entry_id == null);
        manifest.seats[0].document.deck.entries = new NativeLaunchEntry[]{original};
        manifest.seats[1].controller="local_human";fails("UNITY_GAME_SETUP_UNSUPPORTED",()->new NativeGameLaunch(manifest));manifest.seats[1].controller="engine_ai";manifest.format="commander";fails("UNITY_GAME_SETUP_UNSUPPORTED",()->new NativeGameLaunch(manifest));manifest.format="freeform";
        manifest.seats[0].document.deck.entries[0].set_code=null;fails("UNITY_GAME_PRINTING_UNSUPPORTED",()->new NativeGameLaunch(manifest));manifest.seats[0].document.deck.entries[0].set_code="TRK";manifest.seats[0].document.deck.companion_entry_id="extra";fails("UNITY_GAME_SETUP_UNSUPPORTED",()->new NativeGameLaunch(manifest));manifest.seats[0].document.deck.companion_entry_id=null;
        SessionEngine engine=new SessionEngine();JsonObject unknown=prompt();unknown.addProperty("kind","GAME_CHOOSE_UNKNOWN");ManaforgeGameplaySession session=new ManaforgeGameplaySession(projection(),engine,null,true);ManaforgeUnityOpening.TurnOffer offered=session.offer(engine.state,unknown);JsonObject view=offered.snapshot().getAsJsonObject("body").getAsJsonObject("snapshot");shape(view);check(view.get("decision").isJsonNull() && view.getAsJsonArray("actions").size()==0 && view.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("decision")));fails("GAMEPLAY_DECISION_UNSUPPORTED",()->nativeSubmit(offered).submit(new JsonObject()));check(engine.submissions==0);session.close();
    }
    static void triggerOrderingProjectionChecks() throws Exception {
        JsonObject raw=attackState(),prompt=priorityPrompt();prompt.addProperty("kind","GAME_TARGET");prompt.addProperty("is_priority",false);prompt.addProperty("can_finish",false);
        JsonArray targets=new JsonArray();targets.add("native-trigger-1");targets.add("native-trigger-2");prompt.add("targets",targets);JsonArray cards=new JsonArray();
        for(String id:new String[]{"native-trigger-1","native-trigger-2"}) {
            JsonObject card=new JsonObject();card.addProperty("id",id);card.addProperty("hidden",false);card.addProperty("face_down",false);card.addProperty("name","Primeval Herald");card.addProperty("type","Ability");cards.add(card);
        }
        prompt.add("cards",cards);ManaforgeOpeningProjection projection=projection();JsonObject view=projection.projectCoreCombat(raw,prompt,true);shape(view);
        check(view.getAsJsonObject("decision").getAsJsonArray("options").size()==2 && view.getAsJsonArray("actions").size()==0);
        check(!view.toString().contains("native-trigger-"));
        check("native-trigger-2".equals(claim(projection,choose(view,1)).get("value").getAsString()));
        fails("STALE_DECISION",()->claim(projection,choose(view,0)));
        cards.get(0).getAsJsonObject().addProperty("hidden",true);fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(raw,prompt,true));
    }
    static void playableExileChecks() throws Exception {
        for(String action:new String[]{"cast_spell","play_land","select_object","activate"})for(String owner:new String[]{"raw-human","raw-ai"}){
            JsonObject raw=attackState(),prompt=priorityPrompt();raw.addProperty("priority_player","raw-name");raw.addProperty("playable_information_complete",true);
            JsonObject card=raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().deepCopy();
            card.addProperty("id","impulse-card");card.addProperty("exile_owner",owner);card.addProperty("hidden",false);card.addProperty("face_down",false);
            raw.getAsJsonArray("exile").add(card);raw.add("playable",new JsonArray());raw.getAsJsonArray("playable").add("impulse-card");
            raw.getAsJsonObject("action_kinds").addProperty("impulse-card",action);
            ManaforgeOpeningProjection projection=projection();JsonObject view=projection.projectCoreCombat(raw,prompt,true);shape(view);
            check(view.get("actions_complete").getAsBoolean());
            JsonObject offered=view.getAsJsonArray("actions").get(0).getAsJsonObject();check(action.equals(offered.get("kind").getAsString()));
            JsonObject exiled=view.getAsJsonArray("objects").asList().stream().map(JsonElement::getAsJsonObject).filter(row->new JsonPrimitive("exile").equals(row.get("zone"))).findFirst().get();
            check(offered.get("object_id").equals(exiled.get("object_id")));
            JsonObject chosen=projection.claimAction(perform(view),"session","human","raw-game","raw-human",41,8);
            check("object".equals(chosen.get("kind").getAsString()) && "impulse-card".equals(chosen.get("value").getAsString()));
            fails("STALE_DECISION",()->projection.claimAction(perform(view),"session","human","raw-game","raw-human",41,8));
            // Expiry/removal of native permission leaves the visible card browsable, not playable.
            raw.add("playable",new JsonArray());JsonObject expired=projection.projectCoreCombat(raw,prompt,true);shape(expired);
            check(expired.getAsJsonArray("actions").asList().stream().allMatch(item->new JsonPrimitive("pass").equals(item.getAsJsonObject().get("kind"))));
            raw.getAsJsonArray("playable").add("impulse-card");card.addProperty("hidden",true);card.addProperty("face_down",true);
            JsonObject concealed=projection.projectCoreCombat(raw,prompt,true);shape(concealed);check(!concealed.get("actions_complete").getAsBoolean());
            check(concealed.getAsJsonArray("actions").asList().stream().allMatch(item->new JsonPrimitive("pass").equals(item.getAsJsonObject().get("kind"))));
        }
    }
    static void publicStackAndOfferedCardChecks() throws Exception {
        JsonObject raw=landState(),prompt=priorityPrompt(),stacked=raw.getAsJsonArray("hand").get(0).getAsJsonObject().deepCopy();stacked.addProperty("id","public-spell");stacked.addProperty("stack_owner","raw-ai");stacked.addProperty("stack_controller","raw-ai");stacked.addProperty("name","Public spell");raw.getAsJsonArray("stack").add(stacked);JsonObject view=projection().projectCoreCombat(raw,prompt,true);shape(view);check(view.getAsJsonArray("objects").asList().stream().anyMatch(value->"stack".equals(value.getAsJsonObject().get("zone").getAsString())));check(!view.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("stack")));check(view.getAsJsonArray("actions").size()>0);
        JsonObject target=prompt.deepCopy();target.addProperty("kind","GAME_TARGET");target.addProperty("is_priority",false);target.add("targets",JsonParser.parseString("[\"offered-library-land\"]"));target.add("cards",new JsonArray());JsonObject land=stacked.deepCopy();land.addProperty("id","offered-library-land");land.addProperty("name","Native offered Forest");target.getAsJsonArray("cards").add(land);view=projection().projectCoreCombat(raw,target,true);shape(view);check(view.getAsJsonObject("decision").getAsJsonArray("options").get(0).getAsJsonObject().get("label").getAsString().equals("Native offered Forest"));check(!view.toString().contains("offered-library-land"));
        land.addProperty("hidden",true);fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(raw,target,true));land.addProperty("hidden",false);land.addProperty("id","unoffered");fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(raw,target,true));
    }
    static void attachmentProjectionChecks() throws Exception {
        JsonObject raw=attackState();raw.addProperty("priority_player","raw-name");raw.add("playable",new JsonArray());raw.add("action_kinds",new JsonObject());
        JsonObject host=raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();host.addProperty("name","Public host");host.addProperty("type","Creature");host.add("attached_to",JsonNull.INSTANCE);host.add("attachments",JsonParser.parseString("[\"raw-aura\"]"));
        JsonObject aura=host.deepCopy();aura.addProperty("id","raw-aura");aura.addProperty("name","Public Aura");aura.addProperty("type","Enchantment — Aura");aura.addProperty("owner_name","raw-opponent-name");aura.addProperty("controller_name","raw-opponent-name");aura.addProperty("attached_to","raw-card");aura.add("attachments",new JsonArray());raw.getAsJsonArray("players").get(1).getAsJsonObject().getAsJsonArray("battlefield").add(aura);
        ManaforgeOpeningProjection projection=projection();JsonObject snapshot=projection.projectCoreCombat(raw,priorityPrompt(),true);shape(snapshot);
        JsonObject publicHost=snapshot.getAsJsonArray("objects").get(0).getAsJsonObject(),publicAura=snapshot.getAsJsonArray("objects").get(1).getAsJsonObject();
        check(publicAura.get("attached_to").equals(publicHost.get("object_id")));check(publicHost.getAsJsonArray("attachments").get(0).equals(publicAura.get("object_id")));check(!publicHost.get("controller_id").equals(publicAura.get("controller_id")));check(!snapshot.toString().contains("raw-aura"));check(!snapshot.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("attachments")));
        host.add("attachments",new JsonArray());aura.add("attached_to",JsonNull.INSTANCE);JsonObject detached=projection.projectCoreCombat(raw,priorityPrompt(),true);shape(detached);check(detached.getAsJsonArray("objects").get(1).getAsJsonObject().get("attached_to").isJsonNull());
        aura.addProperty("attached_to","raw-human");JsonObject curse=projection.projectCoreCombat(raw,priorityPrompt(),true);check(curse.getAsJsonArray("objects").get(1).getAsJsonObject().get("attached_to").equals(curse.get("viewer_id")));
        aura.addProperty("hidden",true);aura.addProperty("face_down",true);aura.addProperty("name","PRIVATE_ATTACHMENT");host.add("attachments",JsonParser.parseString("[\"raw-aura\"]"));JsonObject concealed=projection.projectCoreCombat(raw,priorityPrompt(),true);shape(concealed);check(!concealed.toString().contains("PRIVATE_ATTACHMENT") && !concealed.toString().contains("raw-aura"));check(concealed.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("attachments")));
    }
    static void commanderProjectionChecks() throws Exception {
        nativeCommanderTerminalChecks();
        JsonObject raw=attackState(),prompt=priorityPrompt();raw.add("priority_player",raw.get("active_player"));JsonObject human=raw.getAsJsonArray("players").get(0).getAsJsonObject();JsonObject card=human.getAsJsonArray("battlefield").get(0).getAsJsonObject().deepCopy();card.addProperty("id","raw-commander");human.getAsJsonArray("command").add(card);raw.getAsJsonArray("playable").add("raw-commander");raw.getAsJsonObject("action_kinds").addProperty("raw-commander","cast_spell");
        raw.add("commander_metadata",JsonParser.parseString("[{\"id\":\"raw-commander\",\"owner\":\"raw-human\",\"name\":\"Public commander\",\"set\":\"M10\",\"number\":\"248\",\"plays\":1,\"tax\":\"{2}\",\"damage\":{\"raw-ai\":7}}]"));raw.addProperty("commander_metadata_complete",true);
        ManaforgeOpeningProjection projection=projection();JsonObject first=projection.projectCoreCombat(raw,prompt,true);shape(first);String reference=first.getAsJsonArray("commanders").get(0).getAsJsonObject().get("commander_id").getAsString();check(first.getAsJsonArray("objects").asList().stream().anyMatch(row->new JsonPrimitive("command").equals(row.getAsJsonObject().get("zone")) && new JsonPrimitive(reference).equals(row.getAsJsonObject().get("commander_id"))));check(!first.toString().contains("raw-commander"));check(!first.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("commander_metadata")));
        human.getAsJsonArray("command").remove(0);human.getAsJsonArray("battlefield").add(card);JsonObject second=projection.projectCoreCombat(raw,prompt,true);shape(second);check(reference.equals(second.getAsJsonArray("commanders").get(0).getAsJsonObject().get("commander_id").getAsString()));
        card.addProperty("owner_name","raw-name");card.addProperty("controller_name","raw-opponent-name");JsonObject controlled=projection.projectCoreCombat(raw,prompt,true);shape(controlled);check(controlled.getAsJsonArray("objects").asList().stream().anyMatch(row->{JsonObject value=row.getAsJsonObject();return new JsonPrimitive(reference).equals(value.get("commander_id")) && new JsonPrimitive("human").equals(value.get("owner_id")) && !value.get("owner_id").equals(value.get("controller_id"));}));card.addProperty("controller_name","raw-name");
        human.getAsJsonArray("battlefield").remove(human.getAsJsonArray("battlefield").size()-1);card.addProperty("exile_owner","raw-human");raw.getAsJsonArray("exile").add(card);JsonObject exiled=projection.projectCoreCombat(raw,prompt,true);shape(exiled);check(exiled.getAsJsonArray("objects").asList().stream().anyMatch(row->new JsonPrimitive("exile").equals(row.getAsJsonObject().get("zone")) && new JsonPrimitive(reference).equals(row.getAsJsonObject().get("commander_id"))));
        card.addProperty("hidden",true);card.addProperty("face_down",true);card.addProperty("name","CONCEALED_EXILE_SECRET");JsonObject concealed=projection.projectCoreCombat(raw,prompt,true);shape(concealed);check(!concealed.toString().contains("CONCEALED_EXILE_SECRET"));check(concealed.getAsJsonArray("unsupported_fields").contains(new JsonPrimitive("exile")));raw.getAsJsonArray("exile").remove(0);raw.getAsJsonArray("hand").add(card);JsonObject hidden=projection.projectCoreCombat(raw,prompt,true);shape(hidden);check(hidden.getAsJsonArray("objects").asList().stream().filter(row->new JsonPrimitive(true).equals(row.getAsJsonObject().get("hidden"))).allMatch(row->row.getAsJsonObject().get("commander_id").isJsonNull()));
        raw.getAsJsonArray("commander_metadata").get(0).getAsJsonObject().addProperty("plays",-1);fails("LIVE_OPENING_PROJECTION_UNSUPPORTED",()->projection().projectCoreCombat(raw,prompt,true));
    }
    static void nativeCommanderTerminalChecks() throws Exception {
        nativeCommanderTraceChecks();
        JsonObject metadata=JsonParser.parseString("{\"status\":\"finished\",\"outcome\":\"win\",\"viewer\":\"human\",\"commander_metadata_complete\":true,\"commanders\":[{\"owner\":\"human\",\"plays\":2,\"damage\":{\"opponent\":21}}],\"public_players\":[{\"id\":\"human\",\"life\":40,\"lost\":false},{\"id\":\"opponent\",\"life\":19,\"lost\":true}]}").getAsJsonObject();
        check(NativeCommanderProof.terminal(metadata,"human").get("native_commanders_cast").getAsInt()==1);
        JsonObject separate=metadata.deepCopy(),other=separate.getAsJsonArray("commanders").get(0).getAsJsonObject().deepCopy();separate.getAsJsonArray("commanders").get(0).getAsJsonObject().getAsJsonObject("damage").addProperty("opponent",20);other.getAsJsonObject("damage").addProperty("opponent",1);separate.getAsJsonArray("commanders").add(other);fails("COMMANDER_ACCEPTANCE_UNPROVEN",()->NativeCommanderProof.terminal(separate,"human"));
        for(int mode=0;mode<6;mode++){JsonObject bad=metadata.deepCopy();if(mode==0)bad.addProperty("status","ok");if(mode==1)bad.addProperty("viewer","other");if(mode==2)bad.getAsJsonArray("commanders").get(0).getAsJsonObject().addProperty("plays",0);if(mode==3)bad.getAsJsonArray("commanders").get(0).getAsJsonObject().getAsJsonObject("damage").addProperty("opponent",20);if(mode==4)bad.getAsJsonArray("public_players").get(1).getAsJsonObject().addProperty("life",0);if(mode==5)bad.addProperty("commander_metadata_complete",false);fails(mode==0 || mode==1 || mode==5?"COMMANDER_RESULT_UNPROVEN":"COMMANDER_ACCEPTANCE_UNPROVEN",()->NativeCommanderProof.terminal(bad,"human"));}
    }
    static void nativeCommanderTraceChecks() throws Exception {
        JsonObject state=attackState(),metadata=JsonParser.parseString("{\"status\":\"ok\",\"cycle\":8,\"objects\":{},\"commanders\":[{\"id\":\"raw-card\",\"owner\":\"raw-human\",\"name\":\"Sidisi, Undead Vizier\",\"plays\":1,\"tax\":\"{2}\"}]}").getAsJsonObject();
        NativeCommanderTrace trace=new NativeCommanderTrace("tax");trace.observe(state,metadata);fails("COMMANDER_SCENARIO_UNPROVEN",trace::proof);
        JsonObject prompt=prompt(),command=JsonParser.parseString("{\"kind\":\"boolean\",\"value\":true}").getAsJsonObject();trace.before(state,prompt,command);
        JsonObject seat=state.getAsJsonArray("players").get(0).getAsJsonObject(),card=seat.getAsJsonArray("battlefield").remove(0).getAsJsonObject();seat.getAsJsonArray("command").add(card);trace.observe(state,metadata);fails("COMMANDER_SCENARIO_UNPROVEN",trace::proof);
        seat.getAsJsonArray("command").remove(0);seat.getAsJsonArray("battlefield").add(card);metadata.getAsJsonArray("commanders").get(0).getAsJsonObject().addProperty("plays",2);trace.observe(state,metadata);fails("COMMANDER_SCENARIO_UNPROVEN",trace::proof);
        metadata.getAsJsonArray("commanders").get(0).getAsJsonObject().addProperty("tax","{4}");trace.observe(state,metadata);check(new JsonPrimitive(true).equals(trace.proof().get("native_commander_tax_verified")));check(!trace.stop());
    }
    static void presentationIdentityChecks() throws Exception {
        ManaforgeOpeningProjection projection=projection();JsonObject raw=state();
        JsonObject first=projection.project(raw,prompt());shape(first);
        String identity=first.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id").getAsString();
        String stale=choose(first,0);
        JsonObject second=projection.project(raw,prompt());shape(second);
        check(identity.equals(second.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id").getAsString()));
        check(!first.getAsJsonArray("objects").get(0).getAsJsonObject().get("object_id").equals(second.getAsJsonArray("objects").get(0).getAsJsonObject().get("object_id")));
        fails("STALE_REVISION",()->projection.claimBoolean(stale,"session","human","raw-game","raw-human",41,8));
        JsonObject oldDecision=JsonParser.parseString(stale).getAsJsonObject();oldDecision.getAsJsonObject("body").add("revision",second.get("revision"));
        fails("STALE_DECISION",()->projection.claimBoolean(oldDecision.toString(),"session","human","raw-game","raw-human",41,8));
        JsonObject row=raw.getAsJsonArray("hand").get(0).getAsJsonObject();row.addProperty("hidden",true);
        JsonObject hidden=projection.project(raw,prompt());shape(hidden);check(hidden.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id").isJsonNull());
        row.addProperty("hidden",false);JsonObject revealed=projection.project(raw,prompt());shape(revealed);
        String fresh=revealed.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id").getAsString();check(!identity.equals(fresh));
        JsonObject removed=raw.getAsJsonArray("hand").remove(0).getAsJsonObject();projection.project(raw,prompt());raw.getAsJsonArray("hand").add(removed);
        JsonObject returned=projection.project(raw,prompt());shape(returned);check(!fresh.equals(returned.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id").getAsString()));
        JsonObject other=projection().project(raw,prompt());check(!returned.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id").equals(other.getAsJsonArray("objects").get(0).getAsJsonObject().get("presentation_id")));
    }
    static void revealObservationChecks() throws Exception {
        ManaforgeOpeningProjection projection=projection();JsonObject raw=state();
        JsonObject row=new JsonObject();row.addProperty("observation_id","observation-one");row.addProperty("group_id","reveal-one");row.addProperty("group_label","Revealed cards");row.addProperty("source","revealed");row.addProperty("hidden",false);row.addProperty("name","Forest");
        JsonArray observations=new JsonArray();observations.add(row);JsonObject hidden=row.deepCopy();hidden.addProperty("hidden",true);hidden.addProperty("observation_id","hidden");hidden.addProperty("name","SECRET");observations.add(hidden);raw.add("observations",observations);
        JsonObject first=projection.project(raw,prompt());shape(first);check(first.getAsJsonArray("observations").size()==1);check(!first.toString().contains("SECRET"));
        check(projection.project(raw,prompt()).getAsJsonArray("observations").size()==1);
        raw.add("observations",new JsonArray());check(projection.project(raw,prompt()).getAsJsonArray("observations").size()==1);
        row=row.deepCopy();row.addProperty("observation_id","observation-two");row.addProperty("group_id","reveal-two");raw.getAsJsonArray("observations").add(row);
        check(projection.project(raw,prompt()).getAsJsonArray("observations").size()==2);
    }
    static void targetingPresentationChecks() throws Exception {
        JsonObject raw=attackState(),prompt=priorityPrompt();prompt.addProperty("kind","GAME_TARGET");prompt.addProperty("is_priority",false);prompt.add("targets",JsonParser.parseString("[\"raw-human\",\"raw-card\"]"));
        JsonObject context=new JsonObject();context.addProperty("source","raw-card");context.addProperty("minimum",1);context.addProperty("maximum",2);context.add("selected",JsonParser.parseString("[{\"id\":\"raw-human\",\"amount\":2},{\"id\":\"PRIVATE_REMOVED_TARGET\"}]"));prompt.add("targeting_context",context);
        JsonObject snapshot=projection().projectCoreCombat(raw,prompt);shape(snapshot);JsonObject projected=snapshot.getAsJsonObject("decision").getAsJsonObject("targeting");
        check(projected!=null && !projected.get("complete").getAsBoolean() && projected.getAsJsonArray("selected").size()==1);check("human".equals(projected.getAsJsonArray("selected").get(0).getAsJsonObject().get("player_id").getAsString()));check(!snapshot.toString().contains("PRIVATE_REMOVED_TARGET") && !snapshot.toString().contains("raw-card"));
        prompt.remove("targeting_context");check(projection().projectCoreCombat(raw,prompt).getAsJsonObject("decision").get("targeting").isJsonNull());
        JsonObject stack=raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().deepCopy();stack.addProperty("id","raw-stack");stack.addProperty("stack_controller","raw-human");stack.addProperty("stack_owner","raw-human");stack.add("stack_targets",JsonParser.parseString("[\"raw-human\",\"PRIVATE_REMOVED_TARGET\",\"raw-human\"]"));stack.addProperty("stack_targets_complete",false);raw.getAsJsonArray("stack").add(stack);
        snapshot=projection().projectCoreCombat(raw,prompt);shape(snapshot);JsonObject relationship=snapshot.getAsJsonArray("stack_targets").get(0).getAsJsonObject();check(relationship.getAsJsonArray("targets").size()==2 && !relationship.get("complete").getAsBoolean());check(!snapshot.toString().contains("PRIVATE_REMOVED_TARGET"));
    }
    public static void main(String[] args) throws Exception {
        presentationIdentityChecks();
        UnityPriorityProjectionChecks.run();
        targetingPresentationChecks();revealObservationChecks();nativeLaunchChecks();triggerOrderingProjectionChecks();publicStackAndOfferedCardChecks();playableExileChecks();automaticPaymentChecks();manualManaChecks();gameplaySessionChecks();combatCaseEvidenceChecks();coreCombatChecks();coreResponseChecks();terminalCombatChecks();coreChoiceChecks();combatCounterChecks();
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
        JsonObject baseState=state(),baseCard=baseState.getAsJsonArray("hand").get(0).getAsJsonObject();
        baseCard.addProperty("base_power","2");baseCard.addProperty("base_toughness","2");baseCard.addProperty("power","4");baseCard.addProperty("toughness","4");
        JsonObject baseView=projection().project(baseState,prompt());shape(baseView);
        JsonObject characteristics=baseView.getAsJsonArray("objects").get(0).getAsJsonObject().getAsJsonObject("characteristics");
        check("2".equals(characteristics.get("base_power").getAsString()) && "2".equals(characteristics.get("base_toughness").getAsString()));
        baseCard.addProperty("hidden",true);JsonObject hiddenBase=projection().project(baseState,prompt());shape(hiddenBase);
        check(hiddenBase.getAsJsonArray("objects").get(0).getAsJsonObject().get("characteristics").isJsonNull());
        genericSelectionChecks();sessionRequestChecks();pileChoiceChecks();emptyOptionalTargetChecks();choiceChecks();landChecks();abilityChecks();stackPriorityChecks();castCorrelationChecks();attackFinishChecks();attackerSelectionChecks();declaredAttackChecks();declaredPriorityChecks();combatDamageChecks();combatCleanupChecks();blockedDamageChecks();turnContinuationChecks();repeatedCombatChecks();combatEntryChecks();
        System.out.println("Opening projection: "+checks+" privacy, schema, isolation and fail-closed checks passed");
    }
}

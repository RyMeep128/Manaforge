import com.google.gson.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Diagnostic public fixture only. Java owns all game commands; no Unity/raw-state export. */
public final class ManaforgeLiveOpening {
    private final BlockingQueue<JsonObject> events = new ArrayBlockingQueue<>(512);
    private final AtomicBoolean overflow = new AtomicBoolean(), cancelled = new AtomicBoolean();
    private final ManaforgeBridge bridge = new ManaforgeBridge(event -> { if(!events.offer(event))overflow.set(true); });
    private final long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
    private JsonObject state, pending;
    private String engineViewer, artifactHash;
    private boolean firstLand;
    private byte[] unityKey;private java.nio.file.Path unityReady;
    private String game, stage="initialize", decisionKind="none";
    private JsonObject next() throws Exception {
        while(System.nanoTime()<deadline && !cancelled.get()) {
            if(overflow.get())throw new IOException("LIVE_OPENING_QUEUE_LIMIT");
            JsonObject event=events.poll(100,TimeUnit.MILLISECONDS);
            if(event==null)continue;
            String kind=event.get("event").getAsString();
            if(kind.equals("error") || kind.equals("disconnected"))throw new IOException("LIVE_OPENING_ENGINE_FAILED");
            if(kind.equals("game_started")){game=event.get("game_id").getAsString();engineViewer=event.get("player_id").getAsString();}
            if(kind.equals("game_state"))state=event;
            if(kind.equals("decision"))pending=event;
            return event;
        }
        throw new IOException("LIVE_OPENING_TIMEOUT_OR_CANCELLED");
    }
    private JsonObject command(String operation) {
        JsonObject value=new JsonObject();value.addProperty("protocol",1);
        value.addProperty("request_id",UUID.randomUUID().toString());value.addProperty("command",operation);return value;
    }
    private JsonObject request(JsonObject command,String expected) throws Exception {
        stage=command.get("command").getAsString();
        bridge.execute(command);
        while(true) {
            JsonObject event=next();
            if(event.get("event").getAsString().equals(expected) && event.has("request_id")
                && event.get("request_id").equals(command.get("request_id")))return event;
        }
    }
    private void advancement(long cycle,long decision) throws Exception {
        if(state!=null && state.get("cycle").getAsLong()>cycle)return;
        while(true){JsonObject follow=pending==null?next():pending;
            if(follow.get("event").getAsString().equals("decision")){if(follow.get("decision_id").getAsLong()>decision){pending=follow;return;}pending=null;}
            if(follow.get("event").getAsString().equals("game_state") && follow.get("cycle").getAsLong()>cycle)return;
        }
    }
    private void firstLand() throws Exception {
        stage="first_land";
        for(int count=0;count<80;count++) {
            JsonObject event=pending==null?next():pending;if(!event.get("event").getAsString().equals("decision"))continue;pending=null;
            if(!event.get("kind").getAsString().equals("GAME_SELECT") || !event.get("is_priority").getAsBoolean())throw new IOException("LIVE_LAND_UNSUPPORTED_DECISION");
            boolean land=false;for(JsonElement action:state.getAsJsonObject("action_kinds").entrySet().stream().map(Map.Entry::getValue).toArray(JsonElement[]::new))land|=action.getAsString().equals("play_land");
            if(!land) {
                // Explicit all-Forest diagnostic passing policy; never installed in product controls.
                JsonObject pass=command("respond");pass.addProperty("game_id",game);pass.add("decision_id",event.get("decision_id"));pass.addProperty("kind","boolean");pass.addProperty("value",false);request(pass,"response_sent");continue;
            }
            int beforeHand=state.getAsJsonArray("hand").size(),beforeBoard=0;
            for(JsonElement player:state.getAsJsonArray("players"))if(player.getAsJsonObject().get("id").getAsString().equals(engineViewer))beforeBoard=player.getAsJsonObject().getAsJsonArray("battlefield").size();
            Map<String,manaforge.protocol.PlayContracts.CardIdentity> bindings=new HashMap<>();manaforge.protocol.PlayContracts.CardIdentity identity=new manaforge.protocol.PlayContracts.CardIdentity();identity.printing_id="selected-forest";identity.deck_entry_id="forest";bindings.put("M10/248",identity);
            ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection(unityReady==null?"live-land":"live-opening","human",engineViewer,bindings);
            JsonObject snapshot=projection.project(state,event),body=new JsonObject(),envelope=new JsonObject();body.addProperty("fixture_only",false);body.add("snapshot",snapshot);envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","land");envelope.add("body",body);
            long cycle=state.get("cycle").getAsLong(),decision=event.get("decision_id").getAsLong();
            if(unityReady!=null) {
                final int handCount=beforeHand,boardCount=beforeBoard;
                ManaforgeUnityOpening.serve(envelope,projection,game,engineViewer,decision,cycle,"1.4.62-V1",artifactHash,unityKey,unityReady,
                    nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_LAND_REJECTED");advancement(cycle,decision);observeLand(handCount,boardCount);},cancelled::get);
                return;
            }
            ManaforgeOpeningLoopback.exchange(envelope,projection,game,engineViewer,decision,cycle,"1.4.62-V1",artifactHash,nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_LAND_REJECTED");},cancelled::get);
            advancement(cycle,decision);
            observeLand(beforeHand,beforeBoard);return;
        }
        throw new IOException("LIVE_LAND_TIMEOUT");
    }
    private void observeLand(int beforeHand,int beforeBoard) throws Exception {
            for(int observed=0;observed<40;observed++) {
                int board=0;for(JsonElement player:state.getAsJsonArray("players"))if(player.getAsJsonObject().get("id").getAsString().equals(engineViewer))board=player.getAsJsonObject().getAsJsonArray("battlefield").size();
                if(board==beforeBoard+1 && state.getAsJsonArray("hand").size()==beforeHand-1)return;
                next();
            }
            throw new IOException("LIVE_LAND_NOT_OBSERVED");
    }
    private void run(int port) throws Exception {
        JsonObject value=command("connect");value.addProperty("port",port);value.addProperty("username","mf_"+UUID.randomUUID().toString().substring(0,8));request(value,"connected");
        value=request(command("status"),"status");
        if(!value.get("engine_version").getAsString().equals("1.4.62-V1"))throw new IOException("LIVE_OPENING_PIN");
        value=command("create_game");value.addProperty("format","freeform");value.addProperty("seats",2);
        JsonArray controllers=new JsonArray();controllers.add("local_human");controllers.add("engine_ai");value.add("controllers",controllers);
        String table=request(value,"table_created").get("table_id").getAsString();
        for(boolean ai:new boolean[]{true,false}) {
            value=command("join_table");value.addProperty("table_id",table);
            if(ai){value.addProperty("controller","engine_ai");value.addProperty("player_name","Public fixture AI");}
            JsonArray cards=new JsonArray();
            for(String[] card:new String[][]{{"Forest","M10","248"},{"Memnite","SOM","174"}}) {
                if(firstLand && card[0].equals("Memnite"))continue;
                JsonObject entry=new JsonObject();entry.addProperty("name",card[0]);entry.addProperty("set",card[1]);entry.addProperty("number",card[2]);entry.addProperty("quantity",firstLand?60:30);cards.add(entry);
            }
            value.add("cards",cards);request(value,"joined");
        }
        value=command("start_game");value.addProperty("table_id",table);request(value,"started");
        stage="opening_decision";
        int pregame=0;
        while(true) {
            JsonObject event=pending==null?next():pending;
            if(!event.get("event").getAsString().equals("decision"))continue;
            pending=null;
            if(state!=null && game!=null && state.getAsJsonArray("hand").size()==7 && state.getAsJsonArray("players").size()==2) {
                Map<String,manaforge.protocol.PlayContracts.CardIdentity> bindings=new HashMap<>();
                for(String[] printing:new String[][]{{"M10/248","selected-forest","forest"},{"SOM/174","selected-memnite","memnite"}}) {
                    manaforge.protocol.PlayContracts.CardIdentity identity=new manaforge.protocol.PlayContracts.CardIdentity();
                    identity.printing_id=printing[1];identity.deck_entry_id=printing[2];bindings.put(printing[0],identity);
                }
                ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection("live-opening","human",engineViewer,bindings);
                JsonObject snapshot=projection.project(state,event);
                JsonObject body=new JsonObject();body.addProperty("fixture_only",false);body.add("snapshot",snapshot);
                JsonObject envelope=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","live-opening");envelope.add("body",body);
                manaforge.protocol.ReceiveMessages.parse(envelope.toString(),"live-opening","human",1,false);
                if(snapshot.getAsJsonArray("objects").size()!=7)throw new IOException("LIVE_OPENING_PROJECTION_FAILED");
                long previousCycle=state.get("cycle").getAsLong(),previousDecision=event.get("decision_id").getAsLong();
                if(unityReady!=null && !firstLand) {
                    ManaforgeUnityOpening.serve(envelope,projection,game,engineViewer,previousDecision,previousCycle,"1.4.62-V1",artifactHash,unityKey,unityReady,
                        nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_OPENING_RESPONSE_REJECTED");advancement(previousCycle,previousDecision);},cancelled::get);
                } else {
                    ManaforgeOpeningLoopback.exchangeChoice(envelope,projection,game,engineViewer,previousDecision,previousCycle,"1.4.62-V1",artifactHash,
                        nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_OPENING_RESPONSE_REJECTED");},cancelled::get,!firstLand);
                    advancement(previousCycle,previousDecision);
                    if(firstLand)firstLand();
                }
                projection.invalidateDecision();return;
            }
            // Explicit public fixture policy ONLY: respond to engine-offered pregame choices.
            if(++pregame>4)throw new IOException("LIVE_OPENING_UNSUPPORTED_PREGAME");
            value=command("respond");value.addProperty("game_id",game);value.add("decision_id",event.get("decision_id"));
            String kind=event.get("kind").getAsString();decisionKind=kind;
            if(kind.equals("GAME_ASK")){value.addProperty("kind","boolean");value.addProperty("value",true);}
            else if(kind.equals("GAME_CHOOSE_CHOICE") && event.has("choices") && event.get("choices").isJsonArray() && event.getAsJsonArray("choices").size()>0) {
                value.addProperty("kind","string");value.add("value",event.getAsJsonArray("choices").get(0));
            } else if(kind.equals("GAME_CHOOSE_CHOICE") && event.has("key_choices") && event.get("key_choices").isJsonObject() && event.getAsJsonObject("key_choices").size()>0) {
                value.addProperty("kind","string");value.addProperty("value",event.getAsJsonObject("key_choices").entrySet().iterator().next().getKey());
            } else if(kind.equals("GAME_TARGET") && state!=null && state.getAsJsonArray("hand").size()==0 && event.has("targets") && event.get("targets").isJsonArray()) {
                String selected=null;
                for(JsonElement target:event.getAsJsonArray("targets"))for(JsonElement player:state.getAsJsonArray("players"))
                    if(target.equals(player.getAsJsonObject().get("id")))selected=target.getAsString();
                if(selected==null)throw new IOException("LIVE_OPENING_UNSUPPORTED_PREGAME");
                value.addProperty("kind","object");value.addProperty("value",selected);
            } else throw new IOException("LIVE_OPENING_UNSUPPORTED_PREGAME");
            request(value,"response_sent");
        }
    }
    public static void main(String[] args) {
        PrintStream report=System.out;System.setOut(System.err);
        ManaforgeLiveOpening probe=new ManaforgeLiveOpening();
        int result=2;
        try {
            if((args.length==3 && args[2].equals("--first-land")) || (args.length==4 && args[3].equals("--first-land")))probe.firstLand=true;
            if((args.length==3 && !probe.firstLand) || args.length==4){
                probe.unityKey=ManaforgeUnityOpening.readBootstrap(System.in);
                probe.unityReady=java.nio.file.Paths.get(args[2]);
            }
        }catch(Exception failure){report.println("{\"failure\":\"LIVE_OPENING_BOOTSTRAP_FAILED\"}");System.exit(2);}

        Thread lifeline=new Thread(() -> {try{while(System.in.read()!=-1){} }catch(IOException ignored){}probe.cancelled.set(true);},"live-opening-owner");lifeline.setDaemon(true);lifeline.start();
        try {
            if((args.length!=2 && args.length!=3 && args.length!=4) || (args.length==4 && !probe.firstLand) || !args[1].matches("[0-9a-f]{64}"))throw new IOException();probe.artifactHash=args[1];int port=Integer.parseInt(args[0]);if(port<1 || port>65535)throw new IOException();
            probe.run(port);
            report.println(("{\"live_engine\":true,\"java_game_commands\":true,\"human_ai_seats\":true,\"opening_hand_count\":7,\"decision_received\":true,\"unity_connected\":false,\"public_projection_validated\":true,\"public_choice_submitted\":true,\"engine_advanced\":true,\"duplicate_native_submission_prevented\":true,\"authenticated_choice\":true,\"duplicate_receipt_reused\":true,\"disconnect_uncertainty_retained\":true}").replace("}",probe.firstLand?",\"first_land_observed\":true}":"}").replace("\"unity_connected\":false","\"unity_connected\":"+(probe.unityReady!=null)).replace("\"duplicate_receipt_reused\":true","\"duplicate_receipt_reused\":"+(probe.unityReady==null)).replace("\"duplicate_native_submission_prevented\":true","\"duplicate_native_submission_prevented\":"+(probe.unityReady==null)));result=0;
        }catch(Exception failure){JsonObject error=new JsonObject();error.addProperty("failure","LIVE_OPENING_FAILED");error.addProperty("stage",probe.stage);
            if(Arrays.asList("LIVE_OPENING_UNSUPPORTED_PREGAME","LIVE_OPENING_TIMEOUT_OR_CANCELLED","LIVE_OPENING_ENGINE_FAILED","LIVE_OPENING_QUEUE_LIMIT","LIVE_OPENING_PIN").contains(failure.getMessage()))error.addProperty("code",failure.getMessage());
            if(Arrays.asList("GAME_ASK","GAME_CHOOSE_CHOICE","GAME_TARGET","GAME_SELECT").contains(probe.decisionKind))error.addProperty("decision_family",probe.decisionKind);
            report.println(error.toString());}
        finally{probe.bridge.execute(probe.command("shutdown"));if(probe.unityKey!=null)Arrays.fill(probe.unityKey,(byte)0);}
        System.exit(result);
    }
}

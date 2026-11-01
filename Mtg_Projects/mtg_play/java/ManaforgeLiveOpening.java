import com.google.gson.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Diagnostic public fixture only. Java owns all game commands; no Unity/raw-state export. */
public final class ManaforgeLiveOpening {
    private static Map<String,manaforge.protocol.PlayContracts.CardIdentity> fixturePrintings() {
        Map<String,manaforge.protocol.PlayContracts.CardIdentity> result=new HashMap<>();
        for(String[] row:new String[][]{{"M10/248","3156ba12-cf21-48a5-aa08-74b447cafc2c","b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6","forest"},{"SOM/174","469cc4e0-49c0-4009-97ea-28e44addec69","7663ac7c-1de3-4250-b96a-fae9dbd66a27","memnite"}}) {
            manaforge.protocol.PlayContracts.CardIdentity identity=new manaforge.protocol.PlayContracts.CardIdentity();identity.printing_id=row[1];identity.oracle_id=row[2];identity.deck_entry_id=row[3];result.put(row[0],identity);
        }
        return result;
    }
    private static Map<String,manaforge.protocol.PlayContracts.CardIdentity> artworkPrintings() {
        Map<String,manaforge.protocol.PlayContracts.CardIdentity> result=new HashMap<>();
        for(String[] row:new String[][]{{"M21/272","3279314f-d639-4489-b2ab-3621bb3ca64b","b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6","forest"},{"M15/223","ee98e86c-ac16-4159-8982-ed14d282811a","a3a98bc9-caa0-49b7-951c-fe4e4f54e4ba","ornithopter"}}) {
            manaforge.protocol.PlayContracts.CardIdentity identity=new manaforge.protocol.PlayContracts.CardIdentity();identity.printing_id=row[1];identity.oracle_id=row[2];identity.deck_entry_id=row[3];result.put(row[0],identity);
        }
        return result;
    }
    private final boolean artworkOpening=Boolean.getBoolean("manaforge.artworkOpening");
    private final BlockingQueue<JsonObject> events = new ArrayBlockingQueue<>(512);
    private final AtomicBoolean overflow = new AtomicBoolean(), cancelled = new AtomicBoolean();
    private final ManaforgeBridge bridge = new ManaforgeBridge(event -> { if(!events.offer(event))overflow.set(true); });
    private final long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
    private JsonObject state, pending;
    private String engineViewer, artifactHash;
    private boolean firstLand,landObserved,unityPriorityPass,firstCreature,castAbilityMatched;
    private byte[] unityKey;private java.nio.file.Path unityReady;
    private byte[] metadataKey;private java.nio.file.Path metadataContext;
    private ManaforgeMetadataChannel.Client metadataClient;private boolean metadataSourceMatched,metadataInstanceMatched;
    private JsonObject sourceMetadata(JsonObject view,String source) throws Exception {
        for(int attempt=0;attempt<40 && System.nanoTime()<deadline;attempt++) {
            JsonObject query=new JsonObject();query.addProperty("command","metadata");query.addProperty("game",game);query.addProperty("player",engineViewer);query.add("cycle",view.get("cycle").deepCopy());
            JsonArray ids=new JsonArray();ids.add(source);query.add("object_ids",ids);query.add("identified_ids",ids.deepCopy());JsonObject result=metadataClient.read(query);
            if(new JsonPrimitive("ok").equals(result.get("status")))return result;
            if(!new JsonPrimitive("retry").equals(result.get("status")))throw new IOException("NATIVE_SOURCE_METADATA_UNAVAILABLE");
            Thread.sleep(25);
        }
        throw new IOException("NATIVE_SOURCE_METADATA_TIMEOUT");
    }
    private void startLifeline() {
        Thread lifeline=new Thread(() -> {try{while(System.in.read()!=-1){} }catch(IOException ignored){}cancelled.set(true);},"live-opening-owner");lifeline.setDaemon(true);lifeline.start();
    }
    private void initializeMetadata() throws Exception {
        if(metadataContext==null || metadataClient!=null)return;
        JsonObject context=new JsonObject();context.addProperty("game",game);context.addProperty("player",engineViewer);
        java.nio.file.Path temporary=java.nio.file.Paths.get(metadataContext.toString()+".tmp");
        java.nio.file.Files.write(temporary,context.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8),java.nio.file.StandardOpenOption.CREATE_NEW);
        java.nio.file.Files.move(temporary,metadataContext,java.nio.file.StandardCopyOption.ATOMIC_MOVE);
        JsonObject address=manaforge.protocol.WireEnvelope.parseObject(manaforge.protocol.TextFrame.read(System.in));
        if(address.size()!=3 || !new JsonPrimitive("127.0.0.1").equals(address.get("host")) || !address.get("port").toString().matches("[0-9]+")
            || !address.get("session").isJsonPrimitive() || !address.getAsJsonPrimitive("session").isString())throw new IOException("METADATA_BOOTSTRAP_INVALID");
        metadataClient=ManaforgeMetadataChannel.connect(Integer.parseInt(address.get("port").getAsString()),address.get("session").getAsString(),metadataKey,game,engineViewer,"1.4.62-V1",artifactHash);
        Arrays.fill(metadataKey,(byte)0);startLifeline();
    }
    private void verifyStackSource(NativeCastCorrelation correlation,String selectedAbility) throws Exception {
        if(metadataClient==null)return;
        for(int attempt=0;attempt<40 && System.nanoTime()<deadline;attempt++) {
            JsonObject query=new JsonObject();query.addProperty("command","metadata");query.addProperty("game",game);query.addProperty("player",engineViewer);query.add("cycle",state.get("cycle").deepCopy());
            JsonArray objects=new JsonArray();for(JsonElement card:state.getAsJsonArray("stack"))objects.add(card.getAsJsonObject().get("id").deepCopy());query.add("object_ids",objects);query.add("identified_ids",objects.deepCopy());
            JsonObject result=metadataClient.read(query);
            if(correlation.matchesStack(state,result)){
                metadataSourceMatched=true;if(!correlation.matchesStackInstance(state,result,selectedAbility))throw new IOException("NATIVE_CAST_INSTANCE_MISMATCH");
                JsonObject limited=query.deepCopy();limited.add("identified_ids",new JsonArray());JsonObject redacted=metadataClient.read(limited);
                if(!new JsonPrimitive("ok").equals(redacted.get("status")) || !state.get("cycle").equals(redacted.get("cycle")) || redacted.getAsJsonObject("objects").size()!=objects.size())throw new IOException("NATIVE_CAST_REDACTION_UNPROVEN");
                for(JsonElement object:redacted.getAsJsonObject("objects").entrySet().stream().map(Map.Entry::getValue).toArray(JsonElement[]::new))
                    if(object.getAsJsonObject().has("source_incarnation") || object.getAsJsonObject().has("spell_ability_ids"))throw new IOException("NATIVE_CAST_REDACTION_FAILED");
                metadataInstanceMatched=true;return;
            }
            if(!new JsonPrimitive("retry").equals(result.get("status")))throw new IOException("NATIVE_STACK_SOURCE_MISMATCH");
            if(!events.isEmpty())next();else Thread.sleep(25);
        }
        throw new IOException("NATIVE_STACK_METADATA_TIMEOUT");
    }
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
        boolean passed=false;
        for(int count=0;count<80;count++) {
            JsonObject event=pending==null?next():pending;if(!event.get("event").getAsString().equals("decision"))continue;pending=null;
            if(!event.get("kind").getAsString().equals("GAME_SELECT") || !event.get("is_priority").getAsBoolean())throw new IOException("LIVE_LAND_UNSUPPORTED_DECISION");
            boolean land=false;for(JsonElement action:state.getAsJsonObject("action_kinds").entrySet().stream().map(Map.Entry::getValue).toArray(JsonElement[]::new))land|=action.getAsString().equals("play_land");
            int beforeHand=state.getAsJsonArray("hand").size(),beforeBoard=0;
            for(JsonElement player:state.getAsJsonArray("players"))if(player.getAsJsonObject().get("id").getAsString().equals(engineViewer))beforeBoard=player.getAsJsonObject().getAsJsonArray("battlefield").size();
            Map<String,manaforge.protocol.PlayContracts.CardIdentity> bindings=fixturePrintings();
            ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection(unityReady==null?"live-land":"live-opening","human",engineViewer,bindings);
            JsonObject snapshot=projection.project(state,event,true),body=new JsonObject(),envelope=new JsonObject();body.addProperty("fixture_only",false);body.add("snapshot",snapshot);envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","land");envelope.add("body",body);
            long cycle=state.get("cycle").getAsLong(),decision=event.get("decision_id").getAsLong();
            if(!land || !passed) {
                // Public diagnostic explicitly passes one offered window before playing a land.
                ManaforgeOpeningLoopback.exchangeChoice(envelope,projection,game,engineViewer,decision,cycle,"1.4.62-V1",artifactHash,
                    nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_PRIORITY_REJECTED");},cancelled::get,false);
                advancement(cycle,decision);passed=true;continue;
            }
            if(unityReady!=null) {
                final int handCount=beforeHand,boardCount=beforeBoard;
                ManaforgeUnityOpening.serve(envelope,projection,game,engineViewer,decision,cycle,"1.4.62-V1",artifactHash,unityKey,unityReady,
                    nativeCommand->{boolean pass="boolean".equals(nativeCommand.get("kind").getAsString()) && !nativeCommand.get("value").getAsBoolean();
                        JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_LAND_REJECTED");advancement(cycle,decision);
                        if(pass)unityPriorityPass=true;else observeLand(handCount,boardCount);},cancelled::get);
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
                if(board==beforeBoard+1 && state.getAsJsonArray("hand").size()==beforeHand-1){landObserved=true;return;}
                next();
            }
            throw new IOException("LIVE_LAND_NOT_OBSERVED");
    }
    private void firstCreature() throws Exception {
        for(int count=0;count<80;count++) {
            JsonObject event=pending==null?next():pending;if(!event.get("event").getAsString().equals("decision"))continue;pending=null;
            if(!event.get("kind").getAsString().equals("GAME_SELECT") || !event.get("is_priority").getAsBoolean())throw new IOException("LIVE_CAST_UNSUPPORTED_DECISION");
            ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection(unityReady==null?"live-cast":"live-opening","human",engineViewer,fixturePrintings());
            JsonObject snapshot=projection.project(state,event,true,true),body=new JsonObject(),envelope=new JsonObject();
            body.addProperty("fixture_only",false);body.add("snapshot",snapshot);envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","cast");envelope.add("body",body);
            boolean cast=false;for(JsonElement action:snapshot.getAsJsonArray("actions"))cast|=action.getAsJsonObject().get("kind").getAsString().equals("cast_spell");
            int hand=state.getAsJsonArray("hand").size();long cycle=state.get("cycle").getAsLong(),decision=event.get("decision_id").getAsLong();
            final JsonObject beforeCast=state.deepCopy();final NativeCastCorrelation[] correlation=new NativeCastCorrelation[1];final String[] selectedAbility=new String[1];
            ManaforgeOpeningLoopback.exchangeChoice(envelope,projection,game,engineViewer,decision,cycle,"1.4.62-V1",artifactHash,
                nativeCommand->{if("object".equals(nativeCommand.get("kind").getAsString())){correlation[0]=NativeCastCorrelation.capture(beforeCast,event,nativeCommand);if(correlation[0]==null)throw new IOException("LIVE_CAST_CORRELATION_UNAVAILABLE");
                        if(metadataClient!=null){correlation[0]=correlation[0].withSourceMetadata(sourceMetadata(beforeCast,nativeCommand.get("value").getAsString()));if(correlation[0]==null)throw new IOException("NATIVE_CAST_SOURCE_UNBOUND");}}
                    JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_CAST_REJECTED");},cancelled::get,cast,"cast_spell");
            stage="creature_advancement";advancement(cycle,decision);if(!cast)continue;
            stage="creature_stack";boolean abilitySubmitted=false;
            for(int observed=0;observed<40;observed++) {
                if(state.getAsJsonArray("hand").size()==hand-1 && state.getAsJsonArray("stack").size()==1
                    && "Memnite".equals(state.getAsJsonArray("stack").get(0).getAsJsonObject().get("name").getAsString())){verifyStackSource(correlation[0],selectedAbility[0]);resolveCreature(projection,body,envelope,hand-1);return;}
                if(pending!=null && "GAME_CHOOSE_ABILITY".equals(pending.get("kind").getAsString())) {
                    if(abilitySubmitted || pending.getAsJsonObject("key_choices").size()!=1)throw new IOException("LIVE_CAST_UNSUPPORTED_ABILITY");
                    JsonObject ability=pending;pending=null;body.add("snapshot",projection.project(state,ability,false,true));
                    if(correlation[0]==null || !correlation[0].matches(state,ability))throw new IOException("LIVE_CAST_ABILITY_MISMATCH");
                    castAbilityMatched=true;
                    long abilityCycle=state.get("cycle").getAsLong(),abilityDecision=ability.get("decision_id").getAsLong();
                    if(unityReady!=null) {
                        ManaforgeUnityOpening.serve(envelope,projection,game,engineViewer,abilityDecision,abilityCycle,"1.4.62-V1",artifactHash,unityKey,unityReady,
                            nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_CAST_ABILITY_REJECTED");
                                advancement(abilityCycle,abilityDecision);observeCreatureStack(hand-1);},cancelled::get);
                        return;
                    }
                    ManaforgeOpeningLoopback.exchangeChoice(envelope,projection,game,engineViewer,abilityDecision,abilityCycle,"1.4.62-V1",artifactHash,
                        nativeCommand->{selectedAbility[0]=nativeCommand.get("value").getAsString();JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_CAST_ABILITY_REJECTED");},cancelled::get,true,"cast_spell");
                    advancement(abilityCycle,abilityDecision);abilitySubmitted=true;continue;
                }
                next();
            }
            throw new IOException("LIVE_CAST_NOT_OBSERVED");
        }
        throw new IOException("LIVE_CAST_TIMEOUT");
    }
    private void observeCreatureStack(int expectedHand) throws Exception {
        for(int observed=0;observed<40;observed++) {
            if(state.getAsJsonArray("hand").size()==expectedHand && state.getAsJsonArray("stack").size()==1
                && "Memnite".equals(state.getAsJsonArray("stack").get(0).getAsJsonObject().get("name").getAsString())) {
                return;
            }
            next();
        }
        throw new IOException("LIVE_CAST_NOT_OBSERVED");
    }
    private void resolveCreature(ManaforgeOpeningProjection projection,JsonObject body,JsonObject envelope,int expectedHand) throws Exception {
        stage="creature_resolution";
        for(int count=0;count<80;count++) {
            if(state.getAsJsonArray("stack").size()==0 && state.getAsJsonArray("hand").size()==expectedHand) {
                for(JsonElement player:state.getAsJsonArray("players"))if(engineViewer.equals(player.getAsJsonObject().get("id").getAsString())) {
                    int creatures=0;
                    for(JsonElement item:player.getAsJsonObject().getAsJsonArray("battlefield")) {
                        JsonObject card=item.getAsJsonObject();
                        if(!card.get("hidden").getAsBoolean() && !card.get("face_down").getAsBoolean() && "Memnite".equals(card.get("name").getAsString())
                            && "1".equals(card.get("power").getAsString()) && "1".equals(card.get("toughness").getAsString()))creatures++;
                    }
                    if(creatures==1)return;
                }
            }
            JsonObject event=pending==null?next():pending;if(!event.get("event").getAsString().equals("decision"))continue;pending=null;
            body.add("snapshot",projection.projectPriorityWithoutStack(state,event));
            long cycle=state.get("cycle").getAsLong(),decision=event.get("decision_id").getAsLong();
            ManaforgeOpeningLoopback.exchangeChoice(envelope,projection,game,engineViewer,decision,cycle,"1.4.62-V1",artifactHash,
                nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_RESOLUTION_PASS_REJECTED");},cancelled::get,false);
            advancement(cycle,decision);
        }
        throw new IOException("LIVE_CREATURE_NOT_RESOLVED");
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
            for(String[] card:artworkOpening?new String[][]{{"Forest","M21","272"},{"Ornithopter","M15","223"}}:new String[][]{{"Forest","M10","248"},{"Memnite","SOM","174"}}) {
                if(firstCreature && !card[0].equals(ai?"Forest":"Memnite"))continue;
                if(firstLand && card[0].equals("Memnite"))continue;
                JsonObject entry=new JsonObject();entry.addProperty("name",card[0]);entry.addProperty("set",card[1]);entry.addProperty("number",card[2]);entry.addProperty("quantity",firstLand || firstCreature?60:30);cards.add(entry);
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
                initializeMetadata();
                Map<String,manaforge.protocol.PlayContracts.CardIdentity> bindings=artworkOpening?artworkPrintings():fixturePrintings();
                ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection("live-opening","human",engineViewer,bindings);
                JsonObject snapshot=projection.project(state,event);
                JsonObject body=new JsonObject();body.addProperty("fixture_only",false);body.add("snapshot",snapshot);
                JsonObject envelope=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","live-opening");envelope.add("body",body);
                manaforge.protocol.ReceiveMessages.parse(envelope.toString(),"live-opening","human",1,false);
                if(snapshot.getAsJsonArray("objects").size()!=7)throw new IOException("LIVE_OPENING_PROJECTION_FAILED");
                long previousCycle=state.get("cycle").getAsLong(),previousDecision=event.get("decision_id").getAsLong();
                if(unityReady!=null && !firstLand && !firstCreature) {
                    ManaforgeUnityOpening.serve(envelope,projection,game,engineViewer,previousDecision,previousCycle,"1.4.62-V1",artifactHash,unityKey,unityReady,
                        nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_OPENING_RESPONSE_REJECTED");advancement(previousCycle,previousDecision);},cancelled::get);
                } else {
                    ManaforgeOpeningLoopback.exchangeChoice(envelope,projection,game,engineViewer,previousDecision,previousCycle,"1.4.62-V1",artifactHash,
                        nativeCommand->{JsonObject sent=request(nativeCommand,"response_sent");if(!sent.get("accepted").getAsBoolean())throw new IOException("LIVE_OPENING_RESPONSE_REJECTED");},cancelled::get,!firstLand && !firstCreature);
                    advancement(previousCycle,previousDecision);
                    if(firstLand)firstLand();
                    if(firstCreature)firstCreature();
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
            if((args.length==3 && args[2].equals("--first-creature")) || (args.length==4 && args[3].equals("--first-creature")))probe.firstCreature=true;
            if((args.length==3 && args[2].equals("--first-land")) || (args.length==4 && args[3].equals("--first-land")))probe.firstLand=true;
            if((args.length==3 && !probe.firstLand && !probe.firstCreature) || args.length==4){
                probe.unityKey=ManaforgeUnityOpening.readBootstrap(System.in);
                probe.unityReady=java.nio.file.Paths.get(args[2]);
            }
            if(probe.artworkOpening && (probe.unityReady==null || probe.firstLand || probe.firstCreature))throw new IOException();
            if(System.getProperty("manaforge.metadataContext")!=null) {
                if(!probe.firstCreature || probe.unityReady!=null)throw new IOException();
                probe.metadataContext=java.nio.file.Paths.get(System.getProperty("manaforge.metadataContext"));
                JsonObject boot=manaforge.protocol.WireEnvelope.parseObject(manaforge.protocol.TextFrame.read(System.in));
                if(boot.size()!=2 || !boot.has("metadata_bootstrap_version") || !boot.get("metadata_bootstrap_version").toString().equals("1") || !boot.get("owner_key_hex").isJsonPrimitive()
                    || !boot.getAsJsonPrimitive("owner_key_hex").isString() || !boot.get("owner_key_hex").getAsString().matches("[0-9a-f]{64}"))throw new IOException();
                probe.metadataKey=new byte[32];String hex=boot.get("owner_key_hex").getAsString();for(int i=0;i<32;i++)probe.metadataKey[i]=(byte)Integer.parseInt(hex.substring(i*2,i*2+2),16);
            }
        }catch(Exception failure){report.println("{\"failure\":\"LIVE_OPENING_BOOTSTRAP_FAILED\"}");System.exit(2);}

        if(probe.metadataContext==null)probe.startLifeline();
        try {
            if((args.length!=2 && args.length!=3 && args.length!=4) || (args.length==4 && !probe.firstLand && !probe.firstCreature) || !args[1].matches("[0-9a-f]{64}"))throw new IOException();probe.artifactHash=args[1];int port=Integer.parseInt(args[0]);if(port<1 || port>65535)throw new IOException();
            probe.run(port);
            report.println(("{\"live_engine\":true,\"java_game_commands\":true,\"human_ai_seats\":true,\"opening_hand_count\":7,\"decision_received\":true,\"unity_connected\":false,\"public_projection_validated\":true,\"public_choice_submitted\":true,\"engine_advanced\":true,\"duplicate_native_submission_prevented\":true,\"authenticated_choice\":true,\"duplicate_receipt_reused\":true,\"disconnect_uncertainty_retained\":true}").replace("}",probe.firstLand?",\"first_land_observed\":"+probe.landObserved+",\"priority_pass_submitted\":true,\"unity_priority_pass_submitted\":"+probe.unityPriorityPass+"}":"}").replace("}",probe.firstCreature?",\"creature_spell_on_stack\":true,\"native_cast_ability_matched\":"+probe.castAbilityMatched+",\"creature_resolved\":"+(probe.unityReady==null)+",\"unity_casting_ability_submitted\":"+(probe.unityReady!=null)+"}":"}").replace("}",probe.metadataContext!=null?",\"native_stack_source_matched\":"+probe.metadataSourceMatched+",\"native_cast_instance_matched\":"+probe.metadataInstanceMatched+"}":"}").replace("\"unity_connected\":false","\"unity_connected\":"+(probe.unityReady!=null)).replace("\"duplicate_receipt_reused\":true","\"duplicate_receipt_reused\":"+(probe.unityReady==null)).replace("\"duplicate_native_submission_prevented\":true","\"duplicate_native_submission_prevented\":"+(probe.unityReady==null)));result=0;
        }catch(Exception failure){JsonObject error=new JsonObject();error.addProperty("failure","LIVE_OPENING_FAILED");error.addProperty("stage",probe.stage);
            if(Arrays.asList("LIVE_OPENING_UNSUPPORTED_PREGAME","LIVE_OPENING_TIMEOUT_OR_CANCELLED","LIVE_OPENING_ENGINE_FAILED","LIVE_OPENING_QUEUE_LIMIT","LIVE_OPENING_PIN").contains(failure.getMessage()))error.addProperty("code",failure.getMessage());
            if(Arrays.asList("GAME_ASK","GAME_CHOOSE_CHOICE","GAME_TARGET","GAME_SELECT").contains(probe.decisionKind))error.addProperty("decision_family",probe.decisionKind);
            report.println(error.toString());}
        finally{probe.bridge.execute(probe.command("shutdown"));if(probe.unityKey!=null)Arrays.fill(probe.unityKey,(byte)0);if(probe.metadataKey!=null)Arrays.fill(probe.metadataKey,(byte)0);if(probe.metadataClient!=null)try{probe.metadataClient.close();}catch(IOException failure){result=2;}}
        System.exit(result);
    }
}

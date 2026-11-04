import com.google.gson.*;
import manaforge.protocol.PlayContracts.*;
import manaforge.protocol.WireMessages;
import java.io.IOException;
import java.util.*;

/** Early viewer projection: boolean openings and noncombat land offers. No rules or raw-state export. */
public final class ManaforgeOpeningProjection {
    private static final Gson JSON=new GsonBuilder().serializeNulls().create();
    private final String session, viewer, engineViewer;
    private final Map<String,CardIdentity> printings=new HashMap<>();
    private final Map<String,String> players=new HashMap<>();
    private final Map<String,String> stackReferences=new HashMap<>();
    private final Map<String,String> commanderReferences=new HashMap<>();
    static boolean completePriorityActions(JsonArray offered,Collection<String> projected) {
        Set<String> expected=new HashSet<>(),actual=new HashSet<>();
        for(JsonElement value:offered){if(!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString() || !expected.add(value.getAsString()))return false;}
        for(String value:projected)if(value!=null)actual.add(value);
        return expected.equals(actual);
    }
    public static final class ChoiceException extends IOException {
        public final String code;
        private ChoiceException(String code){super(code);this.code=code;}
    }
    private long revision;
    private final Set<String> knownCombatDefenders=new HashSet<>();
    private final Set<String> knownCombatants=new HashSet<>();
    private boolean coreCombat;private JsonObject numericPrompt;private final Set<String> stringOptions=new HashSet<>();
    private String decision, nativeGame;
    private Long nativeDecision, nativeCycle;
    private final Map<String,Boolean> options=new HashMap<>();
    private boolean consumed;
    private final Map<String,String> nativeActions=new HashMap<>();
    private final Map<String,String> nativeOptions=new HashMap<>();

    /** Trusted launch/session worker only. Authentication and receipt ledger remain external.
     * Claim is one-shot BEFORE native IO; an uncertain submission must never be replayed. */
    public synchronized JsonObject claimBoolean(String wire,String trustedSession,String trustedViewer,String currentGame,String currentEngineViewer,long currentNativeDecision,long currentNativeCycle) throws IOException {
        return claim(wire,trustedSession,trustedViewer,currentGame,currentEngineViewer,currentNativeDecision,currentNativeCycle,false);
    }
    public synchronized JsonObject claimAction(String wire,String trustedSession,String trustedViewer,String currentGame,String currentEngineViewer,long currentNativeDecision,long currentNativeCycle) throws IOException {
        return claim(wire,trustedSession,trustedViewer,currentGame,currentEngineViewer,currentNativeDecision,currentNativeCycle,true);
    }
    public synchronized JsonObject claimOperation(String wire,String trustedSession,String trustedViewer,String currentGame,String currentEngineViewer,long currentNativeDecision,long currentNativeCycle) throws IOException {
        JsonObject envelope=WireMessages.parse(wire),body=envelope.getAsJsonObject("body");String operation=body.get("operation").getAsString();if(!"choose_number".equals(operation) && !"choose_amounts".equals(operation))return "perform".equals(operation)?claimAction(wire,trustedSession,trustedViewer,currentGame,currentEngineViewer,currentNativeDecision,currentNativeCycle):claimBoolean(wire,trustedSession,trustedViewer,currentGame,currentEngineViewer,currentNativeDecision,currentNativeCycle);
        if(!session.equals(trustedSession))throw new ChoiceException("SESSION_MISMATCH");if(!viewer.equals(trustedViewer) || !engineViewer.equals(currentEngineViewer))throw new ChoiceException("VIEWER_MISMATCH");if(decision==null || consumed || numericPrompt==null || !Objects.equals(nativeGame,currentGame) || nativeDecision!=currentNativeDecision || nativeCycle!=currentNativeCycle)throw new ChoiceException("STALE_DECISION");String mismatch=WireMessages.checkBinding(wire,session,viewer,revision,decision);if(mismatch!=null)throw new ChoiceException(mismatch);JsonObject response;try{response=NativeCombatChoices.numericResponse(numericPrompt,body);}catch(RuntimeException invalid){throw new ChoiceException("ACTION_UNAVAILABLE");}response.addProperty("protocol",1);response.addProperty("command","respond");response.add("request_id",envelope.get("message_id").deepCopy());response.addProperty("game_id",nativeGame);response.addProperty("decision_id",nativeDecision);invalidateDecision();return response;
    }
    private JsonObject claim(String wire,String trustedSession,String trustedViewer,
            String currentGame,String currentEngineViewer,long currentNativeDecision,long currentNativeCycle,boolean action) throws IOException {
        if(!session.equals(trustedSession))throw new ChoiceException("SESSION_MISMATCH");
        if(!viewer.equals(trustedViewer) || !engineViewer.equals(currentEngineViewer))throw new ChoiceException("VIEWER_MISMATCH");
        if(decision==null || consumed || !Objects.equals(nativeGame,currentGame)
                || nativeDecision!=currentNativeDecision || nativeCycle!=currentNativeCycle)
            throw new ChoiceException("STALE_DECISION");
        String mismatch=WireMessages.checkBinding(wire,session,viewer,revision,decision);
        if(mismatch!=null)throw new ChoiceException(mismatch);
        JsonObject envelope=WireMessages.parse(wire),body=envelope.getAsJsonObject("body");
        String operation=body.get("operation").getAsString();
        if(action ? !operation.equals("perform") || !nativeActions.containsKey(body.get("action_id").getAsString())
                  : !operation.equals("choose") || !(options.containsKey(body.get("option_id").getAsString()) || nativeOptions.containsKey(body.get("option_id").getAsString())))throw new ChoiceException("ACTION_UNAVAILABLE");
        Boolean answer=action?null:options.get(body.get("option_id").getAsString());
        String source=action?nativeActions.get(body.get("action_id").getAsString()):nativeOptions.get(body.get("option_id").getAsString());
        boolean stringResponse=!action && stringOptions.contains(body.get("option_id").getAsString());consumed=true;options.clear();nativeActions.clear();nativeOptions.clear();stringOptions.clear();numericPrompt=null;
        JsonObject command=new JsonObject();command.addProperty("protocol",1);command.addProperty("command","respond");
        command.add("request_id",envelope.get("message_id").deepCopy());command.addProperty("game_id",nativeGame);
        boolean poolResponse=action && source!=null && source.startsWith("pool:");boolean objectResponse=source!=null;
        if(poolResponse){command.addProperty("decision_id",nativeDecision);command.addProperty("kind","mana_type");command.addProperty("value",source.substring(5).toUpperCase(Locale.ROOT));command.addProperty("player_id",engineViewer);return command;}
        command.addProperty("decision_id",nativeDecision);command.addProperty("kind",objectResponse?(stringResponse?"string":"object"):"boolean");if(objectResponse)command.addProperty("value",source);else command.addProperty("value",action?false:answer);
        return command;
    }
    public synchronized void invalidateDecision(){decision=null;nativeGame=null;nativeDecision=null;nativeCycle=null;options.clear();nativeActions.clear();nativeOptions.clear();stringOptions.clear();numericPrompt=null;consumed=true;}

    public ManaforgeOpeningProjection(String session,String viewer,String engineViewer,Map<String,CardIdentity> bindings) {
        this.session=session;this.viewer=viewer;this.engineViewer=engineViewer;
        for(Map.Entry<String,CardIdentity> entry:bindings.entrySet())
            printings.put(entry.getKey(),JSON.fromJson(JSON.toJson(entry.getValue()),CardIdentity.class));
    }
    /** Private authenticated metadata in; public stable commander references out. */
    private Set<String> projectCommanders(JsonObject raw,GameSnapshot result) throws IOException {
        Set<String> seen=new HashSet<>();if(!coreCombat || !raw.has("commander_metadata") || !Boolean.TRUE.equals(flag(raw,"commander_metadata_complete")))return seen;
        JsonArray roster=raw.getAsJsonArray("commander_metadata");require(roster.size()<=10);List<CommanderState> projected=new ArrayList<>();
        for(JsonElement item:roster){JsonObject row=item.getAsJsonObject();String id=row.get("id").getAsString(),owner=row.get("owner").getAsString();require(seen.add(id));CommanderState commander=new CommanderState();commander.owner_id=engineViewer.equals(owner)?viewer:players.get(owner);require(commander.owner_id!=null);commander.commander_id=commanderReferences.computeIfAbsent(id,key->opaque());commander.name=text(row,"name");commander.command_zone_plays=integer(row,"plays");require(commander.command_zone_plays==null || commander.command_zone_plays>=0);commander.additional_cast_cost=text(row,"tax");
            CardIdentity binding=printings.get((viewer.equals(commander.owner_id)?"":"opponent/")+text(row,"set")+"/"+text(row,"number"));if(binding!=null){commander.card_identity=JSON.fromJson(JSON.toJson(binding),CardIdentity.class);if(!viewer.equals(commander.owner_id))commander.card_identity.deck_entry_id=null;}
            if(row.has("damage")){List<JsonElement[]> damage=new ArrayList<>();for(Map.Entry<String,JsonElement> entry:row.getAsJsonObject("damage").entrySet()){String seat=engineViewer.equals(entry.getKey())?viewer:players.get(entry.getKey());require(seat!=null);JsonObject value=new JsonObject();value.add("count",entry.getValue());Long count=integer(value,"count");require(count!=null && count>=0);damage.add(new JsonElement[]{new JsonPrimitive(seat),new JsonPrimitive(count)});}commander.damage_dealt=damage.toArray(new JsonElement[0][]);}projected.add(commander);
        }result.commanders=projected.toArray(new CommanderState[0]);return seen;
    }
    private static JsonElement[][] counters(JsonObject row) throws IOException {
        require(row.get("counters").isJsonArray() && row.getAsJsonArray("counters").size()<=256);Set<String> names=new HashSet<>();for(JsonElement value:row.getAsJsonArray("counters")){require(value.isJsonArray() && value.getAsJsonArray().size()==2);JsonObject pair=new JsonObject();pair.add("name",value.getAsJsonArray().get(0));pair.add("count",value.getAsJsonArray().get(1));String name=text(pair,"name");Long count=integer(pair,"count");require(name!=null && names.add(name) && count!=null && count>=0 && count<=Integer.MAX_VALUE);}return JSON.fromJson(row.get("counters"),JsonElement[][].class);
    }
    private static GameObject visibleCard(List<GameObject> cards,String reference) {
        for(GameObject card:cards)if(card.object_id.equals(reference) && "battlefield".equals(card.zone) && Boolean.FALSE.equals(card.hidden) && Boolean.FALSE.equals(card.face_down))return card;return null;
    }
    private static String opaque(){return "mf-"+UUID.randomUUID().toString().replace("-","");}
    private static void require(boolean value) throws IOException {if(!value)throw new IOException("LIVE_OPENING_PROJECTION_UNSUPPORTED");}
    private static String text(JsonObject source,String key) throws IOException {
        JsonElement value=source.get(key);if(value==null || value.isJsonNull())return null;
        require(value.isJsonPrimitive() && value.getAsJsonPrimitive().isString());
        String result=value.getAsString();require(result.length()<=4096);
        return result.replaceAll("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}","[object]");
    }
    private static Long integer(JsonObject source,String key) throws IOException {
        JsonElement value=source.get(key);if(value==null || value.isJsonNull())return null;
        require(value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber() && value.getAsString().matches("-?[0-9]+"));
        try{return Long.valueOf(value.getAsString());}catch(NumberFormatException error){throw new IOException("LIVE_OPENING_PROJECTION_UNSUPPORTED");}
    }
    private static Boolean flag(JsonObject source,String key) throws IOException {
        JsonElement value=source.get(key);if(value==null || value.isJsonNull())return null;
        require(value.isJsonPrimitive() && value.getAsJsonPrimitive().isBoolean());return value.getAsBoolean();
    }
    private static void empty(JsonObject source,String key) throws IOException {
        require(source.has(key) && source.get(key).isJsonArray() && source.getAsJsonArray(key).size()==0);
    }
    public synchronized JsonObject project(JsonObject raw,JsonObject prompt) throws IOException {
        return project(raw,prompt,false);
    }
    /** Opt-in priority port; single-land Unity fixture still accepts a land only. */
    public synchronized JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass) throws IOException {
        return project(raw,prompt,includePriorityPass,false);
    }
    public synchronized JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells) throws IOException {
        return project(raw,prompt,includePriorityPass,includeSpells,false);
    }
    /** Explicit pass-only observation port. Stack contents remain unsupported and never serialized. */
    public synchronized JsonObject projectPriorityWithoutStack(JsonObject raw,JsonObject prompt) throws IOException {
        return project(raw,prompt,true,false,true);
    }
    /** A real priority-state observation with no command authority; used while a receipt is unresolved. */
    public synchronized JsonObject projectReadOnlyPriority(JsonObject raw,JsonObject prompt) throws IOException {
        invalidateDecision();
        require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")));
        require(raw.has("stack") && raw.get("stack").isJsonArray());
        JsonObject snapshot=project(raw,prompt,true,false,raw.getAsJsonArray("stack").size()>0);
        snapshot.add("decision",JsonNull.INSTANCE);snapshot.add("actions",new JsonArray());invalidateDecision();return snapshot;
    }
    /** Explicit native finish-selection response only; attacker/defender selection is not exposed. */
    public synchronized JsonObject projectAttackFinish(JsonObject raw,JsonObject prompt) throws IOException {
        return project(raw,prompt,false,false,false,true);
    }
    public synchronized JsonObject projectAttackSelection(JsonObject raw,JsonObject prompt) throws IOException {
        return project(raw,prompt,false,false,false,true,true);
    }
    private JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells,boolean omitStack) throws IOException {
        return project(raw,prompt,includePriorityPass,includeSpells,omitStack,false);
    }
    private JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells,boolean omitStack,boolean attackFinish) throws IOException {
        return project(raw,prompt,includePriorityPass,includeSpells,omitStack,attackFinish,false);
    }
    public synchronized JsonObject projectBlockedAttackPriority(JsonObject raw,JsonObject prompt) throws IOException {
        invalidateDecision();require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")) && raw.getAsJsonArray("combat").size()==1);
        JsonObject group=raw.getAsJsonArray("combat").get(0).getAsJsonObject();require(group.getAsJsonArray("blockers").size()==1 && Boolean.TRUE.equals(flag(group,"blocked")));
        return retainPriorityPass(project(raw,prompt,true,false,false,false,false,true,true));
    }
    public synchronized JsonObject projectDeclaredAttackPriority(JsonObject raw,JsonObject prompt) throws IOException {
        invalidateDecision();require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")));
        return retainPriorityPass(project(raw,prompt,true,false,false,false,false,true));
    }
    private JsonObject retainPriorityPass(JsonObject snapshot) throws IOException {
        JsonArray passes=new JsonArray();Set<String> retained=new HashSet<>();
        for(JsonElement item:snapshot.getAsJsonArray("actions")){JsonObject action=item.getAsJsonObject();if("pass".equals(action.get("kind").getAsString())){passes.add(action);retained.add(action.get("action_id").getAsString());}}
        require(passes.size()==1);snapshot.add("actions",passes);nativeActions.keySet().retainAll(retained);return snapshot;
    }
    public synchronized JsonObject projectReadOnlyDeclaredAttack(JsonObject raw,JsonObject prompt) throws IOException {
        invalidateDecision();require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")));
        JsonObject snapshot=project(raw,prompt,false,false,false,false,false,true);
        snapshot.add("decision",JsonNull.INSTANCE);snapshot.add("actions",new JsonArray());invalidateDecision();return snapshot;
    }
    public synchronized JsonObject projectSelectedAttackFinish(JsonObject raw,JsonObject prompt) throws IOException {
        return project(raw,prompt,false,false,false,true,false,true);
    }
    public synchronized JsonObject projectReadOnlyAttackAssignment(JsonObject raw,JsonObject prompt) throws IOException {
        JsonObject snapshot=project(raw,prompt,false,false,false,true,false,true);
        snapshot.add("decision",JsonNull.INSTANCE);snapshot.add("actions",new JsonArray());invalidateDecision();return snapshot;
    }
    private JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells,boolean omitStack,boolean attackFinish,boolean includeAttackers) throws IOException {
        return project(raw,prompt,includePriorityPass,includeSpells,omitStack,attackFinish,includeAttackers,false);
    }
    public synchronized JsonObject projectReadOnlyPostDeclaredPriority(JsonObject raw,JsonObject prompt) throws IOException {
        invalidateDecision();require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")));
        JsonObject snapshot=project(raw,prompt,false,false,false,false,false,true,true);
        snapshot.add("decision",JsonNull.INSTANCE);snapshot.add("actions",new JsonArray());invalidateDecision();return snapshot;
    }
    private JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells,boolean omitStack,boolean attackFinish,boolean includeAttackers,boolean combatObservation) throws IOException {
        return project(raw,prompt,includePriorityPass,includeSpells,omitStack,attackFinish,includeAttackers,combatObservation,false);
    }
    public synchronized JsonObject projectSingleTurnAttacker(JsonObject raw,JsonObject prompt,String source) throws IOException {
        JsonObject snapshot=projectTurnCombat(raw,prompt,true,false);JsonArray selected=new JsonArray();Set<String> retained=new HashSet<>();for(JsonElement item:snapshot.getAsJsonArray("actions")){JsonObject action=item.getAsJsonObject();String id=action.get("action_id").getAsString();if("declare_attacker".equals(action.get("kind").getAsString()) && source.equals(nativeActions.get(id))){selected.add(action);retained.add(id);}}require(selected.size()==1);snapshot.add("actions",selected);nativeActions.keySet().retainAll(retained);return snapshot;
    }
    public synchronized JsonObject projectNextTurnCast(JsonObject raw,JsonObject prompt) throws IOException {
        invalidateDecision();require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")));JsonObject snapshot=projectTurnContinuation(raw,prompt,true);JsonArray casts=new JsonArray();Set<String> retained=new HashSet<>();
        for(JsonElement item:snapshot.getAsJsonArray("actions")){JsonObject action=item.getAsJsonObject();if("cast_spell".equals(action.get("kind").getAsString())){casts.add(action);retained.add(action.get("action_id").getAsString());}}require(casts.size()>0);snapshot.add("actions",casts);nativeActions.keySet().retainAll(retained);return snapshot;
    }
    /** Terminal view has no decision authority; outcome comes exclusively from native terminal evidence. */
    public synchronized JsonObject projectCombatResult(JsonObject raw,String outcome) throws IOException {
        invalidateDecision();require(Arrays.asList("win","loss","draw").contains(outcome));JsonObject view=raw.deepCopy();String name=null;for(JsonElement item:view.getAsJsonArray("players"))if(engineViewer.equals(item.getAsJsonObject().get("id").getAsString()))name=item.getAsJsonObject().get("name").getAsString();require(name!=null);view.addProperty("priority_player",name);JsonObject prompt=new JsonObject();prompt.addProperty("kind","GAME_SELECT");prompt.addProperty("is_priority",true);prompt.add("cycle",view.get("cycle").deepCopy());prompt.addProperty("decision_id",0);prompt.addProperty("message","Game finished");
        JsonObject result=projectCoreCombat(view,prompt);result.addProperty("status","finished");result.addProperty("result",outcome);result.add("priority_player_id",JsonNull.INSTANCE);result.add("decision",JsonNull.INSTANCE);result.add("actions",new JsonArray());invalidateDecision();return result;
    }
    /** Native legal declarations/targets for either 1v1 seat; no client-side rules. */
    public synchronized JsonObject projectCoreCombat(JsonObject raw,JsonObject prompt) throws IOException {return projectCoreCombat(raw,prompt,false);}
    public synchronized JsonObject projectCoreCombat(JsonObject raw,JsonObject prompt,boolean spells) throws IOException {
        coreCombat=true;
        try {
            boolean priority="GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority"));
            boolean declaration="GAME_SELECT".equals(text(prompt,"kind")) && !priority && (prompt.has("attackers") ^ prompt.has("blockers"));
            return project(raw,prompt,priority,spells || "GAME_CHOOSE_ABILITY".equals(text(prompt,"kind")),false,declaration,true,raw.getAsJsonArray("combat").size()>0,true,true);
        } finally {coreCombat=false;}
    }
    public synchronized JsonObject projectTurnCombat(JsonObject raw,JsonObject prompt,boolean includeAttackers,boolean assignment) throws IOException {
        boolean priority="GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority"));
        return project(raw,prompt,priority,false,false,!priority,includeAttackers,assignment,false,true);
    }
    public synchronized JsonObject projectTurnContinuation(JsonObject raw,JsonObject prompt) throws IOException {
        return projectTurnContinuation(raw,prompt,false);
    }
    public synchronized JsonObject projectTurnContinuation(JsonObject raw,JsonObject prompt,boolean includeSpells) throws IOException {
        boolean omitStack="GAME_SELECT".equals(text(prompt,"kind")) && Boolean.TRUE.equals(flag(prompt,"is_priority")) && raw.getAsJsonArray("stack").size()>0;
        return project(raw,prompt,true,includeSpells,omitStack,false,false,false,false,true);
    }
    private JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells,boolean omitStack,boolean attackFinish,boolean includeAttackers,boolean combatObservation,boolean includeBlockers) throws IOException {
        return project(raw,prompt,includePriorityPass,includeSpells,omitStack,attackFinish,includeAttackers,combatObservation,includeBlockers,false);
    }
    private JsonObject project(JsonObject raw,JsonObject prompt,boolean includePriorityPass,boolean includeSpells,boolean omitStack,boolean attackFinish,boolean includeAttackers,boolean combatObservation,boolean includeBlockers,boolean turnMode) throws IOException {
        invalidateDecision();
        try {
            require(engineViewer.equals(raw.get("viewer").getAsString()));
            boolean priority="GAME_SELECT".equals(prompt.get("kind").getAsString()) && Boolean.TRUE.equals(flag(prompt,"is_priority"));
            boolean discard=turnMode && "GAME_TARGET".equals(text(prompt,"kind")) && "CLEANUP".equals(text(raw,"step")) && "END".equals(text(raw,"phase")) && raw.getAsJsonArray("hand").size()>7;
            boolean missingDefender=false,missingCombatant=false;
            boolean mana=coreCombat && "GAME_PLAY_MANA".equals(text(prompt,"kind"));
            boolean numeric=coreCombat && ("GAME_GET_AMOUNT".equals(text(prompt,"kind")) || "GAME_GET_MULTI_AMOUNT".equals(text(prompt,"kind")));
            boolean stringChoice=coreCombat && "GAME_CHOOSE_CHOICE".equals(text(prompt,"kind"));
            boolean targeting=coreCombat && "GAME_TARGET".equals(text(prompt,"kind")) && !discard;
            boolean blocking=coreCombat && attackFinish && prompt.has("blockers");
            boolean ability=includeSpells && "GAME_CHOOSE_ABILITY".equals(prompt.get("kind").getAsString());
            require(!omitStack || priority || coreCombat);
            require("GAME_ASK".equals(prompt.get("kind").getAsString()) || priority || ability || attackFinish || discard || targeting || numeric || stringChoice || mana);
            if(attackFinish)require("GAME_SELECT".equals(text(prompt,"kind")) && Boolean.FALSE.equals(flag(prompt,"is_priority"))
                && (blocking?prompt.has("blockers") && !prompt.has("attackers"):prompt.has("attackers") && !prompt.has("blockers")) && prompt.get(blocking?"blockers":"attackers").isJsonArray() && prompt.getAsJsonArray(blocking?"blockers":"attackers").size()<=256);
            require(!priority || (!prompt.has("attackers") && !prompt.has("blockers")));
            require(Objects.equals(integer(raw,"cycle"),integer(prompt,"cycle")) && integer(raw,"cycle")!=null);
            require(integer(prompt,"decision_id")!=null && integer(prompt,"decision_id")>=0 && integer(prompt,"decision_id")<=Integer.MAX_VALUE);
            require(raw.has("game_id") && !raw.get("game_id").isJsonNull());
            if(omitStack || coreCombat)require(raw.has("stack") && raw.get("stack").isJsonArray() && (coreCombat || raw.getAsJsonArray("stack").size()>0));else empty(raw,"stack");
            if(!coreCombat)empty(raw,"exile");if(!combatObservation)empty(raw,"combat");
            GameSnapshot result=new GameSnapshot();result.session_id=session;result.viewer_id=viewer;
            result.revision=revision+1;result.protocol_version=1L;result.status="active";
            result.turn=integer(raw,"turn");result.phase=text(raw,"phase");result.step=text(raw,"step");
            List<PlayerView> seats=new ArrayList<>();Map<String,String> names=new HashMap<>();Set<String> seen=new HashSet<>();
            boolean found=false;Map<String,String> seatNames=new HashMap<>();List<JsonObject> battlefield=new ArrayList<>();Map<JsonObject,String> exileOwners=new IdentityHashMap<>();Map<JsonObject,String> commandOwners=new IdentityHashMap<>();Map<JsonObject,String> graveOwners=new IdentityHashMap<>();
            for(JsonElement item:raw.getAsJsonArray("players")) {
                JsonObject row=item.getAsJsonObject();String id=row.get("id").getAsString();require(seen.add(id));
                boolean local=engineViewer.equals(id);found|=local;
                String publicId=local?viewer:players.computeIfAbsent(id,ignored->opaque());
                names.put(row.get("name").getAsString(),publicId);
                if(!priority && !ability && !attackFinish && !discard && !targeting && !coreCombat)empty(row,"battlefield");else for(JsonElement permanent:row.getAsJsonArray("battlefield"))battlefield.add(permanent.getAsJsonObject());
                if(turnMode){for(JsonElement graveItem:row.getAsJsonArray("graveyard"))graveOwners.put(graveItem.getAsJsonObject(),publicId);}else empty(row,"graveyard");if(coreCombat){for(JsonElement command:row.getAsJsonArray("command"))commandOwners.put(command.getAsJsonObject(),publicId);}else empty(row,"command");seatNames.put(row.get("name").getAsString(),publicId);
                PlayerView seat=new PlayerView();seat.player_id=publicId;seat.name=local?"You":"Player "+(seats.size()+1);
                seat.life=integer(row,"life");seat.hand_count=integer(row,"hand_count");seat.library_count=integer(row,"library_count");
                if(coreCombat && row.has("mana") && !row.get("mana").isJsonNull()){JsonArray pool=row.getAsJsonArray("mana");require(pool.size()<=6);Set<String> colors=new HashSet<>();for(JsonElement pair:pool){require(pair.isJsonArray() && pair.getAsJsonArray().size()==2);JsonObject value=new JsonObject();value.add("color",pair.getAsJsonArray().get(0));value.add("count",pair.getAsJsonArray().get(1));String color=text(value,"color");Long count=integer(value,"count");require(Arrays.asList("white","blue","black","red","green","colorless").contains(color) && colors.add(color) && count!=null && count>=0 && count<=Integer.MAX_VALUE);}seat.mana=JSON.fromJson(pool,JsonElement[][].class);}
                seat.left_game=flag(row,"left");seats.add(seat);
            }
            require(found && seats.size()>=2);
            result.players=seats.toArray(new PlayerView[0]);
            result.active_player_id=names.get(text(raw,"active_player"));result.priority_player_id=names.get(text(raw,"priority_player"));
            require(!(priority || ability) || viewer.equals(result.priority_player_id));
            require(!(attackFinish || discard) || (blocking?!viewer.equals(result.active_player_id):viewer.equals(result.active_player_id)));
            List<GameObject> cards=new ArrayList<>();Set<String> cardIds=new HashSet<>();
            List<JsonObject> displayed=new ArrayList<>();Set<JsonObject> stackRows=Collections.newSetFromMap(new IdentityHashMap<>());if(coreCombat)for(JsonElement item:raw.getAsJsonArray("stack")){displayed.add(item.getAsJsonObject());stackRows.add(item.getAsJsonObject());}Set<JsonObject> handRows=Collections.newSetFromMap(new IdentityHashMap<>());
            for(JsonElement item:raw.getAsJsonArray("hand")){displayed.add(item.getAsJsonObject());handRows.add(item.getAsJsonObject());}displayed.addAll(battlefield);displayed.addAll(graveOwners.keySet());displayed.addAll(commandOwners.keySet());
            if(coreCombat)for(JsonElement item:raw.getAsJsonArray("exile")){JsonObject row=item.getAsJsonObject();if(Boolean.FALSE.equals(flag(row,"hidden")) && Boolean.FALSE.equals(flag(row,"face_down")) && row.has("exile_owner")){String owner=row.get("exile_owner").getAsString(),seat=engineViewer.equals(owner)?viewer:players.get(owner);if(seat!=null){exileOwners.put(row,seat);displayed.add(row);}}}
            Set<String> commanderNativeIds=projectCommanders(raw,result);
            Map<String,String> visibleReferences=new HashMap<>();
            Set<String> currentStackIds=new HashSet<>();
            for(JsonObject row:displayed) {require(cardIds.add(row.get("id").getAsString()));
                GameObject card=new GameObject();
                boolean visibleStack=stackRows.contains(row) && Boolean.FALSE.equals(flag(row,"hidden")) && Boolean.FALSE.equals(flag(row,"face_down"));
                String stackId=row.get("id").getAsString();
                if(visibleStack){currentStackIds.add(stackId);card.object_id=stackReferences.computeIfAbsent(stackId,ignored->opaque());}
                else card.object_id=opaque();
                card.zone=exileOwners.containsKey(row)?"exile":commandOwners.containsKey(row)?"command":stackRows.contains(row)?"stack":handRows.contains(row)?"hand":graveOwners.containsKey(row)?"graveyard":"battlefield";
                card.controller_id=exileOwners.containsKey(row)?null:commandOwners.containsKey(row)?null:stackRows.contains(row)?row.has("stack_controller") && engineViewer.equals(row.get("stack_controller").getAsString())?viewer:players.get(row.has("stack_controller")?row.get("stack_controller").getAsString():null):handRows.contains(row)?viewer:graveOwners.containsKey(row)?graveOwners.get(row):seatNames.get(text(row,"controller_name"));
                String ownerName=text(row,"owner_name");card.owner_id=exileOwners.containsKey(row)?exileOwners.get(row):commandOwners.containsKey(row)?commandOwners.get(row):stackRows.contains(row)?row.has("stack_owner") && engineViewer.equals(row.get("stack_owner").getAsString())?viewer:players.get(row.has("stack_owner")?row.get("stack_owner").getAsString():null):handRows.contains(row)?viewer:graveOwners.containsKey(row)?graveOwners.get(row):ownerName==null || ownerName.isEmpty()?card.controller_id:seatNames.get(ownerName);
                require(exileOwners.containsKey(row) && card.owner_id!=null || stackRows.contains(row) || commandOwners.containsKey(row) && card.owner_id!=null || card.controller_id!=null && card.owner_id!=null);
                if("battlefield".equals(card.zone)){card.tapped=flag(row,"tapped");card.damage=integer(row,"damage");}
                visibleReferences.put(row.get("id").getAsString(),card.object_id);
                Boolean hidden=flag(row,"hidden");require(hidden!=null);card.hidden=hidden;card.face_down=flag(row,"face_down");
                if(!hidden && !Boolean.TRUE.equals(card.face_down)) {
                    String commanderSource=stackRows.contains(row) && row.has("commander_source")?row.get("commander_source").getAsString():row.get("id").getAsString();if(commanderNativeIds.contains(commanderSource))card.commander_id=commanderReferences.get(commanderSource);
                    CardCharacteristics c=new CardCharacteristics();c.name=text(row,"name");c.power=text(row,"power");c.toughness=text(row,"toughness");
                    c.type_line=text(row,"type");c.color=text(row,"color");
                    if(coreCombat){c.loyalty=text(row,"loyalty");c.defense=text(row,"defense");if(row.has("counters"))c.counters=counters(row);}
                    if(row.has("view_rules") && row.get("view_rules").isJsonArray()) {
                        List<String> lines=new ArrayList<>();for(JsonElement line:row.getAsJsonArray("view_rules")) {
                            JsonObject value=new JsonObject();value.add("text",line);lines.add(text(value,"text"));
                        }c.engine_view_text=lines.toArray(new String[0]);
                    }
                    c.unsupported_fields=coreCombat && row.has("loyalty") && row.has("defense")?row.has("counters")?new String[]{"current_abilities","transformed","is_copy","flipped"}:new String[]{"current_abilities","counters","transformed","is_copy","flipped"}:new String[]{"current_abilities","counters","loyalty","defense","transformed","is_copy","flipped"};card.characteristics=c;
                    // Only this already-visible row may acquire a public artwork identity.
                    CardIdentity binding=printings.get((viewer.equals(card.owner_id)?"":"opponent/")+text(row,"set")+"/"+text(row,"number"));
                    if(Boolean.TRUE.equals(flag(row,"token")))binding=NativeGameLaunch.tokenArtwork(row);
                    if(binding!=null){card.card_identity=JSON.fromJson(JSON.toJson(binding),CardIdentity.class);if(!viewer.equals(card.owner_id))card.card_identity.deck_entry_id=null;}
                } else card.hidden=true;
                if(coreCombat && "battlefield".equals(card.zone) && !card.hidden && Boolean.FALSE.equals(card.face_down) && card.characteristics!=null && card.characteristics.type_line!=null && (card.characteristics.type_line.contains("Planeswalker") || card.characteristics.type_line.contains("Battle"))){require(knownCombatDefenders.contains(row.get("id").getAsString()) || knownCombatDefenders.size()<256);knownCombatDefenders.add(row.get("id").getAsString());}
                cards.add(card);
            }
            stackReferences.keySet().retainAll(currentStackIds);
            result.objects=cards.toArray(new GameObject[0]);List<LegalAction> actions=new ArrayList<>();Map<String,String> offeredNative=new HashMap<>();
            if(discard) {
                JsonArray targets=prompt.getAsJsonArray("targets");require(targets.size()>0 && targets.size()<=256);Set<String> unique=new HashSet<>();
                for(JsonElement target:targets){require(target.isJsonPrimitive() && target.getAsJsonPrimitive().isString() && unique.add(target.getAsString()));String reference=visibleReferences.get(target.getAsString());GameObject card=null;for(GameObject item:cards)if(item.object_id.equals(reference))card=item;
                    require(card!=null && "hand".equals(card.zone) && viewer.equals(card.owner_id) && !card.hidden && Boolean.FALSE.equals(card.face_down) && card.characteristics!=null && card.characteristics.name!=null);LegalAction action=new LegalAction();action.action_id=opaque();action.object_id=reference;action.kind="discard";action.label="Discard "+card.characteristics.name;action.priority_class="meaningful";actions.add(action);offeredNative.put(action.action_id,target.getAsString());}
            }
            if(attackFinish) {
                Set<String> candidates=new HashSet<>();
                for(JsonElement candidate:prompt.getAsJsonArray(blocking?"blockers":"attackers")) {
                    require(candidate.isJsonPrimitive() && candidate.getAsJsonPrimitive().isString() && candidates.add(candidate.getAsString()));
                    String reference=visibleReferences.get(candidate.getAsString());GameObject object=null;
                    for(GameObject card:cards)if(card.object_id.equals(reference))object=card;
                    require(object!=null && "battlefield".equals(object.zone) && viewer.equals(object.controller_id) && Boolean.FALSE.equals(object.hidden) && Boolean.FALSE.equals(object.face_down));
                    if(includeAttackers) {
                        LegalAction action=new LegalAction();action.action_id=opaque();action.object_id=reference;action.kind=blocking?"declare_blocker":"declare_attacker";action.label=blocking?"Select blocker":"Select attacker";action.priority_class="meaningful";
                        if(coreCombat){boolean assigned=false;for(JsonElement group:raw.getAsJsonArray("combat"))for(JsonElement selected:group.getAsJsonObject().getAsJsonArray(blocking?"blockers":"attackers"))assigned|=candidate.equals(selected);if(assigned)action.label=blocking?"Remove blocker":"Remove attacker";}
                        if(Boolean.getBoolean("manaforge.liveGame"))action.label+=": "+object.characteristics.name;
                        actions.add(action);offeredNative.put(action.action_id,candidate.getAsString());
                    }
                }
            }
            if(mana){Set<String> unique=new HashSet<>();for(JsonElement source:raw.getAsJsonArray("playable")){require(source.isJsonPrimitive() && source.getAsJsonPrimitive().isString() && unique.add(source.getAsString()));GameObject card=visibleCard(cards,visibleReferences.get(source.getAsString()));if(card==null || !viewer.equals(card.controller_id))continue;LegalAction action=new LegalAction();action.action_id=opaque();action.object_id=card.object_id;action.kind="pay_mana";action.label="Select mana source: "+card.characteristics.name;action.priority_class="meaningful";actions.add(action);offeredNative.put(action.action_id,source.getAsString());}}
            if(mana)for(PlayerView seat:seats)if(viewer.equals(seat.player_id) && seat.mana!=null)for(JsonElement[] value:seat.mana)if(value[1].getAsLong()>0){LegalAction action=new LegalAction();action.action_id=opaque();action.kind="pay_mana";action.label="Use floating mana: "+value[0].getAsString();action.priority_class="meaningful";actions.add(action);offeredNative.put(action.action_id,"pool:"+value[0].getAsString());}
            if(priority && !omitStack && (!turnMode || includeSpells))for(JsonElement item:raw.getAsJsonArray("playable")) {
                String source=item.getAsString(),reference=visibleReferences.get(source);
                if(reference==null)continue;
                JsonElement kind=raw.getAsJsonObject("action_kinds").get(source);if(kind==null || !(kind.getAsString().equals("play_land") || includeSpells && (kind.getAsString().equals("cast_spell") || coreCombat && (kind.getAsString().equals("select_object") || kind.getAsString().equals("activate")))))continue;
                GameObject object=null;for(GameObject candidate:cards)if(candidate.object_id.equals(reference))object=candidate;
                if(object==null || object.hidden || !("command".equals(object.zone)?viewer.equals(object.owner_id):viewer.equals(object.controller_id)) || !("command".equals(object.zone) || "hand".equals(object.zone) || coreCombat && "battlefield".equals(object.zone) && (kind.getAsString().equals("activate") || kind.getAsString().equals("select_object"))))continue;
                LegalAction action=new LegalAction();action.action_id=opaque();action.object_id=reference;action.kind="battlefield".equals(object.zone)?"activate":kind.getAsString();action.label=action.kind.equals("cast_spell")?"Cast spell":action.kind.equals("select_object")?"Select object":action.kind.equals("activate")?"Activate":"Play land";if(coreCombat)action.label+=": "+object.characteristics.name;action.priority_class="meaningful";
                actions.add(action);offeredNative.put(action.action_id,source);
            }
            if((priority && includePriorityPass) || attackFinish) {
                LegalAction pass=new LegalAction();pass.action_id=opaque();pass.kind="pass";pass.label=attackFinish?(blocking?"Finish blocks":"Finish attacks"):"Pass priority";pass.priority_class="unknown";
                actions.add(pass);offeredNative.put(pass.action_id,null);
            }
            if(coreCombat && Boolean.TRUE.equals(flag(prompt,"cancellable")) && Arrays.asList("GAME_PLAY_MANA","GAME_CHOOSE_CHOICE","GAME_GET_MULTI_AMOUNT").contains(text(prompt,"kind"))){LegalAction cancel=new LegalAction();cancel.action_id=opaque();cancel.kind="pass";cancel.label="Cancel choice";cancel.priority_class="meaningful";actions.add(cancel);offeredNative.put(cancel.action_id,null);}
            result.actions=actions.toArray(new LegalAction[0]);
            // An empty rendered list alone never proves absence of responses.
            // Certify only the complete engine list, with every entry projected.
            result.actions_complete=priority && includePriorityPass && !omitStack
                && Boolean.TRUE.equals(flag(raw,"playable_information_complete"))
                && raw.has("playable") && raw.get("playable").isJsonArray()
                && completePriorityActions(raw.getAsJsonArray("playable"),offeredNative.values());
            ChoiceRequest choice=new ChoiceRequest();choice.decision_id=opaque();choice.player_id=viewer;choice.family=priority || ability || attackFinish || discard || targeting || stringChoice || mana?"selection":"boolean";
            choice.prompt=text(prompt,"message");if(coreCombat && choice.prompt==null)choice.prompt=numeric?("GAME_GET_AMOUNT".equals(text(prompt,"kind"))?"Choose a number":"Choose amounts"):"Choose a response";choice.cancellable=false;choice.can_finish=false;choice.is_priority=priority;choice.amounts=new AmountConstraint[0];
            Map<String,String> offeredOptions=new HashMap<>();
            if(numeric) {
                choice.family="GAME_GET_AMOUNT".equals(text(prompt,"kind"))?"number":"amounts";choice.minimum=integer(prompt,"min");choice.maximum=integer(prompt,"max");require(choice.minimum!=null && choice.maximum!=null && choice.minimum>=Integer.MIN_VALUE && choice.maximum<=Integer.MAX_VALUE && choice.minimum<=choice.maximum);choice.options=new ChoiceOption[0];List<AmountConstraint> ranges=new ArrayList<>();
                if("amounts".equals(choice.family)){JsonArray amounts=prompt.getAsJsonArray("amounts");require(amounts.size()>0 && amounts.size()<=256);for(JsonElement item:amounts){JsonObject row=item.getAsJsonObject();AmountConstraint range=new AmountConstraint();range.label=text(row,"message");if(range.label!=null)range.label=range.label.replaceAll("<[^>]*>","").replaceAll("\\s*\\[[0-9a-fA-F]{3}\\]","");range.minimum=integer(row,"min");range.maximum=integer(row,"max");range.defaultValue=integer(row,"default");require(range.label!=null && range.minimum!=null && range.maximum!=null && range.defaultValue!=null && range.minimum>=Integer.MIN_VALUE && range.maximum<=Integer.MAX_VALUE && range.minimum<=range.maximum && range.defaultValue>=range.minimum && range.defaultValue<=range.maximum);ranges.add(range);}}choice.amounts=ranges.toArray(new AmountConstraint[0]);
            } else if(stringChoice) {
                Map<String,String> offered=new LinkedHashMap<>();if(prompt.has("key_choices") && prompt.get("key_choices").isJsonObject())for(Map.Entry<String,JsonElement> entry:prompt.getAsJsonObject("key_choices").entrySet()){JsonObject label=new JsonObject();label.add("value",entry.getValue());offered.put(entry.getKey(),text(label,"value"));}
                if(offered.isEmpty() && prompt.has("choices") && prompt.get("choices").isJsonArray())for(JsonElement item:prompt.getAsJsonArray("choices")){JsonObject label=new JsonObject();label.add("value",item);String value=text(label,"value");require(!offered.containsKey(value));offered.put(value,value);}require(offered.size()>0 && offered.size()<=256);List<ChoiceOption> entries=new ArrayList<>();for(Map.Entry<String,String> entry:offered.entrySet()){require(entry.getValue()!=null);ChoiceOption option=new ChoiceOption();option.option_id=opaque();option.label=entry.getValue();option.object_id=visibleReferences.get(entry.getKey());option.selected=false;entries.add(option);offeredOptions.put(option.option_id,entry.getKey());stringOptions.add(option.option_id);}choice.options=entries.toArray(new ChoiceOption[0]);
            } else if(targeting) {
                JsonArray targets=prompt.getAsJsonArray("targets");require(targets.size()>0 && targets.size()<=256);Set<String> unique=new HashSet<>();List<ChoiceOption> entries=new ArrayList<>();
                for(JsonElement item:targets){require(item.isJsonPrimitive() && item.getAsJsonPrimitive().isString() && unique.add(item.getAsString()));String id=item.getAsString();GameObject card=null;for(GameObject object:cards)if(object.object_id.equals(visibleReferences.get(id)))card=object;String label=null;if(engineViewer.equals(id))label="You";else if(players.containsKey(id)){for(PlayerView seat:seats)if(seat.player_id.equals(players.get(id)))label=seat.name;}else if(card!=null && !card.hidden && Boolean.FALSE.equals(card.face_down) && card.characteristics!=null)label=card.characteristics.name;if(label==null && prompt.has("cards") && prompt.get("cards").isJsonArray()){require(prompt.getAsJsonArray("cards").size()<=256);for(JsonElement offered:prompt.getAsJsonArray("cards")){JsonObject value=offered.getAsJsonObject();if(id.equals(value.get("id").getAsString()) && Boolean.FALSE.equals(flag(value,"hidden")) && Boolean.FALSE.equals(flag(value,"face_down"))){require(label==null);label=text(value,"name");}}}require(label!=null);ChoiceOption option=new ChoiceOption();option.option_id=opaque();option.label=label;if(card!=null){option.object_id=card.object_id;if(Boolean.getBoolean("manaforge.liveGame") && card.controller_id!=null)option.label+=" ("+(viewer.equals(card.controller_id)?"you":"opponent")+")";}else if(engineViewer.equals(id) || players.containsKey(id))option.player_id=engineViewer.equals(id)?viewer:players.get(id);option.selected=false;entries.add(option);offeredOptions.put(option.option_id,id);}
                choice.options=entries.toArray(new ChoiceOption[0]);
                if(Boolean.TRUE.equals(flag(prompt,"can_finish"))){LegalAction finish=new LegalAction();finish.action_id=opaque();finish.kind="pass";finish.label="Finish selection";finish.priority_class="unknown";actions.add(finish);offeredNative.put(finish.action_id,null);result.actions=actions.toArray(new LegalAction[0]);}
            } else if(ability) {
                JsonObject choices=prompt.getAsJsonObject("key_choices");require(choices.size()>0 && choices.size()<=32);
                List<ChoiceOption> entries=new ArrayList<>();
                for(Map.Entry<String,JsonElement> entry:choices.entrySet()) {
                    require(UUID.fromString(entry.getKey()).toString().equals(entry.getKey()));
                    ChoiceOption option=new ChoiceOption();option.option_id=opaque();JsonObject label=new JsonObject();label.add("label",entry.getValue());option.label=text(label,"label");require(option.label!=null);option.selected=false;
                    entries.add(option);offeredOptions.put(option.option_id,entry.getKey());
                }
                choice.options=entries.toArray(new ChoiceOption[0]);
            } else {
                choice.options=new ChoiceOption[priority || attackFinish || discard || mana?0:2];
                for(int i=0;i<choice.options.length;i++){ChoiceOption option=new ChoiceOption();option.option_id=opaque();option.label=i==0?"Yes":"No";option.selected=false;choice.options[i]=option;}
            }
            result.decision=choice;result.combat=new CombatAssignment[0];
            if(combatObservation && coreCombat) {
                require(raw.getAsJsonArray("combat").size()<=256);List<CombatAssignment> groups=new ArrayList<>();Set<String> assigned=new HashSet<>();
                for(JsonElement item:raw.getAsJsonArray("combat")){JsonObject group=item.getAsJsonObject().deepCopy();
                    // Native combat retains departed combatants until the step finishes. They are
                    // not current battlefield objects or legal targets in this viewer snapshot.
                    for(String role:new String[]{"attackers","blockers"}){require(group.getAsJsonArray(role).size()<=256);JsonArray present=new JsonArray();Set<String> unique=new HashSet<>();for(JsonElement source:group.getAsJsonArray(role)){String id=source.getAsString();require(unique.add(id));if(visibleCard(cards,visibleReferences.get(id))!=null)present.add(source);else{require(knownCombatants.contains(id));missingCombatant=true;}}group.add(role,present);}
                    if(group.getAsJsonArray("attackers").size()==0){missingCombatant=true;continue;}
                    CombatAssignment assignment=new CombatAssignment();List<String> attackers=new ArrayList<>(),blockers=new ArrayList<>();String attackingSide=null;
                    require(group.getAsJsonArray("attackers").size()>0 && group.getAsJsonArray("attackers").size()<=256 && group.getAsJsonArray("blockers").size()<=256);
                    for(JsonElement source:group.getAsJsonArray("attackers")){String id=source.getAsString();require(assigned.add(id));GameObject card=visibleCard(cards,visibleReferences.get(id));require(card!=null);if(attackingSide==null)attackingSide=card.controller_id;require(attackingSide.equals(card.controller_id));attackers.add(card.object_id);}
                    require(attackingSide.equals(result.active_player_id));
                    String defender=group.get("defender")==null || group.get("defender").isJsonNull()?null:group.get("defender").getAsString(),defendingSide=engineViewer.equals(defender)?viewer:players.get(defender);if(defendingSide!=null){require(!defendingSide.equals(attackingSide));assignment.defender_id=defendingSide;}else{
                        GameObject card=visibleCard(cards,visibleReferences.get(defender));if(card!=null && card.characteristics!=null && card.characteristics.type_line!=null && (card.characteristics.type_line.contains("Planeswalker") || card.characteristics.type_line.contains("Battle"))){require(!card.characteristics.type_line.contains("Planeswalker") || !attackingSide.equals(card.controller_id));assignment.defender_id=card.object_id;}else{
                    require(defender==null || knownCombatDefenders.contains(defender));assignment.defender_id=null;missingDefender=true;}}
                    Set<String> unique=new HashSet<>();for(JsonElement source:group.getAsJsonArray("blockers")){require(unique.add(source.getAsString()));GameObject card=visibleCard(cards,visibleReferences.get(source.getAsString()));require(card!=null && !attackingSide.equals(card.controller_id) && (defendingSide==null || defendingSide.equals(card.controller_id)));blockers.add(card.object_id);}
                    assignment.attackers=attackers.toArray(new String[0]);assignment.blockers=blockers.toArray(new String[0]);assignment.blocked=flag(group,"blocked");require(assignment.blocked!=null && (blockers.isEmpty() || assignment.blocked));groups.add(assignment);
                }result.combat=groups.toArray(new CombatAssignment[0]);
            } else if(combatObservation) {
                require(raw.getAsJsonArray("combat").size()==1);JsonObject group=raw.getAsJsonArray("combat").get(0).getAsJsonObject();
                require(group.getAsJsonArray("attackers").size()==1 && (includeBlockers || group.getAsJsonArray("blockers").size()==0 && Boolean.FALSE.equals(flag(group,"blocked"))) && flag(group,"blocked")!=null);
                String source=group.getAsJsonArray("attackers").get(0).getAsString(),reference=visibleReferences.get(source);GameObject attacker=null;
                for(GameObject card:cards)if(card.object_id.equals(reference))attacker=card;
                require(attacker!=null && "battlefield".equals(attacker.zone) && viewer.equals(attacker.controller_id) && Boolean.FALSE.equals(attacker.hidden) && Boolean.FALSE.equals(attacker.face_down));
                String nativeDefender=group.get("defender").getAsString(),defender=players.get(nativeDefender);require(defender!=null && seen.contains(nativeDefender) && !engineViewer.equals(nativeDefender));
                for(PlayerView seat:seats)if(defender.equals(seat.player_id))require(Boolean.FALSE.equals(seat.left_game));
                CombatAssignment assignment=new CombatAssignment();assignment.attackers=new String[]{reference};List<String> blockerReferences=new ArrayList<>();Set<String> uniqueBlockers=new HashSet<>();require(group.getAsJsonArray("blockers").size()<=256);
                for(JsonElement item:group.getAsJsonArray("blockers")){require(item.isJsonPrimitive() && item.getAsJsonPrimitive().isString() && uniqueBlockers.add(item.getAsString()));String blockerReference=visibleReferences.get(item.getAsString());GameObject blocker=null;for(GameObject card:cards)if(card.object_id.equals(blockerReference))blocker=card;require(blocker!=null && "battlefield".equals(blocker.zone) && defender.equals(blocker.controller_id) && Boolean.FALSE.equals(blocker.hidden) && Boolean.FALSE.equals(blocker.face_down));blockerReferences.add(blockerReference);}
                assignment.blockers=blockerReferences.toArray(new String[0]);assignment.defender_id=defender;assignment.blocked=flag(group,"blocked");result.combat=new CombatAssignment[]{assignment};
            }result.observations=new CardObservation[0];
            result.unsupported_fields=new String[]{"object_incarnations","commander_metadata","live_abilities","actions","mana","counters","eliminated","observations","attachments","copy_metadata","physical_printing"};
            if(coreCombat && cards.stream().anyMatch(card->"stack".equals(card.zone) && (card.controller_id==null || card.owner_id==null))){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.add("stack_ownership");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(missingCombatant){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.add("combat_lki");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(missingDefender){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.add("combat_defender_lki");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(result.actions_complete){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.remove("actions");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(result.commanders!=null){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.remove("commander_metadata");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(coreCombat && seats.stream().allMatch(seat->seat.mana!=null)){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.remove("mana");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(coreCombat && exileOwners.size()!=raw.getAsJsonArray("exile").size()){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.add("exile");result.unsupported_fields=unsupported.toArray(new String[0]);}
            if(omitStack && !coreCombat){List<String> unsupported=new ArrayList<>(Arrays.asList(result.unsupported_fields));unsupported.add("stack");result.unsupported_fields=unsupported.toArray(new String[0]);}
            JsonObject output=JSON.toJsonTree(result).getAsJsonObject();
            nativeGame=raw.get("game_id").getAsString();nativeDecision=integer(prompt,"decision_id");nativeCycle=integer(raw,"cycle");
            decision=choice.decision_id;consumed=false;
            if(!priority && !ability && !attackFinish && !discard && !targeting && !numeric && !stringChoice && !mana){options.put(choice.options[0].option_id,true);options.put(choice.options[1].option_id,false);}
            if(numeric)numericPrompt=prompt.deepCopy();
            nativeOptions.putAll(offeredOptions);
            nativeActions.putAll(offeredNative);
            if(coreCombat)for(JsonObject row:battlefield){require(knownCombatants.contains(row.get("id").getAsString()) || knownCombatants.size()<4096);knownCombatants.add(row.get("id").getAsString());}
            revision++;return output;
        }catch(IOException failure){throw failure;}catch(RuntimeException failure){IOException sanitized=new IOException("LIVE_OPENING_PROJECTION_UNSUPPORTED");sanitized.setStackTrace(failure.getStackTrace());throw sanitized;}
    }
}

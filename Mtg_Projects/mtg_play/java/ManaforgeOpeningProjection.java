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
    public static final class ChoiceException extends IOException {
        public final String code;
        private ChoiceException(String code){super(code);this.code=code;}
    }
    private long revision;
    private String decision, nativeGame;
    private Long nativeDecision, nativeCycle;
    private final Map<String,Boolean> options=new HashMap<>();
    private boolean consumed;
    private final Map<String,String> nativeActions=new HashMap<>();

    /** Trusted launch/session worker only. Authentication and receipt ledger remain external.
     * Claim is one-shot BEFORE native IO; an uncertain submission must never be replayed. */
    public synchronized JsonObject claimBoolean(String wire,String trustedSession,String trustedViewer,String currentGame,String currentEngineViewer,long currentNativeDecision,long currentNativeCycle) throws IOException {
        return claim(wire,trustedSession,trustedViewer,currentGame,currentEngineViewer,currentNativeDecision,currentNativeCycle,false);
    }
    public synchronized JsonObject claimAction(String wire,String trustedSession,String trustedViewer,String currentGame,String currentEngineViewer,long currentNativeDecision,long currentNativeCycle) throws IOException {
        return claim(wire,trustedSession,trustedViewer,currentGame,currentEngineViewer,currentNativeDecision,currentNativeCycle,true);
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
                  : !operation.equals("choose") || !options.containsKey(body.get("option_id").getAsString()))throw new ChoiceException("ACTION_UNAVAILABLE");
        Boolean answer=action?null:options.get(body.get("option_id").getAsString());
        String source=action?nativeActions.get(body.get("action_id").getAsString()):null;
        consumed=true;options.clear();nativeActions.clear();
        JsonObject command=new JsonObject();command.addProperty("protocol",1);command.addProperty("command","respond");
        command.add("request_id",envelope.get("message_id").deepCopy());command.addProperty("game_id",nativeGame);
        boolean objectResponse=action && source!=null;
        command.addProperty("decision_id",nativeDecision);command.addProperty("kind",objectResponse?"object":"boolean");if(objectResponse)command.addProperty("value",source);else command.addProperty("value",action?false:answer);
        return command;
    }
    public synchronized void invalidateDecision(){decision=null;nativeGame=null;nativeDecision=null;nativeCycle=null;options.clear();nativeActions.clear();consumed=true;}

    public ManaforgeOpeningProjection(String session,String viewer,String engineViewer,Map<String,CardIdentity> bindings) {
        this.session=session;this.viewer=viewer;this.engineViewer=engineViewer;
        for(Map.Entry<String,CardIdentity> entry:bindings.entrySet())
            printings.put(entry.getKey(),JSON.fromJson(JSON.toJson(entry.getValue()),CardIdentity.class));
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
        invalidateDecision();
        try {
            require(engineViewer.equals(raw.get("viewer").getAsString()));
            boolean priority="GAME_SELECT".equals(prompt.get("kind").getAsString()) && Boolean.TRUE.equals(flag(prompt,"is_priority"));
            require("GAME_ASK".equals(prompt.get("kind").getAsString()) || priority);
            require(!priority || (!prompt.has("attackers") && !prompt.has("blockers")));
            require(Objects.equals(integer(raw,"cycle"),integer(prompt,"cycle")) && integer(raw,"cycle")!=null);
            require(integer(prompt,"decision_id")!=null && integer(prompt,"decision_id")>=0 && integer(prompt,"decision_id")<=Integer.MAX_VALUE);
            require(raw.has("game_id") && !raw.get("game_id").isJsonNull());
            empty(raw,"stack");empty(raw,"exile");empty(raw,"combat");
            GameSnapshot result=new GameSnapshot();result.session_id=session;result.viewer_id=viewer;
            result.revision=revision+1;result.protocol_version=1L;result.status="active";
            result.turn=integer(raw,"turn");result.phase=text(raw,"phase");result.step=text(raw,"step");
            List<PlayerView> seats=new ArrayList<>();Map<String,String> names=new HashMap<>();Set<String> seen=new HashSet<>();
            boolean found=false;Map<String,String> seatNames=new HashMap<>();List<JsonObject> battlefield=new ArrayList<>();
            for(JsonElement item:raw.getAsJsonArray("players")) {
                JsonObject row=item.getAsJsonObject();String id=row.get("id").getAsString();require(seen.add(id));
                boolean local=engineViewer.equals(id);found|=local;
                String publicId=local?viewer:players.computeIfAbsent(id,ignored->opaque());
                names.put(row.get("name").getAsString(),publicId);
                if(!priority)empty(row,"battlefield");else for(JsonElement permanent:row.getAsJsonArray("battlefield"))battlefield.add(permanent.getAsJsonObject());
                empty(row,"graveyard");empty(row,"command");seatNames.put(row.get("name").getAsString(),publicId);
                PlayerView seat=new PlayerView();seat.player_id=publicId;seat.name=local?"You":"Player "+(seats.size()+1);
                seat.life=integer(row,"life");seat.hand_count=integer(row,"hand_count");seat.library_count=integer(row,"library_count");
                seat.left_game=flag(row,"left");seats.add(seat);
            }
            require(found && seats.size()>=2);
            result.players=seats.toArray(new PlayerView[0]);
            result.active_player_id=names.get(text(raw,"active_player"));result.priority_player_id=names.get(text(raw,"priority_player"));
            require(!priority || viewer.equals(result.priority_player_id));
            List<GameObject> cards=new ArrayList<>();Set<String> cardIds=new HashSet<>();
            List<JsonObject> displayed=new ArrayList<>();Set<JsonObject> handRows=Collections.newSetFromMap(new IdentityHashMap<>());
            for(JsonElement item:raw.getAsJsonArray("hand")){displayed.add(item.getAsJsonObject());handRows.add(item.getAsJsonObject());}displayed.addAll(battlefield);
            Map<String,String> visibleReferences=new HashMap<>();
            for(JsonObject row:displayed) {require(cardIds.add(row.get("id").getAsString()));
                GameObject card=new GameObject();card.object_id=opaque();card.zone=handRows.contains(row)?"hand":"battlefield";
                card.controller_id=handRows.contains(row)?viewer:seatNames.get(text(row,"controller_name"));
                String ownerName=text(row,"owner_name");card.owner_id=handRows.contains(row)?viewer:ownerName==null || ownerName.isEmpty()?card.controller_id:seatNames.get(ownerName);
                require(card.controller_id!=null && card.owner_id!=null);
                if(!handRows.contains(row)){card.tapped=flag(row,"tapped");card.damage=integer(row,"damage");}
                visibleReferences.put(row.get("id").getAsString(),card.object_id);
                Boolean hidden=flag(row,"hidden");require(hidden!=null);card.hidden=hidden;card.face_down=flag(row,"face_down");
                if(!hidden && !Boolean.TRUE.equals(card.face_down)) {
                    CardCharacteristics c=new CardCharacteristics();c.name=text(row,"name");c.power=text(row,"power");c.toughness=text(row,"toughness");
                    c.type_line=text(row,"type");c.color=text(row,"color");
                    if(row.has("view_rules") && row.get("view_rules").isJsonArray()) {
                        List<String> lines=new ArrayList<>();for(JsonElement line:row.getAsJsonArray("view_rules")) {
                            JsonObject value=new JsonObject();value.add("text",line);lines.add(text(value,"text"));
                        }c.engine_view_text=lines.toArray(new String[0]);
                    }
                    c.unsupported_fields=new String[]{"current_abilities","counters","loyalty","defense","transformed","is_copy","flipped"};card.characteristics=c;
                    CardIdentity binding=viewer.equals(card.owner_id)?printings.get(text(row,"set")+"/"+text(row,"number")):null;
                    if(binding!=null)card.card_identity=JSON.fromJson(JSON.toJson(binding),CardIdentity.class);
                } else card.hidden=true;
                cards.add(card);
            }
            result.objects=cards.toArray(new GameObject[0]);List<LegalAction> actions=new ArrayList<>();Map<String,String> offeredNative=new HashMap<>();
            if(priority)for(JsonElement item:raw.getAsJsonArray("playable")) {
                String source=item.getAsString(),reference=visibleReferences.get(source);
                if(reference==null)continue;
                JsonElement kind=raw.getAsJsonObject("action_kinds").get(source);if(kind==null || !kind.getAsString().equals("play_land"))continue;
                GameObject object=null;for(GameObject candidate:cards)if(candidate.object_id.equals(reference))object=candidate;
                if(object==null || object.hidden || !viewer.equals(object.controller_id) || !"hand".equals(object.zone))continue;
                LegalAction action=new LegalAction();action.action_id=opaque();action.object_id=reference;action.kind=kind.getAsString();action.label="Play land";action.priority_class="meaningful";
                actions.add(action);offeredNative.put(action.action_id,source);
            }
            if(priority && includePriorityPass) {
                LegalAction pass=new LegalAction();pass.action_id=opaque();pass.kind="pass";pass.label="Pass priority";pass.priority_class="unknown";
                actions.add(pass);offeredNative.put(pass.action_id,null);
            }
            result.actions=actions.toArray(new LegalAction[0]);result.actions_complete=false;
            ChoiceRequest choice=new ChoiceRequest();choice.decision_id=opaque();choice.player_id=viewer;choice.family=priority?"selection":"boolean";
            choice.prompt=text(prompt,"message");choice.cancellable=false;choice.can_finish=false;choice.is_priority=priority;choice.amounts=new AmountConstraint[0];
            choice.options=new ChoiceOption[priority?0:2];
            for(int i=0;i<choice.options.length;i++){ChoiceOption option=new ChoiceOption();option.option_id=opaque();option.label=i==0?"Yes":"No";option.selected=false;choice.options[i]=option;}
            result.decision=choice;result.combat=new CombatAssignment[0];result.observations=new CardObservation[0];
            result.unsupported_fields=new String[]{"object_incarnations","commander_metadata","live_abilities","actions","mana","counters","eliminated","observations","attachments","copy_metadata","physical_printing"};
            JsonObject output=JSON.toJsonTree(result).getAsJsonObject();
            nativeGame=raw.get("game_id").getAsString();nativeDecision=integer(prompt,"decision_id");nativeCycle=integer(raw,"cycle");
            decision=choice.decision_id;consumed=false;
            if(!priority){options.put(choice.options[0].option_id,true);options.put(choice.options[1].option_id,false);}
            nativeActions.putAll(offeredNative);
            revision++;return output;
        }catch(IOException failure){throw failure;}catch(RuntimeException failure){throw new IOException("LIVE_OPENING_PROJECTION_UNSUPPORTED");}
    }
}

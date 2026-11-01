import com.google.gson.*;
import manaforge.protocol.PlayContracts.*;
import java.io.IOException;
import java.util.*;

/** Viewer-bound opening-only projection. No rules, IO, engine types or raw-state export. */
public final class ManaforgeOpeningProjection {
    private static final Gson JSON=new GsonBuilder().serializeNulls().create();
    private final String session, viewer, engineViewer;
    private final Map<String,CardIdentity> printings=new HashMap<>();
    private final Map<String,String> players=new HashMap<>();
    private long revision;
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
    public JsonObject project(JsonObject raw,JsonObject prompt) throws IOException {
        try {
            require(engineViewer.equals(raw.get("viewer").getAsString()));
            require("GAME_ASK".equals(prompt.get("kind").getAsString()));
            require(Objects.equals(integer(raw,"cycle"),integer(prompt,"cycle")) && integer(raw,"cycle")!=null);
            require(integer(prompt,"decision_id")!=null);
            empty(raw,"stack");empty(raw,"exile");empty(raw,"combat");
            GameSnapshot result=new GameSnapshot();result.session_id=session;result.viewer_id=viewer;
            result.revision=revision+1;result.protocol_version=1L;result.status="active";
            result.turn=integer(raw,"turn");result.phase=text(raw,"phase");result.step=text(raw,"step");
            List<PlayerView> seats=new ArrayList<>();Map<String,String> names=new HashMap<>();Set<String> seen=new HashSet<>();
            boolean found=false;
            for(JsonElement item:raw.getAsJsonArray("players")) {
                JsonObject row=item.getAsJsonObject();String id=row.get("id").getAsString();require(seen.add(id));
                boolean local=engineViewer.equals(id);found|=local;
                String publicId=local?viewer:players.computeIfAbsent(id,ignored->opaque());
                names.put(row.get("name").getAsString(),publicId);
                empty(row,"battlefield");empty(row,"graveyard");empty(row,"command");
                PlayerView seat=new PlayerView();seat.player_id=publicId;seat.name=local?"You":"Player "+(seats.size()+1);
                seat.life=integer(row,"life");seat.hand_count=integer(row,"hand_count");seat.library_count=integer(row,"library_count");
                seat.left_game=flag(row,"left");seats.add(seat);
            }
            require(found && seats.size()>=2);
            result.players=seats.toArray(new PlayerView[0]);
            result.active_player_id=names.get(text(raw,"active_player"));result.priority_player_id=names.get(text(raw,"priority_player"));
            List<GameObject> cards=new ArrayList<>();Set<String> cardIds=new HashSet<>();
            for(JsonElement item:raw.getAsJsonArray("hand")) {
                JsonObject row=item.getAsJsonObject();require(cardIds.add(row.get("id").getAsString()));
                GameObject card=new GameObject();card.object_id=opaque();card.zone="hand";card.owner_id=viewer;card.controller_id=viewer;
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
                    CardIdentity binding=printings.get(text(row,"set")+"/"+text(row,"number"));
                    if(binding!=null)card.card_identity=JSON.fromJson(JSON.toJson(binding),CardIdentity.class);
                } else card.hidden=true;
                cards.add(card);
            }
            result.objects=cards.toArray(new GameObject[0]);result.actions=new LegalAction[0];result.actions_complete=false;
            ChoiceRequest choice=new ChoiceRequest();choice.decision_id=opaque();choice.player_id=viewer;choice.family="boolean";
            choice.prompt=text(prompt,"message");choice.cancellable=false;choice.can_finish=false;choice.is_priority=false;choice.amounts=new AmountConstraint[0];
            choice.options=new ChoiceOption[2];
            for(int i=0;i<2;i++){ChoiceOption option=new ChoiceOption();option.option_id=opaque();option.label=i==0?"Yes":"No";option.selected=false;choice.options[i]=option;}
            result.decision=choice;result.combat=new CombatAssignment[0];result.observations=new CardObservation[0];
            result.unsupported_fields=new String[]{"object_incarnations","commander_metadata","live_abilities","actions","mana","counters","eliminated","observations"};
            JsonObject output=JSON.toJsonTree(result).getAsJsonObject();revision++;return output;
        }catch(IOException failure){throw failure;}catch(RuntimeException failure){throw new IOException("LIVE_OPENING_PROJECTION_UNSUPPORTED");}
    }
}

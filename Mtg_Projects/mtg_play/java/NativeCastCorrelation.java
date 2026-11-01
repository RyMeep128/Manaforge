import com.google.gson.*;
import java.util.*;

/** Private read-only evidence. Never authorizes IO, settles a receipt, or proves a cast completed. */
public final class NativeCastCorrelation {
    private final String game,viewer,source;
    private final long cycle,decision;
    private final Set<String> abilities;
    private NativeCastCorrelation(String game,String viewer,String source,long cycle,long decision,Set<String> abilities) {
        this.game=game;this.viewer=viewer;this.source=source;this.cycle=cycle;this.decision=decision;this.abilities=Collections.unmodifiableSet(new HashSet<>(abilities));
    }
    private static String string(JsonObject value,String key) {
        JsonElement item=value.get(key);if(item==null || !item.isJsonPrimitive() || !item.getAsJsonPrimitive().isString() || item.getAsString().isEmpty())throw new IllegalArgumentException();return item.getAsString();
    }
    private static long number(JsonObject value,String key) {
        JsonElement item=value.get(key);if(item==null || !item.isJsonPrimitive() || !item.getAsJsonPrimitive().isNumber() || !item.toString().matches("[0-9]+"))throw new IllegalArgumentException();return Long.parseLong(item.getAsString());
    }
    private static String uuid(String value){if(!UUID.fromString(value).toString().equals(value))throw new IllegalArgumentException();return value;}
    private static boolean visibleSource(JsonObject state,String source) {
        int found=0;
        for(JsonElement value:state.getAsJsonArray("hand")) {
            JsonObject card=value.getAsJsonObject();if(!source.equals(string(card,"id")))continue;
            if(!new JsonPrimitive(false).equals(card.get("hidden")) || !new JsonPrimitive(false).equals(card.get("face_down")))return false;
            found++;
        }
        return found==1;
    }
    public static NativeCastCorrelation capture(JsonObject state,JsonObject prompt,JsonObject command) {
        try {
            String game=string(state,"game_id"),viewer=string(state,"viewer"),source=uuid(string(command,"value"));
            long cycle=number(state,"cycle"),decision=number(prompt,"decision_id");
            if(decision>Integer.MAX_VALUE || !game.equals(string(command,"game_id")) || number(command,"decision_id")!=decision || number(prompt,"cycle")!=cycle
                || !"respond".equals(string(command,"command")) || !"object".equals(string(command,"kind"))
                || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority"))
                || !visibleSource(state,source) || !"cast_spell".equals(string(state.getAsJsonObject("action_kinds"),source)))return null;
            boolean offered=false;for(JsonElement id:state.getAsJsonArray("playable"))offered|=source.equals(id.getAsString());if(!offered)return null;
            JsonArray raw=state.getAsJsonObject("casting_ability_ids").getAsJsonArray(source);if(raw.size()==0 || raw.size()>32)return null;
            Set<String> ids=new HashSet<>();for(JsonElement id:raw){if(!id.isJsonPrimitive() || !id.getAsJsonPrimitive().isString() || !ids.add(uuid(id.getAsString())))return null;}
            return new NativeCastCorrelation(game,viewer,source,cycle,decision,ids);
        }catch(RuntimeException unsupported){return null;}
    }
    public boolean matches(JsonObject state,JsonObject prompt) {
        try {
            if(!game.equals(string(state,"game_id")) || !viewer.equals(string(state,"viewer")) || number(state,"cycle")<cycle
                || number(prompt,"cycle")!=number(state,"cycle") || number(prompt,"decision_id")<=decision || number(prompt,"decision_id")>Integer.MAX_VALUE
                || !"GAME_CHOOSE_ABILITY".equals(string(prompt,"kind")) || !visibleSource(state,source))return false;
            JsonObject choices=prompt.getAsJsonObject("key_choices");if(choices.size()!=1)return false;
            Map.Entry<String,JsonElement> choice=choices.entrySet().iterator().next();
            return abilities.contains(uuid(choice.getKey())) && choice.getValue().isJsonPrimitive() && choice.getValue().getAsJsonPrimitive().isString();
        }catch(RuntimeException unsupported){return false;}
    }
    /** Still observation only: guarded native stack-source metadata, not a receipt settlement. */
    public boolean matchesStack(JsonObject state,JsonObject metadata) {
        try {
            if(!game.equals(string(state,"game_id")) || !viewer.equals(string(state,"viewer")) || !"ok".equals(string(metadata,"status"))
                || number(state,"cycle")<cycle || number(metadata,"cycle")!=number(state,"cycle"))return false;
            for(JsonElement value:state.getAsJsonArray("hand"))if(source.equals(string(value.getAsJsonObject(),"id")))return false;
            int found=0;
            for(JsonElement value:state.getAsJsonArray("stack")) {
                JsonObject card=value.getAsJsonObject(),entry=metadata.getAsJsonObject("objects").getAsJsonObject(uuid(string(card,"id")));
                if(entry==null)continue;
                if(source.equals(string(entry,"source")) && viewer.equals(string(entry,"owner")) && viewer.equals(string(entry,"controller"))
                    && new JsonPrimitive(false).equals(card.get("hidden")) && new JsonPrimitive(false).equals(card.get("face_down"))){number(entry,"incarnation");found++;}
            }
            return found==1;
        }catch(RuntimeException unsupported){return false;}
    }
}

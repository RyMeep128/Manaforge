import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Engine-observed manual casting acceptance, with no rule or response-selection implementation. */
public final class NativeCastingCase implements NativeAcceptanceCase {
    private final String key,name;private final Map<String,Long> selected=new LinkedHashMap<>(),stacked=new HashMap<>();
    private String viewer,cancelledSource;private int payments,numbers;private boolean cancelled,completed,verified,activated;
    public NativeCastingCase(String key) {
        if(!Arrays.asList("casting-repeat","casting-cancel","casting-x","casting-ability").contains(key))throw new IllegalArgumentException("CASTING_CASE_INVALID");
        this.key=key;name=key.equals("casting-repeat")?"Memnite":key.equals("casting-cancel")?"Garruk's Companion":"Walking Ballista";
    }
    public String key(){return key;}
    public JsonArray deck(boolean ai) {
        JsonArray result=new JsonArray();for(int i=0;i<60;i++) {
            String card=ai?"Forest":i%2==0?"Forest":name;
            JsonObject row=new JsonObject();row.addProperty("name",card);row.addProperty("set",card.equals("Forest")?"TRK":card.equals("Memnite")?"SOM":card.equals("Garruk's Companion")?"M12":"AER");
            row.addProperty("number",card.equals("Forest")?"325":card.equals("Memnite")?"174":card.equals("Garruk's Companion")?"175":"181");row.addProperty("quantity",1);result.add(row);
        }return result;
    }
    public boolean openingMatches(JsonArray hand){Set<String> seen=new HashSet<>();for(JsonElement item:hand){String value=text(item.getAsJsonObject(),"name");if(!value.equals(name) && !value.equals("Forest"))return false;seen.add(value);}return seen.contains(name) && seen.contains("Forest");}
    private static String text(JsonObject row,String key){JsonElement value=row.get(key);return value==null || value.isJsonNull()?"":value.getAsString();}
    private static JsonObject locate(JsonObject state,String id,String zone){JsonArray cards=state.getAsJsonArray(zone);if(cards!=null)for(JsonElement card:cards)if(id.equals(text(card.getAsJsonObject(),"id")))return card.getAsJsonObject();for(JsonElement player:state.getAsJsonArray("players")){cards=player.getAsJsonObject().getAsJsonArray(zone);if(cards!=null)for(JsonElement card:cards)if(id.equals(text(card.getAsJsonObject(),"id")))return card.getAsJsonObject();}return null;}
    private static JsonObject guard(JsonObject state,String id,Metadata reader) throws Exception {JsonObject result=reader.read(state,id);if(!"ok".equals(text(result,"status")) || !state.get("cycle").equals(result.get("cycle")))throw new IOException("CASTING_CASE_UNGUARDED");JsonObject entry=result.getAsJsonObject("objects").getAsJsonObject(id);if(entry==null)throw new IOException("CASTING_CASE_SOURCE_UNPROVEN");return entry;}
    public void before(JsonObject state,JsonObject prompt,JsonObject command) {
        viewer=text(state,"viewer");String kind=text(prompt,"kind");if(kind.equals("GAME_PLAY_MANA")){payments++;if(new JsonPrimitive(false).equals(command.get("value"))){for(String id:selected.keySet())if(locate(state,id,"hand")!=null || locate(state,id,"battlefield")==null)cancelledSource=id;}}
        if(kind.equals("GAME_GET_AMOUNT") || kind.equals("GAME_GET_MULTI_AMOUNT"))numbers++;
        if(kind.equals("GAME_SELECT") && new JsonPrimitive(true).equals(prompt.get("is_priority")) && "object".equals(text(command,"kind"))){String id=text(command,"value");JsonObject source=locate(state,id,"hand");if(source!=null && name.equals(text(source,"name")))selected.put(id,state.get("turn").getAsLong());else if(locate(state,id,"battlefield")!=null && selected.containsKey(id))activated=true;}
    }
    public boolean observe(JsonObject state,JsonObject prompt,Metadata reader) throws Exception {
        if(cancelledSource!=null && locate(state,cancelledSource,"hand")!=null && new JsonPrimitive(true).equals(prompt.get("is_priority")))cancelled=true;
        for(JsonElement card:state.getAsJsonArray("stack")){String id=text(card.getAsJsonObject(),"id");JsonObject entry=guard(state,id,reader);String source=text(entry,"source");if(selected.containsKey(source) && entry.has("source_incarnation"))stacked.put(source,entry.get("source_incarnation").getAsLong());}
        int live=0;boolean counter=false;for(String id:selected.keySet()) {
            JsonObject source=locate(state,id,"battlefield");if(source==null)continue;JsonObject entry=guard(state,id,reader);
            if(!viewer.equals(text(entry,"owner")) || !viewer.equals(text(entry,"controller")) || !name.equals(text(source,"name")))throw new IOException("CASTING_CASE_SOURCE_CHANGED");
            if(stacked.containsKey(id) && entry.get("incarnation").getAsLong()>stacked.get(id)){live++;verified=true;}
            counter|="1".equals(text(source,"power")) && "1".equals(text(source,"toughness"));
        }
        boolean effect=false;if(key.equals("casting-ability") && activated)for(JsonElement player:state.getAsJsonArray("players"))if(!viewer.equals(text(player.getAsJsonObject(),"id")))effect=player.getAsJsonObject().get("life").getAsLong()==19;
        if(key.equals("casting-ability"))for(String id:stacked.keySet())if(locate(state,id,"graveyard")!=null){JsonObject entry=guard(state,id,reader);effect&=entry.get("incarnation").getAsLong()>stacked.get(id);}
        boolean differentTurns=selected.values().stream().distinct().count()>=2;
        boolean goal=key.equals("casting-repeat")?live>=2 && differentTurns:key.equals("casting-cancel")?cancelled && live==1 && locate(state,cancelledSource,"battlefield")!=null:key.equals("casting-x")?live==1 && counter && numbers>0 && payments>=2:verified && activated && effect;
        completed|=goal && state.getAsJsonArray("stack").size()==0 && new JsonPrimitive(true).equals(prompt.get("is_priority"));return completed;
    }
    public void terminal(String outcome) throws IOException {throw new IOException("CASTING_CASE_UNEXPECTED_TERMINAL");}
    public JsonObject report(){JsonObject result=new JsonObject();result.addProperty("native_casting_case",key);result.addProperty("native_casting_case_completed",completed);result.addProperty("native_casting_case_source_verified",verified);result.addProperty("native_casting_case_stacked_sources",stacked.size());result.addProperty("native_casting_case_mana_responses",payments);result.addProperty("native_casting_case_numeric_responses",numbers);result.addProperty("native_casting_case_cancelled",cancelled);result.addProperty("native_casting_case_activated",activated);return result;}
}

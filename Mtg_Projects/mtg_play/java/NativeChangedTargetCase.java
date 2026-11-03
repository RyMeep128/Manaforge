import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Explicit public fixture: sacrifice a targeted creature in response to Giant Growth. */
public final class NativeChangedTargetCase implements NativeAcceptanceCase {
    private final Map<String,String> selected=new HashMap<>();
    private final Map<String,Long> stacked=new HashMap<>();
    private String viewer,creature;private long creatureIncarnation=-1;
    private boolean targetBound,departedWhileStacked,completed;
    public String key(){return "casting-changed-target";}
    public JsonArray deck(boolean ai){
        JsonArray result=new JsonArray();String[][] rows=ai?new String[][]{{"Forest","TRK","325"}}:new String[][]{{"Forest","TRK","325"},{"Mountain","TRK","323"},{"Memnite","SOM","174"},{"Giant Growth","M10","184"},{"Fling","ELD","126"}};
        for(int i=0;i<60;i++){String[] row=rows[i%rows.length];JsonObject card=new JsonObject();card.addProperty("name",row[0]);card.addProperty("set",row[1]);card.addProperty("number",row[2]);card.addProperty("quantity",1);result.add(card);}return result;
    }
    public boolean openingMatches(JsonArray hand){for(JsonElement row:hand)if(!Arrays.asList("Forest","Mountain","Memnite","Giant Growth","Fling").contains(text(row.getAsJsonObject(),"name")))return false;return hand.size()==7;}
    private static String text(JsonObject row,String key){JsonElement value=row.get(key);return value==null || value.isJsonNull()?"":value.getAsString();}
    private static JsonObject find(JsonObject state,String id,String zone){for(JsonElement seat:state.getAsJsonArray("players")){JsonArray cards=seat.getAsJsonObject().getAsJsonArray(zone);if(cards!=null)for(JsonElement row:cards)if(id.equals(text(row.getAsJsonObject(),"id")))return row.getAsJsonObject();}return null;}
    private static JsonObject guard(JsonObject state,String id,Metadata reader)throws Exception{JsonObject metadata=reader.read(state,id);if(!"ok".equals(text(metadata,"status")) || !state.get("cycle").equals(metadata.get("cycle")))throw new IOException("CHANGED_TARGET_CONTEXT");JsonObject row=metadata.getAsJsonObject("objects").getAsJsonObject(id);if(row==null)throw new IOException("CHANGED_TARGET_OBJECT");return row;}
    public void before(JsonObject state,JsonObject prompt,JsonObject command){
        viewer=text(state,"viewer");if(!"GAME_SELECT".equals(text(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || !"object".equals(text(command,"kind")))return;
        for(JsonElement row:state.getAsJsonArray("hand")){JsonObject card=row.getAsJsonObject();if(text(card,"id").equals(text(command,"value")) && Arrays.asList("Memnite","Giant Growth","Fling").contains(text(card,"name")))selected.put(text(card,"name"),text(card,"id"));}
    }
    public boolean observe(JsonObject state,JsonObject prompt,Metadata reader)throws Exception{
        if(viewer==null)return false;
        if(selected.containsKey("Memnite") && creature==null && find(state,selected.get("Memnite"),"battlefield")!=null){creature=selected.get("Memnite");JsonObject row=guard(state,creature,reader);if(!viewer.equals(text(row,"owner")) || !viewer.equals(text(row,"controller")))throw new IOException("CHANGED_TARGET_OWNER");creatureIncarnation=row.get("incarnation").getAsLong();}
        boolean growthPresent=false;
        for(JsonElement card:state.getAsJsonArray("stack")){String id=text(card.getAsJsonObject(),"id");JsonObject row=guard(state,id,reader);String source=text(row,"source");for(String name:new String[]{"Giant Growth","Fling"})if(source.equals(selected.get(name))){stacked.putIfAbsent(name,row.get("source_incarnation").getAsLong());if(name.equals("Giant Growth")){growthPresent=true;targetBound|=creature!=null && new JsonPrimitive(true).equals(row.get("stack_targets_complete")) && row.getAsJsonArray("stack_targets").contains(new JsonPrimitive(creature));}}}
        boolean departed=false;if(creature!=null && find(state,creature,"graveyard")!=null){JsonObject row=guard(state,creature,reader);departed=viewer.equals(text(row,"owner")) && row.get("incarnation").getAsLong()==creatureIncarnation+1;}
        departedWhileStacked|=targetBound && growthPresent && departed;
        boolean resolved=true;for(String name:new String[]{"Giant Growth","Fling"}){String id=selected.get(name);resolved&=id!=null && stacked.containsKey(name) && find(state,id,"graveyard")!=null;if(resolved){JsonObject row=guard(state,id,reader);resolved=viewer.equals(text(row,"owner")) && row.get("incarnation").getAsLong()>stacked.get(name);}}
        boolean damage=false;for(JsonElement seat:state.getAsJsonArray("players")){JsonObject row=seat.getAsJsonObject();if(!viewer.equals(text(row,"id")))damage=row.get("life").getAsLong()==19;}
        completed|=targetBound && departedWhileStacked && departed && resolved && damage && state.getAsJsonArray("stack").size()==0 && new JsonPrimitive(true).equals(prompt.get("is_priority"));return completed;
    }
    public void terminal(String outcome)throws IOException{throw new IOException("CHANGED_TARGET_UNEXPECTED_TERMINAL");}
    public JsonObject report(){JsonObject value=new JsonObject();value.addProperty("native_casting_case",key());value.addProperty("native_casting_case_completed",completed);value.addProperty("native_casting_case_source_verified",completed);value.addProperty("native_changed_target_bound",targetBound);value.addProperty("native_changed_target_departed_while_stacked",departedWhileStacked);return value;}
}

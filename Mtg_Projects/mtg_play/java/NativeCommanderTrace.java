import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Explicit Sidisi public-deck acceptance. Observes native transitions; never chooses responses. */
public final class NativeCommanderTrace {
    private final String scenario;
    private String commander,viewer,effect,effectName,zone;
    private long casts,stackInc=-1,libraryBefore=-1;
    private boolean battlefield,graveDeclined,returned,taxTwo,taxFour,effectBound,handSeen,complete;
    private Boolean answer;
    public NativeCommanderTrace(String scenario){this.scenario=scenario;}
    private static String text(JsonObject row,String key){JsonElement value=row.get(key);return value==null || value.isJsonNull()?"":value.getAsString();}
    private static JsonObject card(JsonObject state,String id,String zone){JsonArray rows=state.getAsJsonArray(zone);if(rows!=null)for(JsonElement row:rows)if(id.equals(text(row.getAsJsonObject(),"id")))return row.getAsJsonObject();for(JsonElement seat:state.getAsJsonArray("players")){rows=seat.getAsJsonObject().getAsJsonArray(zone);if(rows!=null)for(JsonElement row:rows)if(id.equals(text(row.getAsJsonObject(),"id")))return row.getAsJsonObject();}return null;}
    private static String location(JsonObject state,String id){for(String zone:new String[]{"hand","battlefield","graveyard","command","exile"})if(card(state,id,zone)!=null)return zone;return "";}
    private long library(JsonObject state){for(JsonElement seat:state.getAsJsonArray("players"))if(viewer.equals(text(seat.getAsJsonObject(),"id")))return seat.getAsJsonObject().get("library_count").getAsLong();return -1;}
    public String[] requested(JsonObject state){return effect!=null && !location(state,effect).isEmpty()?new String[]{effect}:new String[0];}
    public void before(JsonObject state,JsonObject prompt,JsonObject command){
        answer=null;
        if("GAME_ASK".equals(text(prompt,"kind")) && "boolean".equals(text(command,"kind")))answer=command.get("value").getAsBoolean();
        if(!"GAME_SELECT".equals(text(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || !"object".equals(text(command,"kind")))return;
        String id=text(command,"value");JsonObject selected=card(state,id,"hand");if(selected==null)selected=card(state,id,"battlefield");if(selected==null)return;
        String name=text(selected,"name");if(Arrays.asList("Baleful Mastery","Forever Young","Phyrexian Reclamation").contains(name)){effect=id;effectName=name;libraryBefore=library(state);effectBound=false;stackInc=-1;}
    }
    public void observe(JsonObject state,JsonObject metadata)throws IOException{
        if(!new JsonPrimitive("ok").equals(metadata.get("status")) || !state.get("cycle").equals(metadata.get("cycle")))return;
        viewer=text(state,"viewer");for(JsonElement item:metadata.getAsJsonArray("commanders")){JsonObject row=item.getAsJsonObject();if(!viewer.equals(text(row,"owner")))continue;if(!"Sidisi, Undead Vizier".equals(text(row,"name")))throw new IOException("COMMANDER_FIXTURE_SOURCE_UNPROVEN");commander=text(row,"id");casts=row.get("plays").getAsLong();taxTwo|=casts==1 && "{2}".equals(text(row,"tax"));taxFour|=casts==2 && "{4}".equals(text(row,"tax"));}
        if(commander==null)return;zone=location(state,commander);battlefield|=zone.equals("battlefield") && casts==1;
        graveDeclined|=battlefield && zone.equals("graveyard") && casts==1 && Boolean.FALSE.equals(answer);
        returned|=battlefield && zone.equals("command") && casts==1 && Boolean.TRUE.equals(answer);
        if(effect!=null)for(JsonElement item:state.getAsJsonArray("stack")){JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(text(item.getAsJsonObject(),"id"));if(entry!=null && effect.equals(text(entry,"source")) && (viewer.equals(text(entry,"owner")) || viewer.equals(text(entry,"controller")) && metadata.getAsJsonObject("objects").has(effect) && viewer.equals(text(metadata.getAsJsonObject("objects").getAsJsonObject(effect),"owner")))){effectBound=true;if(entry.has("source_incarnation"))stackInc=entry.get("source_incarnation").getAsLong();}}
        boolean spellResolved=false;if(effect!=null && effectBound && stackInc>=0 && card(state,effect,"graveyard")!=null){JsonObject row=metadata.getAsJsonObject("objects").getAsJsonObject(effect);spellResolved=row!=null && viewer.equals(text(row,"owner")) && row.get("incarnation").getAsLong()>stackInc;}
        boolean emptyStack=state.getAsJsonArray("stack").size()==0;
        if(scenario.equals("tax"))complete|=returned && casts>=2 && taxTwo && taxFour && zone.equals("battlefield");
        if(scenario.equals("grave-decline"))complete|=graveDeclined;
        if(scenario.startsWith("exile-"))complete|=returned && casts==2 && effectBound && spellResolved && emptyStack && "Baleful Mastery".equals(effectName) && zone.equals(scenario.endsWith("accept")?"command":"exile");
        if(scenario.startsWith("hand-") && graveDeclined && effectBound && "Phyrexian Reclamation".equals(effectName)){
            handSeen|=zone.equals("hand") && casts==1;
            complete|=scenario.endsWith("accept")?zone.equals("command") && casts==1 && emptyStack:handSeen && zone.equals("battlefield") && casts==1;
        }
        if(scenario.startsWith("library-") && graveDeclined && effectBound && spellResolved && emptyStack && "Forever Young".equals(effectName))complete|=scenario.endsWith("accept")?zone.equals("command") && casts==1 && library(state)==libraryBefore-1:zone.equals("hand") && casts==1 && library(state)==libraryBefore;
    }
    public boolean stop(){return complete && !scenario.equals("tax");}
    public JsonObject proof()throws IOException{if(!complete)throw new IOException("COMMANDER_SCENARIO_UNPROVEN");JsonObject result=new JsonObject();result.addProperty("scenario",scenario);result.addProperty("native_commander_scenario_verified",true);result.addProperty("native_command_zone_casts",casts);if(scenario.equals("tax"))result.addProperty("native_commander_tax_verified",taxTwo && taxFour && returned);if(scenario.equals("hand-decline"))result.addProperty("native_hand_cast_without_tax_verified",handSeen && casts==1);return result;}
}

import com.google.gson.*;
import java.io.IOException;

/** Explicit acceptance assertions over authenticated terminal native metadata; no response policy. */
public final class NativeCommanderProof {
    public static JsonObject terminal(JsonObject metadata,String viewer) throws IOException {
        if(!new JsonPrimitive("finished").equals(metadata.get("status")) || !new JsonPrimitive("win").equals(metadata.get("outcome")) || !new JsonPrimitive(viewer).equals(metadata.get("viewer")) || !new JsonPrimitive(true).equals(metadata.get("commander_metadata_complete")))throw new IOException("COMMANDER_RESULT_UNPROVEN");
        int own=0;boolean cast=true,lethal=false;
        for(JsonElement value:metadata.getAsJsonArray("commanders")){JsonObject commander=value.getAsJsonObject();if(!new JsonPrimitive(viewer).equals(commander.get("owner")))continue;own++;cast&=commander.has("plays") && commander.get("plays").getAsLong()>=1;
            for(JsonElement target:metadata.getAsJsonArray("public_players")){JsonObject player=target.getAsJsonObject();String id=player.get("id").getAsString();if(id.equals(viewer) || !new JsonPrimitive(true).equals(player.get("lost")) || player.get("life").getAsLong()<=0)continue;
                JsonElement damage=commander.has("damage")?commander.getAsJsonObject("damage").get(id):null;lethal|=damage!=null && damage.getAsLong()>=21;
            }
        }
        if(own<1 || !cast || !lethal)throw new IOException("COMMANDER_ACCEPTANCE_UNPROVEN");
        JsonObject result=new JsonObject();result.addProperty("native_commanders_cast",own);result.addProperty("native_commander_damage_lethal_verified",true);result.addProperty("native_commander_roster_cast_verified",true);return result;
    }
}

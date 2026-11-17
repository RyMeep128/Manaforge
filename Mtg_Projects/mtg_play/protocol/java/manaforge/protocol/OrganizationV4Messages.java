package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.util.*;
/** V4 positions never introduce identities or hidden membership. */
public final class OrganizationV4Messages {
    private OrganizationV4Messages(){}
    public static JsonObject parseContract(String raw) throws IOException {return OrganizationMessages.parseV4Contract(raw);}
    private static JsonObject legacy(JsonObject message){
        JsonObject copy=message.deepCopy(),body=copy.getAsJsonObject("body");copy.addProperty("organization_version",3);
        if(body.has("versions")){JsonArray versions=new JsonArray();versions.add(3);body.add("versions",versions);}
        if(body.has("seats"))for(JsonElement seat:body.getAsJsonArray("seats"))seat.getAsJsonObject().remove("placements");
        if(body.has("operation")){JsonObject op=body.getAsJsonObject("operation");if(op.get("kind").getAsString().equals("place")){op.addProperty("kind","move");op.add("x",JsonNull.INSTANCE);op.add("y",JsonNull.INSTANCE);op.addProperty("index",0);}}
        return copy;
    }
    public static JsonObject parse(String raw,OrganizationMessages.Context context) throws IOException {
        JsonObject message=parseContract(raw);OrganizationV3Messages.parse(legacy(message).toString(),context);
        if(message.getAsJsonObject("body").has("seats"))for(JsonElement token:message.getAsJsonObject("body").getAsJsonArray("seats")){
            JsonObject seat=token.getAsJsonObject();Set<String> roots=new HashSet<>(),seen=new HashSet<>();for(JsonElement h:seat.getAsJsonArray("root"))roots.add(h.getAsString());
            for(JsonElement p:seat.getAsJsonArray("placements")){String h=p.getAsJsonObject().get("handle").getAsString();if(!roots.contains(h) || !seen.add(h))throw new IOException("ORGANIZATION_CONTEXT");}
        }
        return message;
    }
    public static JsonObject parseReceipt(String raw,String epoch,Collection<String> pending) throws IOException {JsonObject message=parseContract(raw);OrganizationV3Messages.parseReceipt(legacy(message).toString(),epoch,pending);return message;}
    public static String upgrade(String raw,long gameplay) throws IOException {
        JsonObject message=OrganizationV3Messages.parseContract(OrganizationV3Messages.upgrade(raw,gameplay)),body=message.getAsJsonObject("body");message.addProperty("organization_version",4);
        if(body.has("seats"))for(JsonElement seat:body.getAsJsonArray("seats"))seat.getAsJsonObject().add("placements",new JsonArray());
        if(body.has("versions")){JsonArray versions=new JsonArray();versions.add(4);body.add("versions",versions);}
        String result=message.toString();parseContract(result);return result;
    }
}

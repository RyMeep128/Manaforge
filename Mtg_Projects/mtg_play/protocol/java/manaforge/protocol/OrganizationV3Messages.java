package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.util.Collection;
/** V3 adds shared presentation mode; legacy semantics still admit identity and context. */
public final class OrganizationV3Messages {
    private OrganizationV3Messages(){}
    public static JsonObject parseContract(String raw) throws IOException {return OrganizationMessages.parseV3Contract(raw);}
    public static JsonObject legacy(JsonObject message){
        JsonObject copy=message.deepCopy(),body=copy.getAsJsonObject("body");copy.addProperty("organization_version",1);body.remove("gameplay_revision");
        if(body.has("seats"))for(JsonElement seat:body.getAsJsonArray("seats"))for(JsonElement group:seat.getAsJsonObject().getAsJsonArray("groups"))group.getAsJsonObject().remove("presentation_mode");
        if(body.has("operation")){JsonObject op=body.getAsJsonObject("operation");op.remove("presentation_mode");if(op.get("kind").getAsString().equals("set_mode")){op.addProperty("kind","rename");op.addProperty("name","Mode");}}
        return copy;
    }
    public static JsonObject parse(String raw,OrganizationMessages.Context context) throws IOException {JsonObject message=parseContract(raw);OrganizationMessages.parse(legacy(message).toString(),context);return message;}
    public static JsonObject parseReceipt(String raw,String epoch,Collection<String> pending) throws IOException {JsonObject message=parseContract(raw);OrganizationMessages.parseReceipt(legacy(message).toString(),epoch,pending);return message;}
    public static String upgrade(String raw,long gameplay) throws IOException {
        JsonObject message=OrganizationMessages.parseContract(raw),body=message.getAsJsonObject("body");message.addProperty("organization_version",3);
        if(body.has("seats")){body.addProperty("gameplay_revision",gameplay);for(JsonElement seat:body.getAsJsonArray("seats"))for(JsonElement group:seat.getAsJsonObject().getAsJsonArray("groups"))group.getAsJsonObject().addProperty("presentation_mode","panel");}
        if(body.has("operation"))body.getAsJsonObject("operation").add("presentation_mode",JsonNull.INSTANCE);
        if(message.get("message_type").getAsString().equals("organization_capabilities")){JsonArray versions=new JsonArray();versions.add(3);body.add("versions",versions);}
        String result=message.toString();parseContract(result);return result;
    }
}

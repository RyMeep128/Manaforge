package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.util.Collection;
/** V2 adds exact gameplay correlation; v1 semantic admission remains shared. */
public final class OrganizationV2Messages {
    private OrganizationV2Messages(){}
    public static JsonObject parseContract(String raw) throws IOException {return OrganizationMessages.parseV2Contract(raw);}
    public static JsonObject legacy(JsonObject message){JsonObject copy=message.deepCopy();copy.addProperty("organization_version",1);copy.getAsJsonObject("body").remove("gameplay_revision");return copy;}
    public static JsonObject parse(String raw,OrganizationMessages.Context context) throws IOException {JsonObject message=parseContract(raw);OrganizationMessages.parse(legacy(message).toString(),context);return message;}
    public static JsonObject parseReceipt(String raw,String epoch,Collection<String> pending) throws IOException {JsonObject message=parseContract(raw);OrganizationMessages.parseReceipt(legacy(message).toString(),epoch,pending);return message;}
    public static String upgrade(String raw,long gameplayRevision) throws IOException {JsonObject message=OrganizationMessages.parseContract(raw);message.addProperty("organization_version",2);if(message.get("message_type").getAsString().equals("organization_snapshot"))message.getAsJsonObject("body").addProperty("gameplay_revision",gameplayRevision);if(message.get("message_type").getAsString().equals("organization_capabilities")){JsonArray versions=new JsonArray();versions.add(2);message.getAsJsonObject("body").add("versions",versions);}String result=message.toString();parseContract(result);return result;}
}

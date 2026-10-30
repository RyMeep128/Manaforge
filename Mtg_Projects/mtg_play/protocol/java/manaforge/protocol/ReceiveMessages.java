package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Fixed generated DTO-schema subset; strict bounded WireEnvelope parsing always runs first. */
public final class ReceiveMessages {
    private static final JsonObject definitions=JsonParser.parseString(ReceiveContractSchema.JSON).getAsJsonObject().getAsJsonObject("$defs");
    private static boolean valid(JsonElement value, JsonElement element) {
        if (element.isJsonPrimitive()) return element.getAsBoolean();
        JsonObject rule = element.getAsJsonObject();
        if (rule.has("$ref")) {
            String[] parts = rule.get("$ref").getAsString().split("/");
            return valid(value, definitions.get(parts[parts.length - 1]));
        }
        if (rule.has("anyOf")) {
            boolean found = false;
            for (JsonElement part : rule.getAsJsonArray("anyOf")) found |= valid(value, part);
            if (!found) return false;
        }
        if (rule.has("enum")) {
            boolean found = false;
            for (JsonElement option : rule.getAsJsonArray("enum")) found |= value.equals(option);
            if (!found) return false;
        }
        if (rule.has("const") && !value.equals(rule.get("const"))) return false;
        if (rule.has("type")) {
            String type = rule.get("type").getAsString();
            boolean matches;
            switch (type) {
                case "null": matches = value.isJsonNull(); break;
                case "string": matches = value.isJsonPrimitive() && value.getAsJsonPrimitive().isString(); break;
                case "boolean": matches = value.isJsonPrimitive() && value.getAsJsonPrimitive().isBoolean(); break;
                case "integer": matches = value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber()
                    && value.getAsBigDecimal().stripTrailingZeros().scale() <= 0; break;
                case "object": matches = value.isJsonObject(); break;
                case "array": matches = value.isJsonArray(); break;
                default: throw new IllegalArgumentException("Unsupported fixture schema type");
            }
            if (!matches) return false;
        }
        if (rule.has("minimum") && value.getAsBigDecimal().compareTo(rule.get("minimum").getAsBigDecimal()) < 0) return false;
        if (value.isJsonObject()) {
            JsonObject object = value.getAsJsonObject();
            if (rule.has("required"))
                for (JsonElement key : rule.getAsJsonArray("required"))
                    if (!object.has(key.getAsString())) return false;
            if (rule.has("properties")) {
                JsonObject properties = rule.getAsJsonObject("properties");
                for (Map.Entry<String, JsonElement> property : object.entrySet()) {
                    if (properties.has(property.getKey())) {
                        if (!valid(property.getValue(), properties.get(property.getKey()))) return false;
                    } else if (rule.has("additionalProperties") && !rule.get("additionalProperties").getAsBoolean()) return false;
                }
            }
        }
        if (value.isJsonArray()) {
            JsonArray array = value.getAsJsonArray();
            if (rule.has("minItems") && array.size() < rule.get("minItems").getAsInt()) return false;
            if (rule.has("maxItems") && array.size() > rule.get("maxItems").getAsInt()) return false;
            JsonArray prefix = rule.getAsJsonArray("prefixItems");
            for (int i = 0; i < array.size(); i++) {
                JsonElement item = prefix != null && i < prefix.size() ? prefix.get(i) : rule.get("items");
                if (item != null && !valid(array.get(i), item)) return false;
            }
        }
        if (rule.has("allOf"))
            for (JsonElement part : rule.getAsJsonArray("allOf")) if (!valid(value, part)) return false;
        if (rule.has("if") && valid(value, rule.get("if")) && rule.has("then") && !valid(value, rule.get("then"))) return false;
        return true;
    }


    private static void fail(String code) throws WireEnvelope.EnvelopeException { throw new WireEnvelope.EnvelopeException(code); }
    private static boolean unique(JsonArray items,String key) {
        Set<String> seen=new HashSet<>();
        for(JsonElement item:items) { String id=item.getAsJsonObject().get(key).getAsString();if(id.isEmpty() || !seen.add(id))return false; }
        return true;
    }
    private static boolean string(JsonElement value) { return value!=null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString(); }
    public static JsonObject parse(String text,String session,String viewer,long minimumRevision,boolean fixtureMode) throws IOException {
        JsonObject envelope=WireEnvelope.parse(text),body=envelope.getAsJsonObject("body");
        String type=envelope.get("message_type").getAsString();
        if(!Arrays.asList("snapshot","event","result").contains(type))fail("RECEIVE_UNSUPPORTED");
        if(!body.has("fixture_only") || !body.get("fixture_only").isJsonPrimitive() || !body.get("fixture_only").getAsJsonPrimitive().isBoolean())fail("RECEIVE_SHAPE");
        if(body.get("fixture_only").getAsBoolean()!=fixtureMode)fail("RECEIVE_MODE");
        String receivedSession,receivedViewer;long revision;
        if(type.equals("event")) {
            if(body.size()!=4 || !string(body.get("session_id")) || !string(body.get("viewer_id"))
                || !body.has("event") || !valid(body.get("event"),definitions.get("GameEvent")))fail("RECEIVE_SHAPE");
            receivedSession=body.get("session_id").getAsString();receivedViewer=body.get("viewer_id").getAsString();revision=body.getAsJsonObject("event").get("revision").getAsLong();
        } else {
            if(body.size()!=2 || !body.has("snapshot") || !valid(body.get("snapshot"),definitions.get("GameSnapshot")))fail("RECEIVE_SHAPE");
            JsonObject snapshot=body.getAsJsonObject("snapshot");
            receivedSession=snapshot.get("session_id").getAsString();receivedViewer=snapshot.get("viewer_id").getAsString();revision=snapshot.get("revision").getAsLong();
            if(type.equals("result") && (!snapshot.get("status").getAsString().equals("finished") || !string(snapshot.get("result")) || snapshot.get("result").getAsString().isEmpty()))fail("RECEIVE_SHAPE");
            if(!unique(snapshot.getAsJsonArray("players"),"player_id") || !unique(snapshot.getAsJsonArray("objects"),"object_id") || !unique(snapshot.getAsJsonArray("actions"),"action_id"))fail("RECEIVE_CONTEXT");
            if(!snapshot.get("decision").isJsonNull() && !snapshot.getAsJsonObject("decision").get("player_id").getAsString().equals(viewer))fail("RECEIVE_VIEWER");
        }
        if(!receivedSession.equals(session))fail("RECEIVE_SESSION");
        if(!receivedViewer.equals(viewer))fail("RECEIVE_VIEWER");
        if(revision<minimumRevision)fail("RECEIVE_REVISION");
        return envelope;
    }
}

package manaforge.protocol;

import com.google.gson.*;
import com.google.gson.stream.JsonReader;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

/** Test-only validator for the exported schema subset, not a live gateway parser. */
public final class FixtureConsumer {
    private final JsonObject definitions;
    private final Gson gson = new GsonBuilder().serializeNulls().create();

    private FixtureConsumer(JsonObject schema) {
        definitions = schema.getAsJsonObject("$defs");
    }

    private static JsonElement read(Path path) throws Exception {
        JsonReader reader = new JsonReader(new StringReader(new String(Files.readAllBytes(path), StandardCharsets.UTF_8)));
        reader.setStrictness(Strictness.STRICT);
        return JsonParser.parseReader(reader);
    }

    private boolean valid(JsonElement value, JsonElement element) {
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

    private int check(Path path, boolean expected) throws Exception {
        int count = 0;
        for (JsonElement item : read(path).getAsJsonObject().getAsJsonArray("cases")) {
            JsonObject fixture = item.getAsJsonObject();
            String record = fixture.get("record").getAsString();
            if (!definitions.has(record)) throw new AssertionError("Unknown fixture record");
            JsonElement payload = fixture.get("payload");
            if (valid(payload, definitions.get(record)) != expected)
                throw new AssertionError("Fixture validation mismatch: " + fixture.get("name").getAsString());
            if (expected) {
                Class<?> type = Class.forName("manaforge.protocol.PlayContracts$" + record);
                Object model = gson.fromJson(payload, type);
                if (!payload.equals(gson.toJsonTree(model))) throw new AssertionError("DTO round-trip lost data");
            }
            count++;
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        Path directory = Paths.get(args[0]);
        FixtureConsumer consumer = new FixtureConsumer(read(directory.resolve("python-contracts-v1.schema.json")).getAsJsonObject());
        int positive = consumer.check(directory.resolve("fixtures/python-baseline-v1.json"), true);
        int negative = consumer.check(directory.resolve("fixtures/python-negative-v1.json"), false);
        if (positive < 9 || negative < 12) throw new AssertionError("Missing fixture coverage");
        System.out.println("Java fixture DTOs: " + positive + " positive round-trips, " + negative + " negative rejections");
    }
}

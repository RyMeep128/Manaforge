package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
public final class EnvelopeFixtureConsumer {
    public static void main(String[] args) throws Exception {
        JsonObject corpus = JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8)).getAsJsonObject();
        if (corpus.get("max_depth").getAsInt() != WireEnvelope.MAX_DEPTH) throw new AssertionError("Depth mismatch");
        for (JsonElement item : corpus.getAsJsonArray("positive")) {
            String text = item.getAsJsonObject().get("text").getAsString();
            if (!WireEnvelope.parse(text).equals(JsonParser.parseString(text))) throw new AssertionError("Roundtrip mismatch");
        }
        for (JsonElement item : corpus.getAsJsonArray("negative")) {
            JsonObject test = item.getAsJsonObject();
            try { WireEnvelope.parse(test.get("text").getAsString()); throw new AssertionError("Accepted " + test.get("name")); }
            catch (WireEnvelope.EnvelopeException error) {
                if (!error.code.equals(test.get("code").getAsString())) throw new AssertionError(test.get("name") + " code " + error.code);
            }
        }
        System.out.println("Envelope corpus passed: " + corpus.getAsJsonArray("positive").size() + " positive / " + corpus.getAsJsonArray("negative").size() + " negative");
    }
}

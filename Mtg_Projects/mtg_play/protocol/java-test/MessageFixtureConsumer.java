package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
public final class MessageFixtureConsumer {
    public static void main(String[] args) throws Exception {
        JsonObject corpus = JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8)).getAsJsonObject();
        for (JsonElement test : corpus.getAsJsonArray("positive")) {
            JsonElement envelope = test.getAsJsonObject().get("envelope");
            if (!WireMessages.parse(envelope.toString()).equals(envelope)) throw new AssertionError("Body roundtrip");
        }
        for (JsonElement item : corpus.getAsJsonArray("negative")) {
            JsonObject test = item.getAsJsonObject();
            try { WireMessages.parse(test.get("envelope").toString()); throw new AssertionError("Accepted " + test.get("name")); }
            catch (WireEnvelope.EnvelopeException error) {
                if (!error.code.equals(test.get("code").getAsString())) throw new AssertionError("Incorrect safe code " + test.get("name"));
            }
        }
        for (JsonElement item : corpus.getAsJsonArray("current")) {
            JsonObject test = item.getAsJsonObject();
            String code = WireMessages.checkCurrent(test.get("envelope").toString(), "session", "seat-one", 7, "decision", Arrays.asList("action"));
            String expected = test.get("code").isJsonNull() ? null : test.get("code").getAsString();
            if (!Objects.equals(code, expected)) throw new AssertionError("Current-decision check " + test.get("name"));
        }
        System.out.println("Message bodies passed: " + corpus.getAsJsonArray("positive").size() + " positive / " + corpus.getAsJsonArray("negative").size() + " negative / 6 current-decision checks");
    }
}

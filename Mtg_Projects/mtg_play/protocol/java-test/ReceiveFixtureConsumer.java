package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
public final class ReceiveFixtureConsumer {
    private static void parse(JsonObject test) throws Exception {
        ReceiveMessages.parse(test.get("envelope").toString(),test.get("session").getAsString(),test.get("viewer").getAsString(),test.get("minimum_revision").getAsLong(),test.get("fixture_mode").getAsBoolean());
    }
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        for(JsonElement item:corpus.getAsJsonArray("positive"))parse(item.getAsJsonObject());
        for(JsonElement item:corpus.getAsJsonArray("negative")) {
            JsonObject test=item.getAsJsonObject();
            try { parse(test);throw new AssertionError("Accepted "+test.get("name")); }
            catch(WireEnvelope.EnvelopeException error) { if(!error.code.equals(test.get("code").getAsString()))throw new AssertionError(test.get("name")+" code "+error.code); }
        }
        System.out.println("Receive bodies: "+corpus.getAsJsonArray("positive").size()+" positive / "+corpus.getAsJsonArray("negative").size()+" negative passed");
    }
}

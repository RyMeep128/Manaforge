package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
public final class ErrorFixtureConsumer {
    private static String parse(JsonObject test) throws Exception {
        return SessionErrors.parse(test.get("envelope").toString(),test.get("session").isJsonNull()?null:test.get("session").getAsString(),test.get("viewer").getAsString());
    }
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        for(JsonElement item:corpus.getAsJsonArray("positive")) {
            JsonObject test=item.getAsJsonObject();
            if(!parse(test).equals(test.getAsJsonObject("envelope").getAsJsonObject("body").get("code").getAsString()))throw new AssertionError("Lost error category");
        }
        for(JsonElement item:corpus.getAsJsonArray("negative")) {
            JsonObject test=item.getAsJsonObject();
            try { parse(test);throw new AssertionError("Accepted "+test.get("name")); }
            catch(WireEnvelope.EnvelopeException error) {
                if(!error.code.equals(test.get("code").getAsString()) || !error.getMessage().equals(error.code)) throw new AssertionError(test.get("name")+" wrong safe category");
            }
        }
        System.out.println("Session errors: "+corpus.getAsJsonArray("positive").size()+" positive / "+corpus.getAsJsonArray("negative").size()+" negative passed");
    }
}

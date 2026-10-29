import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import com.google.gson.*;
import mage.cards.repository.CardRepository;
import mage.cards.repository.CardInfo;

/** Gives the owned server a stdin shutdown channel, allowing normal JVM shutdown hooks. */
public final class ManaforgeServerHost {
    public static void main(String[] args) throws Exception {
        Thread control = new Thread(() -> {
            try {
                BufferedReader input = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
                String line;
                while ((line = input.readLine()) != null) {
                    if (line.equals("shutdown")) System.exit(0);
                    JsonObject command = JsonParser.parseString(line).getAsJsonObject();
                    String id = java.util.UUID.fromString(command.get("request_id").getAsString()).toString();
                    JsonArray results = new JsonArray();
                    for (JsonElement element : command.getAsJsonArray("cards")) {
                        JsonObject query = element.getAsJsonObject();
                        String name = query.get("name").getAsString();
                        CardInfo card = CardRepository.instance.findCardWithPreferredSetAndNumber(
                            name, query.get("set").getAsString(), query.get("number").getAsString());
                        JsonObject result = new JsonObject();
                        result.addProperty("key", query.get("key").getAsString());
                        if (card == null || !card.getName().equals(name)) {
                            result.addProperty("error", "CARD_NOT_SUPPORTED");
                        } else {
                            result.addProperty("name", card.getName());
                            result.addProperty("set", card.getSetCode());
                            result.addProperty("number", card.getCardNumber());
                        }
                        results.add(result);
                    }
                    Path responses = Paths.get("manaforge-responses");
                    Files.createDirectories(responses);
                    Path temporary = responses.resolve(id + ".tmp");
                    Files.write(temporary, new Gson().toJson(results).getBytes(StandardCharsets.UTF_8));
                    Files.move(temporary, responses.resolve(id + ".json"), StandardCopyOption.ATOMIC_MOVE);

                }
                System.exit(0); // The owning Python process closed its pipe.
            } catch (Exception error) {
                error.printStackTrace(System.err);
                System.exit(1);
            }
        }, "manaforge-server-control");
        control.setDaemon(true);
        control.start();
        mage.server.Main.main(args);
    }
}

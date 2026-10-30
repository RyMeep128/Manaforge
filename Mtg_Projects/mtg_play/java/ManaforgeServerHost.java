import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import com.google.gson.*;
import mage.cards.repository.CardRepository;
import mage.cards.repository.CardInfo;
import mage.cards.decks.Deck;
import mage.cards.decks.DeckValidator;
import mage.cards.decks.DeckValidatorFactory;

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
                    JsonElement results;
                    if (command.has("command") && command.get("command").getAsString().equals("validate_deck")) {
                        results = validateDeck(command);
                    } else if (command.has("command") && command.get("command").getAsString().equals("metadata")) {
                        try {
                            results = ManaforgeGameMetadata.read(command);
                        } catch (java.util.ConcurrentModificationException retry) {
                            JsonObject result = new JsonObject(); result.addProperty("status", "retry"); results = result;
                        } catch (ReflectiveOperationException incompatible) {
                            JsonObject result = new JsonObject(); result.addProperty("status", "error");
                            result.addProperty("code", "PINNED_METADATA_INTERFACE_CHANGED"); results = result;
                        }
                    } else if (command.has("command") && command.get("command").getAsString().equals("printing_names")) {
                        JsonObject names = new JsonObject();
                        for (JsonElement value : command.getAsJsonArray("printings")) {
                            JsonObject query = value.getAsJsonObject();
                            CardInfo card = CardRepository.instance.findCard(query.get("set").getAsString(), query.get("number").getAsString());
                            if (card != null) names.addProperty(query.get("key").getAsString(), card.getName());
                        }
                        results = names;
                    } else {
                    JsonArray resolved = new JsonArray();
                    for (JsonElement element : command.getAsJsonArray("cards")) {
                        JsonObject query = element.getAsJsonObject();
                        String name = query.get("name").getAsString();
                        CardInfo card = CardRepository.instance.findCardWithPreferredSetAndNumber(
                            name, query.get("set").getAsString(), query.get("number").getAsString());
                        boolean alias = false;
                        if ((card == null || !card.getName().equals(name)) && name.contains(" // ")) {
                            String[] faces = name.split(" // ", 2);
                            CardInfo front = CardRepository.instance.findCardWithPreferredSetAndNumber(
                                faces[0], query.get("set").getAsString(), query.get("number").getAsString());
                            if (front != null && front.getName().equals(faces[0])
                                    && java.util.Arrays.asList(front.getSecondSideName(), front.getDoubleFacedSecondSideName(),
                                        front.getFlipCardName(), front.getSpellOptionCardName()).contains(faces[1])) {
                                card = front; alias = true;
                            }
                        }
                        JsonObject result = new JsonObject();
                        result.addProperty("key", query.get("key").getAsString());
                        if (card == null || (!alias && !card.getName().equals(name))) {
                            result.addProperty("error", "CARD_NOT_SUPPORTED");
                        } else {
                            String selectedSet = query.get("set").getAsString();
                            String selectedNumber = query.get("number").getAsString();
                            if ((!selectedSet.isEmpty() && !selectedSet.equalsIgnoreCase(card.getSetCode()))
                                    || (!selectedNumber.isEmpty() && !selectedNumber.equals(card.getCardNumber()))) {
                                result.addProperty("error", "PRINTING_NOT_RESOLVED");
                                resolved.add(result);
                                continue;
                            }
                            result.addProperty("name", card.getName());
                            result.addProperty("set", card.getSetCode());
                            result.addProperty("number", card.getCardNumber());
                        }
                        resolved.add(result);
                    }
                    results = resolved;
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

    private static JsonObject validateDeck(JsonObject command) {
        JsonObject result = new JsonObject();
        String format = command.get("format").getAsString();
        String deckType;
        if (format.equals("freeform")) deckType = "Constructed - Freeform Unlimited";
        else if (format.equals("commander")) deckType = "Variant Magic - Commander";
        else {
            result.addProperty("code", "UNSUPPORTED_GAME_SETUP");
            return result;
        }
        DeckValidator validator = DeckValidatorFactory.instance.createDeckValidator(deckType);
        if (validator == null) {
            result.addProperty("code", "ENGINE_VALIDATOR_UNAVAILABLE");
            return result;
        }
        // Match the pinned server's join-table load/validation path. Never return
        // validator messages: they can contain private deck names and card data.
        try {
            boolean eligible = validator.validate(Deck.load(ManaforgeBridge.deck(command), false, false));
            result.addProperty("eligible", eligible);
        } catch (mage.game.GameException unsupported) {
            result.addProperty("code", "ENGINE_DECK_LOAD_FAILED");
        }
        return result;
    }
}

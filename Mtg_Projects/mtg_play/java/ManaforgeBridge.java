import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import mage.view.*;
import mage.cards.decks.*;
import mage.game.match.MatchOptions;
import mage.players.PlayerType;
import com.google.gson.JsonParser;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import mage.interfaces.MageClient;
import mage.interfaces.callback.ClientCallback;
import mage.players.net.UserData;
import mage.remote.Connection;
import mage.remote.SessionImpl;
import mage.utils.MageVersion;

/** Minimal headless client: no MageFrame or desktop-client dependency. */
public final class ManaforgeBridge implements MageClient {
    private static final PrintStream PROTOCOL = System.out;
    private static final Gson JSON = new Gson();
    private final SessionImpl session = new SessionImpl(this);

    private volatile UUID gameId;
    private volatile int decisionId = -1;
    private volatile String decisionMethod;
    private volatile int amountMin;
    private volatile int amountMax;
    private volatile boolean decisionCancellable;
    private volatile boolean decisionFinishable;
    private int lastDecisionMessageId = -1;
    private int lastStateMessageId = -1;

    private static synchronized void emit(String event, String requestId, JsonObject data) {
        data.addProperty("protocol", 1);
        data.addProperty("event", event);
        if (requestId != null) data.addProperty("request_id", requestId);
        PROTOCOL.println(JSON.toJson(data));
        PROTOCOL.flush();
    }

    private static PlayerType controllerType(String controller) {
        if (controller.equals("local_human")) return PlayerType.HUMAN;
        if (controller.equals("engine_ai")) return PlayerType.COMPUTER_MAD;
        throw new IllegalArgumentException("UNSUPPORTED_CONTROLLER");
    }

    private static void message(String event, String id, String text) {
        JsonObject data = new JsonObject();
        data.addProperty("message", text);
        emit(event, id, data);
    }

    @Override public MageVersion getVersion() { return new MageVersion(SessionImpl.class); }
    @Override public void connected(String text) { message("connection", null, text); }
    @Override public void disconnected(boolean reconnect, boolean keep) {
        message("disconnected", null, "Disconnected from XMage");
    }
    @Override public void showMessage(String text) { message("message", null, text); }
    @Override public void showError(String text) { message("error", null, text); }
    @Override public void onNewConnection() { message("transport_connected", null, "Transport ready"); }
    @Override public synchronized void onCallback(ClientCallback callback) {
        JsonObject data = new JsonObject();
        data.addProperty("method", callback.getMethod().name());
        data.addProperty("message_id", callback.getMessageId());
        emit("callback", null, data);
        try {
            callback.decompressData();
            String method = callback.getMethod().name();
            if (method.equals("START_GAME")) {
                TableClientMessage start = (TableClientMessage) callback.getData();
                gameId = start.getGameId();
                JsonObject started = new JsonObject();
                started.addProperty("game_id", gameId.toString());
                started.addProperty("player_id", start.getPlayerId().toString());
                emit("game_started", null, started);
                if (!session.joinGame(gameId)) throw new IllegalStateException("Cannot join game");
            }
            if (method.equals("GAME_ERROR")) message("error", null, "ENGINE_GAME_FAILED");
            if (method.equals("USER_REQUEST_DIALOG") || method.equals("SIDEBOARD") || method.equals("CONSTRUCT"))
                message("error", null, "UNSUPPORTED_DECISION: " + method);
            Object payload = callback.getData();
            GameView view = payload instanceof GameView ? (GameView) payload : null;
            if (payload instanceof GameClientMessage) view = ((GameClientMessage) payload).getGameView();
            if (payload instanceof AbilityPickerView) view = ((AbilityPickerView) payload).getGameView();
            if (view != null && gameId == null) gameId = callback.getObjectId();
            if (view != null && callback.getMessageId() > lastStateMessageId) {
                lastStateMessageId = callback.getMessageId();
                JsonObject snapshot = state(view);
                snapshot.addProperty("sequence", callback.getMessageId());
                emit("game_state", null, snapshot);
            }
            if (method.equals("GAME_ASK") || method.equals("GAME_SELECT")
                    || method.equals("GAME_TARGET") || method.equals("GAME_GET_AMOUNT")
                    || method.equals("GAME_CHOOSE_CHOICE") || method.equals("GAME_PLAY_MANA")
                    || method.equals("GAME_GET_MULTI_AMOUNT") || method.equals("GAME_CHOOSE_PILE")) {
                GameClientMessage prompt = (GameClientMessage) payload;
                if (callback.getMessageId() <= lastDecisionMessageId) return;
                lastDecisionMessageId = callback.getMessageId();
                decisionId = callback.getMessageId();
                decisionMethod = method;
                JsonObject choice = new JsonObject();
                choice.addProperty("decision_id", decisionId);
                choice.addProperty("cycle", view == null ? -1 : view.getGameCycle());
                choice.addProperty("kind", method);
                choice.addProperty("message", prompt.getMessage());
                choice.addProperty("min", prompt.getMin());
                choice.addProperty("max", prompt.getMax());
                amountMin = prompt.getMin(); amountMax = prompt.getMax();
                JsonArray targetCards = new JsonArray();
                if (prompt.getCardsView1() != null) for (CardView candidate : prompt.getCardsView1().values()) targetCards.add(card(candidate));
                choice.add("cards", targetCards);
                JsonArray secondPile = new JsonArray();
                if (prompt.getCardsView2() != null) for (CardView candidate : prompt.getCardsView2().values()) secondPile.add(card(candidate));
                choice.add("second_pile", secondPile);
                JsonArray amounts = new JsonArray();
                if (prompt.getMessages() != null) for (mage.util.MultiAmountMessage amount : prompt.getMessages()) {
                    JsonObject row = new JsonObject();
                    row.addProperty("message", amount.message); row.addProperty("min", amount.min);
                    row.addProperty("max", amount.max); row.addProperty("default", amount.defaultValue);
                    amounts.add(row);
                }
                choice.add("amounts", amounts);
                decisionCancellable = method.equals("GAME_PLAY_MANA")

                    || (method.equals("GAME_CHOOSE_CHOICE") && !prompt.getChoice().isRequired())
                    || (method.equals("GAME_GET_MULTI_AMOUNT") && prompt.getOptions() != null && Boolean.TRUE.equals(prompt.getOptions().get("canCancel")));
                decisionFinishable = method.equals("GAME_TARGET") && !prompt.isFlag();
                choice.addProperty("cancellable", decisionCancellable);
                choice.addProperty("can_finish", decisionFinishable);
                if (prompt.getOptions() != null) {
                    choice.add("selected_targets", JSON.toJsonTree(prompt.getOptions().get("chosenTargets")));
                    choice.add("attackers", JSON.toJsonTree(prompt.getOptions().get(mage.constants.Constants.Option.POSSIBLE_ATTACKERS)));
                    choice.add("blockers", JSON.toJsonTree(prompt.getOptions().get(mage.constants.Constants.Option.POSSIBLE_BLOCKERS)));
                }
                choice.add("targets", JSON.toJsonTree(prompt.getTargets()));
                if (prompt.getChoice() != null) {
                    choice.addProperty("message", prompt.getChoice().getMessage());
                    choice.addProperty("required", prompt.getChoice().isRequired());
                    choice.add("choices", JSON.toJsonTree(prompt.getChoice().getChoices()));
                    choice.add("key_choices", JSON.toJsonTree(prompt.getChoice().getKeyChoices()));
                }
                emit("decision", null, choice);
            } else if (method.equals("GAME_CHOOSE_ABILITY")) {
                AbilityPickerView picker = (AbilityPickerView) payload;
                decisionCancellable = false;
                if (callback.getMessageId() <= lastDecisionMessageId) return;
                lastDecisionMessageId = callback.getMessageId();
                decisionId = callback.getMessageId();
                decisionMethod = method;
                JsonObject choice = new JsonObject();
                choice.addProperty("decision_id", decisionId);
                choice.addProperty("cycle", view == null ? -1 : view.getGameCycle());
                choice.addProperty("kind", method);
                choice.addProperty("message", picker.getMessage());
                choice.add("key_choices", JSON.toJsonTree(picker.getChoices()));
                emit("decision", null, choice);
            } else if (method.startsWith("GAME_CHOOSE_") || method.equals("GAME_PLAY_MANA")
                    || method.equals("GAME_PLAY_XMANA") || method.equals("GAME_GET_AMOUNT")
                    || method.equals("GAME_GET_MULTI_AMOUNT")) {
                message("error", null, "UNSUPPORTED_DECISION: " + method);
            }
            if (method.equals("END_GAME_INFO") && payload instanceof GameEndView) {
                JsonObject result = new JsonObject();
                result.addProperty("won", ((GameEndView) payload).hasWon());
                emit("game_result", null, result);
            }
            if (method.equals("GAME_OVER")) {
                decisionId = -1;
                message("game_over", null, "Engine confirmed game over");
            }
        } catch (Exception error) {
            error.printStackTrace(System.err);
            message("error", null, "GAME_CALLBACK_FAILED: " + error.getClass().getSimpleName());
        }
    }

    private static JsonObject card(CardView card) {
        JsonObject item = new JsonObject();
        item.addProperty("id", card.getId().toString());
        boolean hidden = card.isFaceDown() || card.hideInfo();
        item.addProperty("hidden", hidden);
        item.addProperty("face_down", card.isFaceDown());
        if (!hidden) {
            item.addProperty("name", card.getName());
            item.addProperty("set", card.getExpansionSetCode());
            item.addProperty("number", card.getCardNumber());
            item.addProperty("token", card.isToken());
            item.addProperty("loyalty", card.getLoyalty());
            item.addProperty("defense", card.getDefense());
            item.addProperty("transformed", card.isTransformed());
            JsonArray counters = new JsonArray();
            if (card.getCounters() != null) for (CounterView counter : card.getCounters()) {
                JsonArray value = new JsonArray(); value.add(counter.getName()); value.add(counter.getCount()); counters.add(value);
            }
            item.add("counters", counters);
            item.addProperty("power", card.getPower());
            item.addProperty("toughness", card.getToughness());
            item.addProperty("type", card.getTypeText());
            item.addProperty("color", card.getColorText());
            // Rules are the engine's view text, not a substitute for full dynamic abilities.
            item.add("view_rules", JSON.toJsonTree(card.getRules()));
        }
        if (card instanceof PermanentView) {
            PermanentView permanent = (PermanentView) card;
            item.addProperty("tapped", permanent.isTapped());
            item.addProperty("flipped", permanent.isFlipped());
            item.addProperty("copy", permanent.isCopy());
            item.add("attachments", JSON.toJsonTree(permanent.getAttachments()));
            item.addProperty("attached_to", permanent.getAttachedTo() == null ? null : permanent.getAttachedTo().toString());
            item.addProperty("damage", permanent.getDamage());
            item.addProperty("owner_name", permanent.getNameOwner());
            item.addProperty("controller_name", permanent.getNameController());
            item.addProperty("can_attack", permanent.isCanAttack());
            item.addProperty("can_block", permanent.isCanBlock());
        }
        return item;
    }

    private static JsonObject observation(SimpleCardView card, String source) {
        JsonObject observation = new JsonObject();
        observation.addProperty("source", source);
        boolean hidden = card instanceof CardView
            ? ((CardView) card).hideInfo() || ((CardView) card).isFaceDown()
            : card.getExpansionSetCode() == null || card.getExpansionSetCode().isEmpty()
                || card.getCardNumber() == null || card.getCardNumber().equals("0");
        observation.addProperty("hidden", hidden);
        if (!hidden) {
            observation.addProperty("set", card.getExpansionSetCode());
            observation.addProperty("number", card.getCardNumber());
            if (card instanceof CardView) observation.addProperty("name", ((CardView) card).getName());
        }
        // Deliberately omit engine object IDs: a past observation must not identify
        // the corresponding object after concealment or a hidden-zone shuffle.
        return observation;
    }

    private JsonObject state(GameView view) {
        JsonObject data = new JsonObject();
        data.addProperty("game_id", gameId == null ? null : gameId.toString());
        data.addProperty("turn", view.getTurn());
        data.addProperty("cycle", view.getGameCycle());
        data.addProperty("viewer", view.getMyPlayer() == null ? null : view.getMyPlayer().getPlayerId().toString());
        data.add("phase", JSON.toJsonTree(view.getPhase() == null ? null : view.getPhase().name()));
        data.add("step", JSON.toJsonTree(view.getStep() == null ? null : view.getStep().name()));
        data.addProperty("active_player", view.getActivePlayerName());
        data.addProperty("priority_player", view.getPriorityPlayerName());
        JsonArray players = new JsonArray();
        for (PlayerView player : view.getPlayers()) {
            JsonObject row = new JsonObject();
            row.addProperty("id", player.getPlayerId().toString());
            row.addProperty("name", player.getName());
            row.addProperty("life", player.getLife());
            row.addProperty("left", player.hasLeft());
            JsonArray mana = new JsonArray();
            ManaPoolView pool = player.getManaPool();
            if (pool != null) {
                String[] colors = {"white", "blue", "black", "red", "green", "colorless"};
                int[] amounts = {pool.getWhite(), pool.getBlue(), pool.getBlack(), pool.getRed(), pool.getGreen(), pool.getColorless()};
                for (int index = 0; index < colors.length; index++) {
                    JsonArray value = new JsonArray(); value.add(colors[index]); value.add(amounts[index]); mana.add(value);
                }
            }
            row.add("mana", mana);
            JsonArray counters = new JsonArray();
            for (CounterView counter : player.getCounters()) {
                JsonArray value = new JsonArray(); value.add(counter.getName()); value.add(counter.getCount()); counters.add(value);
            }
            row.add("counters", counters);
            JsonArray graveyard = new JsonArray();
            for (CardView card : player.getGraveyard().values()) graveyard.add(card(card));
            row.add("graveyard", graveyard);
            JsonArray commandZone = new JsonArray();
            for (CommandObjectView object : player.getCommandObjectList())
                if (object instanceof CommanderView) commandZone.add(card((CardView) object));
            row.add("command", commandZone);
            row.addProperty("hand_count", player.getHandCount());
            row.addProperty("library_count", player.getLibraryCount());
            JsonArray battlefield = new JsonArray();
            for (PermanentView permanent : player.getBattlefield().values()) battlefield.add(card(permanent));
            row.add("battlefield", battlefield);
            players.add(row);
        }
        data.add("players", players);
        JsonArray observations = new JsonArray();
        for (RevealedView revealed : view.getRevealed())
            for (CardView card : revealed.getCards().values()) observations.add(observation(card, "revealed"));
        for (RevealedView companion : view.getCompanion())
            for (CardView card : companion.getCards().values()) observations.add(observation(card, "companion"));
        for (LookedAtView looked : view.getLookedAt())
            for (SimpleCardView card : looked.getCards().values()) observations.add(observation(card, "looked_at"));
        for (PlayerView player : view.getPlayers())
            if (player.getTopCard() != null) observations.add(observation(player.getTopCard(), "library_top"));
        data.add("observations", observations);
        JsonArray combat = new JsonArray();
        for (CombatGroupView group : view.getCombat()) {
            JsonObject entry = new JsonObject();
            entry.add("attackers", JSON.toJsonTree(group.getAttackers().keySet()));
            entry.add("blockers", JSON.toJsonTree(group.getBlockers().keySet()));
            entry.addProperty("defender", group.getDefenderId().toString());
            entry.addProperty("blocked", group.isBlocked());
            combat.add(entry);
        }
        data.add("combat", combat);
        JsonArray hand = new JsonArray();
        if (view.getMyHand() != null) for (CardView card : view.getMyHand().values()) hand.add(card(card));
        data.add("hand", hand);
        JsonArray stack = new JsonArray();
        if (view.getStack() != null) for (CardView card : view.getStack().values()) stack.add(card(card));
        data.add("stack", stack);
        JsonArray exile = new JsonArray();
        for (ExileView group : view.getExile()) for (CardView card : group.values()) exile.add(card(card));
        data.add("exile", exile);
        JsonObject actionKinds = new JsonObject();
        if (view.getCanPlayObjects() != null) for (UUID object : view.getCanPlayObjects().getObjects().keySet()) {
            // Pinned engine data, not a Manaforge legality calculation.
            JsonObject stats = JSON.toJsonTree(view.getCanPlayObjects().getStats(object)).getAsJsonObject();
            int play = stats.getAsJsonArray("basicPlayAbilities").size();
            int cast = stats.getAsJsonArray("basicCastAbilities").size();
            int other = stats.getAsJsonArray("other").size();
            int mana = stats.getAsJsonArray("basicManaAbilities").size();
            actionKinds.addProperty(object.toString(), other > 0 ? "select_object" :
                play > 0 && cast == 0 ? "play_land" : cast > 0 && play == 0 ? "cast_spell" :
                mana > 0 && play == 0 && cast == 0 ? "activate" : "select_object");
        }
        data.add("action_kinds", actionKinds);
        data.add("playable", JSON.toJsonTree(view.getCanPlayObjects() == null
            ? java.util.Collections.emptySet() : view.getCanPlayObjects().getObjects().keySet()));
        return data;
    }

    static DeckCardLists deck(JsonObject command) {
        DeckCardLists deck = new DeckCardLists();
        for (com.google.gson.JsonElement element : command.getAsJsonArray("cards")) {
            JsonObject card = element.getAsJsonObject();
            deck.getCards().add(new DeckCardInfo(requiredString(card, "name"),
                requiredString(card, "number"), requiredString(card, "set"), card.get("quantity").getAsInt()));
        }
        if (command.has("sideboard")) for (com.google.gson.JsonElement element : command.getAsJsonArray("sideboard")) {
            JsonObject card = element.getAsJsonObject();
            deck.getSideboard().add(new DeckCardInfo(requiredString(card, "name"), requiredString(card, "number"),
                requiredString(card, "set"), card.get("quantity").getAsInt()));
        }
        return deck;
    }

    private static String requiredString(JsonObject command, String key) {
        if (!command.has(key) || !command.get(key).isJsonPrimitive()
                || !command.getAsJsonPrimitive(key).isString()) {
            throw new IllegalArgumentException("Expected string field: " + key);
        }
        return command.get(key).getAsString();
    }

    private boolean execute(JsonObject command) {
        String id = null;
        try {
            id = requiredString(command, "request_id");
            if (!command.has("protocol") || !command.get("protocol").toString().equals("1")) {
                throw new IllegalArgumentException("Expected protocol 1");
            }
            String operation = requiredString(command, "command");
            if (operation.equals("connect")) {
                if (session.isConnected()) throw new IllegalArgumentException("Already connected");
                Connection connection = new Connection();
                connection.setHost("127.0.0.1");
                int port = command.get("port").getAsInt();
                if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid port");
                connection.setPort(port);
                connection.setUsername(requiredString(command, "username"));
                connection.setPassword("");
                connection.setProxyType(Connection.ProxyType.NONE);
                connection.setUserIdStr(UUID.randomUUID().toString());
                UserData preferences = UserData.getDefaultUserDataView();
                preferences.setAutoOrderTrigger(false);
                preferences.setAutoTargetLevel(0);
                connection.setUserData(preferences);
                if (!session.connectStart(connection)) {
                    throw new IllegalStateException("XMage connection failed: " + session.getLastError());
                }
                message("connected", id, getVersion().toString());
            } else if (operation.equals("status")) {
                if (!session.isConnected()) throw new IllegalStateException("Not connected");
                UUID room = session.getMainRoomId();
                if (room == null) throw new IllegalStateException("No main room returned");
                // Joining the local lobby requests real server chat callbacks without a game.
                UUID chat = session.getRoomChatId(room).orElseThrow(
                    () -> new IllegalStateException("No lobby chat returned"));
                if (!session.joinChat(chat)) throw new IllegalStateException("Cannot join lobby");
                JsonObject data = new JsonObject();
                data.addProperty("connected", session.isConnected());
                data.addProperty("engine_version", getVersion().toString(false));
                data.addProperty("game_types", session.getGameTypes().size());
                data.addProperty("room_id", room.toString());
                emit("status", id, data);
            } else if (operation.equals("create_game")) {
                String format = command.has("format") ? requiredString(command, "format") : "freeform";
                int seats = command.has("seats") ? command.get("seats").getAsInt() : 2;
                String gameType;
                String deckType;
                if (format.equals("freeform") && seats == 2) {
                    gameType = "Two Player Duel"; deckType = "Constructed - Freeform Unlimited";
                } else if (format.equals("commander") && seats >= 2) {
                    gameType = seats == 2 ? "Commander Two Player Duel" : "Commander Free For All";
                    deckType = "Variant Magic - Commander";
                } else throw new IllegalArgumentException("UNSUPPORTED_GAME_SETUP");
                mage.view.GameTypeView type = null;
                for (mage.view.GameTypeView candidate : session.getGameTypes()) if (candidate.getName().equals(gameType)) type = candidate;
                if (type == null || seats < type.getMinPlayers() || seats > type.getMaxPlayers())
                    throw new IllegalArgumentException("UNSUPPORTED_SEAT_COUNT");
                MatchOptions options = new MatchOptions("Manaforge local game", gameType, false);
                options.setDeckType(deckType);
                options.setWinsNeeded(1);
                options.setAttackOption(mage.constants.MultiplayerAttackOption.MULTIPLE);
                options.setSpectatorsAllowed(false);
                JsonArray controllers = command.has("controllers") ? command.getAsJsonArray("controllers") : null;
                if (controllers != null && controllers.size() != seats)
                    throw new IllegalArgumentException("INVALID_SEATS");
                for (int index = 0; index < seats; index++) {
                    options.getPlayerTypes().add(controllers == null ? PlayerType.HUMAN
                        : controllerType(controllers.get(index).getAsString()));
                }
                TableView table = session.createTable(session.getMainRoomId(), options);
                if (table == null) throw new IllegalStateException("Table creation rejected");
                JsonObject data = new JsonObject();
                data.addProperty("table_id", table.getTableId().toString());
                emit("table_created", id, data);
            } else if (operation.equals("join_table")) {
                PlayerType playerType = controllerType(command.has("controller")
                    ? requiredString(command, "controller") : "local_human");
                String playerName = playerType.isAI() ? requiredString(command, "player_name") : session.getUserName();
                boolean accepted = session.joinTable(session.getMainRoomId(),
                    UUID.fromString(requiredString(command, "table_id")), playerName,
                    playerType, 1, deck(command), "");
                if (!accepted) throw new IllegalStateException("Join table rejected");
                message("joined", id, "Joined table");
            } else if (operation.equals("start_game")) {
                if (!session.startMatch(session.getMainRoomId(), UUID.fromString(requiredString(command, "table_id"))))
                    throw new IllegalStateException("Start match rejected");
                message("started", id, "Start requested");
            } else if (operation.equals("respond")) {
                String kind = requiredString(command, "kind");
                String pendingMethod;
                // Claim exactly one response before remote calls can produce the next prompt.
                synchronized (this) {
                    int expected = command.get("decision_id").getAsInt();
                    if (gameId == null || !gameId.toString().equals(requiredString(command, "game_id"))
                            || expected != decisionId || decisionId < 0)
                        throw new IllegalArgumentException("STALE_DECISION");
                    pendingMethod = decisionMethod;
                    boolean valid = (kind.equals("boolean") && (pendingMethod.equals("GAME_ASK") || pendingMethod.equals("GAME_SELECT") || pendingMethod.equals("GAME_PLAY_MANA") || pendingMethod.equals("GAME_CHOOSE_PILE") || ((decisionFinishable && pendingMethod.equals("GAME_TARGET")) || (decisionCancellable && pendingMethod.equals("GAME_GET_MULTI_AMOUNT")))))
                        || (kind.equals("object") && (pendingMethod.equals("GAME_SELECT") || pendingMethod.equals("GAME_TARGET") || pendingMethod.equals("GAME_CHOOSE_ABILITY") || pendingMethod.equals("GAME_PLAY_MANA")))
                        || (kind.equals("integer") && pendingMethod.equals("GAME_GET_AMOUNT"))
                        || (kind.equals("string") && (pendingMethod.equals("GAME_CHOOSE_CHOICE") || pendingMethod.equals("GAME_GET_MULTI_AMOUNT")));
                    if (!valid) throw new IllegalArgumentException("UNSUPPORTED_RESPONSE");
                    if (kind.equals("object")) UUID.fromString(requiredString(command, "value"));
                    if (kind.equals("boolean") && (!command.get("value").isJsonPrimitive()
                            || !command.getAsJsonPrimitive("value").isBoolean()))
                        throw new IllegalArgumentException("Expected boolean response");
                    if (kind.equals("integer")) {
                        if (!command.get("value").toString().matches("-?[0-9]+")) throw new IllegalArgumentException("Expected integer");
                        int amount = command.get("value").getAsInt();
                        if (amount < amountMin || amount > amountMax) throw new IllegalArgumentException("AMOUNT_OUT_OF_RANGE");
                    }
                    if (kind.equals("string")) requiredString(command, "value");
                    decisionId = -1;
                }
                boolean accepted;
                if (kind.equals("boolean")) accepted = session.sendPlayerBoolean(gameId, command.get("value").getAsBoolean());
                else if (kind.equals("object")) accepted = session.sendPlayerUUID(gameId, UUID.fromString(requiredString(command, "value")));
                else if (kind.equals("integer")) accepted = session.sendPlayerInteger(gameId, command.get("value").getAsInt());
                else if (kind.equals("string")) accepted = session.sendPlayerString(gameId, requiredString(command, "value"));
                else throw new IllegalArgumentException("UNSUPPORTED_RESPONSE");
                // Acceptance is transport acknowledgement, not proof of a rules outcome.
                JsonObject data = new JsonObject();
                data.addProperty("accepted", accepted);
                emit("response_sent", id, data);
            } else if (operation.equals("concede")) {
                if (gameId == null || !session.sendPlayerAction(mage.constants.PlayerAction.CONCEDE, gameId, null))
                    throw new IllegalStateException("Concede rejected");
                message("concede_sent", id, "Concede requested");
            } else if (operation.equals("shutdown")) {
                session.connectStop(false, false);
                JsonObject data = new JsonObject();
                data.addProperty("connected", session.isConnected());
                emit("shutdown", id, data);
                return false;
            } else {
                throw new IllegalArgumentException("Unknown command: " + operation);
            }
        } catch (Exception error) {
            error.printStackTrace(System.err);
            message("error", id, error.toString());
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        // Capture stdout first, then route all engine/library output to stderr.
        System.setOut(System.err);
        ManaforgeBridge bridge = new ManaforgeBridge();
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line;
        while ((line = input.readLine()) != null) {
            try {
                JsonObject command = JsonParser.parseString(line).getAsJsonObject();
                if (!bridge.execute(command)) {
                    System.exit(0); // SwingWorker/JBoss pools otherwise keep the JVM alive.
                }
            } catch (RuntimeException error) {
                message("error", null, "Malformed command: " + error);
            }
        }
        bridge.session.connectStop(false, false);
        System.exit(0);
    }
}

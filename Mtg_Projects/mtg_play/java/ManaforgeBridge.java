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
    private int lastDecisionMessageId = -1;
    private int lastStateMessageId = -1;

    private static synchronized void emit(String event, String requestId, JsonObject data) {
        data.addProperty("protocol", 1);
        data.addProperty("event", event);
        if (requestId != null) data.addProperty("request_id", requestId);
        PROTOCOL.println(JSON.toJson(data));
        PROTOCOL.flush();
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
            Object payload = callback.getData();
            GameView view = payload instanceof GameView ? (GameView) payload : null;
            if (payload instanceof GameClientMessage) view = ((GameClientMessage) payload).getGameView();
            if (payload instanceof AbilityPickerView) view = ((AbilityPickerView) payload).getGameView();
            if (view != null && callback.getMessageId() > lastStateMessageId) {
                lastStateMessageId = callback.getMessageId();
                emit("game_state", null, state(view));
            }
            if (method.equals("GAME_ASK") || method.equals("GAME_SELECT")
                    || method.equals("GAME_TARGET")) {
                GameClientMessage prompt = (GameClientMessage) payload;
                if (callback.getMessageId() <= lastDecisionMessageId) return;
                lastDecisionMessageId = callback.getMessageId();
                decisionId = callback.getMessageId();
                decisionMethod = method;
                JsonObject choice = new JsonObject();
                choice.addProperty("decision_id", decisionId);
                choice.addProperty("kind", method);
                choice.addProperty("message", prompt.getMessage());
                choice.addProperty("min", prompt.getMin());
                choice.addProperty("max", prompt.getMax());
                choice.add("targets", JSON.toJsonTree(prompt.getTargets()));
                if (prompt.getChoice() != null) {
                    choice.add("choices", JSON.toJsonTree(prompt.getChoice().getChoices()));
                    choice.add("key_choices", JSON.toJsonTree(prompt.getChoice().getKeyChoices()));
                }
                emit("decision", null, choice);
            } else if (method.equals("GAME_CHOOSE_ABILITY")) {
                AbilityPickerView picker = (AbilityPickerView) payload;
                if (callback.getMessageId() <= lastDecisionMessageId) return;
                lastDecisionMessageId = callback.getMessageId();
                decisionId = callback.getMessageId();
                decisionMethod = method;
                JsonObject choice = new JsonObject();
                choice.addProperty("decision_id", decisionId);
                choice.addProperty("kind", method);
                choice.addProperty("message", picker.getMessage());
                choice.add("key_choices", JSON.toJsonTree(picker.getChoices()));
                emit("decision", null, choice);
            } else if (method.startsWith("GAME_CHOOSE_") || method.equals("GAME_PLAY_MANA")
                    || method.equals("GAME_PLAY_XMANA") || method.equals("GAME_GET_AMOUNT")
                    || method.equals("GAME_GET_MULTI_AMOUNT")) {
                message("error", null, "UNSUPPORTED_DECISION: " + method);
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
        if (!hidden) {
            item.addProperty("name", card.getName());
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
            item.addProperty("damage", permanent.getDamage());
        }
        return item;
    }

    private JsonObject state(GameView view) {
        JsonObject data = new JsonObject();
        data.addProperty("game_id", gameId == null ? null : gameId.toString());
        data.addProperty("turn", view.getTurn());
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
            row.addProperty("hand_count", player.getHandCount());
            row.addProperty("library_count", player.getLibraryCount());
            JsonArray battlefield = new JsonArray();
            for (PermanentView permanent : player.getBattlefield().values()) battlefield.add(card(permanent));
            row.add("battlefield", battlefield);
            players.add(row);
        }
        data.add("players", players);
        JsonArray hand = new JsonArray();
        if (view.getMyHand() != null) for (CardView card : view.getMyHand().values()) hand.add(card(card));
        data.add("hand", hand);
        JsonArray stack = new JsonArray();
        if (view.getStack() != null) for (CardView card : view.getStack().values()) stack.add(card(card));
        data.add("stack", stack);
        data.add("playable", JSON.toJsonTree(view.getCanPlayObjects() == null
            ? java.util.Collections.emptySet() : view.getCanPlayObjects().getObjects().keySet()));
        return data;
    }

    private static DeckCardLists deck(JsonObject command) {
        DeckCardLists deck = new DeckCardLists();
        for (com.google.gson.JsonElement element : command.getAsJsonArray("cards")) {
            JsonObject card = element.getAsJsonObject();
            deck.getCards().add(new DeckCardInfo(requiredString(card, "name"),
                requiredString(card, "number"), requiredString(card, "set"), card.get("quantity").getAsInt()));
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
                connection.setUserData(UserData.getDefaultUserDataView());
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
                MatchOptions options = new MatchOptions("Manaforge feasibility", "Two Player Duel", false);
                options.setDeckType("Constructed - Freeform Unlimited");
                options.setWinsNeeded(1);
                options.setSpectatorsAllowed(false);
                options.getPlayerTypes().add(PlayerType.HUMAN);
                options.getPlayerTypes().add(PlayerType.HUMAN);
                TableView table = session.createTable(session.getMainRoomId(), options);
                if (table == null) throw new IllegalStateException("Table creation rejected");
                JsonObject data = new JsonObject();
                data.addProperty("table_id", table.getTableId().toString());
                emit("table_created", id, data);
            } else if (operation.equals("join_table")) {
                boolean accepted = session.joinTable(session.getMainRoomId(),
                    UUID.fromString(requiredString(command, "table_id")), session.getUserName(),
                    PlayerType.HUMAN, 1, deck(command), "");
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
                    boolean valid = (kind.equals("boolean") && (pendingMethod.equals("GAME_ASK") || pendingMethod.equals("GAME_SELECT")))
                        || (kind.equals("object") && (pendingMethod.equals("GAME_SELECT") || pendingMethod.equals("GAME_TARGET") || pendingMethod.equals("GAME_CHOOSE_ABILITY")));
                    if (!valid) throw new IllegalArgumentException("UNSUPPORTED_RESPONSE");
                    if (kind.equals("object")) UUID.fromString(requiredString(command, "value"));
                    if (kind.equals("boolean") && (!command.get("value").isJsonPrimitive()
                            || !command.getAsJsonPrimitive("value").isBoolean()))
                        throw new IllegalArgumentException("Expected boolean response");
                    decisionId = -1;
                }
                boolean accepted;
                if (kind.equals("boolean")) accepted = session.sendPlayerBoolean(gameId, command.get("value").getAsBoolean());
                else if (kind.equals("object")) accepted = session.sendPlayerUUID(gameId, UUID.fromString(requiredString(command, "value")));
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

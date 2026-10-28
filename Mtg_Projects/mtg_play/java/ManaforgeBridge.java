import com.google.gson.Gson;
import com.google.gson.JsonObject;
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
    @Override public void onCallback(ClientCallback callback) {
        // Only this method emits callback events. Do not serialize arbitrary engine payloads.
        JsonObject data = new JsonObject();
        data.addProperty("method", callback.getMethod().name());
        data.addProperty("message_id", callback.getMessageId());
        emit("callback", null, data);
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

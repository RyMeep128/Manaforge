package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Header plus first command/ack/shutdown bodies; not a gameplay dispatcher. */
public final class WireMessages {
    private static final List<String> REJECTIONS = Arrays.asList("SESSION_MISMATCH", "VIEWER_MISMATCH", "STALE_REVISION",
        "STALE_DECISION", "ACTION_UNAVAILABLE", "COMMAND_PENDING", "ENGINE_REJECTED");
    private static boolean id(JsonElement token) {
        return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isString()
            && token.getAsString().matches("[A-Za-z0-9_.:-]{1,128}");
    }
    private static boolean string(JsonElement token) { return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isString(); }
    private static boolean revision(JsonElement token) {
        return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isNumber() && token.getAsLong() >= 0;
    }
    private static boolean keys(JsonObject body, String... keys) {
        return body.size() == keys.length && body.keySet().containsAll(Arrays.asList(keys));
    }
    private static void fail() throws WireEnvelope.EnvelopeException { throw new WireEnvelope.EnvelopeException("MESSAGE_INVALID"); }
    public static JsonObject parse(String text) throws IOException {
        JsonObject envelope = WireEnvelope.parse(text), body = envelope.getAsJsonObject("body");
        String type = envelope.get("message_type").getAsString();
        if (type.equals("command")) {
            if (!keys(body, "session_id", "viewer_id", "revision", "operation", "decision_id", "action_id")
                || !id(body.get("session_id")) || !id(body.get("viewer_id")) || !revision(body.get("revision"))
                || !string(body.get("operation")) || !body.get("operation").getAsString().equals("perform")
                || !id(body.get("decision_id")) || !id(body.get("action_id"))) fail();
        } else if (type.equals("ack")) {
            if (!keys(body, "session_id", "viewer_id", "command_id", "request_revision", "outcome", "code")
                || !id(body.get("session_id")) || !id(body.get("viewer_id")) || !(id(body.get("command_id")) && body.get("command_id").getAsString().matches("[A-Za-z0-9_-]{1,128}"))
                || !revision(body.get("request_revision")) || !string(body.get("outcome"))) fail();
            String outcome = body.get("outcome").getAsString();
            String code = string(body.get("code")) ? body.get("code").getAsString() : null;
            boolean noCode = body.get("code").isJsonNull();
            if (!((outcome.equals("submitted") || outcome.equals("confirmed")) && noCode)
                && !(outcome.equals("rejected") && REJECTIONS.contains(code))
                && !(outcome.equals("uncertain") && "COMMAND_UNCERTAIN".equals(code))) fail();
        } else if (type.equals("shutdown")) {
            if (!keys(body, "session_id", "viewer_id", "reason") || !id(body.get("session_id")) || !id(body.get("viewer_id"))
                || !string(body.get("reason")) || !Arrays.asList("client_close", "cancel", "startup_failed").contains(body.get("reason").getAsString())) fail();
        } else throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
        return envelope;
    }
    /** Caller serializes this check with execution against authenticated current engine state. */
    public static String checkCurrent(String text, String session, String viewer, long revision,
        String decision, Collection<String> actions) throws IOException {
        JsonObject envelope = parse(text);
        if (!envelope.get("message_type").getAsString().equals("command")) throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
        JsonObject body = envelope.getAsJsonObject("body");
        if (!body.get("session_id").getAsString().equals(session)) return "SESSION_MISMATCH";
        if (!body.get("viewer_id").getAsString().equals(viewer)) return "VIEWER_MISMATCH";
        if (body.get("revision").getAsLong() != revision) return "STALE_REVISION";
        if (!body.get("decision_id").getAsString().equals(decision)) return "STALE_DECISION";
        if (!actions.contains(body.get("action_id").getAsString())) return "ACTION_UNAVAILABLE";
        return null;
    }
}

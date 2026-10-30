package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.util.Arrays;

/** Authenticated gateway-to-viewer terminal channel errors, never command outcomes. */
public final class SessionErrors {
    private static boolean id(String value) { return value != null && value.matches("[A-Za-z0-9_.:-]{1,128}"); }
    private static boolean id(JsonElement value) {
        return value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString() && id(value.getAsString());
    }
    private static void fail(String code) throws WireEnvelope.EnvelopeException { throw new WireEnvelope.EnvelopeException(code); }
    public static String parse(String text, String session, String viewer) throws IOException {
        if (!id(session) || !id(viewer)) fail("ERROR_CONTEXT");
        JsonObject envelope = WireEnvelope.parse(text);
        if (!envelope.get("message_type").getAsString().equals("error")) fail("ERROR_UNSUPPORTED");
        JsonObject body = envelope.getAsJsonObject("body");
        JsonElement terminal = body.get("terminal"), codeValue = body.get("code");
        if (body.size() != 4 || !id(body.get("session_id")) || !id(body.get("viewer_id"))
            || terminal == null || !terminal.isJsonPrimitive() || !terminal.getAsJsonPrimitive().isBoolean() || !terminal.getAsBoolean()
            || codeValue == null || !codeValue.isJsonPrimitive() || !codeValue.getAsJsonPrimitive().isString()) fail("ERROR_SHAPE");
        String code = codeValue.getAsString();
        if (!Arrays.asList("PROTOCOL_INCOMPATIBLE", "SESSION_CLOSED", "SESSION_FAILED", "ENGINE_UNAVAILABLE", "RECEIVE_OVERFLOW", "INTERNAL_ERROR").contains(code)) fail("ERROR_SHAPE");
        if (!body.get("session_id").getAsString().equals(session)) fail("ERROR_SESSION");
        if (!body.get("viewer_id").getAsString().equals(viewer)) fail("ERROR_VIEWER");
        return code;
    }
}

package manaforge.protocol;

import com.google.gson.*;
import com.google.gson.stream.*;
import java.io.*;
import java.nio.*;
import java.nio.charset.*;
import java.util.*;

/** Strict bounded envelope header. Bodies still require message-specific validation. */
public final class WireEnvelope {
    public static final int MAX_DEPTH = 32;
    public static final class EnvelopeException extends IOException {
        public final String code;
        EnvelopeException(String code) { super(code); this.code = code; }
    }
    private static JsonElement value(JsonReader reader, int depth) throws IOException {
        JsonToken token = reader.peek();
        switch (token) {
            case BEGIN_OBJECT:
                if (depth + 1 > MAX_DEPTH) throw new EnvelopeException("JSON_DEPTH");
                reader.beginObject();
                JsonObject object = new JsonObject();
                while (reader.hasNext()) {
                    String key = scalar(reader.nextName());
                    if (object.has(key)) throw new EnvelopeException("JSON_DUPLICATE");
                    object.add(key, value(reader, depth + 1));
                }
                reader.endObject(); return object;
            case BEGIN_ARRAY:
                if (depth + 1 > MAX_DEPTH) throw new EnvelopeException("JSON_DEPTH");
                reader.beginArray(); JsonArray array = new JsonArray();
                while (reader.hasNext()) array.add(value(reader, depth + 1));
                reader.endArray(); return array;
            case STRING: return new JsonPrimitive(scalar(reader.nextString()));
            case BOOLEAN: return new JsonPrimitive(reader.nextBoolean());
            case NULL: reader.nextNull(); return JsonNull.INSTANCE;
            case NUMBER:
                String number = reader.nextString();
                if (!number.matches("-?(0|[1-9][0-9]*)")) throw new EnvelopeException("JSON_INVALID");
                try { return new JsonPrimitive(Long.parseLong(number)); }
                catch (NumberFormatException error) { throw new EnvelopeException("JSON_INVALID"); }
            default: throw new EnvelopeException("JSON_INVALID");
        }
    }
    public static JsonObject parse(String text) throws IOException {
        if (text == null || text.startsWith("\uFEFF") || text.length() > TextFrame.MAX_BYTES) throw new EnvelopeException("JSON_INVALID");
        try {
            ByteBuffer bytes = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(text));
            if (bytes.remaining() > TextFrame.MAX_BYTES) throw new EnvelopeException("JSON_INVALID");
        } catch (CharacterCodingException error) { throw new EnvelopeException("JSON_INVALID"); }
        JsonElement root;
        try (JsonReader reader = new JsonReader(new StringReader(text))) {
            reader.setStrictness(Strictness.STRICT);
            root = value(reader, 0);
            if (reader.peek() != JsonToken.END_DOCUMENT) throw new EnvelopeException("JSON_INVALID");
        } catch (EnvelopeException error) { throw error; }
        catch (IOException | IllegalStateException error) { throw new EnvelopeException("JSON_INVALID"); }
        if (!root.isJsonObject()) throw new EnvelopeException("ENVELOPE_INVALID");
        JsonObject object = root.getAsJsonObject();
        if (object.size() != 4 || !object.has("wire_version") || !object.get("wire_version").isJsonPrimitive()
            || !object.get("wire_version").getAsJsonPrimitive().isNumber()
            || !string(object, "message_type") || !string(object, "message_id")
            || !object.has("body") || !object.get("body").isJsonObject()) throw new EnvelopeException("ENVELOPE_INVALID");
        if (object.get("wire_version").getAsLong() != 1) throw new EnvelopeException("ENVELOPE_VERSION");
        if (!Arrays.asList("hello", "snapshot", "command", "ack", "event", "result", "shutdown", "error")
            .contains(object.get("message_type").getAsString())
            || !object.get("message_id").getAsString().matches("[A-Za-z0-9_-]{1,128}"))
            throw new EnvelopeException("ENVELOPE_INVALID");
        return object;
    }
    private static String scalar(String text) throws EnvelopeException {
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (++i >= text.length() || !Character.isLowSurrogate(text.charAt(i))) throw new EnvelopeException("JSON_INVALID");
            } else if (Character.isLowSurrogate(c)) throw new EnvelopeException("JSON_INVALID");
        }
        return text;
    }
    private static boolean string(JsonObject object, String key) {
        return object.has(key) && object.get(key).isJsonPrimitive() && object.get(key).getAsJsonPrimitive().isString();
    }
}

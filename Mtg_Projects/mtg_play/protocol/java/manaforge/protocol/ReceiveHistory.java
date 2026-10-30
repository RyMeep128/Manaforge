package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;

/** Per-viewer ordered stream admission. Retains only bounded IDs/digests, never raw snapshots. */
public final class ReceiveHistory implements AutoCloseable {
    private final String session,viewer;
    private final boolean fixtureMode;
    private final int capacity;
    private final Map<String,byte[]> history=new HashMap<>();
    private long revision;
    private boolean terminal,faulted,closed;
    public ReceiveHistory(String session,String viewer,boolean fixtureMode,int capacity) {
        if(session==null || session.trim().isEmpty() || viewer==null || viewer.trim().isEmpty() || capacity<1 || capacity>65536)
            throw new IllegalArgumentException("HISTORY_CONTEXT");
        this.session=session;this.viewer=viewer;this.fixtureMode=fixtureMode;this.capacity=capacity;
    }
    public synchronized long revision(){return revision;}
    public synchronized int size(){return history.size();}
    private static JsonElement sorted(JsonElement value) {
        if(value.isJsonObject()) {
            JsonObject result=new JsonObject();
            for(String name:new TreeSet<>(value.getAsJsonObject().keySet()))result.add(name,sorted(value.getAsJsonObject().get(name)));
            return result;
        }
        if(value.isJsonArray()) { JsonArray result=new JsonArray();for(JsonElement item:value.getAsJsonArray())result.add(sorted(item));return result; }
        if(value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber())return new JsonPrimitive(value.getAsLong());
        return value.deepCopy();
    }
    private static byte[] digest(JsonObject envelope) throws IOException {
        try { return MessageDigest.getInstance("SHA-256").digest(sorted(envelope).toString().getBytes(StandardCharsets.UTF_8)); }
        catch(NoSuchAlgorithmException error){throw new IOException("HISTORY_DIGEST");}
    }
    private static void fail(String code) throws WireEnvelope.EnvelopeException {throw new WireEnvelope.EnvelopeException(code);}
    /** null means an accepted semantic duplicate. New returned trees belong to the caller. */
    public synchronized JsonObject accept(String text) throws IOException {
        if(closed)fail("HISTORY_CLOSED");if(faulted)fail("HISTORY_FAULTED");
        try {
            JsonObject envelope=ReceiveMessages.parse(text,session,viewer,0,fixtureMode),body=envelope.getAsJsonObject("body");
            String id=envelope.get("message_id").getAsString(),type=envelope.get("message_type").getAsString();
            long incoming=body.getAsJsonObject(type.equals("event")?"event":"snapshot").get("revision").getAsLong();
            byte[] digest=digest(envelope),previous=history.get(id);
            if(previous!=null){if(!Arrays.equals(previous,digest))fail("HISTORY_ID_CONFLICT");return null;}
            if(terminal)fail("HISTORY_TERMINAL");if(incoming<revision)fail("RECEIVE_REVISION");if(history.size()>=capacity)fail("HISTORY_FULL");
            history.put(id,digest);revision=incoming;terminal=type.equals("result");return envelope;
        } catch(IOException | RuntimeException error){faulted=true;throw error;}
    }
    public synchronized void close(){closed=true;for(byte[] digest:history.values())Arrays.fill(digest,(byte)0);history.clear();}
}

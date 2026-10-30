package manaforge.protocol;

import com.google.gson.*;
import java.io.*;
import java.security.*;
import javax.crypto.*;
import javax.crypto.spec.SecretKeySpec;
import java.util.*;

/** Single-use viewer authentication primitives; no transport or owner bootstrap. */
public final class ViewerAuthentication {
    private static final String[] FIELDS = {"protocol_version", "engine_version", "artifact_manifest_sha256",
        "session_id", "viewer_id", "server_nonce", "client_nonce", "role", "proof"};
    private static boolean match(JsonElement token, String pattern) {
        return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isString() && token.getAsString().matches(pattern);
    }
    public static JsonObject parse(String text) throws IOException {
        JsonObject envelope = WireEnvelope.parse(text), body = envelope.getAsJsonObject("body");
        if (!envelope.get("message_type").getAsString().equals("hello") || body.size() != FIELDS.length
            || !body.keySet().containsAll(Arrays.asList(FIELDS))
            || !body.get("protocol_version").isJsonPrimitive() || !body.get("protocol_version").getAsJsonPrimitive().isNumber()
            || body.get("protocol_version").getAsLong() != 1
            || !match(body.get("engine_version"), "[A-Za-z0-9_.:-]{1,128}")
            || !match(body.get("session_id"), "[A-Za-z0-9_.:-]{1,128}")
            || !match(body.get("viewer_id"), "[A-Za-z0-9_.:-]{1,128}")
            || !match(body.get("artifact_manifest_sha256"), "[0-9a-f]{64}")
            || !match(body.get("server_nonce"), "[0-9a-f]{64}") || !match(body.get("client_nonce"), "[0-9a-f]{64}")
            || !match(body.get("proof"), "[0-9a-f]{64}") || !match(body.get("role"), "client|gateway"))
            throw new WireEnvelope.EnvelopeException("AUTH_MESSAGE_INVALID");
        return envelope;
    }
    private static byte[] transcript(JsonObject envelope) throws IOException {
        ByteArrayOutputStream stream = new ByteArrayOutputStream();
        TextFrame.write(stream, "manaforge-play-viewer-auth-v1"); TextFrame.write(stream, "1");
        TextFrame.write(stream, envelope.get("message_id").getAsString());
        JsonObject body = envelope.getAsJsonObject("body");
        for (int i = 0; i < FIELDS.length - 1; i++) TextFrame.write(stream, body.get(FIELDS[i]).getAsString());
        return stream.toByteArray();
    }
    public static String computeProof(String template, byte[] viewerKey) throws IOException {
        if (viewerKey == null || viewerKey.length != 32) throw new IllegalArgumentException("AUTH_KEY_INVALID");
        try {
            Mac hmac = Mac.getInstance("HmacSHA256"); hmac.init(new SecretKeySpec(viewerKey, "HmacSHA256"));
            byte[] bytes = hmac.doFinal(transcript(parse(template)));
            StringBuilder text = new StringBuilder();
            for (byte b : bytes) text.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
            Arrays.fill(bytes, (byte)0);
            return text.toString();
        } catch (GeneralSecurityException error) { throw new IOException("AUTH_CRYPTO_UNAVAILABLE"); }
    }
    private static byte[] hex(String value) {
        byte[] result = new byte[value.length() / 2];
        for (int i = 0; i < result.length; i++) result[i] = (byte)Integer.parseInt(value.substring(i*2, i*2+2), 16);
        return result;
    }
    /** Trusted expected fields only; serialize use on the connection worker. */
    public static final class Verifier implements AutoCloseable {
        private final byte[] transcript, proof;
        private boolean consumed;
        public Verifier(String expectedTemplate, byte[] viewerKey) throws IOException {
            transcript = transcript(parse(expectedTemplate)); proof = hex(computeProof(expectedTemplate, viewerKey));
        }
        public synchronized boolean verify(String incoming) throws IOException {
            if (consumed) return false;
            consumed = true;
            try {
                JsonObject envelope = parse(incoming);
                byte[] received = hex(envelope.getAsJsonObject("body").get("proof").getAsString());
                try { return MessageDigest.isEqual(transcript, transcript(envelope)) & MessageDigest.isEqual(proof, received); }
                finally { Arrays.fill(received, (byte)0); }
            } catch (WireEnvelope.EnvelopeException error) { return false; }
            finally { close(); }
        }
        public synchronized void close() { consumed = true; Arrays.fill(transcript, (byte)0); Arrays.fill(proof, (byte)0); }
    }
}

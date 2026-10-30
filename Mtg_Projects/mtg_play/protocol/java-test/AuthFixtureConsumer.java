package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
public final class AuthFixtureConsumer {
    private static byte[] hex(String value) {
        byte[] bytes = new byte[value.length()/2];
        for (int i=0;i<bytes.length;i++) bytes[i]=(byte)Integer.parseInt(value.substring(i*2,i*2+2),16);
        return bytes;
    }
    public static void main(String[] args) throws Exception {
        JsonObject corpus = JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        byte[] key=hex(corpus.get("viewer_key_hex").getAsString());
        for (JsonElement item : corpus.getAsJsonArray("positive")) {
            JsonObject envelope=item.getAsJsonObject().getAsJsonObject("envelope");
            String text=envelope.toString();
            if (!ViewerAuthentication.computeProof(text,key).equals(envelope.getAsJsonObject("body").get("proof").getAsString())) throw new AssertionError("Known-answer mismatch");
            try (ViewerAuthentication.Verifier verifier = new ViewerAuthentication.Verifier(text,key)) {
                if (!verifier.verify(text) || verifier.verify(text)) throw new AssertionError("Single use failed");
            }
        }
        String expected=corpus.getAsJsonArray("positive").get(0).getAsJsonObject().get("envelope").toString();
        for (JsonElement item : corpus.getAsJsonArray("negative")) {
            try (ViewerAuthentication.Verifier verifier = new ViewerAuthentication.Verifier(expected,key)) {
                if (verifier.verify(item.getAsJsonObject().get("envelope").toString()) || verifier.verify(expected)) throw new AssertionError("Tamper/retry accepted");
            }
        }
        byte[] wrong=new byte[32];
        try (ViewerAuthentication.Verifier verifier = new ViewerAuthentication.Verifier(expected,wrong)) {
            if (verifier.verify(expected)) throw new AssertionError("Wrong viewer key accepted");
        }
        try (ViewerAuthentication.Verifier verifier = new ViewerAuthentication.Verifier(expected,key)) {
            verifier.close(); if (verifier.verify(expected)) throw new AssertionError("Disposed verifier accepted");
        }
        try (ViewerAuthentication.Verifier verifier = new ViewerAuthentication.Verifier(expected,key)) {
            java.util.concurrent.atomic.AtomicInteger successes = new java.util.concurrent.atomic.AtomicInteger();
            java.util.concurrent.atomic.AtomicReference<Throwable> failure = new java.util.concurrent.atomic.AtomicReference<>();
            Runnable attempt = () -> { try { if (verifier.verify(expected)) successes.incrementAndGet(); } catch (Throwable error) { failure.set(error); } };
            Thread first = new Thread(attempt), second = new Thread(attempt);
            first.start(); second.start(); first.join(2000); second.join(2000);
            if (first.isAlive() || second.isAlive() || failure.get()!=null || successes.get()!=1) throw new AssertionError("Concurrent attempts");
        }
        System.out.println("Viewer auth: 2 known answers / 14 tamper cases / wrong-key, replay, disposed and concurrent checks passed");
    }
}

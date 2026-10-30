package manaforge.protocol;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public final class FrameFixtureConsumer {
    private static void check(boolean condition) {
        if (!condition) throw new AssertionError("Frame fixture mismatch");
    }
    private static byte[] hex(String value) {
        byte[] bytes = new byte[value.length() / 2];
        for (int i = 0; i < bytes.length; i++) bytes[i] = (byte)Integer.parseInt(value.substring(i*2, i*2+2), 16);
        return bytes;
    }
    private static InputStream input(byte[] bytes, boolean fragmented) {
        return new ByteArrayInputStream(bytes) {
            @Override public synchronized int read(byte[] b, int off, int len) {
                return super.read(b, off, fragmented ? Math.min(1, len) : len);
            }
        };
    }
    public static void main(String[] args) throws Exception {
        JsonObject corpus = JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8)).getAsJsonObject();
        check(corpus.get("max_bytes").getAsInt() == TextFrame.MAX_BYTES);
        check(corpus.get("framing_version").getAsInt() == 1);
        for (boolean fragmented : new boolean[] {false, true}) {
            for (JsonElement value : corpus.getAsJsonArray("positive")) {
                JsonObject test = value.getAsJsonObject();
                byte[] bytes = hex(test.get("hex").getAsString());
                InputStream stream = input(bytes, fragmented);
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                for (JsonElement expected : test.getAsJsonArray("messages")) {
                    String text = expected.getAsString();
                    check(text.equals(TextFrame.read(stream)));
                    TextFrame.write(output, text);
                }
                check(TextFrame.read(stream) == null);
                check(Arrays.equals(bytes, output.toByteArray()));
            }
            for (JsonElement value : corpus.getAsJsonArray("negative")) {
                JsonObject test = value.getAsJsonObject();
                try {
                    TextFrame.read(input(hex(test.get("hex").getAsString()), fragmented));
                    throw new AssertionError("Invalid frame accepted");
                } catch (TextFrame.FrameException error) { check(error.code.equals(test.get("code").getAsString())); }
            }
        }
        char[] boundary = new char[TextFrame.MAX_BYTES]; Arrays.fill(boundary, 'a');
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        String maximum = new String(boundary);
        TextFrame.write(output, maximum);
        check(maximum.equals(TextFrame.read(new ByteArrayInputStream(output.toByteArray()))));
        for (String invalid : new String[] {"", maximum + "a", new String(boundary).replace('a', '火'), "\uD800", "\uFEFF{}"}) {
            ByteArrayOutputStream target = new ByteArrayOutputStream();
            try { TextFrame.write(target, invalid); throw new AssertionError("Invalid write accepted"); }
            catch (TextFrame.FrameException expected) { check(target.size() == 0); }
        }
        System.out.println("Text framing: 4 positive/9 negative fixtures, fragmented reads and boundary writes passed");
    }
}

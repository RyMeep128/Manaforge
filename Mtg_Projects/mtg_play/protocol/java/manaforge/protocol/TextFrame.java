package manaforge.protocol;

import java.io.*;
import java.nio.*;
import java.nio.charset.*;

/** Bounded text framing only. Authentication and JSON validation are separate. */
public final class TextFrame {
    public static final int MAX_BYTES = 1048576;
    private TextFrame() {}

    public static final class FrameException extends IOException {
        public final String code;
        FrameException(String code) { super(code); this.code = code; }
    }
    private static void exact(InputStream input, byte[] bytes, int offset, int count) throws IOException {
        while (count > 0) {
            int n = input.read(bytes, offset, count);
            if (n < 0) throw new FrameException("FRAME_TRUNCATED");
            if (n == 0) {
                int value = input.read();
                if (value < 0) throw new FrameException("FRAME_TRUNCATED");
                bytes[offset] = (byte)value;
                n = 1;
            }
            offset += n; count -= n;
        }
    }
    public static String read(InputStream input) throws IOException {
        int first = input.read();
        if (first < 0) return null; // orderly EOF only between complete frames
        byte[] header = new byte[4]; header[0] = (byte)first;
        exact(input, header, 1, 3);
        long size = ((long)(header[0] & 255) << 24) | ((long)(header[1] & 255) << 16)
            | ((long)(header[2] & 255) << 8) | (header[3] & 255);
        if (size < 1 || size > MAX_BYTES) throw new FrameException("FRAME_SIZE");
        byte[] payload = new byte[(int)size];
        exact(input, payload, 0, payload.length);
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(payload)).toString();
        } catch (CharacterCodingException error) { throw new FrameException("FRAME_UTF8"); }
        if (text.startsWith("\uFEFF")) throw new FrameException("FRAME_BOM");
        return text;
    }
    public static void write(OutputStream output, String text) throws IOException {
        if (text == null || text.length() < 1 || text.length() > MAX_BYTES)
            throw new FrameException("FRAME_SIZE");
        if (text.startsWith("\uFEFF")) throw new FrameException("FRAME_BOM");
        ByteBuffer encoded;
        try {
            encoded = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(text));
        } catch (CharacterCodingException error) { throw new FrameException("FRAME_UTF8"); }
        int size = encoded.remaining();
        if (size > MAX_BYTES) throw new FrameException("FRAME_SIZE");
        output.write(new byte[] { (byte)(size >>> 24), (byte)(size >>> 16), (byte)(size >>> 8), (byte)size });
        output.write(encoded.array(), encoded.position(), size);
    }
}

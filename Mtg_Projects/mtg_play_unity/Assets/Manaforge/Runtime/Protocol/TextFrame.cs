using System;
using System.IO;
using System.Text;

namespace Manaforge.Play.Protocol
{
    // Bounded synchronous framing. Call on a transport worker, never the rendering thread.
    public static class TextFrame
    {
        public const int MaxBytes = 1048576;
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        public sealed class FrameException : IOException
        {
            public string Code { get; }
            public FrameException(string code) : base(code) { Code = code; }
        }
        private static void Exact(Stream input, byte[] bytes, int offset, int count)
        {
            while (count > 0)
            {
                int n = input.Read(bytes, offset, count);
                if (n == 0) throw new FrameException("FRAME_TRUNCATED");
                offset += n; count -= n;
            }
        }
        public static string Read(Stream input)
        {
            int first = input.ReadByte();
            if (first < 0) return null;
            var header = new byte[4]; header[0] = (byte)first;
            Exact(input, header, 1, 3);
            uint size = ((uint)header[0] << 24) | ((uint)header[1] << 16) | ((uint)header[2] << 8) | header[3];
            if (size < 1 || size > MaxBytes) throw new FrameException("FRAME_SIZE");
            var payload = new byte[(int)size];
            Exact(input, payload, 0, payload.Length);
            string text;
            try { text = Utf8.GetString(payload); }
            catch (DecoderFallbackException) { throw new FrameException("FRAME_UTF8"); }
            if (text[0] == '\uFEFF') throw new FrameException("FRAME_BOM");
            return text;
        }
        public static void Write(Stream output, string text)
        {
            if (string.IsNullOrEmpty(text) || text.Length > MaxBytes) throw new FrameException("FRAME_SIZE");
            if (text[0] == '\uFEFF') throw new FrameException("FRAME_BOM");
            int size;
            try { size = Utf8.GetByteCount(text); }
            catch (EncoderFallbackException) { throw new FrameException("FRAME_UTF8"); }
            if (size > MaxBytes) throw new FrameException("FRAME_SIZE");
            var bytes = Utf8.GetBytes(text);
            output.Write(new[] { (byte)(size >> 24), (byte)(size >> 16), (byte)(size >> 8), (byte)size }, 0, 4);
            output.Write(bytes, 0, bytes.Length);
        }
    }
}

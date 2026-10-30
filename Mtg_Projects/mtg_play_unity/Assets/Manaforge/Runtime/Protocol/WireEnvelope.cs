using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    public static class WireEnvelope
    {
        public const int MaxDepth = 32;
        public sealed class EnvelopeException : IOException
        {
            public string Code { get; }
            public EnvelopeException(string code) : base(code) { Code = code; }
        }
        private static readonly Regex Token = new Regex(
            @"\G(?:[ \t\r\n]+|""(?:[^""\\\x00-\x1f]|\\(?:[""\\/bfnrt]|u[0-9a-fA-F]{4}))*""|-?(?:0|[1-9][0-9]*)|true|false|null|[{}\[\],:])",
            RegexOptions.CultureInvariant);
        private static void Syntax(string text)
        {
            if (text == null || text.Length > TextFrame.MaxBytes) throw new EnvelopeException("JSON_INVALID");
            try { if (new UTF8Encoding(false, true).GetByteCount(text) > TextFrame.MaxBytes) throw new EnvelopeException("JSON_INVALID"); }
            catch (EncoderFallbackException) { throw new EnvelopeException("JSON_INVALID"); }
            int position = 0, depth = 0;
            char previous = '\0';
            while (position < text.Length)
            {
                var match = Token.Match(text, position);
                if (!match.Success) throw new EnvelopeException("JSON_INVALID");
                char first = text[position];
                position += match.Length;
                if (first == ' ' || first == '\t' || first == '\r' || first == '\n') continue;
                if (first == '"') Escapes(match.Value);
                if (first == '-' || (first >= '0' && first <= '9'))
                {
                    if (!long.TryParse(match.Value, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out _)
                        || (position < text.Length && " \t\r\n,]}:".IndexOf(text[position]) < 0))
                        throw new EnvelopeException("JSON_INVALID");
                }
                if (first == '{' || first == '[') { if (++depth > MaxDepth) throw new EnvelopeException("JSON_DEPTH"); }
                if (first == '}' || first == ']') { if (previous == ',') throw new EnvelopeException("JSON_INVALID"); depth--; }
                previous = first;
            }
        }
        private static JsonTextReader Reader(string text) => new JsonTextReader(new StringReader(text))
        { DateParseHandling = DateParseHandling.None, MaxDepth = MaxDepth, SupportMultipleContent = false };

        private static void Escapes(string token)
        {
            // Newtonsoft replaces lone escaped surrogates; reject them before that conversion.
            for (int i = 1; i < token.Length - 1; i++)
            {
                if (token[i] != '\\') continue;
                if (token[++i] != 'u') continue;
                int value = int.Parse(token.Substring(i + 1, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                i += 4;
                if (value >= 0xDC00 && value <= 0xDFFF) throw new EnvelopeException("JSON_INVALID");
                if (value < 0xD800 || value > 0xDBFF) continue;
                if (i + 6 >= token.Length || token[i + 1] != '\\' || token[i + 2] != 'u')
                    throw new EnvelopeException("JSON_INVALID");
                int low = int.Parse(token.Substring(i + 3, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                if (low < 0xDC00 || low > 0xDFFF) throw new EnvelopeException("JSON_INVALID");
                i += 6;
            }
        }
        private static void Scalar(string text)
        {
            for (int i = 0; i < text.Length; i++)
            {
                if (char.IsHighSurrogate(text[i]))
                {
                    if (++i >= text.Length || !char.IsLowSurrogate(text[i])) throw new EnvelopeException("JSON_INVALID");
                }
                else if (char.IsLowSurrogate(text[i])) throw new EnvelopeException("JSON_INVALID");
            }
        }
        public static JObject Parse(string text)
        {
            var envelope = ParseObject(text);
            if (envelope == null || envelope.Count != 4 || envelope["wire_version"]?.Type != JTokenType.Integer
                || envelope["message_type"]?.Type != JTokenType.String || envelope["message_id"]?.Type != JTokenType.String
                || !(envelope["body"] is JObject)) throw new EnvelopeException("ENVELOPE_INVALID");
            if ((long)envelope["wire_version"] != 1) throw new EnvelopeException("ENVELOPE_VERSION");
            string type = (string)envelope["message_type"];
            if (Array.IndexOf(new[] {"hello", "snapshot", "command", "ack", "event", "result", "shutdown", "error"}, type) < 0
                || !Regex.IsMatch((string)envelope["message_id"], @"\A[A-Za-z0-9_-]{1,128}\z"))
                throw new EnvelopeException("ENVELOPE_INVALID");
            return envelope; // Body remains unvalidated.
        }

        internal static JObject ParseObject(string text)
        {
            Syntax(text);
            try
            {
                // Validate duplicates before constructing a tree; each nested object has its own namespace.
                var names = new Stack<HashSet<string>>();
                using (var reader = Reader(text))
                {
                    while (reader.Read())
                    {
                        if (reader.TokenType == JsonToken.PropertyName || reader.TokenType == JsonToken.String) Scalar((string)reader.Value);
                        if (reader.TokenType == JsonToken.StartObject) names.Push(new HashSet<string>(StringComparer.Ordinal));
                        else if (reader.TokenType == JsonToken.EndObject) names.Pop();
                        else if (reader.TokenType == JsonToken.PropertyName && !names.Peek().Add((string)reader.Value))
                            throw new EnvelopeException("JSON_DUPLICATE");
                    }
                }
                JObject envelope;
                using (var reader = Reader(text)) envelope = JToken.ReadFrom(reader) as JObject;
                return envelope; // body is UNVALIDATED; never dispatch directly
            }
            catch (JsonException) { throw new EnvelopeException("JSON_INVALID"); }
        }
    }
}

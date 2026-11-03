using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Viewer channel only. Never give this API an owner credential or all-seat manifest.
    public static class ViewerAuthentication
    {
        private static readonly string[] Fields = { "protocol_version", "engine_version", "artifact_manifest_sha256",
            "session_id", "viewer_id", "server_nonce", "client_nonce", "role", "proof" };
        private static bool Match(JToken token, string pattern) => token?.Type == JTokenType.String && Regex.IsMatch((string)token, pattern);
        public static JObject Parse(string text)
        {
            var envelope = WireEnvelope.Parse(text);
            var body = (JObject)envelope["body"];
            if ((string)envelope["message_type"] != "hello" || body.Count != Fields.Length || !Fields.All(f => body.Property(f) != null)
                || body["protocol_version"]?.Type != JTokenType.Integer || (long)body["protocol_version"] != 1
                || !Match(body["engine_version"], @"\A[A-Za-z0-9_.:-]{1,128}\z")
                || !Match(body["session_id"], @"\A[A-Za-z0-9_.:-]{1,128}\z")
                || !Match(body["viewer_id"], @"\A[A-Za-z0-9_.:-]{1,128}\z")
                || !Match(body["artifact_manifest_sha256"], @"\A[0-9a-f]{64}\z")
                || !Match(body["server_nonce"], @"\A[0-9a-f]{64}\z")
                || !Match(body["client_nonce"], @"\A[0-9a-f]{64}\z")
                || !Match(body["proof"], @"\A[0-9a-f]{64}\z")
                || body["role"]?.Type != JTokenType.String || !new[] { "client", "gateway" }.Contains((string)body["role"]))
                throw new WireEnvelope.EnvelopeException("AUTH_MESSAGE_INVALID");
            return envelope;
        }
        private static byte[] Transcript(JObject envelope)
        {
            using var stream = new MemoryStream();
            TextFrame.Write(stream, "manaforge-play-viewer-auth-v1");
            TextFrame.Write(stream, "1");
            TextFrame.Write(stream, (string)envelope["message_id"]);
            var body = (JObject)envelope["body"];
            foreach (string field in Fields.Take(Fields.Length - 1)) TextFrame.Write(stream, body[field].ToString());
            return stream.ToArray();
        }
        public static string ComputeProof(string template, byte[] viewerKey)
        {
            if (viewerKey == null || viewerKey.Length != 32) throw new ArgumentException("AUTH_KEY_INVALID");
            using var hmac = new HMACSHA256(viewerKey);
            return string.Concat(hmac.ComputeHash(Transcript(Parse(template))).Select(b => b.ToString("x2")));
        }
        private static byte[] Hex(string value) => Enumerable.Range(0, value.Length / 2)
            .Select(i => Convert.ToByte(value.Substring(i * 2, 2), 16)).ToArray();
        private static bool Equal(byte[] left, byte[] right)
        {
            if (left.Length != right.Length) return false;
            int difference = 0;
            for (int i = 0; i < left.Length; i++) difference |= left[i] ^ right[i];
            return difference == 0;
        }
        // Construct from trusted expected fields, never from the unverified incoming hello.
        // Serialize use on the connection worker. Any attempt consumes this verifier.
        public sealed class Verifier : IDisposable
        {
            private readonly byte[] transcript;
            private readonly byte[] proof;
            private bool consumed;
            private readonly object gate = new object();
            public Verifier(string expectedTemplate, byte[] viewerKey)
            {
                transcript = Transcript(Parse(expectedTemplate));
                proof = Hex(ComputeProof(expectedTemplate, viewerKey));
            }
            public bool Verify(string incoming)
            {
                lock (gate)
                {
                    if (consumed) return false;
                    consumed = true;
                    try
                    {
                        var envelope = Parse(incoming);
                        var receivedProof = Hex((string)envelope["body"]["proof"]);
                        try { return Equal(transcript, Transcript(envelope)) & Equal(proof, receivedProof); }
                        finally { Array.Clear(receivedProof, 0, receivedProof.Length); }
                    }
                    catch (WireEnvelope.EnvelopeException) { return false; }
                    finally { Dispose(); }
                }
            }
            public void Dispose()
            {
                lock (gate)
                {
                    consumed = true;
                    Array.Clear(transcript, 0, transcript.Length);
                    Array.Clear(proof, 0, proof.Length);
                }
            }
        }
    }
}

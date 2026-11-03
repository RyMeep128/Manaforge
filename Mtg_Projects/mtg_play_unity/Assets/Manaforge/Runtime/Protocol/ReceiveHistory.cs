using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Per-viewer ordered stream admission, not game rules or a rendering projection.
    public sealed class ReceiveHistory : IDisposable
    {
        private readonly object gate = new object();
        private readonly string session, viewer;
        private readonly bool fixtureMode;
        private readonly int capacity;
        private readonly Dictionary<string, byte[]> history = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        private long revision;
        private bool terminal, faulted, closed;
        public ReceiveHistory(string session, string viewer, bool fixtureMode = false, int capacity = 4096)
        {
            if (string.IsNullOrWhiteSpace(session) || string.IsNullOrWhiteSpace(viewer) || capacity < 1 || capacity > 65536)
                throw new ArgumentException("HISTORY_CONTEXT");
            this.session = session; this.viewer = viewer; this.fixtureMode = fixtureMode; this.capacity = capacity;
        }
        public long Revision { get { lock (gate) return revision; } }
        public int Count { get { lock (gate) return history.Count; } }
        private static JToken Sorted(JToken token)
        {
            if (token is JObject obj) return new JObject(obj.Properties().OrderBy(p => p.Name, StringComparer.Ordinal)
                .Select(p => new JProperty(p.Name, Sorted(p.Value))));
            if (token is JArray array) return new JArray(array.Select(Sorted));
            return token.DeepClone();
        }
        private static byte[] Digest(JObject envelope)
        {
            using var hash = SHA256.Create();
            return hash.ComputeHash(Encoding.UTF8.GetBytes(Sorted(envelope).ToString(Formatting.None)));
        }
        private static void Fail(string code) => throw new WireEnvelope.EnvelopeException(code);
        // null means an already accepted semantic duplicate. New trees are caller-owned mutable intermediates.
        public JObject Accept(string text)
        {
            lock (gate)
            {
                if (closed) Fail("HISTORY_CLOSED");
                if (faulted) Fail("HISTORY_FAULTED");
                try
                {
                    // Check duplicate identity before revision admission, but never skip shape/privacy/context validation.
                    var envelope = ReceiveMessages.Parse(text, session, viewer, 0, fixtureMode);
                    string id = (string)envelope["message_id"], type = (string)envelope["message_type"];
                    var body = (JObject)envelope["body"];
                    long incoming = (long)(type == "event" ? body["event"]["revision"] : body["snapshot"]["revision"]);
                    var digest = Digest(envelope);
                    if (history.TryGetValue(id, out var previous))
                    {
                        if (!previous.SequenceEqual(digest)) Fail("HISTORY_ID_CONFLICT");
                        return null;
                    }
                    if (terminal) Fail("HISTORY_TERMINAL");
                    if (incoming < revision) Fail("RECEIVE_REVISION");
                    if (history.Count >= capacity) Fail("HISTORY_FULL");
                    history.Add(id, digest); revision = incoming; terminal = type == "result";
                    return envelope;
                }
                catch { faulted = true; throw; }
            }
        }
        public void Dispose()
        {
            lock (gate)
            {
                closed = true;
                foreach (var digest in history.Values) Array.Clear(digest, 0, digest.Length);
                history.Clear();
            }
        }
    }
}

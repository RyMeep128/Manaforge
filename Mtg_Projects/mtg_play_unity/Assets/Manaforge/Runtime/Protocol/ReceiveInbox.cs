using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace Manaforge.Play.Protocol
{
    public enum ReceiveInboxState { Open, Completed, Cancelled, Faulted, Disposed }
    public sealed class ReceiveInboxStop
    {
        public ReceiveInboxState State { get; }
        public string Code { get; }
        internal ReceiveInboxStop(ReceiveInboxState state, string code) { State = state; Code = code; }
    }
    // Immutable encoded packet. Ownership transfers on dequeue; the consumer must dispose it.
    // Parse/project on a worker, never decode this packet on the Unity rendering thread.
    public sealed class ReceivePacket : IDisposable
    {
        private readonly object gate = new object();
        private byte[] bytes;
        public int ByteCount { get; }
        internal ReceivePacket(byte[] bytes) { this.bytes = bytes; ByteCount = bytes.Length; }
        public string ReadJson()
        {
            lock (gate)
            {
                if (bytes == null) throw new ObjectDisposedException(nameof(ReceivePacket));
                return Encoding.UTF8.GetString(bytes);
            }
        }
        public void Dispose()
        { lock (gate) { if (bytes != null) { Array.Clear(bytes, 0, bytes.Length); bytes = null; } } }
    }
    // Client-side worker inbox. Not a renderer projection, socket owner or game model.
    public sealed class ReceiveInbox : IDisposable
    {
        private readonly object gate = new object();
        private readonly ReceiveHistory history;
        private readonly Queue<ReceivePacket> packets = new Queue<ReceivePacket>();
        private readonly int maximumMessages, maximumBytes;
        private readonly TaskCompletionSource<ReceiveInboxStop> completion =
            new TaskCompletionSource<ReceiveInboxStop>(TaskCreationOptions.RunContinuationsAsynchronously);
        private ReceiveInboxState state;
        private int queuedBytes;
        public ReceiveInbox(string session, string viewer, bool fixtureMode = false,
            int maximumMessages = 128, int maximumBytes = 8 * 1024 * 1024, int historyCapacity = 4096)
        {
            if (maximumMessages < 1 || maximumMessages > 1024 || maximumBytes < 1 || maximumBytes > 64 * 1024 * 1024)
                throw new ArgumentException("INBOX_CONTEXT");
            history = new ReceiveHistory(session, viewer, fixtureMode, historyCapacity);
            this.maximumMessages = maximumMessages; this.maximumBytes = maximumBytes;
        }
        public Task<ReceiveInboxStop> Completion => completion.Task;
        public ReceiveInboxState State { get { lock (gate) return state; } }
        public int Count { get { lock (gate) return packets.Count; } }
        public int QueuedBytes { get { lock (gate) return queuedBytes; } }
        private static void Fail(string code) => throw new WireEnvelope.EnvelopeException(code);
        private void CheckOpen()
        {
            if (state == ReceiveInboxState.Completed) Fail("INBOX_COMPLETE");
            CheckReadable();
        }
        private void CheckReadable()
        {
            if (state == ReceiveInboxState.Cancelled) Fail("INBOX_CANCELLED");
            if (state == ReceiveInboxState.Faulted) Fail("INBOX_FAULTED");
            if (state == ReceiveInboxState.Disposed) Fail("INBOX_CLOSED");
        }
        private void Stop(ReceiveInboxState next, string code, bool clear)
        {
            state = next;
            if (clear) { while (packets.Count > 0) packets.Dequeue().Dispose(); queuedBytes = 0; }
            history.Dispose();
            completion.TrySetResult(new ReceiveInboxStop(next, code)); // continuations never run under this lock
        }
        // Producer must call in wire order. A duplicate consumes neither a slot nor byte budget.
        public bool Enqueue(string text)
        {
            lock (gate)
            {
                CheckOpen();
                try
                {
                    var envelope = history.Accept(text);
                    if (envelope == null) return false;
                    string normalized = envelope.ToString(Formatting.None);
                    int size = Encoding.UTF8.GetByteCount(normalized);
                    if (size > TextFrame.MaxBytes || packets.Count >= maximumMessages || size > maximumBytes - queuedBytes)
                        Fail("INBOX_OVERFLOW");
                    packets.Enqueue(new ReceivePacket(Encoding.UTF8.GetBytes(normalized))); queuedBytes += size;
                    return true;
                }
                catch (WireEnvelope.EnvelopeException error) { Stop(ReceiveInboxState.Faulted, error.Code, true); throw; }
                catch { Stop(ReceiveInboxState.Faulted, "INBOX_INVALID", true); throw new WireEnvelope.EnvelopeException("INBOX_INVALID"); }
            }
        }
        public bool TryTake(out ReceivePacket packet)
        {
            lock (gate)
            {
                CheckReadable();
                packet = null;
                if (packets.Count == 0) return false;
                packet = packets.Dequeue(); queuedBytes -= packet.ByteCount; return true;
            }
        }
        // Owner EOF/completion preserves validated packets for draining, but admits no further input.
        public void FinishInput()
        { lock (gate) { if (state == ReceiveInboxState.Open) Stop(ReceiveInboxState.Completed, null, false); } }
        public void Cancel()
        {
            lock (gate)
                if (state == ReceiveInboxState.Open || state == ReceiveInboxState.Completed)
                    Stop(ReceiveInboxState.Cancelled, "INBOX_CANCELLED", true);
        }
        public void Dispose()
        { lock (gate) { if (state != ReceiveInboxState.Disposed) Stop(ReceiveInboxState.Disposed, "INBOX_CLOSED", true); } }
    }
}

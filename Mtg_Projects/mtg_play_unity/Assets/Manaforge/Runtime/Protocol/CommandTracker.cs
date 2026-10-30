using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    public enum CommandState { AwaitingAck, Submitted, Confirmed, Rejected, Uncertain }

    public sealed class TrackedCommand
    {
        public string CommandId { get; }
        public long RequestRevision { get; }
        public CommandState State { get; }
        public string Code { get; }
        internal TrackedCommand(string id, long revision, CommandState state, string code)
        { CommandId = id; RequestRevision = revision; State = state; Code = code; }
    }

    // Client transport bookkeeping only. Construct after viewer authentication.
    // Neither accepting an ACK nor tracking a command proves engine execution.
    public sealed class CommandTracker : IDisposable
    {
        private sealed class Record
        {
            internal string Id;
            internal long Revision;
            internal CommandState State;
            internal string Code;
            internal TrackedCommand Snapshot() => new TrackedCommand(Id, Revision, State, Code);
        }
        private readonly object gate = new object();
        private readonly string session, viewer;
        private readonly int capacity;
        private readonly Dictionary<string, Record> records = new Dictionary<string, Record>(StringComparer.Ordinal);
        private Record active;
        private bool connected = true, faulted, disposed;
        public CommandTracker(string session, string viewer, int capacity = 4096)
        {
            if (string.IsNullOrEmpty(session) || string.IsNullOrEmpty(viewer) || capacity < 1 || capacity > 65536)
                throw new ArgumentException("TRACKER_CONTEXT_INVALID");
            this.session = session; this.viewer = viewer; this.capacity = capacity;
        }
        public bool CanSubmit { get { lock (gate) return !disposed && connected && !faulted && active == null && records.Count < capacity; } }
        private void Open()
        { if (disposed) throw new WireEnvelope.EnvelopeException("TRACKER_CLOSED"); }
        private static void Uncertain(Record record)
        {
            if (record == null) return;
            record.State = CommandState.Uncertain; record.Code = "COMMAND_UNCERTAIN";
        }
        private void InvalidAck(string code)
        {
            faulted = true; connected = false; Uncertain(active);
            throw new WireEnvelope.EnvelopeException(code);
        }
        // Call BEFORE the first write. If the write may have failed partially, Disconnect.
        public TrackedCommand Begin(string commandText)
        {
            lock (gate)
            {
                Open();
                if (faulted) throw new WireEnvelope.EnvelopeException("TRACKER_FAULTED");
                if (!connected) throw new WireEnvelope.EnvelopeException("TRACKER_DISCONNECTED");
                if (active != null) throw new WireEnvelope.EnvelopeException(active.State == CommandState.Uncertain ? "COMMAND_UNCERTAIN" : "COMMAND_PENDING");
                var envelope = WireMessages.Parse(commandText);
                var body = (JObject)envelope["body"];
                if ((string)envelope["message_type"] != "command" || (string)body["session_id"] != session || (string)body["viewer_id"] != viewer)
                    throw new WireEnvelope.EnvelopeException("COMMAND_CONTEXT");
                string id = (string)envelope["message_id"];
                if (records.ContainsKey(id)) throw new WireEnvelope.EnvelopeException("COMMAND_ID_REUSED");
                if (records.Count >= capacity) throw new WireEnvelope.EnvelopeException("COMMAND_HISTORY_FULL");
                active = new Record { Id = id, Revision = (long)body["revision"], State = CommandState.AwaitingAck };
                records.Add(id, active);
                return active.Snapshot();
            }
        }
        public TrackedCommand Accept(string acknowledgementText)
        {
            lock (gate)
            {
                Open();
                if (faulted) throw new WireEnvelope.EnvelopeException("TRACKER_FAULTED");
                if (!connected) throw new WireEnvelope.EnvelopeException("TRACKER_DISCONNECTED");
                JObject envelope;
                try { envelope = WireMessages.Parse(acknowledgementText); }
                catch (WireEnvelope.EnvelopeException) { InvalidAck("ACK_INVALID"); throw; }
                var body = (JObject)envelope["body"];
                if ((string)envelope["message_type"] != "ack") InvalidAck("ACK_INVALID");
                if ((string)body["session_id"] != session || (string)body["viewer_id"] != viewer) InvalidAck("ACK_CONTEXT");
                if (!records.TryGetValue((string)body["command_id"], out var record)) InvalidAck("ACK_UNKNOWN");
                if ((long)body["request_revision"] != record.Revision) InvalidAck("ACK_REVISION");
                string outcome = (string)body["outcome"], code = (string)body["code"];
                CommandState state = outcome == "submitted" ? CommandState.Submitted : outcome == "confirmed" ? CommandState.Confirmed
                    : outcome == "rejected" ? CommandState.Rejected : CommandState.Uncertain;
                if (record.State == CommandState.Confirmed || record.State == CommandState.Rejected)
                {
                    if (record.State != state || record.Code != code) InvalidAck("ACK_CONFLICT");
                    return record.Snapshot(); // harmless repeated terminal receipt; does not release another pending command
                }
                if (record.State == CommandState.Uncertain && state == CommandState.Submitted) return record.Snapshot();
                record.State = state; record.Code = code;
                if (state == CommandState.Confirmed || state == CommandState.Rejected) active = null;
                return record.Snapshot();
            }
        }
        // Authenticated terminal channel error. Preserve uncertain receipts; never reinterpret as an ACK.
        // Invalid/misrouted error data also fails closed and forbids reconnecting this tracker.
        public string AcceptSessionError(string text)
        {
            lock (gate)
            {
                Open(); faulted = true; connected = false; Uncertain(active);
                return SessionErrors.Parse(text, session, viewer);
            }
        }
        public TrackedCommand Current { get { lock (gate) return active?.Snapshot(); } }
        public void Disconnect()
        { lock (gate) { Open(); connected = false; Uncertain(active); } }
        // A freshly authenticated connection does not resolve a previous command's uncertainty.
        public void AuthenticatedReconnect()
        {
            lock (gate)
            {
                Open(); if (faulted) throw new WireEnvelope.EnvelopeException("TRACKER_FAULTED");
                connected = true;
            }
        }
        public void Dispose()
        { lock (gate) { disposed = true; connected = false; active = null; records.Clear(); } }
    }
}

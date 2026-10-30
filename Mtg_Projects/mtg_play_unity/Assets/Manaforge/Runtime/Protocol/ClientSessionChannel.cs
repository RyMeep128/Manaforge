using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    public enum ClientChannelState { Active, Completed, Stopped, Disposed }
    public sealed class ClientChannelStop
    {
        public bool Graceful { get; }
        public string Code { get; }
        internal ClientChannelStop(bool graceful,string code){Graceful=graceful;Code=code;}
    }
    public sealed class ClientReceive
    {
        public string Type { get; }
        public bool Applied { get; }
        public TrackedCommand Receipt { get; }
        internal ClientReceive(string type,bool applied=true,TrackedCommand receipt=null){Type=type;Applied=applied;Receipt=receipt;}
    }
    // Construct ONLY after authenticating the gateway against trusted viewer/pin context.
    // Owns a connected transport, packet inbox and command tracking; never starts processes.
    public sealed class ClientSessionChannel : IDisposable
    {
        private readonly object gate=new object();
        private readonly LoopbackFrameReader transport;
        private readonly ReceiveInbox inbox;
        private readonly CommandTracker commands;
        private readonly string session,viewer;
        private readonly HashSet<string> actions=new HashSet<string>(StringComparer.Ordinal);
        private readonly TaskCompletionSource<ClientChannelStop> completion=new TaskCompletionSource<ClientChannelStop>(TaskCreationOptions.RunContinuationsAsynchronously);
        private ClientChannelState state;
        private string decision,shutdownReason;
        private long revision;
        private bool resultSeen,shutdownRequested;
        public ClientSessionChannel(LoopbackFrameReader ownedTransport,string session,string viewer,bool fixtureMode=false,
            int maximumMessages=128,int maximumBytes=8*1024*1024)
        {
            if(ownedTransport==null || ownedTransport.IsClosed)throw new ArgumentException("SESSION_TRANSPORT");
            inbox=new ReceiveInbox(session,viewer,fixtureMode,maximumMessages,maximumBytes);
            commands=new CommandTracker(session,viewer);transport=ownedTransport;this.session=session;this.viewer=viewer;
        }
        public ClientChannelState State {get{lock(gate)return state;}}
        public Task<ClientChannelStop> Completion=>completion.Task;
        public TrackedCommand Pending {get{lock(gate)return commands.Current;}}
        public int QueuedCount {get{lock(gate)return inbox.Count;}}
        public bool CanSubmit {get{lock(gate)return state==ClientChannelState.Active && !transport.IsClosed && !resultSeen
            && !shutdownRequested && !string.IsNullOrEmpty(decision) && actions.Count>0 && commands.CanSubmit;}}
        private static void Fail(string code)=>throw new WireEnvelope.EnvelopeException(code);
        private void Open()
        {
            if(state!=ClientChannelState.Active)Fail("SESSION_STOPPED");
            if(transport.IsClosed){Stop("SESSION_TRANSPORT_CLOSED");Fail("SESSION_STOPPED");}
        }
        // Called under gate. Blocking socket IO never runs under gate; closing releases siblings.
        private void Stop(string code,bool graceful=false)
        {
            if(state==ClientChannelState.Disposed || state==ClientChannelState.Stopped)return;
            if(state==ClientChannelState.Completed && graceful)return;
            state=graceful?ClientChannelState.Completed:ClientChannelState.Stopped;
            actions.Clear();decision=null;commands.Disconnect();
            if(graceful)inbox.FinishInput();else inbox.Cancel();
            transport.Dispose();completion.TrySetResult(new ClientChannelStop(graceful,code));
        }
        private void Failed(string code){lock(gate)Stop(code);}
        public TrackedCommand Submit(string text,int milliseconds=5000,CancellationToken cancellation=default)
        {
            TrackedCommand receipt;
            lock(gate)
            {
                Open();if(resultSeen)Fail("SESSION_RESULT");if(shutdownRequested)Fail("SESSION_SHUTDOWN_PENDING");
                var envelope=WireMessages.Parse(text);
                if((string)envelope["message_type"]!="command" || (string)envelope["body"]["operation"]!="perform")Fail("SESSION_COMMAND_UNSUPPORTED");
                if(string.IsNullOrEmpty(decision))Fail("SESSION_NO_DECISION");
                string rejection=WireMessages.CheckCurrent(text,session,viewer,revision,decision,actions);
                if(rejection!=null)Fail(rejection);
                receipt=commands.Begin(text); // reservation is atomic with admission, before first write
            }
            try{transport.Write(text,milliseconds,cancellation);return receipt;}
            catch(TextFrame.FrameException error){Failed(error.Code);throw;}
            catch{Failed("SESSION_WRITE_FAILED");throw new WireEnvelope.EnvelopeException("SESSION_WRITE_FAILED");}
        }
        public ClientReceive ReceiveNext(int milliseconds,CancellationToken cancellation=default)
        {
            lock(gate)Open();
            try
            {
                string text=transport.Read(milliseconds,cancellation);
                lock(gate)
                {
                    Open();if(text==null){Stop("SESSION_EOF");return new ClientReceive("eof");}
                    var envelope=WireEnvelope.Parse(text);string type=(string)envelope["message_type"];
                    if(type=="snapshot" || type=="event" || type=="result")
                    {
                        bool applied=inbox.Enqueue(text);
                        if(applied)
                        {
                            var body=envelope["body"];
                            if(type=="event") {
                                long incoming=(long)body["event"]["revision"];
                                if(incoming>revision){revision=incoming;decision=null;actions.Clear();}
                            } else {
                                var snapshot=body["snapshot"];revision=(long)snapshot["revision"];
                                decision=snapshot["decision"].Type==JTokenType.Null?null:(string)snapshot["decision"]["decision_id"];
                                actions.Clear();foreach(var action in snapshot["actions"])actions.Add((string)action["action_id"]);
                                if((string)snapshot["status"]!="active"){decision=null;actions.Clear();}
                                if(type=="result"){resultSeen=true;decision=null;actions.Clear();}
                            }
                        }
                        return new ClientReceive(type,applied);
                    }
                    if(type=="ack")return new ClientReceive(type,true,commands.Accept(text));
                    if(type=="error"){string code=commands.AcceptSessionError(text);Stop(code);return new ClientReceive(type);}
                    if(type=="shutdown") {
                        var body=WireMessages.Parse(text)["body"];
                        if(!shutdownRequested || (string)body["session_id"]!=session || (string)body["viewer_id"]!=viewer
                            || (string)body["reason"]!=shutdownReason)Fail("SESSION_SHUTDOWN_INVALID");
                        Stop("SESSION_SHUTDOWN",true);return new ClientReceive(type);
                    }
                    Fail("SESSION_MESSAGE_UNSUPPORTED");return null;
                }
            }
            catch(TextFrame.FrameException error){Failed(error.Code);throw;}
            catch(WireEnvelope.EnvelopeException error){Failed(error.Code);throw;}
            catch{Failed("SESSION_RECEIVE_FAILED");throw new WireEnvelope.EnvelopeException("SESSION_RECEIVE_FAILED");}
        }
        public void RequestShutdown(string reason,int milliseconds=5000,CancellationToken cancellation=default)
        {
            string text=new JObject{["wire_version"]=1,["message_type"]="shutdown",["message_id"]="client-close",
                ["body"]=new JObject{["session_id"]=session,["viewer_id"]=viewer,["reason"]=reason}}.ToString(Formatting.None);
            WireMessages.Parse(text);
            lock(gate){Open();if(shutdownRequested)Fail("SESSION_SHUTDOWN_PENDING");shutdownRequested=true;shutdownReason=reason;}
            try{transport.Write(text,milliseconds,cancellation);}
            catch(TextFrame.FrameException error){Failed(error.Code);throw;}
            catch{Failed("SESSION_WRITE_FAILED");throw new WireEnvelope.EnvelopeException("SESSION_WRITE_FAILED");}
        }
        public bool TryTake(out ReceivePacket packet)
        {
            lock(gate){packet=null;return (state==ClientChannelState.Active || state==ClientChannelState.Completed) && inbox.TryTake(out packet);}
        }
        public void Cancel(){Failed("SESSION_CANCELLED");}
        public void Dispose()
        {
            lock(gate){if(state==ClientChannelState.Disposed)return;Stop("SESSION_DISPOSED");
                inbox.Dispose();commands.Dispose();transport.Dispose();state=ClientChannelState.Disposed;}
        }
    }
}

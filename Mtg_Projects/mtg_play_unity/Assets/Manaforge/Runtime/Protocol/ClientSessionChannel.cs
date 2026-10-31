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
        private readonly HashSet<string> options=new HashSet<string>(StringComparer.Ordinal);
        private bool canFinish,cancellable,mana;
        private readonly HashSet<string> objectIds=new HashSet<string>(StringComparer.Ordinal);
        private NumericDecisionBounds numeric;
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
        public string SessionId=>session;
        public string ViewerId=>viewer;
        public Task<ClientChannelStop> Completion=>completion.Task;
        public TrackedCommand Pending {get{lock(gate)return commands.Current;}}
        public int QueuedCount {get{lock(gate)return inbox.Count;}}
        private bool DecisionAvailable()=>state==ClientChannelState.Active && !transport.IsClosed && !resultSeen && !shutdownRequested && !string.IsNullOrEmpty(decision);
        private bool CanSubmitLocked()=>DecisionAvailable() && (actions.Count>0 || options.Count>0 || canFinish || cancellable || (mana && objectIds.Count>0) || (numeric?.Available ?? false)) && commands.CanSubmit;
        public bool CanSubmit {get{lock(gate)return CanSubmitLocked();}}
        // Availability snapshot only. Submit still performs final atomic admission and command validation.
        public bool MatchesDecision(string expectedSession,string expectedViewer,long expectedRevision,string expectedDecision,bool requireCanSubmit=false)
        {lock(gate)return DecisionAvailable() && session==expectedSession && viewer==expectedViewer && revision==expectedRevision && decision==expectedDecision && (!requireCanSubmit || CanSubmitLocked());}
        private static void Fail(string code)=>throw new WireEnvelope.EnvelopeException(code);
        private void Open()
        {
            if(state!=ClientChannelState.Active)Fail("SESSION_STOPPED");
            if(transport.IsClosed){Stop("SESSION_TRANSPORT_CLOSED");Fail("SESSION_STOPPED");}
        }
        private void ClearDecision(){decision=null;actions.Clear();options.Clear();canFinish=false;cancellable=false;numeric=null;mana=false;objectIds.Clear();}
        // Called under gate. Blocking socket IO never runs under gate; closing releases siblings.
        private void Stop(string code,bool graceful=false)
        {
            if(state==ClientChannelState.Disposed || state==ClientChannelState.Stopped)return;
            if(state==ClientChannelState.Completed && graceful)return;
            state=graceful?ClientChannelState.Completed:ClientChannelState.Stopped;
            ClearDecision();commands.Disconnect();
            if(graceful)inbox.FinishInput();else inbox.Cancel();
            transport.Dispose();completion.TrySetResult(new ClientChannelStop(graceful,code));
        }
        private void Failed(string code){lock(gate)Stop(code);}
        public TrackedCommand Submit(string text,int milliseconds=5000,CancellationToken cancellation=default)
        {using(var prepared=PrepareSubmission(text))return WriteSubmission(prepared,milliseconds,cancellation);}
        // Internal split lets a presentation lease hold only bounded admission, never socket IO.
        internal sealed class PreparedSubmission : IDisposable
        {
            private readonly ClientSessionChannel owner;private string text;private int claimed;
            internal TrackedCommand Receipt {get;}
            internal PreparedSubmission(ClientSessionChannel owner,string text,TrackedCommand receipt){this.owner=owner;this.text=text;Receipt=receipt;}
            internal string Claim(ClientSessionChannel supplied)
            {if(!ReferenceEquals(owner,supplied) || Interlocked.CompareExchange(ref claimed,1,0)!=0 || text==null)throw new WireEnvelope.EnvelopeException("SESSION_SUBMISSION_INVALID");return text;}
            public void Dispose(){Interlocked.Exchange(ref text,null);}
        }
        internal PreparedSubmission PrepareSubmission(string text)
        {
            TrackedCommand receipt;
            lock(gate)
            {
                Open();if(resultSeen)Fail("SESSION_RESULT");if(shutdownRequested)Fail("SESSION_SHUTDOWN_PENDING");
                var envelope=WireMessages.Parse(text);
                if((string)envelope["message_type"]!="command")Fail("SESSION_COMMAND_UNSUPPORTED");
                var body=envelope["body"];string operation=(string)body["operation"];
                if(operation!="perform" && operation!="choose" && operation!="finish_selection" && operation!="cancel" && operation!="choose_number" && operation!="choose_amounts" && operation!="select_mana_source")Fail("SESSION_COMMAND_UNSUPPORTED");
                if(string.IsNullOrEmpty(decision))Fail("SESSION_NO_DECISION");
                string rejection=operation=="perform"?WireMessages.CheckCurrent(text,session,viewer,revision,decision,actions)
                    :WireMessages.CheckBinding(text,session,viewer,revision,decision);
                if(rejection!=null)Fail(rejection);
                if(operation=="choose" && !options.Contains((string)body["option_id"]))Fail("OPTION_UNAVAILABLE");
                if(operation=="finish_selection" && !canFinish)Fail("SELECTION_NOT_FINISHABLE");
                if(operation=="cancel" && !cancellable)Fail("CANCELLATION_UNSUPPORTED");
                if(operation=="choose_number" || operation=="choose_amounts") {
                    string numericRejection=numeric==null?"SESSION_NUMERIC_UNAVAILABLE":numeric.Reject(operation,body);
                    if(numericRejection!=null)Fail(numericRejection);
                }
                if(operation=="select_mana_source") {
                    if(!mana)Fail("DECISION_FAMILY_MISMATCH");
                    if(!objectIds.Contains((string)body["object_id"]))Fail("STALE_OR_INVALID_OBJECT");
                }
                receipt=commands.Begin(text); // reservation is atomic with admission, before first write
                return new PreparedSubmission(this,text,receipt);
            }
        }
        internal TrackedCommand WriteSubmission(PreparedSubmission prepared,int milliseconds,CancellationToken cancellation)
        {
            string text=prepared.Claim(this);
            try{transport.Write(text,milliseconds,cancellation);return prepared.Receipt;}
            catch(TextFrame.FrameException error){Failed(error.Code);throw;}
            catch{Failed("SESSION_WRITE_FAILED");throw new WireEnvelope.EnvelopeException("SESSION_WRITE_FAILED");}
            finally{prepared.Dispose();}
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
                                if(incoming>revision){revision=incoming;ClearDecision();}
                            } else {
                                var snapshot=body["snapshot"];revision=(long)snapshot["revision"];
                                ClearDecision();var request=snapshot["decision"];
                                if(request.Type!=JTokenType.Null) {
                                    numeric=new NumericDecisionBounds(request);mana=(string)request["family"]=="mana";
                                    decision=(string)request["decision_id"];canFinish=(bool)request["can_finish"];cancellable=(bool)request["cancellable"];
                                    foreach(var option in request["options"])options.Add((string)option["option_id"]);
                                }
                                if(mana)foreach(var obj in snapshot["objects"])objectIds.Add((string)obj["object_id"]);
                                foreach(var action in snapshot["actions"])actions.Add((string)action["action_id"]);
                                if((string)snapshot["status"]!="active")ClearDecision();
                                if(type=="result"){resultSeen=true;ClearDecision();}
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

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;

namespace Manaforge.Play
{
    // Worker-owned ordered packet/receipt handoff. Never hand raw packets directly to scenes.
    public sealed class ViewerSessionUpdate : IDisposable
    {
        public ClientReceive Receive {get;} public ReceivePacket Packet {get;}
        private ProjectedDecisionFrame decision;
        public ProjectedDecisionFrame Decision=>Volatile.Read(ref decision);
        public int ByteCount=>Packet?.ByteCount??0;
        internal ViewerSessionUpdate(ClientReceive receive,ReceivePacket packet,ProjectedDecisionFrame decision=null){Receive=receive;Packet=packet;this.decision=decision;}
        public void Dispose(){Interlocked.Exchange(ref decision,null);Packet?.Dispose();}
    }
    public sealed class ViewerSessionOutcome
    {
        public CardProjectionContext Context {get;} public string Status {get;} public string Result {get;}
        internal ViewerSessionOutcome(ProjectedCardFrame frame){Context=frame.Context;Status=frame.Status;Result=frame.Result;}
    }
    public sealed class ViewerSessionStop
    {
        public string Code {get;} public bool Graceful {get;}
        public TrackedCommand Pending {get;} public TrackedCommand LastReceipt {get;}
        public ViewerSessionOutcome Outcome {get;}
        internal ViewerSessionStop(string code,bool graceful,TrackedCommand pending,TrackedCommand receipt,ViewerSessionOutcome outcome)
        {Code=code;Graceful=graceful;Pending=pending;LastReceipt=receipt;Outcome=outcome;}
    }
    // Exclusive receive consumer of an already authenticated channel. Host retains channel ownership.
    public sealed class ViewerSessionReceiver : IDisposable
    {
        private readonly object gate=new object();private readonly ClientSessionChannel channel;
        private readonly ViewerSurfaceTicket ticket;private readonly bool fixtureMode;
        private readonly Queue<ViewerSessionUpdate> updates=new Queue<ViewerSessionUpdate>();
        private readonly int maximumUpdates,maximumBytes;private int bytes,receiving;private bool stopped;
        private TrackedCommand lastReceipt;private ViewerSessionOutcome outcome;
        private readonly TaskCompletionSource<ViewerSessionStop> completion=new TaskCompletionSource<ViewerSessionStop>(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task<ViewerSessionStop> Completion=>completion.Task;
        public ViewerDecisionBinding Decisions {get;}
        public int Count {get{lock(gate)return updates.Count;}}
        public int QueuedBytes {get{lock(gate)return bytes;}}
        public bool IsStopped {get{lock(gate)return stopped;}}
        public ViewerSessionReceiver(ClientSessionChannel channel,ViewerSurfaceTicket ticket,bool fixtureMode=false,int maximumUpdates=128,int maximumBytes=8*1024*1024)
        {
            if(channel==null || ticket==null || channel.SessionId!=ticket.SessionId || channel.ViewerId!=ticket.ViewerId
                || channel.State!=ClientChannelState.Active || channel.QueuedCount!=0 || ticket.Mailbox.IsStopped
                || maximumUpdates<1 || maximumUpdates>1024 || maximumBytes<1 || maximumBytes>64*1024*1024)throw new ArgumentException("VIEWER_RECEIVE_CONTEXT");
            this.channel=channel;this.ticket=ticket;this.fixtureMode=fixtureMode;this.maximumUpdates=maximumUpdates;this.maximumBytes=maximumBytes;
            Decisions=new ViewerDecisionBinding(channel,ticket);
            channel.Completion.ContinueWith(task=>Stop("VIEWER_CHANNEL_STOPPED",task.Result.Graceful),TaskScheduler.Default);
        }
        private void Stop(string code,bool graceful=false)
        {
            TrackedCommand receipt;ViewerSessionOutcome result;
            lock(gate) {
                if(stopped)return;stopped=true;while(updates.Count>0)updates.Dequeue().Dispose();bytes=0;
                ticket.Mailbox.Dispose();Decisions.Dispose();receipt=lastReceipt;result=outcome;
            }
            // Do not dispose the borrowed tracker: the host still owns uncertain-command evidence.
            if(channel.State==ClientChannelState.Active)channel.Cancel();
            completion.TrySetResult(new ViewerSessionStop(code,graceful,channel.Pending,receipt,result));
        }
        public bool TryTake(out ViewerSessionUpdate update)
        {lock(gate){update=null;if(stopped || updates.Count==0)return false;update=updates.Dequeue();bytes-=update.ByteCount;return true;}}
        // Blocking transport entry point: host schedules on its connection worker, with explicit read budget.
        // Invalid budget precedes any mutation. Stop/cancel revoke only the captured viewer epoch.
        public bool ReceiveOnce(int milliseconds=5000,CancellationToken cancellation=default)
        {
            if(milliseconds<1 || milliseconds>60000)throw new ArgumentOutOfRangeException(nameof(milliseconds));
            if(Interlocked.CompareExchange(ref receiving,1,0)!=0){Stop("VIEWER_RECEIVE_CONCURRENT");return false;}
            ReceivePacket packet=null;ViewerSessionUpdate update=null;
            try {
                if(IsStopped)return false;
                if(ticket.Mailbox.IsStopped){Stop("VIEWER_REVOKED");return false;}
                var received=channel.ReceiveNext(milliseconds,cancellation);
                if(channel.State!=ClientChannelState.Active){Stop("VIEWER_CHANNEL_STOPPED",channel.Completion.Result.Graceful);return false;}
                ProjectedCardFrame frame=null;ProjectedDecisionFrame decisions=null;long? minimum=null;
                if(received.Applied && (received.Type=="snapshot" || received.Type=="event" || received.Type=="result")) {
                    if(!channel.TryTake(out packet))throw new InvalidOperationException();
                    string text=packet.ReadJson();
                    if(received.Type=="event")minimum=(long)ReceiveMessages.Parse(text,ticket.SessionId,ticket.ViewerId,0,fixtureMode)["body"]["event"]["revision"];
                    else {var snapshot=ViewerCardProjection.ValidateSnapshot(text,ticket.SessionId,ticket.ViewerId,0,fixtureMode);frame=new ProjectedCardFrame(snapshot);decisions=ViewerDecisionProjection.Project(snapshot);}
                }
                update=new ViewerSessionUpdate(received,packet,decisions);packet=null;
                lock(gate) {
                    if(stopped || ticket.Mailbox.IsStopped){Stop("VIEWER_REVOKED");return false;}
                    if(received.Receipt!=null){lastReceipt=received.Receipt;Decisions.ObserveReceipt(received.Receipt);}
                    if(received.Type=="result" && frame!=null)outcome=new ViewerSessionOutcome(frame);
                    if(updates.Count>=maximumUpdates || update.ByteCount>maximumBytes-bytes){Stop("VIEWER_RECEIVE_OVERFLOW");return false;}
                    if(minimum.HasValue){ticket.Mailbox.AdvanceMinimumRevision(minimum.Value);Decisions.AdvanceMinimumRevision(minimum.Value);}
                    if(frame!=null)ticket.Mailbox.TryPostFrame(frame);
                    if(decisions!=null)Decisions.Observe(decisions);
                    updates.Enqueue(update);bytes+=update.ByteCount;update=null;return true;
                }
            }
            catch{Stop("VIEWER_RECEIVE_FAILED");return false;}
            finally{packet?.Dispose();update?.Dispose();Volatile.Write(ref receiving,0);}
        }
        public void Cancel(){Stop("VIEWER_OWNER_CANCELLED");}
        public void Dispose(){Stop("VIEWER_RECEIVE_DISPOSED");}
    }
}

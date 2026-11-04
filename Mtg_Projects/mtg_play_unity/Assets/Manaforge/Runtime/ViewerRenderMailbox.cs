using System;
using System.Collections.Generic;

namespace Manaforge.Play
{
    // CPU-only ownership boundary: many worker producers, one UI consumer. No Unity graphics/IO.
    public sealed class ViewerRenderMailbox : IDisposable
    {
        private readonly object gate=new object();
        private readonly ViewerSurfaceTicket ticket;
        private readonly int maximumArtwork;
        private readonly long maximumBytes;
        private readonly Queue<PreparedCardArtwork> artwork=new Queue<PreparedCardArtwork>();
        private readonly HashSet<ViewerArtworkRequest> requests=new HashSet<ViewerArtworkRequest>();
        private ProjectedCardFrame latest;
        private readonly ViewerAnimationJournal animations=new ViewerAnimationJournal();
        private long newestRevision=-1,minimumRevision,bytes;
        private bool stopped;
        private System.Threading.Tasks.TaskCompletionSource<bool> space=NewSpace();
        private static System.Threading.Tasks.TaskCompletionSource<bool> NewSpace()=>new System.Threading.Tasks.TaskCompletionSource<bool>(System.Threading.Tasks.TaskCreationOptions.RunContinuationsAsynchronously);
        private void SignalSpace(){var previous=space;space=NewSpace();previous.TrySetResult(true);}
        internal ViewerRenderMailbox(ViewerSurfaceTicket ticket,int maximumArtwork,long maximumBytes)
        {ValidateLimits(maximumArtwork,maximumBytes);this.ticket=ticket;this.maximumArtwork=maximumArtwork;this.maximumBytes=maximumBytes;}
        internal static void ValidateLimits(int count,long bytes)
        {if(count<1 || count>64 || bytes<1 || bytes>64*1024*1024)throw new ArgumentException("RENDER_MAILBOX_LIMITS");}
        public bool IsStopped {get{lock(gate)return stopped;}}
        public long MinimumRevision {get{lock(gate)return minimumRevision;}}
        public int ArtworkCount {get{lock(gate)return artwork.Count;}}
        public long ArtworkBytes {get{lock(gate)return bytes;}}
        internal ProjectedCardFrame AnimationFrame {get{lock(gate)return stopped?null:latest;}}
        public bool HasPendingFrame {get{lock(gate)return latest!=null;}}
        private void ClearArtwork()
        {while(artwork.Count>0)artwork.Dequeue().Dispose();requests.Clear();bytes=0;SignalSpace();}
        // Coalesces immutable snapshots, not game events, command receipts or wire history.
        public bool TryPostFrame(ProjectedCardFrame frame,ProjectedDecisionFrame decision=null)
        {
            if(frame==null)throw new ArgumentNullException(nameof(frame));
            if(decision!=null && (decision.Context.SessionId!=frame.Context.SessionId || decision.Context.ViewerId!=frame.Context.ViewerId || decision.Context.Revision!=frame.Context.Revision))return false;
            lock(gate) {
                if(stopped || frame.Context.SessionId!=ticket.SessionId || frame.Context.ViewerId!=ticket.ViewerId
                    || frame.Context.Revision<minimumRevision || frame.Context.Revision<=newestRevision)return false;
                animations.Observe(frame,decision);
                newestRevision=frame.Context.Revision;latest=frame;ClearArtwork();return true;
            }
        }
        public bool AdvanceMinimumRevision(long minimum)
        {
            if(minimum<0)throw new ArgumentOutOfRangeException(nameof(minimum));
            lock(gate) {
                if(stopped || minimum<=minimumRevision)return false;
                minimumRevision=minimum;
                if(latest!=null && latest.Context.Revision<minimum)latest=null;
                if(newestRevision<minimum)ClearArtwork();return true;
            }
        }
        internal bool AllowsFrame(long revision){lock(gate)return !stopped && revision>=minimumRevision && revision>=newestRevision;}
        internal bool AllowsArtwork(long revision){lock(gate)return !stopped && revision>=minimumRevision && revision==newestRevision;}
        internal void ObserveAppliedFrame(long revision)
        {
            lock(gate) {
                if(stopped)return;
                if(revision>newestRevision){newestRevision=revision;ClearArtwork();}
                if(latest!=null && latest.Context.Revision<=revision)latest=null;
            }
        }
        // Consumes the completion on every non-null call, including rejection after shutdown.
        public bool TryPostArtwork(PreparedCardArtwork prepared)
        {
            int result=PostArtworkDeferred(prepared,out _);
            if(result==0)prepared.Dispose();
            return result==1;
        }
        // 1 transfers ownership, -1 rejects/consumes, 0 retains producer ownership
        // until the bounded queue drains. A stale epoch wakes and rejects promptly.
        internal int PostArtworkDeferred(PreparedCardArtwork prepared,out System.Threading.Tasks.Task available)
        {
            if(prepared==null)throw new ArgumentNullException(nameof(prepared));
            lock(gate) {
                available=null;
                if(artwork.Contains(prepared))return -1; // Already owned: do not clear its queued buffer.
                long size=(long)prepared.Width*prepared.Height*4;var request=prepared.Request;
                if(stopped || prepared.IsDisposed || !ReferenceEquals(request.Ticket,ticket) || request.Revision!=newestRevision
                    || request.Revision<minimumRevision || requests.Contains(request) || size>maximumBytes) {
                    prepared.Dispose();return -1;
                }
                if(artwork.Count>=maximumArtwork || size>maximumBytes-bytes){available=space.Task;return 0;}
                artwork.Enqueue(prepared);requests.Add(request);bytes+=size;return 1;
            }
        }
        public bool TryPeekFrame(out ProjectedCardFrame frame){lock(gate){frame=stopped?null:latest;return frame!=null;}}
        // Pending snapshots always precede texture work. Ownership transfers to the UI consumer.
        public bool TryTakeArtwork(out PreparedCardArtwork prepared)
        {
            lock(gate) {
                prepared=null;if(stopped || latest!=null || artwork.Count==0)return false;
                prepared=artwork.Dequeue();requests.Remove(prepared.Request);bytes-=(long)prepared.Width*prepared.Height*4;SignalSpace();return true;
            }
        }
        internal bool HasMajorAnimation {get{lock(gate)return !stopped && animations.HasMajor;}}
        internal GameplayMotionBatch[] TakeAnimations(long revision)
        {lock(gate)return stopped?Array.Empty<GameplayMotionBatch>():animations.TakeThrough(revision);}
        public void Dispose(){lock(gate){if(stopped)return;stopped=true;latest=null;animations.Clear();ClearArtwork();}}
    }
}

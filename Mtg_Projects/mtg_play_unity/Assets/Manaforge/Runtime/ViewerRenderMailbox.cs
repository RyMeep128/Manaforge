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
        private long newestRevision=-1,minimumRevision,bytes;
        private bool stopped;
        internal ViewerRenderMailbox(ViewerSurfaceTicket ticket,int maximumArtwork,long maximumBytes)
        {ValidateLimits(maximumArtwork,maximumBytes);this.ticket=ticket;this.maximumArtwork=maximumArtwork;this.maximumBytes=maximumBytes;}
        internal static void ValidateLimits(int count,long bytes)
        {if(count<1 || count>64 || bytes<1 || bytes>64*1024*1024)throw new ArgumentException("RENDER_MAILBOX_LIMITS");}
        public bool IsStopped {get{lock(gate)return stopped;}}
        public long MinimumRevision {get{lock(gate)return minimumRevision;}}
        public int ArtworkCount {get{lock(gate)return artwork.Count;}}
        public long ArtworkBytes {get{lock(gate)return bytes;}}
        public bool HasPendingFrame {get{lock(gate)return latest!=null;}}
        private void ClearArtwork()
        {while(artwork.Count>0)artwork.Dequeue().Dispose();requests.Clear();bytes=0;}
        // Coalesces immutable snapshots, not game events, command receipts or wire history.
        public bool TryPostFrame(ProjectedCardFrame frame)
        {
            if(frame==null)throw new ArgumentNullException(nameof(frame));
            lock(gate) {
                if(stopped || frame.Context.SessionId!=ticket.SessionId || frame.Context.ViewerId!=ticket.ViewerId
                    || frame.Context.Revision<minimumRevision || frame.Context.Revision<=newestRevision)return false;
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
            if(prepared==null)throw new ArgumentNullException(nameof(prepared));
            lock(gate) {
                if(artwork.Contains(prepared))return false; // Already owned: do not clear its queued buffer.
                long size=(long)prepared.Width*prepared.Height*4;var request=prepared.Request;
                if(stopped || prepared.IsDisposed || !ReferenceEquals(request.Ticket,ticket) || request.Revision!=newestRevision
                    || request.Revision<minimumRevision || requests.Contains(request) || artwork.Count>=maximumArtwork || size>maximumBytes-bytes) {
                    prepared.Dispose();return false;
                }
                artwork.Enqueue(prepared);requests.Add(request);bytes+=size;return true;
            }
        }
        public bool TryPeekFrame(out ProjectedCardFrame frame){lock(gate){frame=stopped?null:latest;return frame!=null;}}
        // Pending snapshots always precede texture work. Ownership transfers to the UI consumer.
        public bool TryTakeArtwork(out PreparedCardArtwork prepared)
        {
            lock(gate) {
                prepared=null;if(stopped || latest!=null || artwork.Count==0)return false;
                prepared=artwork.Dequeue();requests.Remove(prepared.Request);bytes-=(long)prepared.Width*prepared.Height*4;return true;
            }
        }
        public void Dispose(){lock(gate){if(stopped)return;stopped=true;latest=null;ClearArtwork();}}
    }
}

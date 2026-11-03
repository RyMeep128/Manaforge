using System;
using Manaforge.Play.Protocol;

namespace Manaforge.Play
{
    // Opaque per-snapshot offer. Retained offers never expose another offer's data.
    public sealed class ViewerDecisionOffer
    {
        private readonly ViewerDecisionBinding owner;
        internal ViewerDecisionOffer(ViewerDecisionBinding owner){this.owner=owner;}
        public ProjectedDecisionFrame Frame=>owner.Read(this);
        public bool CanSubmit=>owner.CanSubmit(this);
    }
    // Owns display binding only, not legality, command IDs, IO or a second game state.
    public sealed class ViewerDecisionBinding : IDisposable
    {
        private readonly object gate=new object();private readonly ClientSessionChannel channel;private readonly ViewerSurfaceTicket ticket;
        private ProjectedDecisionFrame frame;private ViewerDecisionOffer offer;private Reservation reserved;private bool stopped;
        internal sealed class Reservation
        {internal readonly ViewerDecisionOffer Offer;internal readonly ProjectedDecisionFrame Frame;internal Reservation(ViewerDecisionOffer offer,ProjectedDecisionFrame frame){Offer=offer;Frame=frame;}}
        internal ViewerDecisionBinding(ClientSessionChannel channel,ViewerSurfaceTicket ticket){this.channel=channel;this.ticket=ticket;}
        private bool CurrentLocked()=>!stopped && frame!=null && offer!=null && frame.Status=="active" && frame.Decision!=null
            && ticket.Mailbox.AllowsFrame(frame.Context.Revision)
            && channel.MatchesDecision(ticket.SessionId,ticket.ViewerId,frame.Context.Revision,frame.Decision.DecisionId);
        public ViewerDecisionOffer Current {get{lock(gate)return CurrentLocked()?offer:null;}}
        public bool IsCurrent(ViewerDecisionOffer supplied){lock(gate)return ReferenceEquals(supplied,offer) && CurrentLocked();}
        internal ProjectedDecisionFrame Read(ViewerDecisionOffer supplied){lock(gate)return ReferenceEquals(supplied,offer) && CurrentLocked()?frame:null;}
        internal bool CanSubmit(ViewerDecisionOffer supplied){lock(gate)return reserved==null && ReferenceEquals(supplied,offer) && CurrentLocked() && channel.MatchesDecision(ticket.SessionId,ticket.ViewerId,frame.Context.Revision,frame.Decision.DecisionId,true);}
        internal Reservation Reserve(ViewerDecisionOffer supplied)
        {
            lock(gate) {
                if(!ReferenceEquals(supplied,offer) || !CurrentLocked())throw new WireEnvelope.EnvelopeException("STALE_DECISION");
                if(reserved!=null)throw new WireEnvelope.EnvelopeException("COMMAND_PENDING");
                if(!channel.MatchesDecision(ticket.SessionId,ticket.ViewerId,frame.Context.Revision,frame.Decision.DecisionId,true)) {
                    var pending=channel.Pending;throw new WireEnvelope.EnvelopeException(pending==null?"COMMAND_UNAVAILABLE":pending.State==CommandState.Uncertain?"COMMAND_UNCERTAIN":"COMMAND_PENDING");
                }
                reserved=new Reservation(supplied,frame);return reserved;
            }
        }
        internal ClientSessionChannel.PreparedSubmission Prepare(Reservation supplied,string text)
        {
            lock(gate) {
                if(!ReferenceEquals(supplied,reserved) || !ReferenceEquals(supplied.Offer,offer) || !CurrentLocked())throw new WireEnvelope.EnvelopeException("STALE_DECISION");
                return channel.PrepareSubmission(text);
            }
        }
        internal void Release(Reservation supplied){lock(gate){if(ReferenceEquals(supplied,reserved))reserved=null;}}
        internal void Observe(ProjectedDecisionFrame snapshot)
        {
            lock(gate) {
                if(stopped)return;
                if(snapshot==null || snapshot.Context.SessionId!=ticket.SessionId || snapshot.Context.ViewerId!=ticket.ViewerId)throw new InvalidOperationException("VIEWER_DECISION_CONTEXT");
                frame=null;offer=null;
                if(snapshot.Status!="active" || snapshot.Decision==null || !ticket.Mailbox.AllowsFrame(snapshot.Context.Revision))return;
                frame=snapshot;offer=new ViewerDecisionOffer(this);
            }
        }
        internal void AdvanceMinimumRevision(long revision){lock(gate){if(frame!=null && frame.Context.Revision<revision){frame=null;offer=null;}}}
        internal void ObserveReceipt(TrackedCommand receipt)
        {
            if(receipt.State!=CommandState.Rejected || (receipt.Code!="STALE_REVISION" && receipt.Code!="STALE_DECISION" && receipt.Code!="ACTION_UNAVAILABLE" && receipt.Code!="SESSION_MISMATCH" && receipt.Code!="VIEWER_MISMATCH"))return;
            lock(gate){if(frame!=null && receipt.RequestRevision==frame.Context.Revision && receipt.DecisionId==frame.Decision.DecisionId){frame=null;offer=null;}}
        }
        public void Dispose(){lock(gate){stopped=true;frame=null;offer=null;reserved=null;}}
    }
}

using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Opaque epoch ticket. A worker may retain it, but only this UI owner may publish with it.
    public sealed class ViewerSurfaceTicket
    {
        public string SessionId {get;} public string ViewerId {get;}
        public ViewerRenderMailbox Mailbox {get;}
        internal ViewerSurfaceTicket(string session,string viewer,int maximumArtwork,long maximumBytes)
        {SessionId=session;ViewerId=viewer;Mailbox=new ViewerRenderMailbox(this,maximumArtwork,maximumBytes);}
    }
    public sealed class ViewerCardSurface : IDisposable
    {
        private readonly int thread=Thread.CurrentThread.ManagedThreadId;
        private readonly Dictionary<string,CardView> views=new Dictionary<string,CardView>(StringComparer.Ordinal);
        private readonly Dictionary<string,ProjectedCard> cards=new Dictionary<string,ProjectedCard>(StringComparer.Ordinal);
        private readonly Dictionary<string,ViewerArtworkRequest> requests=new Dictionary<string,ViewerArtworkRequest>(StringComparer.Ordinal);
        private readonly Dictionary<string,ArtworkBinding> artwork=new Dictionary<string,ArtworkBinding>(StringComparer.Ordinal);
        private string inspectedObject;
        private sealed class ArtworkBinding
        {
            public readonly Texture2D Texture;public readonly CardVisualIdentity Identity;public readonly CardCompactProfile Profile;
            public readonly string Oracle,Printing;
            public ArtworkBinding(PreparedCardArtwork prepared,Texture2D texture)
            {Texture=texture;Identity=prepared.Identity;Profile=prepared.Profile;Oracle=prepared.Request.OracleId;Printing=prepared.Request.PrintingId;}
        }
        private ViewerSurfaceTicket ticket;
        private IDisposable privateAssets;
        private ViewerArtworkJobs artworkJobs;
        private long revision=-1,minimumRevision;
        private int readyFrame;
        private bool disposed,transitioning,faulted;
        public VisualElement CardsRoot {get;}=new VisualElement{name="viewer-cards"};
        public CardView InspectionView {get;}=new CardView();
        public ViewerCardSurface(VisualElement parent)
        {
            if(parent==null)throw new ArgumentNullException(nameof(parent));
            CardsRoot.style.flexDirection=FlexDirection.Row;CardsRoot.style.flexWrap=Wrap.Wrap;
            InspectionView.SetPresentation(CardPresentationMode.Full,300);
            parent.Add(CardsRoot);parent.Add(InspectionView);
        }
        private void ThreadOnly(){if(thread!=Thread.CurrentThread.ManagedThreadId)throw new InvalidOperationException("VIEWER_SURFACE_THREAD");}
        private void Open()
        {
            ThreadOnly();if(disposed)throw new ObjectDisposedException(nameof(ViewerCardSurface));
            if(transitioning || faulted)throw new InvalidOperationException("VIEWER_SURFACE_UNAVAILABLE");
        }
        // Clear references before asking an explicitly transferred private resource scope to dispose.
        private void ClearOwnedState()
        {
            ticket?.Mailbox.Dispose();artworkJobs?.Dispose();artworkJobs=null;ticket=null;revision=-1;cards.Clear();requests.Clear();artwork.Clear();inspectedObject=null;InspectionView.Conceal();
            foreach(var view in views.Values)view.Dispose();views.Clear();CardsRoot.Clear();
            var assets=privateAssets;privateAssets=null;
            try{assets?.Dispose();}catch{privateAssets=assets;throw;}
        }
        // Ownership of newPrivateAssets transfers only on success. Never pass a shared/public cache.
        public ViewerSurfaceTicket BeginViewer(string session,string viewer,IDisposable newPrivateAssets=null,long minimumRevision=0,
            int maximumArtworkCompletions=32,long maximumArtworkBytes=8*1024*1024)
        {
            Open();
            if(string.IsNullOrWhiteSpace(session) || string.IsNullOrWhiteSpace(viewer) || minimumRevision<0)throw new ArgumentException("VIEWER_SURFACE_CONTEXT");
            ViewerRenderMailbox.ValidateLimits(maximumArtworkCompletions,maximumArtworkBytes);
            var artworkScope=newPrivateAssets as ViewerArtworkScope;artworkScope?.CheckUnowned();
            transitioning=true;
            try{ClearOwnedState();}
            catch{faulted=true;throw new InvalidOperationException("VIEWER_SURFACE_CLEANUP_FAILED");}
            finally{transitioning=false;}
            // One whole empty rendered frame, including deferred Unity texture destruction.
            readyFrame=Time.frameCount+2;
            this.minimumRevision=minimumRevision;
            var next=new ViewerSurfaceTicket(session,viewer,maximumArtworkCompletions,maximumArtworkBytes);next.Mailbox.AdvanceMinimumRevision(minimumRevision);
            try{artworkScope?.Claim(next);}catch{faulted=true;throw new InvalidOperationException("VIEWER_SURFACE_ASSET_SCOPE");}
            privateAssets=newPrivateAssets;ticket=next;return ticket;
        }
        // Trusted receive owner advances this watermark when newer events precede their full snapshot.
        // Visibility revocation/disconnect must use ClearViewer, not merely advance this watermark.
        public bool SetMinimumRevision(ViewerSurfaceTicket supplied,long minimum)
        {
            Open();if(minimum<0)throw new ArgumentOutOfRangeException(nameof(minimum));
            if(ticket==null || !ReferenceEquals(ticket,supplied) || minimum<=minimumRevision)return false;
            minimumRevision=minimum;requests.Clear();ticket.Mailbox.AdvanceMinimumRevision(minimum);return true;
        }
        public bool ClearViewer(ViewerSurfaceTicket supplied)
        {
            Open();if(ticket==null || !ReferenceEquals(ticket,supplied))return false;
            transitioning=true;
            try{ClearOwnedState();return true;}
            catch{faulted=true;throw new InvalidOperationException("VIEWER_SURFACE_CLEANUP_FAILED");}
            finally{transitioning=false;}
        }
        public bool TryPresent(ViewerSurfaceTicket supplied,ProjectedCardFrame frame)
        {
            Open();if(frame==null)throw new ArgumentNullException(nameof(frame));
            if(ticket==null || !ReferenceEquals(ticket,supplied) || Time.frameCount<readyFrame
                || !ticket.Mailbox.AllowsFrame(frame.Context.Revision)
                || frame.Context.SessionId!=ticket.SessionId || frame.Context.ViewerId!=ticket.ViewerId
                || frame.Context.Revision<minimumRevision || frame.Context.Revision<=revision)return false;
            // No wire decision/action IDs are stored here. Inspection never submits a game command.
            transitioning=true;
            try {
                InspectionView.Conceal();inspectedObject=null;cards.Clear();requests.Clear();
                var present=new HashSet<string>(StringComparer.Ordinal);
                foreach(var card in frame.Cards) {
                    present.Add(card.ObjectId);cards.Add(card.ObjectId,card);
                    if(!views.TryGetValue(card.ObjectId,out var view)) {
                        view=new CardView();view.SetPresentation(CardPresentationMode.Compact,160);
                        views.Add(card.ObjectId,view);CardsRoot.Add(view);
                    }
                    if(artwork.TryGetValue(card.ObjectId,out var binding) && (!ArtworkPermitted(card)
                        || binding.Oracle!=card.Printing.OracleId || binding.Printing!=card.Printing.PrintingId))artwork.Remove(card.ObjectId);
                    view.SetPresentation(card.Zone=="battlefield"?CardPresentationMode.Compact:CardPresentationMode.Full,card.Zone=="battlefield"?160:220);
                    Bind(view,card);
                }
                foreach(var id in new List<string>(views.Keys))if(!present.Contains(id)){views[id].Dispose();views.Remove(id);artwork.Remove(id);}
                revision=frame.Context.Revision;ticket.Mailbox.ObserveAppliedFrame(revision);return true;
            }
            catch {
                faulted=true;
                try{ClearOwnedState();}catch{}
                throw new InvalidOperationException("VIEWER_SURFACE_PRESENT_FAILED");
            }
            finally{transitioning=false;}
        }
        private static bool ArtworkPermitted(ProjectedCard card)=>!card.Hidden && card.FaceDown==false
            && !string.IsNullOrWhiteSpace(card.Printing?.PrintingId) && !string.IsNullOrWhiteSpace(card.Printing?.OracleId);
        public ViewerArtworkJobs CreateArtworkJobs(ViewerSurfaceTicket supplied,
            Func<ViewerArtworkRequest,CancellationToken,System.Threading.Tasks.Task<PreparedCardArtwork>> provider,int concurrency=2,int maximumQueued=32)
        {
            Open();
            if(ticket==null || !ReferenceEquals(ticket,supplied) || ticket.Mailbox.IsStopped || !(privateAssets is ViewerArtworkScope) || artworkJobs!=null)
                throw new InvalidOperationException("VIEWER_SURFACE_JOBS_UNAVAILABLE");
            artworkJobs=new ViewerArtworkJobs(ticket,provider,concurrency,maximumQueued);return artworkJobs;
        }
        public ViewerArtworkRequest RequestArtwork(ViewerSurfaceTicket supplied,string objectId)
        {
            Open();
            if(ticket==null || !ReferenceEquals(ticket,supplied) || !(privateAssets is ViewerArtworkScope) || revision<minimumRevision
                || !ticket.Mailbox.AllowsArtwork(revision)
                || objectId==null || !cards.TryGetValue(objectId,out var card) || !ArtworkPermitted(card) || artwork.ContainsKey(objectId))return null;
            if(!requests.TryGetValue(objectId,out var request)){request=new ViewerArtworkRequest(ticket,card);requests.Add(objectId,request);}return request;
        }
        // On a valid UI-thread entry, consumes/clears the prepared CPU buffer even when rejected.
        public bool TryApplyArtwork(ViewerSurfaceTicket supplied,PreparedCardArtwork prepared)
        {
            Open();if(prepared==null)throw new ArgumentNullException(nameof(prepared));
            try {
                var request=prepared.Request;
                if(prepared.IsDisposed || ticket==null || !ReferenceEquals(ticket,supplied) || !ReferenceEquals(ticket,request.Ticket)
                    || !ticket.Mailbox.AllowsArtwork(request.Revision)
                    || request.Revision!=revision || revision<minimumRevision || !(privateAssets is ViewerArtworkScope scope)
                    || !requests.TryGetValue(request.ObjectId,out var pending) || !ReferenceEquals(pending,request)
                    || !cards.TryGetValue(request.ObjectId,out var card) || !ArtworkPermitted(card))return false;
                transitioning=true;
                try {
                    requests.Remove(request.ObjectId);
                    if(!scope.TryUpload(prepared,out var texture))return false;
                    artwork[card.ObjectId]=new ArtworkBinding(prepared,texture);Bind(views[card.ObjectId],card);
                    if(inspectedObject==card.ObjectId){Bind(InspectionView,card);InspectionView.style.rotate=new Rotate(new Angle(0));}
                    return true;
                }
                catch {
                    faulted=true;try{ClearOwnedState();}catch{}
                    throw new InvalidOperationException("VIEWER_SURFACE_ARTWORK_FAILED");
                }
                finally{transitioning=false;}
            }
            finally{prepared.Dispose();}
        }
        private void Bind(CardView view,ProjectedCard card)
        {
            view.style.rotate=new Rotate(new Angle(0));
            if(card.Hidden){view.Conceal();return;}
            artwork.TryGetValue(card.ObjectId,out var binding);
            if(binding==null)view.BindUnavailable();else view.Bind(binding.Identity,binding.Texture,binding.Profile?.Crop??CardCompactProfile.StandardArtCrop);
            var c=card.Characteristics;
            string pt=c?.Power!=null && c.Toughness!=null?c.Power+"/"+c.Toughness:null;
            // No printed text, invented mana cost, inferred artwork/face or reconstructed current rules.
            string unavailable=binding==null?"Artwork / rules unavailable":"Current rules unavailable";
            if(card.Tapped==null)unavailable+=" / tap state unavailable";
            view.UpdateValues(new CardDisplayValues(c?.Name,null,c?.TypeLine,null,pt,unavailable,binding?.Profile,loyalty:c?.Loyalty,defense:c?.Defense,hidePrintedStats:true));
            if(card.Tapped==true)view.style.rotate=new Rotate(new Angle(90));
        }
        public bool Inspect(ViewerSurfaceTicket supplied,string objectId)
        {
            Open();if(ticket==null || !ReferenceEquals(ticket,supplied) || !ticket.Mailbox.AllowsFrame(revision))return false;
            transitioning=true;
            try {
                InspectionView.Conceal();inspectedObject=null;
                if(objectId==null || !cards.TryGetValue(objectId,out var card) || card.Hidden)return false;
                Bind(InspectionView,card);InspectionView.style.rotate=new Rotate(new Angle(0));inspectedObject=objectId;return true;
            }
            catch {
                faulted=true;try{ClearOwnedState();}catch{}
                throw new InvalidOperationException("VIEWER_SURFACE_INSPECTION_FAILED");
            }
            finally{transitioning=false;}
        }
        // Host calls once per UI update. No waiting, decoding or unbounded draining.
        public int DrainMailbox(ViewerSurfaceTicket supplied,int maximumArtworkUploads=2)
        {
            Open();if(maximumArtworkUploads<0 || maximumArtworkUploads>16)throw new ArgumentOutOfRangeException(nameof(maximumArtworkUploads));
            if(ticket==null || !ReferenceEquals(ticket,supplied))return 0;
            var mailbox=ticket.Mailbox;
            if(mailbox.IsStopped){ClearViewer(supplied);return 0;}
            SetMinimumRevision(supplied,mailbox.MinimumRevision);
            int processed=0;
            if(mailbox.TryPeekFrame(out var frame)) {
                if(!TryPresent(supplied,frame)){if(mailbox.IsStopped)ClearViewer(supplied);return 0;}processed++;
            }
            for(int i=0;i<maximumArtworkUploads && mailbox.TryTakeArtwork(out var prepared);i++) {
                TryApplyArtwork(supplied,prepared);processed++;
            }
            if(mailbox.IsStopped)ClearViewer(supplied);
            return processed;
        }
        public void Dispose()
        {
            ThreadOnly();if(transitioning)throw new InvalidOperationException("VIEWER_SURFACE_UNAVAILABLE");
            if(disposed && privateAssets==null)return;disposed=true;transitioning=true;
            try{ClearOwnedState();}
            catch{throw new InvalidOperationException("VIEWER_SURFACE_CLEANUP_FAILED");}
            finally{try{CardsRoot.RemoveFromHierarchy();InspectionView.Dispose();}finally{transitioning=false;}}
        }
    }
}

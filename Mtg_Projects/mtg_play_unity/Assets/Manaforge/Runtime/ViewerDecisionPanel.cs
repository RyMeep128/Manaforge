using System;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using UnityEngine.UIElements;
using UnityEngine;

namespace Manaforge.Play
{
    // Main-thread presentation of explicit engine choices. No receive-queue ownership or automatic play.
    public sealed class ViewerDecisionPanel : IDisposable
    {
        public const int PageSize=16;
        private readonly int thread=Thread.CurrentThread.ManagedThreadId;
        private readonly ViewerSessionHost host;
        public VisualElement Root {get;}=new VisualElement{name="viewer-decision-panel"};
        private readonly Label prompt=new Label{name="decision-prompt",enableRichText=false};
        private readonly Label status=new Label{name="decision-status",enableRichText=false};
        private readonly VisualElement controls=new VisualElement{name="decision-controls"};
        private readonly VisualElement pages=new VisualElement{name="decision-pages"};
        private ViewerDecisionOffer offer;private int page;private bool disposed;private Task<TrackedCommand> pending;
        public ViewerDecisionPanel(VisualElement parent,ViewerSessionHost host)
        {
            if(parent==null || host==null)throw new ArgumentNullException();this.host=host;
            Root.style.backgroundColor=new Color(.07f,.10f,.13f);Root.style.paddingLeft=16;Root.style.paddingRight=16;Root.style.paddingTop=12;Root.style.paddingBottom=12;
            prompt.style.fontSize=20;prompt.style.color=Color.white;prompt.style.marginBottom=8;prompt.style.whiteSpace=WhiteSpace.Normal;
            status.style.fontSize=14;status.style.color=new Color(.8f,.85f,.9f);status.style.marginBottom=8;status.style.whiteSpace=WhiteSpace.Normal;pages.style.flexDirection=FlexDirection.Row;
            Root.Add(prompt);Root.Add(status);Root.Add(controls);Root.Add(pages);parent.Add(Root);Root.style.display=DisplayStyle.None;
        }
        private void ThreadOnly(){if(Thread.CurrentThread.ManagedThreadId!=thread)throw new InvalidOperationException("VIEWER_DECISION_THREAD");}
        private void Clear()
        {
            offer=null;page=0;prompt.text="";status.text="";controls.Clear();pages.Clear();Root.style.display=DisplayStyle.None;
            // Observe a retired task without carrying its result or touching UI from its worker.
            if(pending!=null)pending.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);pending=null;
        }
        public void Tick()
        {
            ThreadOnly();if(disposed)return;var current=host.PresentedDecision;
            if(!ReferenceEquals(current,offer)){Clear();offer=current;if(offer!=null)Build();}
            if(offer==null)return;
            if(pending!=null && pending.IsCompleted){bool failed=pending.IsCanceled || pending.IsFaulted;_=pending.Exception;status.text=failed?"Command was not confirmed. Check the current decision.":"Command sent. Waiting for gateway state.";pending=null;}
            controls.SetEnabled(offer.CanSubmit && pending==null);
            if(!offer.CanSubmit && pending==null && string.IsNullOrEmpty(status.text))status.text="Waiting for gateway state.";
        }
        private void Send(ViewerDecisionOffer captured,Func<Task<TrackedCommand>> submit)
        {
            ThreadOnly();if(disposed || pending!=null || !ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured) || !captured.CanSubmit)return;
            pending=submit();status.text="Sending command…";controls.SetEnabled(false);
        }
        private static Button Button(string name,string text,Action click)
        {var button=new Button(click){name=name,text=text??"Unlabelled engine option"};foreach(var label in button.Query<TextElement>().ToList())label.enableRichText=false;button.enableRichText=false;button.style.fontSize=16;button.style.color=Color.white;button.style.backgroundColor=new Color(.18f,.24f,.30f);button.style.paddingTop=8;button.style.paddingBottom=8;button.style.marginBottom=4;return button;}
        private void Build()
        {
            var captured=offer;var frame=captured?.Frame;if(frame==null){Clear();return;}
            prompt.text=frame.Decision.Prompt??"Engine decision";Root.style.display=DisplayStyle.Flex;controls.Clear();pages.Clear();
            int total=frame.Actions.Count+frame.Decision.Options.Count;int start=page*PageSize,end=Math.Min(total,start+PageSize);
            for(int i=start;i<end;i++) {
                if(i<frame.Actions.Count){var action=frame.Actions[i];controls.Add(Button("decision-action-"+i,action.Label,()=>Send(captured,()=>host.PerformAsync(captured,action))));}
                else {var option=frame.Decision.Options[i-frame.Actions.Count];controls.Add(Button("decision-option-"+(i-frame.Actions.Count),option.Label,()=>Send(captured,()=>host.ChooseAsync(captured,option))));}
            }
            if(frame.Decision.CanFinish)controls.Add(Button("decision-finish","Finish selection",()=>Send(captured,()=>host.FinishSelectionAsync(captured))));
            if(frame.Decision.Cancellable)controls.Add(Button("decision-cancel","Cancel choice",()=>Send(captured,()=>host.CancelChoiceAsync(captured))));
            if(frame.Decision.Family=="number" || frame.Decision.Family=="amounts" || frame.Decision.Family=="mana")status.text="This decision needs input controls that are not available in this panel yet.";
            if(total>PageSize) {
                var previous=Button("decision-previous","Previous",()=>Move(captured,-1));previous.SetEnabled(page>0);pages.Add(previous);
                pages.Add(new Label("Page "+(page+1)+" of "+((total+PageSize-1)/PageSize)){enableRichText=false});
                var next=Button("decision-next","Next",()=>Move(captured,1));next.SetEnabled(end<total);pages.Add(next);
            }
            controls.SetEnabled(captured.CanSubmit && pending==null);
        }
        private void Move(ViewerDecisionOffer captured,int delta)
        {
            if(disposed || !ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured))return;
            var frame=captured.Frame;if(frame==null)return;int last=Math.Max(0,(frame.Actions.Count+frame.Decision.Options.Count-1)/PageSize);page=Math.Max(0,Math.Min(last,page+delta));Build();
        }
        public void Dispose(){ThreadOnly();if(disposed)return;disposed=true;Clear();Root.RemoveFromHierarchy();}
    }
}

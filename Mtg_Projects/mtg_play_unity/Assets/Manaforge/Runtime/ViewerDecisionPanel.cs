using System;
using System.Globalization;
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
        private readonly ViewerSessionHost host;private readonly ViewerManaSourceInput manaInput;
        public VisualElement Root {get;}=new VisualElement{name="viewer-decision-panel"};
        private readonly Label prompt=new Label{name="decision-prompt",enableRichText=false};
        private readonly Label status=new Label{name="decision-status",enableRichText=false};
        private readonly VisualElement controls=new VisualElement{name="decision-controls"};
        private readonly VisualElement pages=new VisualElement{name="decision-pages"};
        private string[] numericText;private int numericPage;private Button numericSubmit;
        private TrackedCommand submitted;
        private ViewerDecisionOffer offer;private int page;private bool disposed;private Task<TrackedCommand> pending;
        public ViewerDecisionPanel(VisualElement parent,ViewerSessionHost host)
        {
            if(parent==null || host==null)throw new ArgumentNullException();this.host=host;manaInput=new ViewerManaSourceInput(host,(captured,source)=>Send(captured,()=>host.SelectManaSourceAsync(captured,source)));
            Root.style.backgroundColor=new Color(.07f,.10f,.13f);Root.style.paddingLeft=16;Root.style.paddingRight=16;Root.style.paddingTop=12;Root.style.paddingBottom=12;
            prompt.style.fontSize=20;prompt.style.color=Color.white;prompt.style.marginBottom=8;prompt.style.whiteSpace=WhiteSpace.Normal;
            status.style.fontSize=14;status.style.color=new Color(.8f,.85f,.9f);status.style.marginBottom=8;status.style.whiteSpace=WhiteSpace.Normal;pages.style.flexDirection=FlexDirection.Row;
            Root.Add(prompt);Root.Add(status);Root.Add(controls);Root.Add(pages);parent.Add(Root);Root.style.display=DisplayStyle.None;
        }
        private void ThreadOnly(){if(Thread.CurrentThread.ManagedThreadId!=thread)throw new InvalidOperationException("VIEWER_DECISION_THREAD");}
        private void Clear()
        {
            manaInput.Refresh(null);offer=null;submitted=null;page=0;numericText=null;numericPage=0;numericSubmit=null;prompt.text="";status.text="";controls.Clear();pages.Clear();Root.style.display=DisplayStyle.None;
            // Observe a retired task without carrying its result or touching UI from its worker.
            if(pending!=null)pending.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);pending=null;
        }
        public void Tick()
        {
            ThreadOnly();if(disposed)return;var current=host.PresentedDecision;
            if(!ReferenceEquals(current,offer)){Clear();offer=current;if(offer!=null)Build();}
            manaInput.Refresh(offer);if(offer==null)return;
            if(pending!=null && pending.IsCompleted){
                if(pending.Status==TaskStatus.RanToCompletion)submitted=pending.Result;
                var error=pending.Exception?.GetBaseException() as WireEnvelope.EnvelopeException;
                status.text=error?.Code=="AMOUNT_OUT_OF_RANGE"?"Enter values within the displayed limits.":error?.Code=="SESSION_NUMERIC_UNAVAILABLE"?"Numeric limits are unavailable. Wait for gateway state.":pending.IsCanceled || pending.IsFaulted?"Command was not confirmed. Check the current decision.":"Command sent. Waiting for gateway state.";pending=null;
            }
            var feedback=host.CommandFeedback(offer,submitted);
            if(feedback!=null)status.text=FeedbackText(feedback.State);
            controls.SetEnabled(offer.CanSubmit && pending==null);manaInput.SetEnabled(offer.CanSubmit && pending==null);
            numericSubmit?.SetEnabled(TryNumbers(out _,false));
            if(!offer.CanSubmit && pending==null && string.IsNullOrEmpty(status.text))status.text="Waiting for gateway state.";
        }
        private void Send(ViewerDecisionOffer captured,Func<Task<TrackedCommand>> submit)
        {
            ThreadOnly();if(disposed || pending!=null || !ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured) || !captured.CanSubmit)return;
            submitted=null;pending=submit();status.text="Sending command...";controls.SetEnabled(false);manaInput.SetEnabled(false);
        }
        private static string FeedbackText(CommandState state)
        {
            switch(state) {
                case CommandState.Submitted:return "Gateway reports submitted. Waiting for confirmation.";
                case CommandState.Confirmed:return "Gateway confirmed command. Waiting for updated state.";
                case CommandState.Rejected:return "Gateway rejected command. Check the current decision.";
                case CommandState.Uncertain:return "Command outcome is uncertain. Do not retry.";
                default:return "Command sent. Waiting for gateway state.";
            }
        }
        private static Button Button(string name,string text,Action click)
        {var button=new Button(click){name=name,text=text??"Unlabelled engine option"};foreach(var label in button.Query<TextElement>().ToList())label.enableRichText=false;button.enableRichText=false;button.style.fontSize=16;button.style.color=Color.white;button.style.backgroundColor=new Color(.18f,.24f,.30f);button.style.paddingTop=8;button.style.paddingBottom=8;button.style.marginBottom=4;return button;}
        private void Build()
        {
            var captured=offer;var frame=captured?.Frame;if(frame==null){Clear();return;}
            prompt.text=frame.Decision.Prompt??"Engine decision";Root.style.display=DisplayStyle.Flex;controls.Clear();pages.Clear();numericSubmit=null;
            int total=frame.Actions.Count+frame.Decision.Options.Count;int start=page*PageSize,end=Math.Min(total,start+PageSize);
            for(int i=start;i<end;i++) {
                if(i<frame.Actions.Count){var action=frame.Actions[i];controls.Add(Button("decision-action-"+i,action.Label,()=>Send(captured,()=>host.PerformAsync(captured,action))));}
                else {var option=frame.Decision.Options[i-frame.Actions.Count];controls.Add(Button("decision-option-"+(i-frame.Actions.Count),option.Label,()=>Send(captured,()=>host.ChooseAsync(captured,option))));}
            }
            if(frame.Decision.CanFinish)controls.Add(Button("decision-finish","Finish selection",()=>Send(captured,()=>host.FinishSelectionAsync(captured))));
            if(frame.Decision.Cancellable)controls.Add(Button("decision-cancel","Cancel choice",()=>Send(captured,()=>host.CancelChoiceAsync(captured))));
            if(frame.Decision.Family=="number" || frame.Decision.Family=="amounts")BuildNumbers(captured,frame.Decision);
            if(frame.Decision.Family=="mana")status.text=frame.ManaSourceReferences.Count==0?"No cards are available for mana-source selection.":"Choose a card to use as a mana source. The game validates your selection.";
            if(total>PageSize) {
                var previous=Button("decision-previous","Previous",()=>Move(captured,-1));previous.SetEnabled(page>0);pages.Add(previous);
                pages.Add(new Label("Page "+(page+1)+" of "+((total+PageSize-1)/PageSize)){enableRichText=false});
                var next=Button("decision-next","Next",()=>Move(captured,1));next.SetEnabled(end<total);pages.Add(next);
            }
            controls.SetEnabled(captured.CanSubmit && pending==null);
        }
        private static string Integer(long value)=>value.ToString(CultureInfo.InvariantCulture);
        private static Label NumericLabel(string text)
        {var label=new Label(text){enableRichText=false};label.style.color=Color.white;label.style.whiteSpace=WhiteSpace.Normal;return label;}
        private void BuildNumbers(ViewerDecisionOffer captured,ProjectedDecision decision)
        {
            bool number=decision.Family=="number";
            if(!decision.Minimum.HasValue || !decision.Maximum.HasValue || decision.Minimum>decision.Maximum || (!number && decision.Amounts.Count>WireMessages.MaxAmountValues)) {
                controls.Add(NumericLabel("Supported numeric limits are unavailable. Wait for gateway state."));return;
            }
            foreach(var constraint in decision.Amounts)if(!number && constraint.Minimum>constraint.Maximum){controls.Add(NumericLabel("Supported numeric limits are unavailable. Wait for gateway state."));return;}
            int count=number?1:decision.Amounts.Count;if(numericText==null)numericText=new string[count];
            controls.Add(NumericLabel((number?"Allowed value: ":"Allowed total: ")+Integer(decision.Minimum.Value)+" to "+Integer(decision.Maximum.Value)));
            controls.Add(NumericLabel("Enter a whole number in each field. Values are not selected automatically."));
            int start=numericPage*PageSize,end=Math.Min(count,start+PageSize);
            for(int i=start;i<end;i++) {
                int index=i;var constraint=number?null:decision.Amounts[i];
                string label=number?"Number":(constraint.Label??"Amount")+" ("+Integer(constraint.Minimum)+" to "+Integer(constraint.Maximum)+")";
                var field=new TextField(label){name="decision-number-"+i,value=numericText[i]??""};field.labelElement.enableRichText=false;field.labelElement.style.color=Color.white;field.style.fontSize=16;
                foreach(var text in field.Query<TextElement>().ToList())text.enableRichText=false;
                field.style.marginTop=6;field.style.marginBottom=6;field.RegisterValueChangedCallback(change=>{
                    if(disposed || !ReferenceEquals(offer,captured) || numericText==null)return;
                    numericText[index]=change.newValue;numericSubmit?.SetEnabled(TryNumbers(out _,false));
                });controls.Add(field);
            }
            if(count>PageSize) {
                var navigation=new VisualElement();navigation.style.flexDirection=FlexDirection.Row;
                var previous=Button("decision-numeric-previous","Previous amounts",()=>MoveNumbers(captured,-1));previous.SetEnabled(numericPage>0);navigation.Add(previous);
                navigation.Add(NumericLabel("Page "+(numericPage+1)+" of "+((count+PageSize-1)/PageSize)));
                var next=Button("decision-numeric-next","Next amounts",()=>MoveNumbers(captured,1));next.SetEnabled(end<count);navigation.Add(next);controls.Add(navigation);
            }
            numericSubmit=Button("decision-number-submit",number?"Submit number":"Submit amounts",()=>{
                if(TryNumbers(out var values))Send(captured,()=>number?host.ChooseNumberAsync(captured,values[0]):host.ChooseAmountsAsync(captured,values));
            });numericSubmit.SetEnabled(TryNumbers(out _,false));controls.Add(numericSubmit);
        }
        private bool TryNumbers(out long[] values,bool collect=true)
        {
            values=null;if(numericText==null)return false;if(collect)values=new long[numericText.Length];
            for(int i=0;i<numericText.Length;i++) {
                if(string.IsNullOrEmpty(numericText[i]) || numericText[i].Length>20 || !long.TryParse(numericText[i],NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out long parsed))return false;
                if(collect)values[i]=parsed;
            }
            return true;
        }
        private void MoveNumbers(ViewerDecisionOffer captured,int delta)
        {
            if(disposed || !ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured) || numericText==null)return;
            int last=Math.Max(0,(numericText.Length-1)/PageSize);numericPage=Math.Max(0,Math.Min(last,numericPage+delta));Build();
        }
        private void Move(ViewerDecisionOffer captured,int delta)
        {
            if(disposed || !ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured))return;
            var frame=captured.Frame;if(frame==null)return;int last=Math.Max(0,(frame.Actions.Count+frame.Decision.Options.Count-1)/PageSize);page=Math.Max(0,Math.Min(last,page+delta));Build();
        }
        public void Dispose(){ThreadOnly();if(disposed)return;disposed=true;manaInput.Dispose();Clear();Root.RemoveFromHierarchy();}
    }
}

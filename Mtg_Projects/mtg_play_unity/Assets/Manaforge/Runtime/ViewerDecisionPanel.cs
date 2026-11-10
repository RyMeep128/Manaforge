using System;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using UnityEngine.UIElements;
using UnityEngine;

namespace Manaforge.Play
{
    // Main-thread presentation and priority scheduling. All commands use the current authenticated offer.
    public sealed class ViewerDecisionPanel : IDisposable
    {
        public const int PageSize=16;
        private readonly int thread=Thread.CurrentThread.ManagedThreadId;
        private readonly ViewerSessionHost host;private readonly ViewerManaSourceInput manaInput;
        public VisualElement Root {get;}=new VisualElement{name="viewer-decision-panel"};
        private readonly Label prompt=new Label{name="decision-prompt",enableRichText=false};
        private readonly Label manaPool=new Label{name="decision-mana-pool",enableRichText=false};
        private readonly Label status=new Label{name="decision-status",enableRichText=false};
        private readonly VisualElement controls=new VisualElement{name="decision-controls"};
        private readonly VisualElement pages=new VisualElement{name="decision-pages"};
        private readonly VisualElement decisionBody=new VisualElement{name="decision-body"};
        private readonly YieldStatusView yieldStatus;
        private bool built,soleAbilityAttempted;private string selectedGroup;
        private readonly System.Collections.Generic.Dictionary<string,int> groupPages=new System.Collections.Generic.Dictionary<string,int>();
        private readonly System.Collections.Generic.List<CardView> groupPreviews=new System.Collections.Generic.List<CardView>();
        private void ClearGroupPreviews(){foreach(var view in groupPreviews)view.Dispose();groupPreviews.Clear();}
        public YieldPresentation Presentation {get;private set;}
        public bool SuppressSpatialInput=>Presentation?.Compact==true;
        private string[] numericText;private int numericPage;private Button numericSubmit;
        private TrackedCommand submitted;
        private float autoAfter=-1;
        private bool priorityEnabled;
        private readonly System.Collections.Generic.List<Task<TrackedCommand>> priorityTasks=new System.Collections.Generic.List<Task<TrackedCommand>>();
        private readonly System.Collections.Generic.List<TrackedCommand> priorityReceipts=new System.Collections.Generic.List<TrackedCommand>();
        public void EnablePriority(){ThreadOnly();priorityEnabled=true;}
        public UnityPriorityPolicy Priority {get;}=new UnityPriorityPolicy();
        public bool PriorityControlsOpen {get;set;}
        // Decorative presentation may briefly hold automation, never manual controls.
        public Func<bool> PresentationHold {get;set;}
        public ProjectedDecisionFrame PriorityFrame=>offer?.Frame;
        public ViewerDecisionOffer CurrentOffer=>offer;
        public void PrioritySettingsChanged(){ThreadOnly();autoAfter=-1;}
        private bool spatialPresentation;private Foldout cardChoices;
        private Func<string,CardView> choicePreview;
        public bool IsLibraryOrdering {get;private set;}
        public void SetChoicePreview(Func<string,CardView> preview){ThreadOnly();choicePreview=preview;}
        public static bool LibraryOrdering(string prompt)
            =>!string.IsNullOrEmpty(prompt) && prompt.IndexOf("order",StringComparison.OrdinalIgnoreCase)>=0
                && prompt.IndexOf("library",StringComparison.OrdinalIgnoreCase)>=0;
        private ViewerDecisionOffer offer;private int page;private bool disposed;private Task<TrackedCommand> pending;
        public ViewerDecisionPanel(VisualElement parent,ViewerSessionHost host)
        {
            if(parent==null || host==null)throw new ArgumentNullException();this.host=host;manaInput=new ViewerManaSourceInput(host,(captured,source)=>Send(captured,()=>host.SelectManaSourceAsync(captured,source)));
            Root.style.backgroundColor=new Color(.07f,.10f,.13f);Root.style.paddingLeft=16;Root.style.paddingRight=16;Root.style.paddingTop=12;Root.style.paddingBottom=12;
            prompt.style.fontSize=20;prompt.style.color=Color.white;prompt.style.marginBottom=8;prompt.style.whiteSpace=WhiteSpace.Normal;
            status.style.fontSize=14;status.style.color=new Color(.8f,.85f,.9f);status.style.marginBottom=8;status.style.whiteSpace=WhiteSpace.Normal;pages.style.flexDirection=FlexDirection.Row;
            decisionBody.Add(prompt);decisionBody.Add(manaPool);decisionBody.Add(status);decisionBody.Add(controls);decisionBody.Add(pages);Root.Add(decisionBody);yieldStatus=new YieldStatusView(Root,()=>{Priority.CancelYield();PrioritySettingsChanged();});parent.Add(Root);Root.style.display=DisplayStyle.None;
        }
        private void ThreadOnly(){if(Thread.CurrentThread.ManagedThreadId!=thread)throw new InvalidOperationException("VIEWER_DECISION_THREAD");}
        private void Clear()
        {
            Root.RemoveFromClassList("session-request");Root.RemoveFromClassList("library-ordering");Root.RemoveFromClassList("command-pending");Root.RemoveFromClassList("command-uncertain");Root.RemoveFromClassList("command-confirmed");
            ClearGroupPreviews();groupPages.Clear();selectedGroup=null;built=false;soleAbilityAttempted=false;autoAfter=-1;IsLibraryOrdering=false;manaInput.Refresh(null);offer=null;submitted=null;page=0;numericText=null;numericPage=0;numericSubmit=null;prompt.text="";manaPool.text="";status.text="";controls.Clear();pages.Clear();cardChoices=null;Root.style.display=Presentation?.Compact==true?DisplayStyle.Flex:DisplayStyle.None;
            // Observe a retired task without carrying its result or touching UI from its worker.
            if(pending!=null)pending.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);pending=null;
        }
        private void MonitorPriorityCommands()
        {
            for(int i=priorityTasks.Count-1;i>=0;i--){
                var task=priorityTasks[i];if(!task.IsCompleted)continue;
                if(task.Status==TaskStatus.RanToCompletion && task.Result!=null)priorityReceipts.Add(task.Result);
                else{_=task.Exception;Priority.Failed();}
                priorityTasks.RemoveAt(i);
            }
            for(int i=priorityReceipts.Count-1;i>=0;i--){
                var receipt=host.CommandOutcome(priorityReceipts[i]);
                if(receipt==null || receipt.State==CommandState.AwaitingAck || receipt.State==CommandState.Submitted)continue;
                if(receipt.State==CommandState.Rejected || receipt.State==CommandState.Uncertain)Priority.Failed();
                priorityReceipts.RemoveAt(i);
            }
        }
        public void Tick()
        {
            ThreadOnly();if(disposed)return;if(priorityEnabled)MonitorPriorityCommands();var current=host.PresentedDecision;
            if(!ReferenceEquals(current,offer)){
                Clear();offer=current;
                if(offer?.Frame?.Decision!=null){var decision=offer.Frame.Decision;Debug.Log("Manaforge decision: family="+decision.Family+" priority="+decision.IsPriority+" options="+decision.Options.Count+" actions="+offer.Frame.Actions.Count+" finish="+decision.CanFinish+" stack="+offer.Frame.StackIds.Count);}
            }
            if(host.Completion.IsCompleted){Priority.Suspend();autoAfter=-1;}
            Priority.Observe(offer?.Frame);
            Presentation=YieldPresentation.Resolve(Priority.Current,offer?.Frame,PriorityControlsOpen,host.Completion.IsCompleted);
            yieldStatus.Bind(Presentation);
            if(!Presentation.Compact && offer!=null && !built)Build();
            decisionBody.style.display=Presentation.Compact?DisplayStyle.None:DisplayStyle.Flex;
            Root.style.display=Presentation.Compact || offer!=null || Presentation.Mode==YieldPresentationMode.Failed?DisplayStyle.Flex:DisplayStyle.None;
            if(Presentation.Mode==YieldPresentationMode.Failed && offer==null){prompt.text=Presentation.Text;}
            manaInput.Refresh(offer);if(offer==null)return;
            if(pending!=null && pending.IsCompleted){
                if(pending.Status==TaskStatus.RanToCompletion)submitted=pending.Result;
                else Priority.Failed();
                var error=pending.Exception?.GetBaseException() as WireEnvelope.EnvelopeException;
                status.text=error?.Code=="AMOUNT_OUT_OF_RANGE"?"Enter values within the displayed limits.":error?.Code=="SESSION_NUMERIC_UNAVAILABLE"?"Numeric limits are unavailable. Wait for gateway state.":pending.IsCanceled || pending.IsFaulted?"Command was not confirmed. Check the current decision.":"Command sent. Waiting for gateway state.";pending=null;
            }
            var feedback=host.CommandFeedback(offer,submitted);
            if(feedback!=null){
                status.text=FeedbackText(feedback.State);
                if(feedback.State==CommandState.Rejected || feedback.State==CommandState.Uncertain)Priority.Failed();
            }
            Root.EnableInClassList("command-pending",pending!=null || feedback?.State==CommandState.Submitted);
            Root.EnableInClassList("command-uncertain",feedback?.State==CommandState.Uncertain);
            Root.EnableInClassList("command-confirmed",feedback?.State==CommandState.Confirmed);
            controls.SetEnabled(offer.CanSubmit && pending==null);manaInput.SetEnabled(offer.CanSubmit && pending==null);
            numericSubmit?.SetEnabled(TryNumbers(out _,false));
            controls.Q<Button>("decision-pass-turn")?.SetEnabled(offer.CanSubmit && pending==null && !Priority.Current.Paused);
            if(!offer.CanSubmit && pending==null && string.IsNullOrEmpty(status.text))status.text="Waiting for gateway state.";
            if(!soleAbilityAttempted && pending==null && offer.CanSubmit && offer.Frame.Decision?.AbilitySelection==true
                && offer.Frame.Decision.Family=="selection" && !offer.Frame.Decision.IsPriority && offer.Frame.Decision.RequestId==null
                && !offer.Frame.Decision.CanFinish && offer.Frame.Decision.Options.Count==1 && offer.Frame.Actions.Count==0){
                soleAbilityAttempted=true;var captured=offer;var only=captured.Frame.Decision.Options[0];Send(captured,()=>host.ChooseAsync(captured,only));return;
            }
            var automatic=priorityEnabled?Priority.Evaluate(offer.Frame):null;
            if(automatic==null || pending!=null || !offer.CanSubmit || PriorityControlsOpen || PresentationHold?.Invoke()==true){autoAfter=-1;return;}
            if(autoAfter<0){autoAfter=Time.unscaledTime+.35f;return;}
            if(Time.unscaledTime>=autoAfter){
                var captured=offer;autoAfter=-1;
                if(ReferenceEquals(host.PresentedDecision,captured) && Priority.Claim(captured.Frame))
                    Send(captured,()=>host.PerformAsync(captured,automatic),true);
            }
        }
        private bool Send(ViewerDecisionOffer captured,Func<Task<TrackedCommand>> submit,bool automatic=false)
        {
            ThreadOnly();if(disposed || pending!=null || !ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured) || !captured.CanSubmit)return false;
            if(!automatic && SuppressSpatialInput)return false;
            autoAfter=-1;if(!automatic && captured.Frame?.Decision?.IsPriority==true && Presentation?.Mode!=YieldPresentationMode.Stopped)Priority.CancelYield();
            submitted=null;pending=submit();if(priorityEnabled)priorityTasks.Add(pending);status.text="Sending command...";controls.SetEnabled(false);manaInput.SetEnabled(false);return true;
        }
        // Spatial input uses the same current offer, pending task and command feedback as buttons.
        public int ObjectChoiceCount(ViewerDecisionOffer captured,string objectId)
        {
            ThreadOnly();var frame=captured?.Frame;if(SuppressSpatialInput || disposed || objectId==null || frame==null || !ReferenceEquals(captured,offer) || !ReferenceEquals(host.PresentedDecision,captured))return 0;
            return System.Linq.Enumerable.Count(frame.Actions,a=>a.ObjectId==objectId)+System.Linq.Enumerable.Count(frame.Decision.Options,o=>o.ObjectId==objectId);
        }
        public bool TryActivateObject(ViewerDecisionOffer captured,string objectId)
        {
            if(ObjectChoiceCount(captured,objectId)!=1)return false;var frame=captured.Frame;
            foreach(var action in frame.Actions)if(action.ObjectId==objectId)return Send(captured,()=>host.PerformAsync(captured,action));
            foreach(var option in frame.Decision.Options)if(option.ObjectId==objectId)return Send(captured,()=>host.ChooseAsync(captured,option));
            return false;
        }
        public bool TryCancelCurrentChoice(){var captured=offer;return captured?.Frame?.Decision?.Cancellable==true && Send(captured,()=>host.CancelChoiceAsync(captured));}
        public bool TryActivatePlayer(ViewerDecisionOffer captured,string playerId)
        {
            ThreadOnly();var frame=captured?.Frame;if(SuppressSpatialInput || disposed || frame==null || playerId==null)return false;
            var matches=System.Linq.Enumerable.Where(frame.Decision.Options,o=>o.PlayerId==playerId).GetEnumerator();
            using(matches){if(!matches.MoveNext())return false;var option=matches.Current;if(matches.MoveNext())return false;return Send(captured,()=>host.ChooseAsync(captured,option));}
        }
        public VisualElement ObjectChoices(ViewerDecisionOffer captured,string objectId)
        {
            ThreadOnly();var result=new VisualElement();if(ObjectChoiceCount(captured,objectId)==0)return result;var frame=captured.Frame;
            foreach(var action in frame.Actions)if(action.ObjectId==objectId)result.Add(Button("board-action",action.Label,()=>Send(captured,()=>host.PerformAsync(captured,action))));
            foreach(var option in frame.Decision.Options)if(option.ObjectId==objectId)result.Add(Button("board-option",option.Label,()=>Send(captured,()=>host.ChooseAsync(captured,option))));
            return result;
        }
        public void SetSpatialPresentation(bool value)
        {
            ThreadOnly();if(spatialPresentation==value)return;spatialPresentation=value;if(offer!=null)Build();
        }
        private void AddTurnPass(ViewerDecisionOffer captured,ProjectedAction action)
        {
            var frame=captured.Frame;
            if(!priorityEnabled || action.Kind!="pass" || action.ObjectId!=null || frame.Decision?.IsPriority!=true
                || frame.Decision.PlayerId!=frame.Context.ViewerId || frame.PriorityPlayerId!=frame.Context.ViewerId
                || !frame.Turn.HasValue || frame.ActivePlayerId==null || frame.Status!="active" || frame.Result!=null)return;
            bool ownTurn=frame.ActivePlayerId==frame.Context.ViewerId;
            var button=Button("decision-pass-turn",ownTurn?"End turn":"Pass to my turn",()=>{
                if(!ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured) || !captured.CanSubmit || pending!=null || Priority.Current.Paused)return;
                Priority.BeginYield(ownTurn?"end-turn":"turn",frame);PrioritySettingsChanged();
            });
            button.SetEnabled(captured.CanSubmit && !Priority.Current.Paused);controls.Add(button);
        }
        private void AddChoice(Button button,bool boundToBoard)
        {
            if(IsLibraryOrdering || !spatialPresentation || !boundToBoard){controls.Add(button);return;}
            if(cardChoices==null){cardChoices=new Foldout{text="Card and player choices",value=false,name="board-choice-alternatives"};cardChoices.style.width=Length.Percent(100);controls.Add(cardChoices);}
            cardChoices.Add(button);
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
            var captured=offer;var frame=captured?.Frame;if(frame==null){Clear();return;}built=true;ClearGroupPreviews();
            var floating=frame.ViewerMana==null?"":string.Join(", ",System.Linq.Enumerable.Select(System.Linq.Enumerable.Where(frame.ViewerMana,pair=>pair.Value>0),pair=>pair.Key+" "+pair.Value));manaPool.text=string.IsNullOrEmpty(floating)?"":"Floating mana: "+floating;manaPool.style.display=string.IsNullOrEmpty(floating)?DisplayStyle.None:DisplayStyle.Flex;prompt.text=OpeningHandFan.PlainPrompt(frame.Decision.Prompt??"Choose an action");Root.style.display=DisplayStyle.Flex;controls.Clear();pages.Clear();numericSubmit=null;cardChoices=null;
            if(!string.IsNullOrEmpty(frame.PaymentReason)){status.text="Manual payment required: "+frame.PaymentReason.Replace('_',' ').ToLowerInvariant()+".";UnityEngine.Debug.Log("Manaforge payment fallback: "+frame.PaymentReason);}
            Root.EnableInClassList("session-request",frame.Decision.RequestId!=null);
            IsLibraryOrdering=LibraryOrdering(prompt.text);
            Root.EnableInClassList("library-ordering",IsLibraryOrdering);
            if(frame.Decision.Groups.Count>0){BuildGroups(captured);controls.SetEnabled(captured.CanSubmit && pending==null);return;}
            int total=frame.Actions.Count+frame.Decision.Options.Count;int start=page*PageSize,end=Math.Min(total,start+PageSize);
            for(int i=start;i<end;i++) {
                if(i<frame.Actions.Count){var action=frame.Actions[i];AddChoice(Button("decision-action-"+i,action.Label,()=>Send(captured,()=>host.PerformAsync(captured,action))),action.ObjectId!=null);AddTurnPass(captured,action);}
                else {
                    var option=frame.Decision.Options[i-frame.Actions.Count];
                    var button=Button("decision-option-"+(i-frame.Actions.Count),(option.Selected?"Selected: ":"")+OpeningHandFan.PlainPrompt(option.Label??"Choose card"),()=>Send(captured,()=>host.ChooseAsync(captured,option)));
                    if(IsLibraryOrdering){
                        var tile=new VisualElement{name="library-choice"};
                        var preview=option.ObjectId==null?null:choicePreview?.Invoke(option.ObjectId);
                        if(preview!=null){preview.pickingMode=PickingMode.Ignore;tile.Add(preview);}
                        tile.Add(button);controls.Add(tile);
                    }else AddChoice(button,option.ObjectId!=null || option.PlayerId!=null);
                }
            }
            // In the spatial view, pass/finish/cancel actions remain available even when
            // card alternatives occupy a different page. Keep the engine's exact index/token.
            if(spatialPresentation)for(int i=0;i<frame.Actions.Count;i++)if((i<start || i>=end) && frame.Actions[i].Kind=="pass"){
                int index=i;var action=frame.Actions[i];controls.Add(Button("decision-action-"+index,action.Label,()=>Send(captured,()=>host.PerformAsync(captured,action))));AddTurnPass(captured,action);
            }
            if(frame.Decision.CanFinish)controls.Add(Button("decision-finish","Finish selection",()=>Send(captured,()=>host.FinishSelectionAsync(captured))));
            if(frame.Decision.Cancellable)controls.Add(Button("decision-cancel","Cancel choice",()=>Send(captured,()=>host.CancelChoiceAsync(captured))));
            if(frame.Decision.Family=="number" || frame.Decision.Family=="amounts")BuildNumbers(captured,frame.Decision);
            if(total>PageSize) {
                var previous=Button("decision-previous","Previous",()=>Move(captured,-1));previous.SetEnabled(page>0);pages.Add(previous);
                pages.Add(new Label("Page "+(page+1)+" of "+((total+PageSize-1)/PageSize)){enableRichText=false});
                var next=Button("decision-next","Next",()=>Move(captured,1));next.SetEnabled(end<total);pages.Add(next);
            }
            controls.SetEnabled(captured.CanSubmit && pending==null);
        }
        private void BuildGroups(ViewerDecisionOffer captured)
        {
            ProjectedChoiceOption selected=null;
            var groupScroll=new ScrollView(ScrollViewMode.Vertical){name="decision-groups"};groupScroll.style.maxHeight=420;controls.Add(groupScroll);
            foreach(var group in captured.Frame.Decision.Groups){
                var tile=new VisualElement{name="choice-group"};tile.AddToClassList("mf-menu");tile.style.marginBottom=12;
                tile.Add(NumericLabel(group.Label+" · "+group.Cards.Count+" cards"));
                var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.maxHeight=390;tile.Add(scroll);
                if(group.Cards.Count==0)scroll.Add(NumericLabel("Empty pile"));
                int page=groupPages.TryGetValue(group.GroupId,out var requested)?Mathf.Clamp(requested,0,Math.Max(0,(group.Cards.Count-1)/PageSize)):0;
                for(int index=page*PageSize;index<Math.Min(group.Cards.Count,(page+1)*PageSize);index++){var card=group.Cards[index];
                    var view=new CardView();view.SetPresentation(CardPresentationMode.Full,190);
                    if(card.Hidden)view.Conceal();else{view.BindUnavailable();view.UpdateValues(new CardDisplayValues(card.Name,null,card.TypeLine,card.Rules,null,"Pile card"));}
                    scroll.Add(view);groupPreviews.Add(view);
                }
                if(group.Cards.Count>PageSize){
                    var previous=Button("decision-group-previous-"+group.GroupId,"Previous cards",()=>{groupPages[group.GroupId]=page-1;Build();});previous.SetEnabled(page>0);tile.Add(previous);
                    tile.Add(NumericLabel("Page "+(page+1)+" / "+((group.Cards.Count+PageSize-1)/PageSize)));
                    var next=Button("decision-group-next-"+group.GroupId,"Next cards",()=>{groupPages[group.GroupId]=page+1;Build();});next.SetEnabled((page+1)*PageSize<group.Cards.Count);tile.Add(next);
                }
                ProjectedChoiceOption option=null;foreach(var candidate in captured.Frame.Decision.Options)if(candidate.OptionId==group.OptionId)option=candidate;
                if(option==null)continue;
                tile.Add(Button("decision-group-"+group.GroupId,(selectedGroup==group.OptionId?"Selected: ":"")+option.Label,()=>{selectedGroup=group.OptionId;Build();}));groupScroll.Add(tile);
                if(selectedGroup==group.OptionId)selected=option;
            }
            var confirmation=Button("decision-group-confirm",selected==null?"Confirm pile":"Confirm: "+selected.Label,()=>{if(selected!=null)Send(captured,()=>host.ChooseAsync(captured,selected));});
            confirmation.SetEnabled(selected!=null);controls.Add(confirmation);
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
            ClearGroupPreviews();
            var frame=captured.Frame;if(frame==null)return;int last=Math.Max(0,(frame.Actions.Count+frame.Decision.Options.Count-1)/PageSize);page=Math.Max(0,Math.Min(last,page+delta));Build();
        }
        public void Dispose(){ThreadOnly();if(disposed)return;disposed=true;Priority.Suspend();PresentationHold=null;priorityTasks.Clear();priorityReceipts.Clear();manaInput.Dispose();yieldStatus.Dispose();Clear();prompt.RemoveFromHierarchy();Root.RemoveFromHierarchy();}
    }
}

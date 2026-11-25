using System;
using System.Globalization;
using System.Linq;
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
        private GameplayPriorityActions priorityActions;
        internal bool UnifiedPriorityActions=>priorityActions!=null;
        internal bool PriorityCommandPending=>pending!=null;
        internal bool AutomaticPriorityPending {get;private set;}
        internal bool PrioritySessionActive=>!disposed && host.Authenticated && !host.Completion.IsCompleted;
        internal bool CanPassPriority {get{var frame=offer?.Frame;return PrioritySessionActive && !LayoutEditing && pending==null && frame?.Decision?.IsPriority==true && ReferenceEquals(offer,host.PresentedDecision) && offer.CanSubmit && frame.Decision.Family=="selection" && frame.Decision.Groups.Count==0 && frame.Decision.PlayerId==frame.Context.ViewerId && frame.PriorityPlayerId==frame.Context.ViewerId && frame.Status=="active" && frame.Result==null && frame.Actions.Count(action=>action.Kind=="pass" && action.ObjectId==null)==1;}}
        private float continuityUntil;private YieldPresentation displayPresentation;
        private bool built,soleAbilityAttempted;private string selectedGroup;
        private readonly System.Collections.Generic.List<CardView> groupPreviews=new System.Collections.Generic.List<CardView>();
        private void ClearGroupPreviews(){foreach(var view in groupPreviews)view.Dispose();groupPreviews.Clear();InvalidateAmountArtwork();amountArtwork.Clear();}
        private readonly System.Collections.Generic.List<(string objectId,VisualElement slot)> amountArtwork=new System.Collections.Generic.List<(string,VisualElement)>();
        private readonly System.Collections.Generic.List<CardView> amountPreviews=new System.Collections.Generic.List<CardView>();
        private Func<int> choiceArtworkState;private int amountArtworkState=-1;
        internal void SetChoiceArtworkState(Func<int> state){choiceArtworkState=state;}
        internal void InvalidateAmountArtwork(){foreach(var preview in amountPreviews)preview.Dispose();amountPreviews.Clear();amountArtworkState=-1;}
        private void RefreshAmountArtwork(){
            var frame=offer?.Frame;
            if(amountArtwork.Count==0 || frame==null || !ReferenceEquals(offer,host.PresentedDecision) || !host.HasPresentedRevision(frame.Context.Revision))return;
            int state=choiceArtworkState?.Invoke()??0;if(state==amountArtworkState)return;
            InvalidateAmountArtwork();amountArtworkState=state;
            foreach(var item in amountArtwork){
                item.slot.Clear();var preview=choicePreview?.Invoke(item.objectId);
                if(preview==null){item.slot.Add(NumericLabel("Card preview unavailable"));continue;}
                preview.name="damage-card-"+item.objectId;preview.pickingMode=PickingMode.Ignore;preview.style.alignSelf=Align.Center;
                preview.SetPresentation(CardPresentationMode.Full,150);item.slot.Add(preview);amountPreviews.Add(preview);
            }
        }
        public YieldPresentation Presentation {get;private set;}
        public bool LayoutEditing {get;private set;}
        public void SetLayoutEditing(bool value){ThreadOnly();if(LayoutEditing==value)return;LayoutEditing=value;autoAfter=-1;}
        public bool SuppressSpatialInput=>LayoutEditing || Presentation?.Compact==true;
        private string[] numericText;private Button numericSubmit;
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
        public void PrioritySettingsChanged(){ThreadOnly();autoAfter=-1;if(priorityActions!=null){Presentation=YieldPresentation.Resolve(Priority.Current,offer?.Frame,PriorityControlsOpen,host.Completion.IsCompleted);priorityActions.Refresh();}}
        private bool spatialPresentation;private Foldout cardChoices;
        private Func<string,CardView> choicePreview;
        public bool IsLibraryOrdering {get;private set;}
        public void SetChoicePreview(Func<string,CardView> preview){ThreadOnly();choicePreview=preview;}
        public static bool LibraryOrdering(string prompt)
            =>!string.IsNullOrEmpty(prompt) && prompt.IndexOf("order",StringComparison.OrdinalIgnoreCase)>=0
                && prompt.IndexOf("library",StringComparison.OrdinalIgnoreCase)>=0;
        private ViewerDecisionOffer offer;private bool disposed;private Task<TrackedCommand> pending;
        public ViewerDecisionPanel(VisualElement parent,ViewerSessionHost host)
        {
            if(parent==null || host==null)throw new ArgumentNullException();this.host=host;manaInput=new ViewerManaSourceInput(host,(captured,source)=>Send(captured,()=>host.SelectManaSourceAsync(captured,source)));
            Root.style.backgroundColor=new Color(.07f,.10f,.13f);Root.style.paddingLeft=16;Root.style.paddingRight=16;Root.style.paddingTop=12;Root.style.paddingBottom=12;
            prompt.style.fontSize=20;prompt.style.color=Color.white;prompt.style.marginBottom=8;prompt.style.whiteSpace=WhiteSpace.Normal;
            status.style.minHeight=18;status.style.fontSize=14;status.style.color=new Color(.8f,.85f,.9f);status.style.marginBottom=8;status.style.whiteSpace=WhiteSpace.Normal;pages.style.flexDirection=FlexDirection.Row;
            decisionBody.Add(prompt);decisionBody.Add(manaPool);decisionBody.Add(status);decisionBody.Add(controls);decisionBody.Add(pages);Root.Add(decisionBody);yieldStatus=new YieldStatusView(Root,()=>{Priority.CancelPassing(PriorityFrame);PrioritySettingsChanged();});parent.Add(Root);Root.style.display=DisplayStyle.None;
        }
        internal void UseUnifiedPriorityActions(Action openSettings)
        {
            ThreadOnly();if(priorityActions!=null)return;priorityActions=new GameplayPriorityActions(this,openSettings);Root.Add(priorityActions.Root);EnablePriority();
        }
        internal bool TryPassPriority()
        {
            ThreadOnly();if(!CanPassPriority || Priority.Current.Paused || YieldPresentation.Resolve(Priority.Current,offer?.Frame,PriorityControlsOpen,host.Completion.IsCompleted).Compact)return false;
            var captured=offer;var frame=captured?.Frame;if(frame==null)return false;var pass=frame.Actions.Single(action=>action.Kind=="pass" && action.ObjectId==null);
            bool sent=Send(captured,()=>host.PerformAsync(captured,pass));priorityActions?.Refresh();return sent;
        }
        internal bool TryBeginPriorityYield(string mode)
        {
            ThreadOnly();if(!CanPassPriority || Priority.Current.Paused || PriorityControlsOpen)return false;
            var frame=offer?.Frame;if(frame==null)return false;Priority.BeginYield(mode,frame);PrioritySettingsChanged();return Priority.Current.Yield==mode;
        }
        internal void CancelPriorityYield(){ThreadOnly();if(!PrioritySessionActive || LayoutEditing)return;Priority.CancelPassing(PriorityFrame);PrioritySettingsChanged();}
        internal void ResumePriority(){ThreadOnly();if(!PrioritySessionActive || LayoutEditing)return;Priority.Resume();PrioritySettingsChanged();}
        internal System.Collections.Generic.IEnumerable<VisualElement> PriorityAlternatives()
        {
            var captured=offer;var frame=captured?.Frame;if(frame?.Decision?.IsPriority!=true)yield break;
            for(int index=0;index<frame.Actions.Count;index++){var action=frame.Actions[index];if(action.Kind!="pass" || action.ObjectId!=null)yield return Button("decision-action-"+index,action.Label,()=>Send(captured,()=>host.PerformAsync(captured,action)));}
            for(int index=0;index<frame.Decision.Options.Count;index++){var option=frame.Decision.Options[index];yield return Button("decision-option-"+index,option.Label,()=>Send(captured,()=>host.ChooseAsync(captured,option)));}
        }
        private void ThreadOnly(){if(Thread.CurrentThread.ManagedThreadId!=thread)throw new InvalidOperationException("VIEWER_DECISION_THREAD");}
        private void Clear(bool preserveStatus=false)
        {
            if(preserveStatus){continuityUntil=Time.unscaledTime+.12f;float height=Root.resolvedStyle.height;if(!float.IsNaN(height) && height>0)Root.style.minHeight=height;}else{continuityUntil=0;Root.style.minHeight=StyleKeyword.Null;}
            Root.RemoveFromClassList("session-request");Root.RemoveFromClassList("library-ordering");Root.RemoveFromClassList("searchable-menu");Root.RemoveFromClassList("command-pending");Root.RemoveFromClassList("command-uncertain");Root.RemoveFromClassList("command-confirmed");
            ClearGroupPreviews();selectedGroup=null;built=false;soleAbilityAttempted=false;autoAfter=-1;IsLibraryOrdering=false;manaInput.Refresh(null);offer=null;submitted=null;numericText=null;numericSubmit=null;if(!preserveStatus){StableStatusText.Set(prompt,"",true);manaPool.text="";status.text="";}controls.Clear();pages.Clear();cardChoices=null;if(!preserveStatus)Root.style.display=DisplayStyle.None;
            // Observe a retired task without carrying its result or touching UI from its worker.
            if(pending!=null)pending.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);pending=null;
        }
        private void MonitorPriorityCommands()
        {
            for(int i=priorityTasks.Count-1;i>=0;i--){
                var task=priorityTasks[i];if(!task.IsCompleted)continue;
                if(task.Status==TaskStatus.RanToCompletion && task.Result!=null)priorityReceipts.Add(task.Result);
                else{_=task.Exception;if(!RetiredBeforeSubmission(task))Priority.Failed();}
                priorityTasks.RemoveAt(i);
            }
            for(int i=priorityReceipts.Count-1;i>=0;i--){
                var receipt=host.CommandOutcome(priorityReceipts[i]);
                if(receipt==null || receipt.State==CommandState.AwaitingAck || receipt.State==CommandState.Submitted)continue;
                if(receipt.State==CommandState.Rejected || receipt.State==CommandState.Uncertain)Priority.Failed();
                priorityReceipts.RemoveAt(i);
            }
        }
        private static bool RetiredBeforeSubmission(Task task)
        {
            var error=task.Exception?.GetBaseException() as WireEnvelope.EnvelopeException;
            // These failures occur during admission, before any command is written.
            // Never retry the retired offer; a fresh native offer may progress.
            return error?.Code=="STALE_DECISION" || error?.Code=="STALE_REVISION" || error?.Code=="SESSION_NO_DECISION";
        }
        public void Tick()
        {
            ThreadOnly();if(disposed)return;if(priorityEnabled)MonitorPriorityCommands();var current=host.PresentedDecision;
            // Network reception can revoke an offer between any two Frame reads.
            // Render one immutable snapshot; dispatch still validates the live offer.
            var frame=current?.Frame;if(frame?.Decision==null){current=null;frame=null;}
            if(!ReferenceEquals(current,offer)){
                var retiredCommand=submitted??(pending?.Status==TaskStatus.RanToCompletion?pending.Result:null);
                var retiredReceipt=retiredCommand==null?null:host.CommandOutcome(retiredCommand);
                bool openingMulligan=prompt.text.StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase);
                Clear(preserveStatus:host.Authenticated && !host.Completion.IsCompleted);offer=current;
                if(current==null && retiredReceipt?.State==CommandState.Confirmed){status.text=FeedbackText(CommandState.Confirmed,openingMulligan);Root.AddToClassList("command-confirmed");}
                if(frame!=null){var decision=frame.Decision;Debug.Log("Manaforge decision: family="+decision.Family+" priority="+decision.IsPriority+" options="+decision.Options.Count+" actions="+frame.Actions.Count+" finish="+decision.CanFinish+" stack="+frame.StackIds.Count);}
            }
            if(host.Completion.IsCompleted){Priority.Suspend();autoAfter=-1;}
            Priority.Observe(frame);
            var automatic=priorityEnabled?Priority.Evaluate(frame):null;
            AutomaticPriorityPending=automatic!=null || frame?.Decision?.IsPriority==true && Priority.Current.Attempted.Contains(frame.Decision.DecisionId);
            Presentation=YieldPresentation.Resolve(Priority.Current,frame,PriorityControlsOpen,host.Completion.IsCompleted);
            bool bridge=offer==null && !host.Completion.IsCompleted && Time.unscaledTime<continuityUntil;
            if(!bridge || displayPresentation==null)displayPresentation=Presentation;
            bool unified=priorityActions!=null && PrioritySessionActive && (frame?.Decision?.IsPriority==true && frame.Decision.Family=="selection" && frame.Decision.Groups.Count==0 || offer==null && (priorityActions.HasPresented || Priority.Current.Yield!=null));
            yieldStatus.Bind(displayPresentation);if(priorityActions!=null)yieldStatus.Root.style.display=DisplayStyle.None;
            Root.EnableInClassList("unified-priority",unified);
            if(unified){Root.style.minHeight=StyleKeyword.Null;priorityActions.Refresh();}
            else if(!Presentation.Compact && offer!=null && !built)Build(frame);
            RefreshAmountArtwork();
            if(priorityActions!=null){priorityActions.Root.style.display=unified?DisplayStyle.Flex:DisplayStyle.None;if(!PrioritySessionActive)priorityActions.Reset();}
            decisionBody.style.display=unified || displayPresentation.Compact?DisplayStyle.None:DisplayStyle.Flex;
            bool retired=!host.Authenticated && (!host.Completion.IsCompleted || host.Completion.Result.Code=="VIEWER_OWNER_ENDED");
            Root.style.display=retired?DisplayStyle.None:unified || displayPresentation.Compact || offer!=null || bridge || Presentation.Mode==YieldPresentationMode.Failed?DisplayStyle.Flex:DisplayStyle.None;
            if(Presentation.Mode==YieldPresentationMode.Failed && offer==null){prompt.text=Presentation.Text;}
            manaInput.Refresh(offer);if(offer==null){controls.SetEnabled(false);return;}
            if(pending!=null && pending.IsCompleted){
                if(pending.Status==TaskStatus.RanToCompletion)submitted=pending.Result;
                else if(!RetiredBeforeSubmission(pending))Priority.Failed();
                var error=pending.Exception?.GetBaseException() as WireEnvelope.EnvelopeException;
                status.text=error?.Code=="AMOUNT_OUT_OF_RANGE"?"Enter values within the displayed limits.":error?.Code=="SESSION_NUMERIC_UNAVAILABLE"?"Numeric limits are unavailable. Wait for the game to update.":pending.IsCanceled || pending.IsFaulted?"Command was not confirmed. Check the current decision.":"Choice sent. Waiting for the game.";pending=null;
            }
            var feedback=host.CommandFeedback(offer,submitted);
            if(feedback!=null){
                status.text=FeedbackText(feedback.State,(frame?.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase));
                if(feedback.State==CommandState.Rejected || feedback.State==CommandState.Uncertain)Priority.Failed();
            }
            Root.EnableInClassList("command-pending",pending!=null || feedback?.State==CommandState.Submitted);
            Root.EnableInClassList("command-uncertain",feedback?.State==CommandState.Uncertain);
            Root.EnableInClassList("command-confirmed",feedback?.State==CommandState.Confirmed);
            controls.SetEnabled(offer.CanSubmit && pending==null);manaInput.SetEnabled(offer.CanSubmit && pending==null);priorityActions?.Refresh();
            numericSubmit?.SetEnabled(TryNumbers(out _,false));
            controls.Q<Button>("decision-pass-turn")?.SetEnabled(offer.CanSubmit && pending==null && !Priority.Current.Paused);
            if(!offer.CanSubmit && pending==null && string.IsNullOrEmpty(status.text))status.text="Waiting for the game.";
            if(automatic==null || pending!=null || !offer.CanSubmit || PriorityControlsOpen || LayoutEditing || PresentationHold?.Invoke()==true){autoAfter=-1;return;}
            if(autoAfter<0)autoAfter=Time.unscaledTime;
            if(Time.unscaledTime>=autoAfter){
                var captured=offer;autoAfter=-1;
                if(ReferenceEquals(host.PresentedDecision,captured) && Priority.Claim(frame))
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
            if(ObjectChoiceCount(captured,objectId)!=1)return false;var frame=captured.Frame;if(frame?.Decision==null)return false;
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
            ThreadOnly();var result=new VisualElement();if(ObjectChoiceCount(captured,objectId)==0)return result;var frame=captured.Frame;if(frame?.Decision==null)return result;
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
            if(!priorityEnabled || action.Kind!="pass" || action.ObjectId!=null || frame?.Decision?.IsPriority!=true
                || frame.Decision.PlayerId!=frame.Context.ViewerId || frame.PriorityPlayerId!=frame.Context.ViewerId
                || !frame.Turn.HasValue || frame.ActivePlayerId==null || frame.Status!="active" || frame.Result!=null)return;
            bool ownTurn=frame.ActivePlayerId==frame.Context.ViewerId;
            var button=Button("decision-pass-turn",ownTurn?"End turn":"Pass until response",()=>{
                if(!ReferenceEquals(offer,captured) || !ReferenceEquals(host.PresentedDecision,captured) || !captured.CanSubmit || pending!=null || Priority.Current.Paused)return;
                Priority.BeginYield("response",frame);PrioritySettingsChanged();
            });
            button.SetEnabled(captured.CanSubmit && !Priority.Current.Paused);controls.Add(button);
        }
        private void AddChoice(Button button,bool boundToBoard)
        {
            if(IsLibraryOrdering || !spatialPresentation || !boundToBoard){controls.Add(button);return;}
            if(cardChoices==null){cardChoices=new Foldout{text="Card and player choices",value=false,name="board-choice-alternatives"};cardChoices.style.width=Length.Percent(100);controls.Add(cardChoices);}
            cardChoices.Add(button);
        }
        internal static string FeedbackText(CommandState state,bool openingMulligan=false)
        {
            switch(state) {
                case CommandState.Submitted:return openingMulligan?"Waiting for your opponent to decide…":"Waiting for the game to update…";
                case CommandState.Confirmed:return openingMulligan?"Choice accepted. Waiting for the next opening-hand decision…":"Action accepted. Waiting for the game to update…";
                case CommandState.Rejected:return "That action could not be applied. Check the current decision.";
                case CommandState.Uncertain:return "Command outcome is uncertain. Do not retry.";
                default:return "Choice sent. Waiting for the game.";
            }
        }
        private static Button Button(string name,string text,Action click)
        {var button=new Button(click){name=name,text=text??"Unlabelled engine option"};foreach(var label in button.Query<TextElement>().ToList())label.enableRichText=false;button.enableRichText=false;button.style.fontSize=16;button.style.color=Color.white;button.style.backgroundColor=new Color(.18f,.24f,.30f);button.style.paddingTop=8;button.style.paddingBottom=8;button.style.marginBottom=4;return button;}
        private void Build(ProjectedDecisionFrame snapshot=null)
        {
            var captured=offer;var frame=snapshot??captured?.Frame;if(frame?.Decision==null){Clear();return;}built=true;Root.style.minHeight=StyleKeyword.Null;status.text="";ClearGroupPreviews();
            var floating=frame.ViewerMana==null?"":string.Join(", ",System.Linq.Enumerable.Select(System.Linq.Enumerable.Where(frame.ViewerMana,pair=>pair.Value>0),pair=>pair.Key+" "+pair.Value));manaPool.text=string.IsNullOrEmpty(floating)?"":"Floating mana: "+floating;manaPool.style.display=string.IsNullOrEmpty(floating)?DisplayStyle.None:DisplayStyle.Flex;StableStatusText.Set(prompt,OpeningHandFan.PlainPrompt(frame.Decision.Prompt??"Choose an action"),!frame.Decision.IsPriority);Root.style.display=DisplayStyle.Flex;controls.Clear();pages.Clear();numericSubmit=null;cardChoices=null;
            if(!string.IsNullOrEmpty(frame.PaymentReason)){status.text="Manual payment required: "+frame.PaymentReason.Replace('_',' ').ToLowerInvariant()+".";UnityEngine.Debug.Log("Manaforge payment fallback: "+frame.PaymentReason);}
            Root.EnableInClassList("session-request",frame.Decision.RequestId!=null);
            Root.EnableInClassList("searchable-menu",frame.Decision.Menu!=null);
            status.style.minHeight=frame.Decision.Menu!=null?0:18;
            IsLibraryOrdering=LibraryOrdering(prompt.text);
            Root.EnableInClassList("library-ordering",IsLibraryOrdering);
            if(frame.Decision.Groups.Count>0){BuildGroups(captured,frame);controls.SetEnabled(captured.CanSubmit && pending==null);return;}
            if(frame.Decision.Menu!=null){
                controls.Add(new SearchableChoiceMenu(frame.Decision,option=>Send(captured,()=>host.ChooseAsync(captured,option))).Root);
                if(frame.Decision.Cancellable)controls.Add(Button("decision-cancel","Cancel choice",()=>Send(captured,()=>host.CancelChoiceAsync(captured))));
                controls.SetEnabled(captured.CanSubmit && pending==null);return;
            }
            int total=frame.Actions.Count+frame.Decision.Options.Count;int start=0,end=total;
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

            if(frame.Decision.CanFinish)controls.Add(Button("decision-finish","Finish selection",()=>Send(captured,()=>host.FinishSelectionAsync(captured))));
            if(frame.Decision.Cancellable)controls.Add(Button("decision-cancel","Cancel choice",()=>Send(captured,()=>host.CancelChoiceAsync(captured))));
            if(frame.Decision.Family=="mana" && frame.ManaSourceReferences.Count==0)status.text="No cards are available for mana-source selection.";
            if(frame.Decision.Family=="number" || frame.Decision.Family=="amounts")BuildNumbers(captured,frame.Decision);
            controls.SetEnabled(captured.CanSubmit && pending==null);
        }
        private void BuildGroups(ViewerDecisionOffer captured,ProjectedDecisionFrame frame)
        {
            ProjectedChoiceOption selected=null;
            var groupScroll=new ScrollView(ScrollViewMode.Vertical){name="decision-groups"};groupScroll.style.maxHeight=420;controls.Add(groupScroll);
            foreach(var group in frame.Decision.Groups){
                var tile=new VisualElement{name="choice-group"};tile.AddToClassList("mf-menu");tile.style.marginBottom=12;
                tile.Add(NumericLabel(group.Label+" · "+group.Cards.Count+" cards"));
                var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.maxHeight=390;tile.Add(scroll);
                if(group.Cards.Count==0)scroll.Add(NumericLabel("Empty pile"));
                for(int index=0;index<group.Cards.Count;index++){var card=group.Cards[index];
                    var view=new CardView();view.SetPresentation(CardPresentationMode.Full,190);
                    if(card.Hidden)view.Conceal();else{view.BindUnavailable();view.UpdateValues(new CardDisplayValues(card.Name,null,card.TypeLine,card.Rules,null,"Pile card"));}
                    scroll.Add(view);groupPreviews.Add(view);
                }
                ProjectedChoiceOption option=null;foreach(var candidate in frame.Decision.Options)if(candidate.OptionId==group.OptionId)option=candidate;
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
                controls.Add(NumericLabel("Supported numeric limits are unavailable. Wait for the game to update."));return;
            }
            foreach(var constraint in decision.Amounts)if(!number && constraint.Minimum>constraint.Maximum){controls.Add(NumericLabel("Supported numeric limits are unavailable. Wait for the game to update."));return;}
            int count=number?1:decision.Amounts.Count;if(numericText==null)numericText=new string[count];
            controls.Add(NumericLabel((number?"Allowed value: ":"Allowed total: ")+Integer(decision.Minimum.Value)+" to "+Integer(decision.Maximum.Value)));
            controls.Add(NumericLabel(number?"Enter a whole number, then confirm.":"Set each amount, then confirm. Drag tiles to rearrange recipients."));
            var total=new Label{name="decision-assigned-total",enableRichText=false};total.AddToClassList("numeric-total");if(!number)controls.Add(total);
            void UpdateTotal()
            {
                if(number)return;long sum=0;bool complete=true;
                try{for(int index=0;index<numericText.Length;index++){if(!long.TryParse(numericText[index],NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out long value)){complete=false;continue;}sum=checked(sum+value);}}
                catch(OverflowException){total.text="The assigned total is too large.";return;}
                total.text=complete?"Assigned: "+Integer(sum)+(decision.Minimum==decision.Maximum?" / "+Integer(decision.Maximum.Value):" (allowed "+Integer(decision.Minimum.Value)+" to "+Integer(decision.Maximum.Value)+")"):"Set an amount for every recipient.";
            }
            var recipients=new VisualElement{name="decision-amount-recipients"};recipients.AddToClassList("amount-recipients");controls.Add(recipients);
            var fields=new System.Collections.Generic.List<TextField>();
            for(int i=0;i<count;i++) {
                int index=i;var constraint=number?null:decision.Amounts[i];long min=number?decision.Minimum.Value:constraint.Minimum,max=number?decision.Maximum.Value:constraint.Maximum;
                var tile=new VisualElement{name="decision-amount-recipient-"+i,userData=i};tile.AddToClassList("amount-recipient");recipients.Add(tile);
                var handle=new Label(number?"Number":"↔ Drag to arrange"){name="decision-amount-handle-"+i,focusable=!number};handle.AddToClassList("amount-recipient-handle");tile.Add(handle);
                if(!number && constraint.ObjectId!=null){
                    var artwork=new VisualElement{name="decision-amount-artwork-"+i};artwork.AddToClassList("amount-recipient-artwork");tile.Add(artwork);
                    amountArtwork.Add((constraint.ObjectId,artwork));
                }
                var caption=NumericLabel(number?"Choose a number":constraint.Label??"Recipient");caption.name="decision-amount-name-"+i;caption.AddToClassList("amount-recipient-name");tile.Add(caption);
                var limits=NumericLabel(Integer(min)+" to "+Integer(max));limits.AddToClassList("amount-recipient-limits");tile.Add(limits);
                var stepper=new VisualElement();stepper.AddToClassList("amount-stepper");tile.Add(stepper);
                var field=new TextField(){name="decision-number-"+i,value=numericText[i]??""};fields.Add(field);field.AddToClassList("amount-value");field.style.width=field.style.minWidth=field.style.maxWidth=80;field.style.height=field.style.minHeight=38;field.style.flexShrink=0;field.style.fontSize=20;
                foreach(var text in field.Query<TextElement>().ToList())text.enableRichText=false;
                void Step(int direction)
                {
                    if(disposed || !ReferenceEquals(offer,captured) || !captured.CanSubmit || pending!=null || numericText==null)return;
                    long next;if(!long.TryParse(numericText[index],NumberStyles.AllowLeadingSign,CultureInfo.InvariantCulture,out next))next=direction>0 && min<max?min+1:min;
                    else if(direction>0 && next<max)next++;else if(direction<0 && next>min)next--;
                    field.value=Integer(Math.Max(min,Math.Min(max,next)));
                }
                var minus=Button("decision-amount-minus-"+i,"−",()=>Step(-1));var plus=Button("decision-amount-plus-"+i,"+",()=>Step(1));
                foreach(var button in new[]{minus,plus}){button.style.width=button.style.minWidth=button.style.maxWidth=34;button.style.height=button.style.minHeight=38;button.style.paddingLeft=button.style.paddingRight=0;button.style.marginBottom=0;button.style.flexShrink=0;}
                minus.tooltip="Decrease amount";plus.tooltip="Increase amount";stepper.Add(minus);stepper.Add(field);stepper.Add(plus);
                field.RegisterValueChangedCallback(change=>{
                    if(disposed || !ReferenceEquals(offer,captured) || numericText==null)return;
                    numericText[index]=change.newValue;numericSubmit?.SetEnabled(TryNumbers(out _,false));UpdateTotal();
                });
                if(!number){
                    int pointer=-1;Vector2 origin=default;bool dragged=false;
                    handle.tooltip="Drag to rearrange recipients. Left and right arrows move this tile.";
                    void Place(int at){int current=recipients.IndexOf(tile);at=Math.Max(0,Math.Min(recipients.childCount-1,at));if(at==current)return;if(at<current)tile.PlaceBehind(recipients[at]);else tile.PlaceInFront(recipients[at]);}
                    handle.RegisterCallback<PointerDownEvent>(ev=>{if(ev.button!=0 || !ReferenceEquals(offer,captured) || !captured.CanSubmit)return;pointer=ev.pointerId;origin=ev.position;dragged=false;handle.CapturePointer(pointer);handle.Focus();ev.StopPropagation();});
                    handle.RegisterCallback<PointerMoveEvent>(ev=>{if(pointer!=ev.pointerId || !handle.HasPointerCapture(pointer))return;if(Vector2.Distance(origin,ev.position)>8)dragged=true;tile.EnableInClassList("amount-recipient-dragging",dragged);if(dragged)tile.style.translate=new Translate(ev.position.x-origin.x,ev.position.y-origin.y);ev.StopPropagation();});
                    handle.RegisterCallback<PointerUpEvent>(ev=>{if(pointer!=ev.pointerId)return;bool valid=ReferenceEquals(offer,captured) && captured.CanSubmit;if(dragged && valid){var target=recipients.Children().FirstOrDefault(child=>child!=tile && child.worldBound.Contains(ev.position));if(target!=null)Place(recipients.IndexOf(target));}handle.ReleasePointer(pointer);pointer=-1;tile.style.translate=new Translate(0,0);tile.RemoveFromClassList("amount-recipient-dragging");ev.StopPropagation();});
                    handle.RegisterCallback<PointerCaptureOutEvent>(ev=>{pointer=-1;tile.style.translate=new Translate(0,0);tile.RemoveFromClassList("amount-recipient-dragging");});
                    handle.RegisterCallback<KeyDownEvent>(ev=>{if(!ReferenceEquals(offer,captured) || !captured.CanSubmit)return;if(ev.keyCode!=KeyCode.LeftArrow && ev.keyCode!=KeyCode.RightArrow)return;Place(recipients.IndexOf(tile)+(ev.keyCode==KeyCode.LeftArrow?-1:1));ev.StopPropagation();});
                }
            }
            bool suggested=!number && decision.Amounts.All(amount=>amount.Default.HasValue && amount.Default>=amount.Minimum && amount.Default<=amount.Maximum);
            if(suggested){try{long sum=0;foreach(var amount in decision.Amounts)sum=checked(sum+amount.Default.Value);suggested=sum>=decision.Minimum && sum<=decision.Maximum;}catch(OverflowException){suggested=false;}}
            if(suggested)controls.Add(Button("decision-amount-suggested","Use suggested amounts",()=>{if(!ReferenceEquals(offer,captured) || !captured.CanSubmit || pending!=null)return;for(int i=0;i<fields.Count;i++)fields[i].value=Integer(decision.Amounts[i].Default.Value);}));
            UpdateTotal();
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
        public void Dispose(){ThreadOnly();if(disposed)return;disposed=true;LayoutEditing=false;Priority.Suspend();PresentationHold=null;priorityTasks.Clear();priorityReceipts.Clear();manaInput.Dispose();yieldStatus.Dispose();priorityActions?.Reset();Clear();prompt.RemoveFromHierarchy();Root.RemoveFromHierarchy();}
    }
}

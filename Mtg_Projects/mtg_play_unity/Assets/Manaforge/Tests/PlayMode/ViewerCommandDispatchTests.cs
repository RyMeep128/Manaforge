using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
using GameObject=UnityEngine.GameObject;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerCommandDispatchTests
    {
        private GameObject node;private PanelSettings settings;private ViewerCardSurface surface;private JObject source;
        private readonly List<ViewerDecisionPanel> panels=new List<ViewerDecisionPanel>();
        private readonly List<ViewerSessionHost> hosts=new List<ViewerSessionHost>();private readonly List<ViewerSessionHostTests.Peer> peers=new List<ViewerSessionHostTests.Peer>();
        private JObject Snapshot(string id="snapshot",bool selection=false)
        {
            var frame=(JObject)source.DeepClone();frame["message_id"]=id;
            if(selection){var snapshot=frame["body"]["snapshot"];snapshot["actions"]=new JArray();var decision=snapshot["decision"];decision["family"]="selection";decision["can_finish"]=true;decision["cancellable"]=true;decision["options"]=new JArray(new JObject{["option_id"]="fixture-option",["label"]="Engine option",["object_id"]=JValue.CreateNull(),["player_id"]=JValue.CreateNull(),["selected"]=false});}
            return frame;
        }
        private ViewerSessionHost Start(JObject frame,out ViewerSessionHostTests.Peer peer,out TaskCompletionSource<bool> owner)
        {peer=new ViewerSessionHostTests.Peer(frame.ToString());peers.Add(peer);owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);hosts.Add(host);return host;}
        private static IEnumerator Until(Func<bool> done){double end=Time.realtimeSinceStartupAsDouble+10;while(!done() && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(done(),Is.True,"Command dispatcher timed out");}
        private static string Error(Task task){Assert.That(task.IsFaulted,Is.True);var error=task.Exception.GetBaseException() as WireEnvelope.EnvelopeException;Assert.That(error,Is.Not.Null);return error.Code;}
        private static Task<TrackedCommand> Receipt(ViewerSessionHost host)=>Task.Run(()=>{
            var time=Stopwatch.StartNew();while(time.ElapsedMilliseconds<3000){if(host.TryTake(out var update)){using(update)if(update.Receive.Receipt!=null)return update.Receive.Receipt;}else Thread.Sleep(10);}throw new Exception("Fixture receipt timeout");
        });
        private static JObject Ack(JObject command,string outcome)=>new JObject{["wire_version"]=1,["message_type"]="ack",["message_id"]="ack-"+outcome,["body"]=new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["command_id"]=command["message_id"],["request_revision"]=7,["outcome"]=outcome,["code"]=JValue.CreateNull()}};
        [UnitySetUp] public IEnumerator Setup()
        {
            source=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"];
            node=new GameObject("Bound command test");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;surface=new ViewerCardSurface(doc.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup()
        {foreach(var panel in panels)panel.Dispose();panels.Clear();foreach(var host in hosts)host.Dispose();yield return Until(()=>hosts.TrueForAll(host=>host.Completion.IsCompleted));hosts.Clear();foreach(var peer in peers)peer.Dispose();peers.Clear();surface.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator PerformWritesOneExactCommandAndOnlyReceiptsAdvanceItsOutcome()
        {
            var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var action=offer.Frame.Actions[0];
            var first=host.PerformAsync(offer,action);Assert.That(offer.CanSubmit,Is.False);var duplicate=host.PerformAsync(offer,action);yield return Until(()=>first.IsCompleted && duplicate.IsCompleted);Assert.That(Error(duplicate),Is.EqualTo("COMMAND_PENDING"));Assert.That(first.Result.State,Is.EqualTo(CommandState.AwaitingAck));
            var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);var command=read.GetAwaiter().GetResult();Assert.That((string)command["body"]["action_id"],Is.EqualTo(action.ActionId));Assert.That((string)command["body"]["decision_id"],Is.EqualTo(offer.Frame.Decision.DecisionId));Assert.That((string)command["message_id"],Is.EqualTo(first.Result.CommandId));Assert.That(peer.PendingCommandBytes,Is.Zero);
            foreach(string outcome in new[]{"submitted","confirmed"}){var send=Task.Run(()=>peer.ReplyForFixture(Ack(command,outcome)));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);Assert.That(receipt.Result.State,Is.EqualTo(outcome=="submitted"?CommandState.Submitted:CommandState.Confirmed));}
            Assert.That(first.Result.State,Is.EqualTo(CommandState.AwaitingAck));host.Cancel();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.LastReceipt.State,Is.EqualTo(CommandState.Confirmed));Assert.That(host.Completion.Result.Session.Pending,Is.Null);
        }
        [UnityTest] public IEnumerator ChooseFinishAndCancelUseOnlyOfferedTokensAndFlags()
        {
            var ids=new HashSet<string>();foreach(string operation in new[]{"choose","finish_selection","cancel"}) {
                var host=Start(Snapshot(selection:true),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;
                var sent=operation=="choose"?host.ChooseAsync(offer,offer.Frame.Decision.Options[0]):operation=="cancel"?host.CancelChoiceAsync(offer):host.FinishSelectionAsync(offer);yield return Until(()=>sent.IsCompleted);Assert.That(sent.Result.State,Is.EqualTo(CommandState.AwaitingAck));
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);var command=read.Result;Assert.That((string)command["body"]["operation"],Is.EqualTo(operation));Assert.That(ids.Add((string)command["message_id"]),Is.True);if(operation=="choose")Assert.That((string)command["body"]["option_id"],Is.EqualTo("fixture-option"));
                host.Cancel();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.Pending.State,Is.EqualTo(CommandState.Uncertain));
            }
        }
        [UnityTest] public IEnumerator ForeignActionOrOptionObjectsWithMatchingIdsAreRefusedWithoutWriting()
        {
            foreach(bool selection in new[]{false,true}) {
                var frame=Snapshot(selection:selection);var host=Start(frame,out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var foreign=ViewerDecisionProjection.ParseSnapshot(frame.ToString(),"fixture-session","one",0,true);
                var sent=selection?host.ChooseAsync(offer,foreign.Decision.Options[0]):host.PerformAsync(offer,foreign.Actions[0]);yield return Until(()=>sent.IsCompleted);Assert.That(Error(sent),Is.EqualTo(selection?"OPTION_UNAVAILABLE":"ACTION_UNAVAILABLE"));Assert.That(offer.CanSubmit,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero);host.Cancel();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator StaleAndReplacementEpochOffersCannotWriteCommands()
        {
            var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var old=host.CurrentDecision;var oldAction=old.Frame.Actions[0];var next=Snapshot("next");next["body"]["snapshot"]["revision"]=8;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));
            var refused=host.PerformAsync(old,oldAction);yield return Until(()=>refused.IsCompleted);Assert.That(Error(refused),Is.EqualTo("STALE_DECISION"));Assert.That(peer.PendingCommandBytes,Is.Zero);var foreign=host.CurrentDecision;var foreignAction=foreign.Frame.Actions[0];
            var replacement=Start(next,out var nextPeer,out var nextOwner);yield return Until(()=>replacement.CurrentDecision!=null);var denied=replacement.PerformAsync(foreign,foreignAction);yield return Until(()=>denied.IsCompleted);Assert.That(Error(denied),Is.EqualTo("STALE_DECISION"));Assert.That(nextPeer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator CancellationBeforeAdmissionAndEndedOwnerNeverWrite()
        {
            var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var action=offer.Frame.Actions[0];using var cancel=new CancellationTokenSource();cancel.Cancel();var local=host.PerformAsync(offer,action,cancel.Token);Assert.That(local.IsCanceled,Is.True);Assert.That(offer.CanSubmit,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero);
            owner.TrySetResult(true);var ended=host.PerformAsync(offer,action);yield return Until(()=>ended.IsCompleted && host.Completion.IsCompleted);Assert.That(Error(ended),Is.EqualTo("SESSION_STOPPED"));Assert.That(host.Completion.Result.Session.Pending,Is.Null);
        }
        private ViewerDecisionPanel Panel(ViewerSessionHost host)
        {var panel=new ViewerDecisionPanel(node.GetComponent<UIDocument>().rootVisualElement,host);panels.Add(panel);return panel;}
        private static void Click(Button button)
        {Assert.That(button,Is.Not.Null);using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=button;button.SendEvent(submit);}}
        private IEnumerator Show(ViewerSessionHost host,ViewerDecisionPanel panel)
        {yield return Until(()=>{host.Tick();panel.Tick();return host.PresentedDecision!=null;});}
        private JObject PrioritySnapshot(int revision=7,bool stack=false)
        {
            var wire=Snapshot("priority-"+revision);var snapshot=wire["body"]["snapshot"];
            snapshot["revision"]=revision;snapshot["turn"]=1;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["active_player_id"]="one";snapshot["priority_player_id"]="one";
            snapshot["decision"]["decision_id"]="priority-"+revision;snapshot["decision"]["is_priority"]=true;snapshot["decision"]["family"]="selection";snapshot["decision"]["options"]=new JArray();
            snapshot["objects"][0]["zone"]=stack?"stack":"hand";
            snapshot["actions"]=new JArray(new JObject{["action_id"]="pass-"+revision,["kind"]="pass",["object_id"]=null,["label"]="Pass priority",["priority_class"]="unknown"});return wire;
        }
        [UnityTest] public IEnumerator CombinedPriorityKeepsButtonsAndGeometryAcrossPassingAndBindsOnlyCurrentOffer()
        {
            var host=Start(PrioritySnapshot(),out var peer,out var owner);var panel=Panel(host);panel.UseUnifiedPriorityActions(()=>{});panel.Priority.Current.Automatic=false;panel.PresentationHold=()=>true;GameplayTheme.Attach(panel.Root);
            var root=node.GetComponent<UIDocument>().rootVisualElement;root.style.width=1280;root.style.height=720;panel.Root.style.width=275;
            yield return Show(host,panel);yield return null;
            var area=panel.Root.Q("priority-actions");var primary=panel.Root.Q<Button>("priority-actions-primary");var secondary=panel.Root.Q<Button>("priority-actions-secondary");
            var original=area.worldBound;var primaryBounds=primary.worldBound;var secondaryBounds=secondary.worldBound;
            Assert.That(primary.text,Is.EqualTo("Next"));Assert.That(secondary.text,Is.EqualTo("End turn"));var more=panel.Root.Q<Button>("priority-actions-more");Assert.That(more.resolvedStyle.width,Is.EqualTo(36));Assert.That(secondary.worldBound.xMax,Is.LessThanOrEqualTo(more.worldBound.xMin-8));
            Click(secondary);panel.Tick();yield return null;Assert.That(panel.Priority.Current.Yield,Is.EqualTo("end-turn"));Assert.That(primary.text,Is.EqualTo("Cancel"));
            Assert.That(panel.Root.Q("yield-status").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(panel.Root.Q("decision-body").style.display.value,Is.EqualTo(DisplayStyle.None));
            foreach(int revision in new[]{8,9,10}){
                var next=PrioritySnapshot(revision);next["body"]["snapshot"]["decision"]["prompt"]=revision%2==0?"Play instants and activated abilities":"Play spells and abilities";
                var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);yield return Until(()=>{host.Tick();panel.Tick();return host.HasPresentedRevision(revision);});yield return null;
                Assert.That(panel.Root.Q("priority-actions"),Is.SameAs(area));Assert.That(panel.Root.Q<Button>("priority-actions-primary"),Is.SameAs(primary));Assert.That(panel.Root.Q<Button>("priority-actions-secondary"),Is.SameAs(secondary));
                Assert.That(area.worldBound,Is.EqualTo(original));Assert.That(primary.worldBound,Is.EqualTo(primaryBounds));Assert.That(secondary.worldBound,Is.EqualTo(secondaryBounds));Assert.That(primary.text,Is.EqualTo("Cancel"));
            }
            Click(primary);panel.Tick();yield return null;Assert.That(panel.Priority.Current.Yield,Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(primary.text,Is.EqualTo("Next"));
            Click(primary);Click(primary);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
            Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("pass-10"));Assert.That((string)read.Result["body"]["decision_id"],Is.EqualTo("priority-10"));Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(primary.enabledSelf,Is.False);
            owner.TrySetResult(true);yield return Until(()=>{host.Tick();panel.Tick();return host.Completion.IsCompleted;});Click(primary);Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator CombinedResolveAllHonorsStopsRequiredChoicesFailureAndResolutionBoundary()
        {
            var host=Start(PrioritySnapshot(stack:true),out var peer,out var owner);var panel=Panel(host);panel.UseUnifiedPriorityActions(()=>{});panel.Priority.Current.Automatic=false;panel.PresentationHold=()=>true;GameplayTheme.Attach(panel.Root);panel.Root.style.width=275;
            yield return Show(host,panel);yield return null;var primary=panel.Root.Q<Button>("priority-actions-primary");var secondary=panel.Root.Q<Button>("priority-actions-secondary");var bounds=primary.worldBound;
            Assert.That(primary.text,Is.EqualTo("Resolve"));Assert.That(secondary.text,Is.EqualTo("Resolve All"));Click(secondary);panel.Tick();Assert.That(panel.Priority.Current.Yield,Is.EqualTo("resolve-stack"));Assert.That(primary.text,Is.EqualTo("Cancel"));
            panel.Priority.SetStop("phase","PRECOMBAT_MAIN",true);panel.PrioritySettingsChanged();panel.Tick();Assert.That(panel.Presentation.Mode,Is.EqualTo(YieldPresentationMode.Stopped));Assert.That(primary.text,Is.EqualTo("Resolve"));Assert.That(secondary.text,Is.EqualTo("Cancel passing"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            panel.Priority.SetStop("phase","PRECOMBAT_MAIN",false);panel.PrioritySettingsChanged();panel.Tick();Assert.That(primary.text,Is.EqualTo("Cancel"));
            var required=PrioritySnapshot(8,true);required["body"]["snapshot"]["decision"]["is_priority"]=false;required["body"]["snapshot"]["actions"]=new JArray();required["body"]["snapshot"]["decision"]["options"]=new JArray(new JObject{["option_id"]="required",["label"]="Choose this card",["object_id"]=null,["player_id"]=null,["selected"]=false});
            var send=Task.Run(()=>peer.ReplyForFixture(required));yield return Until(()=>send.IsCompleted);yield return Until(()=>{host.Tick();panel.Tick();return host.HasPresentedRevision(8);});yield return null;
            Assert.That(panel.Root.Q("priority-actions").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(panel.Root.Q("decision-body").style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(panel.Root.Q<Button>("decision-option-0"),Is.Not.Null);Assert.That(panel.SuppressSpatialInput,Is.False);Click(primary);Assert.That(peer.PendingCommandBytes,Is.Zero);
            var resolved=PrioritySnapshot(9);send=Task.Run(()=>peer.ReplyForFixture(resolved));yield return Until(()=>send.IsCompleted);yield return Until(()=>{host.Tick();panel.Tick();return host.HasPresentedRevision(9);});yield return null;
            Assert.That(panel.Priority.Current.Yield,Is.Null);Assert.That(panel.Priority.Current.ResolveBoundary,Is.EqualTo("priority-9"));Assert.That(primary.text,Is.EqualTo("Next"));Assert.That(primary.worldBound,Is.EqualTo(bounds));Assert.That(panel.Priority.Evaluate(panel.PriorityFrame),Is.Null);
            panel.Priority.Failed();panel.PrioritySettingsChanged();panel.Tick();Assert.That(primary.text,Is.EqualTo("Resume"));Click(primary);panel.Tick();Assert.That(panel.Priority.Current.Paused,Is.False);Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator YieldPanelRetainsCancelAndRestoresRequiredInput()
        {
            var envelope=Snapshot();var snapshot=envelope["body"]["snapshot"];
            snapshot["turn"]=1;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";
            snapshot["active_player_id"]="one";snapshot["priority_player_id"]="one";
            snapshot["decision"]["is_priority"]=true;snapshot["decision"]["family"]="selection";snapshot["decision"]["options"]=new JArray();
            snapshot["actions"]=new JArray(new JObject{["action_id"]="yield-pass",["kind"]="pass",["object_id"]=null,["label"]="Pass priority",["priority_class"]="unknown"});
            var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            panel.Priority.BeginYield("end-turn",host.PresentedDecision.Frame);panel.Tick();
            var cancel=panel.Root.Q<Button>("yield-status-cancel");var status=panel.Root.Q<VisualElement>("yield-status");
            Assert.That(panel.SuppressSpatialInput,Is.True);Assert.That(panel.Root.Q<VisualElement>("decision-body").style.display.value,Is.EqualTo(DisplayStyle.None));
            var next=(JObject)envelope.DeepClone();next["message_id"]="required-after-yield";next["body"]["snapshot"]["revision"]=8;
            next["body"]["snapshot"]["decision"]["is_priority"]=false;next["body"]["snapshot"]["decision"]["decision_id"]="required-after-yield";
            next["body"]["snapshot"]["actions"]=new JArray();next["body"]["snapshot"]["decision"]["options"]=new JArray(new JObject{["option_id"]="required-option",["label"]="Required choice",["object_id"]=null,["player_id"]=null,["selected"]=false});
            var old=host.CurrentDecision;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(old,host.CurrentDecision));yield return Show(host,panel);
            Assert.That(panel.SuppressSpatialInput,Is.False);Assert.That(panel.Priority.Current.Yield,Is.EqualTo("end-turn"));
            Assert.That(panel.Root.Q<Button>("decision-option-0"),Is.Not.Null);Assert.That(panel.Root.Q<VisualElement>("yield-status"),Is.SameAs(status));Assert.That(panel.Root.Q<Button>("yield-status-cancel"),Is.SameAs(cancel));
            Click(cancel);panel.Tick();Assert.That(panel.Priority.Current.Yield,Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator TargetClickUsesExactOfferedOption()=>TargetGesture(false);
        [UnityTest] public IEnumerator TargetDragUsesExactOfferedOption()=>TargetGesture(true);
        [UnityTest] public IEnumerator TargetDragOutsideDoesNotSubmit()=>TargetGesture(true,true);
        [UnityTest] public IEnumerator NewOfferCancelsTargetDrag()=>TargetGesture(true,false,true);
        private IEnumerator TargetGesture(bool drag,bool invalid=false,bool stale=false)
        {
            var envelope=BoardSnapshot();var snapshot=envelope["body"]["snapshot"];snapshot["actions"]=new JArray();snapshot["decision"]["is_priority"]=false;snapshot["decision"]["family"]="selection";
            var source=snapshot["objects"][0].DeepClone();source["object_id"]="targeting-source";source["presentation_id"]=null;((JArray)snapshot["objects"]).Add(source);
            snapshot["decision"]["targeting"]=new JObject{["source_id"]="targeting-source",["minimum"]=1,["maximum"]=1,["selected"]=new JArray(),["complete"]=true};
            snapshot["decision"]["options"]=new JArray(new JObject{["option_id"]="exact-target-option",["label"]="Legal target",["object_id"]="fixture-0002",["player_id"]=null,["selected"]=false});
            var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var root=node.GetComponent<UIDocument>().rootVisualElement;root.style.width=1280;root.style.height=720;
            using(var input=new ViewerBoardInput(root,surface,host,panel))using(var targeting=new ViewerTargetingController(root,surface,panel,Array.Empty<PlayerPanel>())){
                input.Refresh();targeting.Observe(host.PresentedDecision.Frame);yield return null;
                CardView origin=null,target=null;surface.VisitPresented((card,view)=>{if(card.ObjectId=="targeting-source")origin=view;else target=view;});
                Assert.That(target,Is.Not.Null);Assert.That(origin,Is.Not.Null);Assert.That(target.ClassListContains("mf-target-legal"),Is.True);
                var pressed=drag?origin:target;
                using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=pressed.worldBound.center})){down.target=pressed;pressed.SendEvent(down);}
                var drop=invalid?new Vector2(1200,700):target.worldBound.center;
                if(drag)using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=drop})){move.target=root;root.SendEvent(move);}
                Assert.That(peer.PendingCommandBytes,Is.Zero);
                if(stale){var next=(JObject)envelope.DeepClone();next["message_id"]="fresh-target";next["body"]["snapshot"]["revision"]=8;next["body"]["snapshot"]["decision"]["decision_id"]="fresh-target";var old=host.CurrentDecision;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(old,host.CurrentDecision));yield return Show(host,panel);targeting.Observe(host.PresentedDecision.Frame);input.Refresh();}
                using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=drop})){up.target=drag?root:target;((VisualElement)up.target).SendEvent(up);}
                if(invalid || stale){Assert.That(peer.PendingCommandBytes,Is.Zero);yield break;}
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("exact-target-option"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator DecisionPanelWaitsForPresentedSnapshotAndClearsOnOwnerLoss()
        {
            var host=Start(Snapshot(selection:true),out var peer,out var owner);var panel=Panel(host);yield return Until(()=>host.CurrentDecision!=null);panel.Tick();Assert.That(panel.Root.Q("decision-controls").childCount,Is.Zero);Assert.That(panel.Root.Q<Label>("decision-prompt").text,Is.Empty);
            yield return Show(host,panel);var cached=panel.Root.Q<Button>("decision-option-0");Assert.That(cached,Is.Not.Null);owner.TrySetResult(true);panel.Tick();Assert.That(panel.Root.Q("decision-controls").childCount,Is.Zero);Assert.That(panel.Root.Q<Label>("decision-prompt").text,Is.Empty);Click(cached);Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator DecisionPanelSubmitsExactOptionAndNeverCallsAWriteConfirmation()
        {
            var frame=Snapshot(selection:true);frame["body"]["snapshot"]["decision"]["prompt"]="Choose a public fixture option";frame["body"]["snapshot"]["decision"]["options"][0]["label"]="Select the engine-provided option";
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Click(panel.Root.Q<Button>("decision-option-0"));Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.False);
            var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("fixture-option"));yield return Until(()=>{panel.Tick();return panel.Root.Q<Label>("decision-status").text=="Command sent. Waiting for gateway state.";});Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.False);
            surface.CardsRoot.style.display=DisplayStyle.None;surface.InspectionView.style.display=DisplayStyle.None;panel.Root.style.width=620;
            var target=new RenderTexture(1280,720,24);Texture2D pixels=null;var previous=RenderTexture.active;
            try{target.Create();settings.targetTexture=target;for(int i=0;i<5;i++){host.Tick();panel.Tick();yield return null;}pixels=new Texture2D(1280,720,TextureFormat.RGBA32,false);RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1280,720),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(Application.dataPath,"../Artifacts/DecisionPanelProof.png"),pixels.EncodeToPNG());}
            finally{settings.targetTexture=null;RenderTexture.active=previous;if(pixels!=null)UnityEngine.Object.Destroy(pixels);target.Release();UnityEngine.Object.Destroy(target);}
        }
        [UnityTest] public IEnumerator DecisionPanelActionFinishAndCancelUseOnlyExplicitEngineControls()
        {
            foreach(string operation in new[]{"perform","finish_selection","cancel"}) {
                var frame=Snapshot(selection:operation!="perform");frame["body"]["snapshot"]["decision"]["prompt"]="<b>Literal engine prompt</b>";var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Assert.That(panel.Root.Q<Label>("decision-prompt").enableRichText,Is.False);Assert.That(panel.Root.Q<Label>("decision-prompt").text,Is.EqualTo("<b>Literal engine prompt</b>"));
                string button=operation=="perform"?"decision-action-0":operation=="cancel"?"decision-cancel":"decision-finish";Click(panel.Root.Q<Button>(button));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo(operation));host.Cancel();yield return Until(()=>host.Completion.IsCompleted);panel.Tick();Assert.That(panel.Root.Q("decision-controls").childCount,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator PileScrollingAndSelectionSendNothingUntilExplicitConfirmation()
        {
            var frame=Snapshot(selection:true);var decision=frame["body"]["snapshot"]["decision"];decision["is_priority"]=false;decision["can_finish"]=false;decision["cancellable"]=false;
            decision["options"]=new JArray(new JObject{["option_id"]="first-option",["label"]="First pile",["object_id"]=null,["player_id"]=null,["selected"]=false},new JObject{["option_id"]="second-option",["label"]="Second pile",["object_id"]=null,["player_id"]=null,["selected"]=false});
            var cards=new JArray();for(int i=0;i<33;i++)cards.Add(new JObject{["hidden"]=false,["name"]="Public card "+i,["type_line"]="Instant",["rules"]=new JArray("Engine text")});
            decision["groups"]=new JArray(new JObject{["group_id"]="first",["label"]="Pile 1",["option_id"]="first-option",["cards"]=cards},new JObject{["group_id"]="second",["label"]="Pile 2",["option_id"]="second-option",["cards"]=new JArray()});
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            Assert.That(panel.Root.Query<CardView>().ToList().Count,Is.EqualTo(33));Assert.That(panel.Root.Q<Button>("decision-group-confirm").enabledSelf,Is.False);
            Assert.That(panel.Root.Q<Button>("decision-group-next-first"),Is.Null);Assert.That(panel.Root.Query<CardView>().ToList().Count,Is.EqualTo(33));Assert.That(peer.PendingCommandBytes,Is.Zero);
            Click(panel.Root.Q<Button>("decision-group-second"));Assert.That(peer.PendingCommandBytes,Is.Zero);var confirm=panel.Root.Q<Button>("decision-group-confirm");Assert.That(confirm.enabledInHierarchy,Is.True);Assert.That(confirm.text,Does.Contain("Second pile"));Click(confirm);
            var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("choose"));Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("second-option"));Assert.That(read.Result["body"]["cards"],Is.Null);
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);panel.Tick();Assert.That(panel.Root.Query<CardView>().ToList(),Is.Empty);
        }
        [UnityTest] public IEnumerator PermissionDialogDoesNotAutomaticallyGrantConsent()
        {
            var frame=Snapshot(selection:true);var decision=frame["body"]["snapshot"]["decision"];decision["is_priority"]=false;decision["can_finish"]=false;decision["cancellable"]=false;
            decision["request"]=new JObject{["request_id"]=(string)decision["decision_id"],["kind"]="hand_visibility"};
            decision["options"]=new JArray(new JObject{["option_id"]="accept",["label"]="Accept",["object_id"]=null,["player_id"]=null,["selected"]=false},new JObject{["option_id"]="deny",["label"]="Reject",["object_id"]=null,["player_id"]=null,["selected"]=false});
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);panel.EnablePriority();yield return Show(host,panel);
            for(int i=0;i<5;i++){panel.Tick();yield return null;}Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(panel.Root.ClassListContains("session-request"),Is.True);
            Click(panel.Root.Q<Button>("decision-option-1"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("deny"));
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);panel.Tick();Assert.That(panel.Root.ClassListContains("session-request"),Is.False);
        }
        [UnityTest] public IEnumerator PanelFeedbackUsesOwnedReceiptsWithoutConsumingTheOrderedQueue()
        {
            var host=Start(Snapshot(selection:true),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Click(panel.Root.Q<Button>("decision-option-0"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);var command=read.Result;
            foreach(string outcome in new[]{"submitted","confirmed"}) {
                var send=Task.Run(()=>peer.ReplyForFixture(Ack(command,outcome)));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);Assert.That(receipt.Result.State,Is.EqualTo(outcome=="submitted"?CommandState.Submitted:CommandState.Confirmed));
                string expected=outcome=="submitted"?"Gateway reports submitted. Waiting for confirmation.":"Gateway confirmed command. Waiting for updated state.";yield return Until(()=>{panel.Tick();return panel.Root.Q<Label>("decision-status").text==expected;});Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.EqualTo(outcome=="confirmed"));
            }
        }
        [UnityTest] public IEnumerator PanelRejectFeedbackCannotOverwriteTheNextCommandWithRepeatedOldReceipt()
        {
            var host=Start(Snapshot(selection:true),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Click(panel.Root.Q<Button>("decision-option-0"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);var rejected=Ack(read.Result,"rejected");rejected["body"]["code"]="ENGINE_REJECTED";var send=Task.Run(()=>peer.ReplyForFixture(rejected));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);receipt.GetAwaiter().GetResult();yield return Until(()=>{panel.Tick();return panel.Root.Q<Label>("decision-status").text=="Gateway rejected command. Check the current decision.";});
            Click(panel.Root.Q<Button>("decision-option-0"));var second=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>second.IsCompleted);Assert.That((string)second.Result["message_id"],Is.Not.EqualTo((string)read.Result["message_id"]));rejected["message_id"]="repeat-old-rejection";send=Task.Run(()=>peer.ReplyForFixture(rejected));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);receipt.GetAwaiter().GetResult();yield return Until(()=>{panel.Tick();return panel.Root.Q<Label>("decision-status").text=="Command sent. Waiting for gateway state.";});Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.False);
        }
        [UnityTest] public IEnumerator PanelDoesNotApplyALateConfirmationToANewDecision()
        {
            var host=Start(Snapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Click(panel.Root.Q<Button>("decision-action-0"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);var old=host.CurrentDecision;var next=Snapshot("new-feedback-decision");next["body"]["snapshot"]["revision"]=8;next["body"]["snapshot"]["decision"]["decision_id"]="fresh-decision";var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(old,host.CurrentDecision));yield return Show(host,panel);
            send=Task.Run(()=>peer.ReplyForFixture(Ack(read.Result,"confirmed")));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);Assert.That(receipt.Result.State,Is.EqualTo(CommandState.Confirmed));panel.Tick();Assert.That(panel.Root.Q<Label>("decision-status").text,Does.Not.Contain("confirmed"));Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.True);
        }
        [UnityTest] public IEnumerator PanelUncertaintyBlocksRetryAndOwnerLossClearsAllFeedback()
        {
            var host=Start(Snapshot(selection:true),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var cached=panel.Root.Q<Button>("decision-option-0");Click(cached);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);var uncertain=Ack(read.Result,"uncertain");uncertain["body"]["code"]="COMMAND_UNCERTAIN";var send=Task.Run(()=>peer.ReplyForFixture(uncertain));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);Assert.That(receipt.Result.State,Is.EqualTo(CommandState.Uncertain));yield return Until(()=>{panel.Tick();return panel.Root.Q<Label>("decision-status").text=="Command outcome is uncertain. Do not retry.";});Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.False);Click(cached);Assert.That(peer.PendingCommandBytes,Is.Zero);
            send=Task.Run(()=>peer.ReplyForFixture(Ack(read.Result,"submitted")));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);Assert.That(receipt.Result.State,Is.EqualTo(CommandState.Uncertain));panel.Tick();Assert.That(panel.Root.Q<Label>("decision-status").text,Is.EqualTo("Command outcome is uncertain. Do not retry."));owner.TrySetResult(true);panel.Tick();Assert.That(panel.Root.Q<Label>("decision-status").text,Is.Empty);Assert.That(panel.Root.style.display.value,Is.EqualTo(DisplayStyle.None));yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.Pending.State,Is.EqualTo(CommandState.Uncertain));
        }
        [UnityTest] public IEnumerator DecisionPanelPagesEveryEngineOptionWithoutAutomaticallyChoosing()
        {
            var frame=Snapshot(selection:true);var options=(JArray)frame["body"]["snapshot"]["decision"]["options"];options.Clear();for(int i=0;i<ViewerDecisionPanel.PageSize+1;i++)options.Add(new JObject{["option_id"]="option-"+i,["label"]="Public option "+i,["object_id"]=JValue.CreateNull(),["player_id"]=JValue.CreateNull(),["selected"]=false});
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Assert.That(panel.Root.Q<Button>("decision-next"),Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(panel.Root.Q<Button>("decision-option-16"),Is.Not.Null);Assert.That(panel.Root.Q<Button>("decision-option-0"),Is.Not.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);
            Click(panel.Root.Q<Button>("decision-option-16"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("option-16"));
        }
        [UnityTest] public IEnumerator RetainedButtonsCannotSubmitAfterNewSnapshotOrViewerReplacement()
        {
            var host=Start(Snapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var button=panel.Root.Q<Button>("decision-action-0");var old=host.CurrentDecision;var next=Snapshot("new-panel");next["body"]["snapshot"]["revision"]=8;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));Click(button);Assert.That(peer.PendingCommandBytes,Is.Zero);panel.Tick();Assert.That(panel.Root.Q("decision-controls").childCount,Is.Zero);
            yield return Show(host,panel);var cached=panel.Root.Q<Button>("decision-action-0");var replacement=Start(next,out var nextPeer,out var nextOwner);panel.Tick();Assert.That(panel.Root.Q("decision-controls").childCount,Is.Zero);Click(cached);Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(nextPeer.PendingCommandBytes,Is.Zero);yield return Until(()=>replacement.CurrentDecision!=null);
        }
        private JObject BoardSnapshot(bool multiple=false)
        {
            var frame=Snapshot();var snapshot=frame["body"]["snapshot"];
            var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
            snapshot["objects"]=corpus["positive"][0]["envelope"]["body"]["snapshot"]["objects"].DeepClone();snapshot["objects"][0]["zone"]="battlefield";snapshot["objects"][0]["tapped"]=false;
            snapshot["actions"][0]["object_id"]="fixture-0002";snapshot["actions"][0]["kind"]="declare_attacker";
            if(multiple){var extra=snapshot["actions"][0].DeepClone();extra["action_id"]="another-action";extra["kind"]="activate";extra["label"]="Second offered action";((JArray)snapshot["actions"]).Add(extra);}
            return frame;
        }
        [UnityTest] public IEnumerator SingleNativeAbilityChoosesOnceAndMultipleAbilitiesWaitForInput()
        {
            foreach(int count in new[]{1,2}){
                var envelope=Snapshot(selection:true);var decision=envelope["body"]["snapshot"]["decision"];decision["ability_selection"]=true;decision["is_priority"]=false;decision["can_finish"]=false;
                if(count==2){var other=decision["options"][0].DeepClone();other["option_id"]="other-ability";((JArray)decision["options"]).Add(other);}
                var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
                if(count==2){for(int i=0;i<5;i++)panel.Tick();Assert.That(peer.PendingCommandBytes,Is.Zero);Click(panel.Root.Q<Button>("decision-option-1"));}
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
                Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("choose"));Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo(count==1?"fixture-option":"other-ability"));
                var rejected=Ack(read.Result,"rejected");rejected["body"]["code"]="ENGINE_REJECTED";var send=Task.Run(()=>peer.ReplyForFixture(rejected));yield return Until(()=>send.IsCompleted);var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);yield return null;
                for(int i=0;i<5;i++)panel.Tick();Assert.That(peer.PendingCommandBytes,Is.Zero,"A rejected single ability must not retry automatically");host.Cancel();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator HandSingleClickPreviewsAndDoubleClickSubmitsExactlyOnce()=>HandDoubleClick("cast_spell");
        [UnityTest] public IEnumerator HandLandAlsoRequiresDoubleClick()=>HandDoubleClick("play_land");
        [UnityTest] public IEnumerator CreatureAbilityUsesDoubleClickWithoutASingleClickActivation()=>HandDoubleClick("activate",true);
        private IEnumerator HandDoubleClick(string kind,bool battlefield=false)
        {
            var envelope=BoardSnapshot();envelope["body"]["snapshot"]["objects"][0]["zone"]=battlefield?"battlefield":"hand";
            if(battlefield)envelope["body"]["snapshot"]["objects"][0]["characteristics"]["type_line"]="Creature";
            envelope["body"]["snapshot"]["actions"][0]["kind"]=kind;
            var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            var root=node.GetComponent<UIDocument>().rootVisualElement;
            using(var input=new ViewerBoardInput(root,surface,host,panel)){
                input.Refresh();var view=surface.CardsRoot.Q<CardView>();
                for(int count=1;count<=2;count++){
                    using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,clickCount=count,mousePosition=view.worldBound.center})){down.target=view;view.SendEvent(down);}
                    Assert.That(peer.PendingCommandBytes,Is.Zero);
                    using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,clickCount=count,mousePosition=view.worldBound.center})){up.target=view;view.SendEvent(up);}
                    if(count==1)Assert.That(peer.PendingCommandBytes,Is.Zero);
                }
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
                Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("fixture-action"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator RequiredHandSelectionStillUsesOneClick()
        {
            var envelope=BoardSnapshot();var snapshot=envelope["body"]["snapshot"];snapshot["objects"][0]["zone"]="hand";snapshot["actions"]=new JArray();
            snapshot["decision"]["is_priority"]=false;snapshot["decision"]["family"]="selection";
            snapshot["decision"]["options"]=new JArray(new JObject{["option_id"]="required-card",["label"]="Choose card",["object_id"]="fixture-0002",["player_id"]=JValue.CreateNull(),["selected"]=false});
            var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            using(var input=new ViewerBoardInput(node.GetComponent<UIDocument>().rootVisualElement,surface,host,panel)){
                input.Refresh();var view=surface.CardsRoot.Q<CardView>();
                using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,clickCount=1,mousePosition=view.worldBound.center})){down.target=view;view.SendEvent(down);}
                using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,clickCount=1,mousePosition=view.worldBound.center})){up.target=view;view.SendEvent(up);}
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
                Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("required-card"));
            }
        }
        [UnityTest] public IEnumerator BoardKeyboardSelectionUsesExactOfferAndBlocksPendingDuplicates()
        {
            var host=Start(BoardSnapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            var root=node.GetComponent<UIDocument>().rootVisualElement;using(var input=new ViewerBoardInput(root,surface,host,panel)){
                input.Refresh();var view=surface.CardsRoot.Q<CardView>();Assert.That(view.ClassListContains("actionable"),Is.True);
                SubmitCard(view);SubmitCard(view);input.Refresh();Assert.That(view.ClassListContains("actionable"),Is.False);
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
                Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("fixture-action"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator AmbiguousBoardObjectRequiresExplicitMenuChoice()
        {
            var host=Start(BoardSnapshot(multiple:true),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var offer=host.PresentedDecision;
            Assert.That(panel.ObjectChoiceCount(offer,"fixture-0002"),Is.EqualTo(2));Assert.That(panel.TryActivateObject(offer,"fixture-0002"),Is.False);Assert.That(peer.PendingCommandBytes,Is.Zero);
            var menu=panel.ObjectChoices(offer,"fixture-0002");node.GetComponent<UIDocument>().rootVisualElement.Add(menu);
            Click(menu.Query<Button>().ToList()[1]);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
            Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("another-action"));menu.RemoveFromHierarchy();
        }
        [UnityTest] public IEnumerator NewSnapshotCancelsCapturedDragWithoutSubmittingEitherDecision()
        {
            var host=Start(BoardSnapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var root=node.GetComponent<UIDocument>().rootVisualElement;
            using(var input=new ViewerBoardInput(root,surface,host,panel)){
                input.Refresh();var view=surface.CardsRoot.Q<CardView>();yield return null;
                using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=view.worldBound.center})){down.target=view;view.SendEvent(down);}
                using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=new Vector2(400,300)})){move.target=view;view.SendEvent(move);}
                Assert.That(root.Q<Label>("board-drag-ghost").style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(peer.PendingCommandBytes,Is.Zero);
                var next=BoardSnapshot();next["message_id"]="next-board";next["body"]["snapshot"]["revision"]=8;var old=host.PresentedDecision;
                var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));yield return Show(host,panel);input.Refresh();
                using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=new Vector2(400,300)})){up.target=view;view.SendEvent(up);}
                Assert.That(root.Q<Label>("board-drag-ghost").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(peer.PendingCommandBytes,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator BattlefieldDropWritesOnlyOnReleaseAndOutsideDropDoesNothing()
        {
            var envelope=BoardSnapshot();envelope["body"]["snapshot"]["objects"][0]["zone"]="hand";envelope["body"]["snapshot"]["actions"][0]["kind"]="cast_spell";
            var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var root=node.GetComponent<UIDocument>().rootVisualElement;
            root.style.width=1280;root.style.height=720;yield return null;
            using(var input=new ViewerBoardInput(root,surface,host,panel)){
                input.Refresh();var view=surface.CardsRoot.Q<CardView>();
                for(int pass=0;pass<2;pass++){
                    using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=view.worldBound.center})){down.target=view;view.SendEvent(down);}
                    var point=pass==0?new Vector2(1200,700):new Vector2(400,300);
                    using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=point})){move.target=view;view.SendEvent(move);}
                    Assert.That(peer.PendingCommandBytes,Is.Zero);
                    using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=point})){up.target=view;view.SendEvent(up);}
                    if(pass==0)Assert.That(peer.PendingCommandBytes,Is.Zero);
                }
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("fixture-action"));
            }
        }
        [UnityTest] public IEnumerator DraggingAnOfferedLibraryCardUsesOnlyItsCurrentOptionToken()
        {
            var envelope=BoardSnapshot();var snapshot=envelope["body"]["snapshot"];snapshot["objects"][0]["zone"]="library";snapshot["actions"]=new JArray();
            snapshot["decision"]["options"]=new JArray(new JObject{["option_id"]="exact-library-choice",["label"]="Engine card choice",["object_id"]="fixture-0002",["player_id"]=JValue.CreateNull(),["selected"]=false});
            var host=Start(envelope,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var root=node.GetComponent<UIDocument>().rootVisualElement;
            root.style.width=1280;root.style.height=720;yield return null;
            using(var input=new ViewerBoardInput(root,surface,host,panel)){
                input.Refresh();var view=surface.CardsRoot.Q<CardView>();
                using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=view.worldBound.center})){down.target=view;view.SendEvent(down);}
                var point=new Vector2(400,300);
                using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=point})){move.target=view;view.SendEvent(move);}
                Assert.That(peer.PendingCommandBytes,Is.Zero);
                using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=point})){up.target=view;view.SendEvent(up);}
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
                Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("exact-library-choice"));
                Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("choose"));
            }
        }
        [UnityTest] public IEnumerator SpatialCardAndPlayerTargetsRetainExactOfferedOptionTokens()
        {
            foreach(bool player in new[]{false,true}){
                var frame=BoardSnapshot();frame["body"]["snapshot"]["actions"]=new JArray();frame["body"]["snapshot"]["decision"]["options"]=new JArray(new JObject{["option_id"]="exact-target",["label"]="Engine target",["object_id"]=player?JValue.CreateNull():new JValue("fixture-0002"),["player_id"]=player?new JValue("two"):JValue.CreateNull(),["selected"]=false});
                var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var offer=host.PresentedDecision;
                Assert.That(player?panel.TryActivatePlayer(offer,"one"):panel.TryActivateObject(offer,"unknown"),Is.False);Assert.That(peer.PendingCommandBytes,Is.Zero);
                Assert.That(player?panel.TryActivatePlayer(offer,"two"):panel.TryActivateObject(offer,"fixture-0002"),Is.True);
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("exact-target"));
                host.Cancel();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator DragPreviewBorrowsCurrentTextureAndClearsItWhenOwnerEnds()
        {
            var host=Start(BoardSnapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var root=node.GetComponent<UIDocument>().rootVisualElement;
            var texture=new Texture2D(2,2);try{
                using(var input=new ViewerBoardInput(root,surface,host,panel)){
                    input.Refresh();var view=surface.CardsRoot.Q<CardView>();var identity=VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate("public-oracle","public-printing","front",true,true),System.Array.Empty<VisualPrintingCandidate>());
                    view.Bind(identity,texture,CardCompactProfile.StandardArtCrop);yield return null;
                    using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=view.worldBound.center})){down.target=view;view.SendEvent(down);}
                    using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=new Vector2(400,300)})){move.target=view;view.SendEvent(move);}
                    Assert.That(root.Q<Image>("board-drag-art").image,Is.SameAs(texture));owner.TrySetResult(true);input.Refresh();
                    Assert.That(root.Q<Image>("board-drag-art").image,Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);
                }
            }finally{UnityEngine.Object.Destroy(texture);}
        }
        [UnityTest] public IEnumerator SpatialFallbackCollapsesCardButtonsButRetainsExactCommands()
        {
            var host=Start(BoardSnapshot(),out var peer,out var owner);var panel=Panel(host);panel.SetSpatialPresentation(true);yield return Show(host,panel);
            var fallback=panel.Root.Q<Foldout>("board-choice-alternatives");Assert.That(fallback,Is.Not.Null);Assert.That(fallback.value,Is.False);Assert.That(fallback.Q<Button>("decision-action-0"),Is.Not.Null);
            Assert.That(peer.PendingCommandBytes,Is.Zero);fallback.value=true;Click(fallback.Q<Button>("decision-action-0"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
            Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("fixture-action"));
        }
        [UnityTest] public IEnumerator SpatialPrimaryActionRemainsVisibleBeyondTheCardChoicePage()
        {
            var frame=BoardSnapshot();var actions=(JArray)frame["body"]["snapshot"]["actions"];var template=actions[0].DeepClone();actions.Clear();
            for(int i=0;i<17;i++){var action=template.DeepClone();action["action_id"]="card-action-"+i;actions.Add(action);}
            var pass=template.DeepClone();pass["action_id"]="exact-pass";pass["object_id"]=null;pass["kind"]="pass";pass["label"]="Pass priority";actions.Add(pass);
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);panel.SetSpatialPresentation(true);yield return Show(host,panel);
            var button=panel.Root.Q<Button>("decision-action-17");Assert.That(button,Is.Not.Null);Assert.That(button.parent,Is.SameAs(panel.Root.Q<VisualElement>("decision-controls")));
            Click(button);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["action_id"],Is.EqualTo("exact-pass"));
        }
        private JObject ManaSnapshot()
        {var frame=Snapshot(selection:true);var decision=frame["body"]["snapshot"]["decision"];decision["family"]="mana";decision["options"]=new JArray();decision["can_finish"]=false;decision["cancellable"]=false;return frame;}
        private static void SubmitCard(CardView card)
        {Assert.That(card,Is.Not.Null);using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=card;card.SendEvent(submit);}}
        private static void ClickCard(CardView card,int button=0)
        {Assert.That(card,Is.Not.Null);using(var click=ClickEvent.GetPooled(new Event{type=EventType.MouseUp,button=button,clickCount=1})){Assert.That(click.button,Is.EqualTo(button));click.target=card;card.SendEvent(click);}}
        private JObject VisibleManaSnapshot()
        {
            var frame=ManaSnapshot();var sample=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0];frame["body"]["snapshot"]["objects"]=new JArray(sample.DeepClone());return frame;
        }
        [UnityTest] public IEnumerator ManaPanelCardClickUsesBoundSourceAndDoesNotOverrideEmbeddedControls()
        {
            var host=Start(VisibleManaSnapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var card=surface.CardsRoot.Q<CardView>();Assert.That(card.focusable,Is.True);var embedded=new Button(){text="Inspect only"};card.Add(embedded);using(var click=ClickEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,clickCount=1})){click.target=embedded;embedded.SendEvent(click);}Assert.That(peer.PendingCommandBytes,Is.Zero);embedded.RemoveFromHierarchy();ClickCard(card,1);Assert.That(peer.PendingCommandBytes,Is.Zero);
            surface.InspectionView.style.display=DisplayStyle.None;panel.Root.style.width=720;var target=new RenderTexture(1280,720,24);Texture2D pixels=null;var previous=RenderTexture.active;
            try{target.Create();settings.targetTexture=target;for(int i=0;i<5;i++){host.Tick();panel.Tick();yield return null;}pixels=new Texture2D(1280,720,TextureFormat.RGBA32,false);RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1280,720),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(Application.dataPath,"../Artifacts/DecisionManaProof.png"),pixels.EncodeToPNG());}
            finally{settings.targetTexture=null;RenderTexture.active=previous;if(pixels!=null)UnityEngine.Object.Destroy(pixels);target.Release();UnityEngine.Object.Destroy(target);}
            ClickCard(card);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("select_mana_source"));Assert.That((string)read.Result["body"]["object_id"],Is.EqualTo("fixture-0002"));Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator ManaPanelDoesNotInferEligibilityOrExposeConcealedIdentity()
        {
            foreach(string kind in new[]{"hidden","tapped","other-controller"}) {
                var frame=kind=="hidden"?ManaSnapshot():VisibleManaSnapshot();var obj=frame["body"]["snapshot"]["objects"][0];if(kind=="tapped")obj["tapped"]=true;if(kind=="other-controller")obj["controller_id"]="two";
                var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var card=surface.CardsRoot.Q<CardView>();if(kind=="hidden"){Assert.That(card.Q<Label>("name").text,Is.Empty);Assert.That(card.Artwork,Is.Null);}SubmitCard(card);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["object_id"],Is.EqualTo((string)obj["object_id"]));Assert.That(read.Result["body"]["card_identity"],Is.Null);host.Cancel();yield return Until(()=>host.Completion.IsCompleted);panel.Tick();
            }
        }
        [UnityTest] public IEnumerator ManaPanelRetainedCardCannotSubmitAfterSnapshotChangeOrOwnerLoss()
        {
            var host=Start(VisibleManaSnapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var retained=surface.CardsRoot.Q<CardView>();var old=host.CurrentDecision;var next=VisibleManaSnapshot();next["message_id"]="new-card-input";next["body"]["snapshot"]["revision"]=8;next["body"]["snapshot"]["objects"][0]["object_id"]="replacement-source";var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));SubmitCard(retained);Assert.That(peer.PendingCommandBytes,Is.Zero);yield return Show(host,panel);Assert.That(retained.focusable,Is.False);SubmitCard(retained);Assert.That(peer.PendingCommandBytes,Is.Zero);
            var current=surface.CardsRoot.Q<CardView>();owner.TrySetResult(true);panel.Tick();Assert.That(current.focusable,Is.False);SubmitCard(current);Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(panel.Root.Q<Label>("decision-status").text,Is.Empty);
        }
        [UnityTest] public IEnumerator ManaPanelOnlyBindsManaDecisionsAndBlocksPendingInputUntilExplicitRetry()
        {
            var host=Start(Snapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var card=surface.CardsRoot.Q<CardView>();Assert.That(card.focusable,Is.False);SubmitCard(card);Assert.That(peer.PendingCommandBytes,Is.Zero);var old=host.CurrentDecision;var next=VisibleManaSnapshot();next["message_id"]="mana-input-enabled";next["body"]["snapshot"]["revision"]=8;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));yield return Show(host,panel);card=surface.CardsRoot.Q<CardView>();SubmitCard(card);var first=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>first.IsCompleted);Assert.That(card.focusable,Is.False);SubmitCard(card);ClickCard(card);Assert.That(peer.PendingCommandBytes,Is.Zero);
            var rejected=Ack(first.Result,"rejected");rejected["body"]["request_revision"]=8;rejected["body"]["code"]="ENGINE_REJECTED";send=Task.Run(()=>peer.ReplyForFixture(rejected));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();var receipt=Receipt(host);yield return Until(()=>receipt.IsCompleted);Assert.That(receipt.Result.State,Is.EqualTo(CommandState.Rejected));panel.Tick();Assert.That(card.focusable,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero);SubmitCard(card);var second=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>second.IsCompleted);Assert.That((string)second.Result["message_id"],Is.Not.EqualTo((string)first.Result["message_id"]));panel.Dispose();Assert.That(card.focusable,Is.False);SubmitCard(card);Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator EmptyManaObjectSetDoesNotCreateSourceOrAutomaticCommand()
        {
            var frame=ManaSnapshot();frame["body"]["snapshot"]["objects"]=new JArray();var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Assert.That(surface.CardsRoot.Query<CardView>().ToList(),Is.Empty);Assert.That(panel.Root.Q<Label>("decision-status").text,Is.EqualTo("No cards are available for mana-source selection."));Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator ManaSourceReferenceWritesExactOpaqueTokenAndPreservesUncertainty()
        {
            var frame=ManaSnapshot();var host=Start(frame,out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var reference=offer.Frame.ManaSourceReferences[0];var sent=host.SelectManaSourceAsync(offer,reference);yield return Until(()=>sent.IsCompleted);Assert.That(sent.Result.State,Is.EqualTo(CommandState.AwaitingAck));
            var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("select_mana_source"));Assert.That((string)read.Result["body"]["object_id"],Is.EqualTo(reference.ObjectId));Assert.That((string)read.Result["body"]["decision_id"],Is.EqualTo(reference.DecisionId));Assert.That(read.Result["body"]["card_identity"],Is.Null);
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.Pending.State,Is.EqualTo(CommandState.Uncertain));
        }
        [UnityTest] public IEnumerator ForeignAndNullManaReferencesNeverWriteAndCurrentReferenceRemainsUsable()
        {
            var frame=ManaSnapshot();var foreign=ViewerDecisionProjection.ParseSnapshot(frame.ToString(),"fixture-session","one",0,true);var host=Start(frame,out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;
            foreach(var reference in new[]{foreign.ManaSourceReferences[0],null}){var denied=host.SelectManaSourceAsync(offer,reference);yield return Until(()=>denied.IsCompleted);Assert.That(Error(denied),Is.EqualTo("STALE_OR_INVALID_OBJECT"));Assert.That(offer.CanSubmit,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero);}
            var sent=host.SelectManaSourceAsync(offer,offer.Frame.ManaSourceReferences[0]);yield return Until(()=>sent.IsCompleted);Assert.That(sent.Result.State,Is.EqualTo(CommandState.AwaitingAck));
        }
        [UnityTest] public IEnumerator ReplacedManaIncarnationsAndOffersNeverWrite()
        {
            var host=Start(ManaSnapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var old=host.CurrentDecision;var reference=old.Frame.ManaSourceReferences[0];var next=ManaSnapshot();next["message_id"]="next-mana";next["body"]["snapshot"]["revision"]=8;next["body"]["snapshot"]["objects"][0]["object_id"]="new-incarnation";
            var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(old,host.CurrentDecision));
            var stale=host.SelectManaSourceAsync(old,reference);yield return Until(()=>stale.IsCompleted);Assert.That(Error(stale),Is.EqualTo("STALE_DECISION"));var rebound=host.SelectManaSourceAsync(host.CurrentDecision,reference);yield return Until(()=>rebound.IsCompleted);Assert.That(Error(rebound),Is.EqualTo("STALE_OR_INVALID_OBJECT"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            var valid=host.SelectManaSourceAsync(host.CurrentDecision,host.CurrentDecision.Frame.ManaSourceReferences[0]);yield return Until(()=>valid.IsCompleted);Assert.That(valid.Result.State,Is.EqualTo(CommandState.AwaitingAck));
        }
        [UnityTest] public IEnumerator NonManaDecisionsCannotBorrowSourceReferences()
        {
            var frame=ManaSnapshot();var references=ViewerDecisionProjection.ParseSnapshot(frame.ToString(),"fixture-session","one",0,true).ManaSourceReferences;var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);Assert.That(host.CurrentDecision.Frame.ManaSourceReferences,Is.Empty);
            var denied=host.SelectManaSourceAsync(host.CurrentDecision,references[0]);yield return Until(()=>denied.IsCompleted);Assert.That(Error(denied),Is.EqualTo("STALE_OR_INVALID_OBJECT"));Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        private JObject NumericSnapshot(string family,long minimum,long maximum,params long[] ranges)
        {
            var frame=Snapshot(selection:true);var decision=frame["body"]["snapshot"]["decision"];decision["family"]=family;decision["minimum"]=minimum;decision["maximum"]=maximum;decision["options"]=new JArray();decision["can_finish"]=false;decision["cancellable"]=false;
            var amounts=new JArray();for(int i=0;i<ranges.Length;i+=2)amounts.Add(new JObject{["label"]="Engine constraint",["minimum"]=ranges[i],["maximum"]=ranges[i+1],["default"]=JValue.CreateNull()});decision["amounts"]=amounts;return frame;
        }
        [UnityTest] public IEnumerator AmountRecipientTilesStayReadableAndReorderingPreservesExactRecipientAmounts()
        {
            var wire=NumericSnapshot("amounts",5,5,0,5,0,5,0,5);var amounts=wire["body"]["snapshot"]["decision"]["amounts"];amounts[0]["label"]="Soldier Token, P/T: 2/2";amounts[1]["label"]="Krenko, Tin Street Kingpin, P/T: 3/3";amounts[2]["label"]="Defending player";
            var host=Start(wire,out var peer,out var owner);var panel=Panel(host);GameplayTheme.Attach(panel.Root);panel.Root.style.width=760;yield return Show(host,panel);yield return null;
            var first=panel.Root.Q<TextField>("decision-number-0");Assert.That(first.value,Is.Empty);Assert.That(first.resolvedStyle.width,Is.GreaterThanOrEqualTo(80));Assert.That(first.resolvedStyle.height,Is.GreaterThanOrEqualTo(38));
            Assert.That(panel.Root.Q<Label>("decision-amount-name-1").text,Is.EqualTo("Krenko, Tin Street Kingpin, P/T: 3/3"));Assert.That(panel.Root.Q<Label>("decision-amount-name-1").resolvedStyle.whiteSpace,Is.EqualTo(WhiteSpace.Normal));
            Click(panel.Root.Q<Button>("decision-amount-plus-0"));Click(panel.Root.Q<Button>("decision-amount-plus-0"));panel.Root.Q<TextField>("decision-number-1").value="3";panel.Root.Q<TextField>("decision-number-2").value="0";yield return null;
            var recipients=panel.Root.Q("decision-amount-recipients");var handle=panel.Root.Q("decision-amount-handle-0");var destination=panel.Root.Q("decision-amount-recipient-2").worldBound.center;
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=handle.worldBound.center})){down.target=handle;handle.SendEvent(down);}
            using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=destination})){move.target=handle;handle.SendEvent(move);}
            using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=destination})){up.target=handle;handle.SendEvent(up);}yield return null;
            Assert.That(recipients[2].userData,Is.EqualTo(0));Assert.That(first.value,Is.EqualTo("2"));Assert.That(peer.PendingCommandBytes,Is.Zero,"Rearranging tiles is not a game command");
            Assert.That(panel.Root.Q<Label>("decision-assigned-total").text,Is.EqualTo("Assigned: 5 / 5"));Click(panel.Root.Q<Button>("decision-number-submit"));
            var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);CollectionAssert.AreEqual(new long[]{2,3,0},read.Result["body"]["values"].Select(value=>(long)value));
        }
        [UnityTest] public IEnumerator DamageArtworkUsesExactRecipientsRefreshesLateArtAndClearsOnRevision()
        {
            var wire=NumericSnapshot("amounts",5,5,0,5,0,5,0,5);var amounts=wire["body"]["snapshot"]["decision"]["amounts"];
            amounts[0]["label"]="Same creature";amounts[0]["object_id"]="recipient-one";
            amounts[1]["label"]="Same creature";amounts[1]["object_id"]="recipient-two";
            amounts[2]["label"]="Defending player";
            var host=Start(wire,out var peer,out var owner);var panel=Panel(host);
            var firstTexture=new Texture2D(2,2);var secondTexture=new Texture2D(2,2);int state=0;
            var previews=new List<CardView>();
            panel.SetChoiceArtworkState(()=>state);
            panel.SetChoicePreview(id=>{var view=new CardView();if(state==0)view.BindUnavailable();else view.Bind(VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate("oracle",id,"front",true,true),Array.Empty<VisualPrintingCandidate>()),id=="recipient-one"?firstTexture:secondTexture,new Rect(0,0,1,1));previews.Add(view);return view;});
            try{
                yield return Show(host,panel);yield return null;
                Assert.That(panel.Root.Q("decision-amount-artwork-0").Q<CardView>().Artwork,Is.Null);
                Assert.That(panel.Root.Q("decision-amount-artwork-1").Q<CardView>().Artwork,Is.Null);
                Assert.That(panel.Root.Q("decision-amount-artwork-2"),Is.Null,"A player row cannot borrow a card image");
                panel.Root.Q<TextField>("decision-number-0").value="2";panel.Root.Q<TextField>("decision-number-1").value="3";panel.Root.Q<TextField>("decision-number-2").value="0";
                var handle=panel.Root.Q("decision-amount-handle-0");using(var key=KeyDownEvent.GetPooled('\0',KeyCode.RightArrow,EventModifiers.None)){key.target=handle;handle.SendEvent(key);}
                state=1;panel.Tick();yield return null;
                Assert.That(panel.Root.Q("decision-amount-artwork-0").Q<CardView>().Artwork,Is.SameAs(firstTexture));
                Assert.That(panel.Root.Q("decision-amount-artwork-1").Q<CardView>().Artwork,Is.SameAs(secondTexture));
                Assert.That(panel.Root.Q<TextField>("decision-number-0").value,Is.EqualTo("2"));Assert.That(panel.Root.Q("decision-amount-recipients")[1].userData,Is.EqualTo(0));
                Assert.That(previews.Take(2).All(view=>view.parent==null && view.Artwork==null),Is.True,"Late artwork must retire the old borrowed previews");
                panel.InvalidateAmountArtwork();Assert.That(panel.Root.Q("decision-amount-artwork-0").Q<CardView>(),Is.Null);
                panel.Tick();Click(panel.Root.Q<Button>("decision-number-submit"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);
                CollectionAssert.AreEqual(new long[]{2,3,0},read.Result["body"]["values"].Select(value=>(long)value));
                var next=NumericSnapshot("number",0,10);next["message_id"]="damage-artwork-retired";next["body"]["snapshot"]["revision"]=8;
                var sent=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>sent.IsCompleted);yield return Until(()=>{host.Tick();panel.Tick();return host.PresentedDecision?.Frame.Context.Revision==8;});
                Assert.That(panel.Root.Q("decision-amount-artwork-0"),Is.Null);Assert.That(previews.All(view=>view.parent==null && view.Artwork==null),Is.True);
            }finally{UnityEngine.Object.Destroy(firstTexture);UnityEngine.Object.Destroy(secondTexture);}
        }
        [UnityTest] public IEnumerator NumericPanelRequiresExplicitWholeNumberAndPreservesZeroAndSignedLimits()
        {
            foreach(string input in new[]{"0",long.MinValue.ToString(System.Globalization.CultureInfo.InvariantCulture),long.MaxValue.ToString(System.Globalization.CultureInfo.InvariantCulture)}) {
                var host=Start(NumericSnapshot("number",long.MinValue,long.MaxValue),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var field=panel.Root.Q<TextField>("decision-number-0");var submit=panel.Root.Q<Button>("decision-number-submit");Assert.That(field.value,Is.Empty);Assert.That(submit.enabledSelf,Is.False);Assert.That(peer.PendingCommandBytes,Is.Zero);
                foreach(string invalid in new[]{"","1.5","1,000","9223372036854775808"," 1"}){field.value=invalid;panel.Tick();Assert.That(submit.enabledSelf,Is.False);Click(submit);Assert.That(peer.PendingCommandBytes,Is.Zero);}
                field.value=input;panel.Tick();Assert.That(submit.enabledSelf,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero);Click(submit);var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("choose_number"));Assert.That((long)read.Result["body"]["value"],Is.EqualTo(long.Parse(input,System.Globalization.CultureInfo.InvariantCulture)));host.Cancel();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator AmountPanelIgnoresDefaultsAndPreservesExplicitValuesAcrossPages()
        {
            var ranges=Enumerable.Range(0,ViewerDecisionPanel.PageSize+1).SelectMany(_=>new long[]{0,5}).ToArray();var frame=NumericSnapshot("amounts",5,5,ranges);foreach(var amount in frame["body"]["snapshot"]["decision"]["amounts"])amount["default"]=5;
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);for(int i=0;i<ViewerDecisionPanel.PageSize;i++){var field=panel.Root.Q<TextField>("decision-number-"+i);Assert.That(field.value,Is.Empty);field.value="0";}
            Assert.That(panel.Root.Q<Button>("decision-number-submit").enabledSelf,Is.False);Assert.That(panel.Root.Q<Button>("decision-numeric-next"),Is.Null);Assert.That(panel.Root.Q<TextField>("decision-number-16").value,Is.Empty);panel.Root.Q<TextField>("decision-number-16").value="5";Assert.That(panel.Root.Q<Button>("decision-numeric-previous"),Is.Null);Assert.That(panel.Root.Q<TextField>("decision-number-0").value,Is.EqualTo("0"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            Assert.That(panel.Root.Q<Button>("decision-number-submit").enabledSelf,Is.True);Click(panel.Root.Q<Button>("decision-number-submit"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);CollectionAssert.AreEqual(Enumerable.Repeat(0L,16).Concat(new[]{5L}),read.Result["body"]["values"].Select(value=>(long)value));
        }
        [UnityTest] public IEnumerator AmountPanelKeepsInvalidRangeInputEditableUntilExplicitCorrection()
        {
            var frame=NumericSnapshot("amounts",5,5,0,5,0,5);frame["body"]["snapshot"]["decision"]["prompt"]="Distribute five between these public fixture amounts";var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            panel.Root.Q<TextField>("decision-number-0").value="1";panel.Root.Q<TextField>("decision-number-1").value="1";Click(panel.Root.Q<Button>("decision-number-submit"));yield return Until(()=>{panel.Tick();return panel.Root.Q<Label>("decision-status").text=="Enter values within the displayed limits.";});Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(panel.Root.Q<TextField>("decision-number-0").value,Is.EqualTo("1"));Assert.That(panel.Root.Q<VisualElement>("decision-controls").enabledSelf,Is.True);
            panel.Root.Q<TextField>("decision-number-0").value="2";panel.Root.Q<TextField>("decision-number-1").value="3";
            surface.CardsRoot.style.display=DisplayStyle.None;surface.InspectionView.style.display=DisplayStyle.None;panel.Root.style.width=700;var target=new RenderTexture(1280,720,24);Texture2D pixels=null;var previous=RenderTexture.active;
            try{target.Create();settings.targetTexture=target;for(int i=0;i<5;i++){host.Tick();panel.Tick();yield return null;}pixels=new Texture2D(1280,720,TextureFormat.RGBA32,false);RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1280,720),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(Application.dataPath,"../Artifacts/DecisionNumbersProof.png"),pixels.EncodeToPNG());}
            finally{settings.targetTexture=null;RenderTexture.active=previous;if(pixels!=null)UnityEngine.Object.Destroy(pixels);target.Release();UnityEngine.Object.Destroy(target);}
            Click(panel.Root.Q<Button>("decision-number-submit"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);CollectionAssert.AreEqual(new long[]{2,3},read.Result["body"]["values"].Select(value=>(long)value));
        }
        [UnityTest] public IEnumerator NumericPanelDropsOldInputAndCallbacksWhenSnapshotChanges()
        {
            var host=Start(NumericSnapshot("number",0,10),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var field=panel.Root.Q<TextField>("decision-number-0");field.value="7";var cached=panel.Root.Q<Button>("decision-number-submit");var old=host.CurrentDecision;var next=NumericSnapshot("number",0,10);next["message_id"]="next-numeric-panel";next["body"]["snapshot"]["revision"]=8;
            var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(old,host.CurrentDecision));Click(cached);Assert.That(peer.PendingCommandBytes,Is.Zero);yield return Show(host,panel);Assert.That(panel.Root.Q<TextField>("decision-number-0").value,Is.Empty);field.value="8";Assert.That(panel.Root.Q<TextField>("decision-number-0").value,Is.Empty);Assert.That(panel.Root.Q<Button>("decision-number-submit").enabledSelf,Is.False);owner.TrySetResult(true);panel.Tick();Assert.That(panel.Root.Query<TextField>().ToList(),Is.Empty);
        }
        [UnityTest] public IEnumerator NumericPanelDoesNotGuessMissingLimitsOrRenderBeyondWireCapacity()
        {
            foreach(bool excessive in new[]{false,true}) {
                var frame=excessive?NumericSnapshot("amounts",0,0,new long[(WireMessages.MaxAmountValues+1)*2]):NumericSnapshot("number",0,5);if(!excessive)frame["body"]["snapshot"]["decision"]["minimum"]=JValue.CreateNull();var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Assert.That(panel.Root.Q<TextField>(),Is.Null);Assert.That(panel.Root.Q<Button>("decision-number-submit"),Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);host.Cancel();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator NumberCommandsPreserveSignedExtremesWithoutDefaults()
        {
            foreach(long value in new[]{long.MinValue,0L,long.MaxValue}) {
                var host=Start(NumericSnapshot("number",long.MinValue,long.MaxValue),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var sent=host.ChooseNumberAsync(host.CurrentDecision,value);yield return Until(()=>sent.IsCompleted);Assert.That(sent.Result.State,Is.EqualTo(CommandState.AwaitingAck));
                var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("choose_number"));Assert.That((long)read.Result["body"]["value"],Is.EqualTo(value));host.Cancel();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator OrderedAmountsCopyCallerInputBeforeWorkerDispatch()
        {
            var host=Start(NumericSnapshot("amounts",5,5,0,5,0,5),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var values=new long[]{2,3};var sent=host.ChooseAmountsAsync(host.CurrentDecision,values);values[0]=999;yield return Until(()=>sent.IsCompleted);Assert.That(sent.Result.State,Is.EqualTo(CommandState.AwaitingAck));
            var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo("choose_amounts"));CollectionAssert.AreEqual(new long[]{2,3},read.Result["body"]["values"].Select(value=>(long)value));
        }
        [UnityTest] public IEnumerator InvalidNumericValuesDoNotWriteOrConsumeTheOffer()
        {
            var host=Start(NumericSnapshot("amounts",5,5,0,5,0,5),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;
            foreach(var values in new[]{new long[]{1},new long[]{1,1},new long[]{6,-1},new long[WireMessages.MaxAmountValues+1],null}) {
                var sent=host.ChooseAmountsAsync(offer,values);yield return Until(()=>sent.IsCompleted);Assert.That(Error(sent),Is.EqualTo("AMOUNT_OUT_OF_RANGE"));Assert.That(offer.CanSubmit,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero);
            }
            var wrong=host.ChooseNumberAsync(offer,5);yield return Until(()=>wrong.IsCompleted);Assert.That(Error(wrong),Is.EqualTo("DECISION_FAMILY_MISMATCH"));Assert.That(offer.CanSubmit,Is.True);
            var valid=host.ChooseAmountsAsync(offer,new long[]{0,5});yield return Until(()=>valid.IsCompleted);Assert.That(valid.Result.State,Is.EqualTo(CommandState.AwaitingAck));
        }
        [UnityTest] public IEnumerator NumericOverflowAndStaleOffersNeverBecomeCommands()
        {
            var host=Start(NumericSnapshot("amounts",0,long.MaxValue,0,long.MaxValue,0,long.MaxValue),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var old=host.CurrentDecision;
            var overflow=host.ChooseAmountsAsync(old,new[]{long.MaxValue,long.MaxValue});yield return Until(()=>overflow.IsCompleted);Assert.That(Error(overflow),Is.EqualTo("AMOUNT_OUT_OF_RANGE"));Assert.That(peer.PendingCommandBytes,Is.Zero);
            var next=NumericSnapshot("number",0,10);next["message_id"]="new-number";next["body"]["snapshot"]["revision"]=8;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));
            var stale=host.ChooseAmountsAsync(old,new long[]{0,0});yield return Until(()=>stale.IsCompleted);Assert.That(Error(stale),Is.EqualTo("STALE_DECISION"));var range=host.ChooseNumberAsync(host.CurrentDecision,11);yield return Until(()=>range.IsCompleted);Assert.That(Error(range),Is.EqualTo("AMOUNT_OUT_OF_RANGE"));Assert.That(peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator ReparentedPromptClearsWithViewerAndIsRemovedOnDispose()
        {
            var host=Start(Snapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);
            var prompt=panel.Root.Q<Label>("decision-prompt");Assert.That(prompt.text,Is.Not.Empty);
            var header=new VisualElement();panel.Root.parent.Add(header);header.Add(prompt);
            Assert.That(header[0],Is.SameAs(prompt));Assert.That(peer.PendingCommandBytes,Is.Zero);
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);host.Tick();panel.Tick();
            Assert.That(prompt.text,Is.Empty);panel.Dispose();Assert.That(prompt.parent,Is.Null);Assert.That(header.childCount,Is.Zero);
        }
        [UnityTest] public IEnumerator ConcurrentClicksAdmitExactlyOneCommand()
        {
            var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var action=offer.Frame.Actions[0];var attempts=new Task<TrackedCommand>[16];var launch=Task.Run(()=>Parallel.For(0,attempts.Length,i=>attempts[i]=host.PerformAsync(offer,action)));yield return Until(()=>launch.IsCompleted);launch.GetAwaiter().GetResult();yield return Until(()=>attempts.All(task=>task.IsCompleted));
            Assert.That(attempts.Count(task=>task.Status==TaskStatus.RanToCompletion),Is.EqualTo(1));foreach(var task in attempts.Where(task=>task.IsFaulted))Assert.That(Error(task),Is.EqualTo("COMMAND_PENDING"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);read.GetAwaiter().GetResult();Assert.That(peer.PendingCommandBytes,Is.Zero);
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);
        }
    }
}

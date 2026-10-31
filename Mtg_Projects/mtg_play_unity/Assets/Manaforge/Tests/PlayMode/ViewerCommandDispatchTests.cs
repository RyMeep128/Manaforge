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
        [UnityTest] public IEnumerator DecisionPanelWaitsForPresentedSnapshotAndClearsOnOwnerLoss()
        {
            var host=Start(Snapshot(selection:true),out var peer,out var owner);var panel=Panel(host);yield return Until(()=>host.CurrentDecision!=null);panel.Tick();Assert.That(panel.Root.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(panel.Root.Q<Label>("decision-prompt").text,Is.Empty);
            yield return Show(host,panel);var cached=panel.Root.Q<Button>("decision-option-0");Assert.That(cached,Is.Not.Null);owner.TrySetResult(true);panel.Tick();Assert.That(panel.Root.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(panel.Root.Q<Label>("decision-prompt").text,Is.Empty);Click(cached);Assert.That(peer.PendingCommandBytes,Is.Zero);
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
                string button=operation=="perform"?"decision-action-0":operation=="cancel"?"decision-cancel":"decision-finish";Click(panel.Root.Q<Button>(button));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["operation"],Is.EqualTo(operation));host.Cancel();yield return Until(()=>host.Completion.IsCompleted);panel.Tick();Assert.That(panel.Root.style.display.value,Is.EqualTo(DisplayStyle.None));
            }
        }
        [UnityTest] public IEnumerator DecisionPanelPagesEveryEngineOptionWithoutAutomaticallyChoosing()
        {
            var frame=Snapshot(selection:true);var options=(JArray)frame["body"]["snapshot"]["decision"]["options"];options.Clear();for(int i=0;i<ViewerDecisionPanel.PageSize+1;i++)options.Add(new JObject{["option_id"]="option-"+i,["label"]="Public option "+i,["object_id"]=JValue.CreateNull(),["player_id"]=JValue.CreateNull(),["selected"]=false});
            var host=Start(frame,out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);Assert.That(panel.Root.Q<Button>("decision-option-16"),Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);Click(panel.Root.Q<Button>("decision-next"));Assert.That(panel.Root.Q<Button>("decision-option-16"),Is.Not.Null);Assert.That(panel.Root.Q<Button>("decision-option-0"),Is.Null);Assert.That(peer.PendingCommandBytes,Is.Zero);
            Click(panel.Root.Q<Button>("decision-option-16"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);Assert.That((string)read.Result["body"]["option_id"],Is.EqualTo("option-16"));
        }
        [UnityTest] public IEnumerator RetainedButtonsCannotSubmitAfterNewSnapshotOrViewerReplacement()
        {
            var host=Start(Snapshot(),out var peer,out var owner);var panel=Panel(host);yield return Show(host,panel);var button=panel.Root.Q<Button>("decision-action-0");var old=host.CurrentDecision;var next=Snapshot("new-panel");next["body"]["snapshot"]["revision"]=8;var send=Task.Run(()=>peer.ReplyForFixture(next));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();yield return Until(()=>host.CurrentDecision!=null && !ReferenceEquals(host.CurrentDecision,old));Click(button);Assert.That(peer.PendingCommandBytes,Is.Zero);panel.Tick();Assert.That(panel.Root.style.display.value,Is.EqualTo(DisplayStyle.None));
            yield return Show(host,panel);var cached=panel.Root.Q<Button>("decision-action-0");var replacement=Start(next,out var nextPeer,out var nextOwner);panel.Tick();Assert.That(panel.Root.style.display.value,Is.EqualTo(DisplayStyle.None));Click(cached);Assert.That(peer.PendingCommandBytes,Is.Zero);Assert.That(nextPeer.PendingCommandBytes,Is.Zero);yield return Until(()=>replacement.CurrentDecision!=null);
        }
        private JObject ManaSnapshot()
        {var frame=Snapshot(selection:true);var decision=frame["body"]["snapshot"]["decision"];decision["family"]="mana";decision["options"]=new JArray();decision["can_finish"]=false;decision["cancellable"]=false;return frame;}
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
            Assert.That(panel.Root.Q<Button>("decision-number-submit").enabledSelf,Is.False);Click(panel.Root.Q<Button>("decision-numeric-next"));Assert.That(panel.Root.Q<TextField>("decision-number-16").value,Is.Empty);panel.Root.Q<TextField>("decision-number-16").value="5";Click(panel.Root.Q<Button>("decision-numeric-previous"));Assert.That(panel.Root.Q<TextField>("decision-number-0").value,Is.EqualTo("0"));Assert.That(peer.PendingCommandBytes,Is.Zero);
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
        [UnityTest] public IEnumerator ConcurrentClicksAdmitExactlyOneCommand()
        {
            var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var action=offer.Frame.Actions[0];var attempts=new Task<TrackedCommand>[16];var launch=Task.Run(()=>Parallel.For(0,attempts.Length,i=>attempts[i]=host.PerformAsync(offer,action)));yield return Until(()=>launch.IsCompleted);launch.GetAwaiter().GetResult();yield return Until(()=>attempts.All(task=>task.IsCompleted));
            Assert.That(attempts.Count(task=>task.Status==TaskStatus.RanToCompletion),Is.EqualTo(1));foreach(var task in attempts.Where(task=>task.IsFaulted))Assert.That(Error(task),Is.EqualTo("COMMAND_PENDING"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);read.GetAwaiter().GetResult();Assert.That(peer.PendingCommandBytes,Is.Zero);
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);
        }
    }
}

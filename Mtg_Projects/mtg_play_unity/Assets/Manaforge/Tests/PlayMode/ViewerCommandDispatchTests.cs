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
        {foreach(var host in hosts)host.Dispose();yield return Until(()=>hosts.TrueForAll(host=>host.Completion.IsCompleted));hosts.Clear();foreach(var peer in peers)peer.Dispose();peers.Clear();surface.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);yield return null;}
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
        [UnityTest] public IEnumerator ConcurrentClicksAdmitExactlyOneCommand()
        {
            var host=Start(Snapshot(),out var peer,out var owner);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;var action=offer.Frame.Actions[0];var attempts=new Task<TrackedCommand>[16];var launch=Task.Run(()=>Parallel.For(0,attempts.Length,i=>attempts[i]=host.PerformAsync(offer,action)));yield return Until(()=>launch.IsCompleted);launch.GetAwaiter().GetResult();yield return Until(()=>attempts.All(task=>task.IsCompleted));
            Assert.That(attempts.Count(task=>task.Status==TaskStatus.RanToCompletion),Is.EqualTo(1));foreach(var task in attempts.Where(task=>task.IsFaulted))Assert.That(Error(task),Is.EqualTo("COMMAND_PENDING"));var read=Task.Run(()=>WireMessages.Parse(peer.ReadCommandForFixture()));yield return Until(()=>read.IsCompleted);read.GetAwaiter().GetResult();Assert.That(peer.PendingCommandBytes,Is.Zero);
            host.Cancel();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Session.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);
        }
    }
}

using System;
using System.Collections;
using System.IO;
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
    public sealed class ViewerDecisionBindingTests
    {
        private GameObject node;private PanelSettings settings;private ViewerCardSurface surface;private JObject source,corpus;
        private JObject Snapshot(string id="s1",long revision=7){var value=(JObject)source.DeepClone();value["message_id"]=id;value["body"]["snapshot"]["revision"]=revision;return value;}
        private static JObject Message(string type,string id,JObject body)=>new JObject{["wire_version"]=1,["message_type"]=type,["message_id"]=id,["body"]=body};
        private static IEnumerator Until(Func<bool> done){double end=Time.realtimeSinceStartupAsDouble+10;while(!done() && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(done(),Is.True,"Decision binding timed out");}
        private static IEnumerator Read(ViewerSessionReceiver receiver){var task=Task.Run(()=>receiver.ReceiveOnce(2000));yield return Until(()=>task.IsCompleted);task.GetAwaiter().GetResult();}
        [UnitySetUp] public IEnumerator Setup()
        {
            string root=Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures");source=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(root,"receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"];corpus=JObject.Parse(File.ReadAllText(Path.Combine(root,"wire-receive-v1.json")));
            node=new GameObject("Decision binding tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;surface=new ViewerCardSurface(doc.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator PendingReceiptsKeepThePromptButNeverEnableAnotherSubmission()
        {
            using var pair=new ViewerSessionReceiverTests.Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Snapshot());yield return Read(receiver);var offer=receiver.Decisions.Current;Assert.That(offer,Is.Not.Null);Assert.That(offer.CanSubmit,Is.True);
            var command=Message("command","c1",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=7,["operation"]="perform",["decision_id"]="fixture-decision",["action_id"]="fixture-action"});
            var send=Task.Run(()=>pair.Channel.Submit(command.ToString()));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();TextFrame.Read(pair.Peer.GetStream());Assert.That(offer.Frame,Is.Not.Null);Assert.That(offer.CanSubmit,Is.False);
            foreach(string outcome in new[]{"submitted","confirmed"}){pair.Send(Message("ack","ack-"+outcome,new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["command_id"]="c1",["request_revision"]=7,["outcome"]=outcome,["code"]=JValue.CreateNull()}));yield return Read(receiver);Assert.That(receiver.Decisions.Current,Is.SameAs(offer));Assert.That(offer.CanSubmit,Is.EqualTo(outcome=="confirmed"));}
            receiver.Cancel();Assert.That(offer.Frame,Is.Null);Assert.That(offer.CanSubmit,Is.False);
        }
        [UnityTest] public IEnumerator AnotherSnapshotRetiresOldOfferEvenWhenAllEngineTokensAreIdentical()
        {
            using var pair=new ViewerSessionReceiverTests.Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Snapshot());yield return Read(receiver);var first=receiver.Decisions.Current;
            var next=Snapshot("s2");next["body"]["snapshot"]["decision"]["prompt"]="Updated prompt";pair.Send(next);yield return Read(receiver);var current=receiver.Decisions.Current;
            Assert.That(current,Is.Not.SameAs(first));Assert.That(first.Frame,Is.Null);Assert.That(first.CanSubmit,Is.False);Assert.That(receiver.Decisions.IsCurrent(first),Is.False);Assert.That(current.Frame.Decision.Prompt,Is.EqualTo("Updated prompt"));
        }
        [UnityTest] public IEnumerator NewerEventRevokesOfferButSameRevisionEventPreservesItsBinding()
        {
            using var pair=new ViewerSessionReceiverTests.Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Snapshot());yield return Read(receiver);var first=receiver.Decisions.Current;
            var ev=(JObject)corpus["positive"][6]["envelope"].DeepClone();ev["message_id"]="event8";ev["body"]["session_id"]="fixture-session";ev["body"]["event"]["revision"]=8;pair.Send(ev);yield return Read(receiver);Assert.That(first.Frame,Is.Null);Assert.That(receiver.Decisions.Current,Is.Null);
            pair.Send(Snapshot("s8",8));yield return Read(receiver);var current=receiver.Decisions.Current;ev["message_id"]="same-revision";pair.Send(ev);yield return Read(receiver);Assert.That(receiver.Decisions.Current,Is.SameAs(current));Assert.That(current.CanSubmit,Is.True);
        }
        [UnityTest] public IEnumerator ReplacementReceiverNeverAcceptsAnOldOfferWithMatchingContextStrings()
        {
            using var firstPair=new ViewerSessionReceiverTests.Pair();var firstTicket=surface.BeginViewer("fixture-session","one");using var first=new ViewerSessionReceiver(firstPair.Channel,firstTicket,true);firstPair.Send(Snapshot());yield return Read(first);var old=first.Decisions.Current;
            using var nextPair=new ViewerSessionReceiverTests.Pair();var nextTicket=surface.BeginViewer("fixture-session","one");using var next=new ViewerSessionReceiver(nextPair.Channel,nextTicket,true);nextPair.Send(Snapshot());yield return Read(next);
            Assert.That(old.Frame,Is.Null);Assert.That(next.Decisions.IsCurrent(old),Is.False);Assert.That(next.Decisions.Current.CanSubmit,Is.True);first.Cancel();Assert.That(next.Decisions.Current,Is.Not.Null);
        }
        [UnityTest] public IEnumerator TerminalOrMissingDecisionSnapshotsClearOffersWithoutInventingAnOutcome()
        {
            for(int mode=0;mode<3;mode++)using(var pair=new ViewerSessionReceiverTests.Pair()) {
                var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Snapshot());yield return Read(receiver);var offer=receiver.Decisions.Current;
                JObject next;
                if(mode==0){next=Snapshot("empty",8);next["body"]["snapshot"]["decision"]=JValue.CreateNull();}
                else{next=(JObject)corpus["positive"][mode==1?4:5]["envelope"].DeepClone();next["message_id"]="terminal";next["body"]["snapshot"]["session_id"]="fixture-session";next["body"]["snapshot"]["revision"]=8;}
                pair.Send(next);yield return Read(receiver);Assert.That(offer.Frame,Is.Null);Assert.That(receiver.Decisions.Current,Is.Null);Assert.That(offer.CanSubmit,Is.False);
            }
        }
        [UnityTest] public IEnumerator ChannelStopAndOverflowImmediatelyDisableOldOffers()
        {
            for(int mode=0;mode<2;mode++)using(var pair=new ViewerSessionReceiverTests.Pair()) {
                var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true,maximumUpdates:1);pair.Send(Snapshot());yield return Read(receiver);var offer=receiver.Decisions.Current;
                if(mode==0)pair.Channel.Cancel();else{pair.Send(Snapshot("overflow",8));yield return Read(receiver);}
                Assert.That(offer.Frame,Is.Null);Assert.That(offer.CanSubmit,Is.False);yield return Until(()=>receiver.Completion.IsCompleted);Assert.That(receiver.Decisions.Current,Is.Null);
            }
        }
        [UnityTest] public IEnumerator ExplicitStaleRejectionRequiresANewSnapshotBeforeOfferingControlsAgain()
        {
            using var pair=new ViewerSessionReceiverTests.Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Snapshot());yield return Read(receiver);var old=receiver.Decisions.Current;
            var command=Message("command","c1",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=7,["operation"]="perform",["decision_id"]="fixture-decision",["action_id"]="fixture-action"});var send=Task.Run(()=>pair.Channel.Submit(command.ToString()));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();TextFrame.Read(pair.Peer.GetStream());
            pair.Send(Message("ack","stale",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["command_id"]="c1",["request_revision"]=7,["outcome"]="rejected",["code"]="STALE_DECISION"}));yield return Read(receiver);Assert.That(old.Frame,Is.Null);Assert.That(receiver.Decisions.Current,Is.Null);
            pair.Send(Snapshot("fresh",8));yield return Read(receiver);Assert.That(receiver.Decisions.Current.CanSubmit,Is.True);Assert.That(receiver.Decisions.IsCurrent(old),Is.False);
        }
        [UnityTest] public IEnumerator LateRejectionForAnotherDecisionDoesNotRetireTheFreshOffer()
        {
            foreach(long revision in new long[]{7,8})using(var pair=new ViewerSessionReceiverTests.Pair()) {
                var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Snapshot());yield return Read(receiver);
                var command=Message("command","c1",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=7,["operation"]="perform",["decision_id"]="fixture-decision",["action_id"]="fixture-action"});var send=Task.Run(()=>pair.Channel.Submit(command.ToString()));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();TextFrame.Read(pair.Peer.GetStream());
                var fresh=Snapshot("next-decision",revision);fresh["body"]["snapshot"]["decision"]["decision_id"]="fixture-next-decision";pair.Send(fresh);yield return Read(receiver);var current=receiver.Decisions.Current;Assert.That(current.CanSubmit,Is.False);
                pair.Send(Message("ack","old-rejection",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["command_id"]="c1",["request_revision"]=7,["outcome"]="rejected",["code"]="STALE_DECISION"}));yield return Read(receiver);
                Assert.That(receiver.Decisions.Current,Is.SameAs(current));Assert.That(current.CanSubmit,Is.True);Assert.That(current.Frame.Decision.DecisionId,Is.EqualTo("fixture-next-decision"));
            }
        }
    }
}

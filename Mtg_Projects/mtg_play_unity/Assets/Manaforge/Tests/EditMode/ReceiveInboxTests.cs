using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class ReceiveInboxTests
    {
        private static JObject Corpus() => JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/receive-history-v1.json")));
        private static JObject Snapshot() => (JObject)Corpus()["cases"][0]["steps"][0]["envelope"].DeepClone();
        private static string Json(JToken value) => value.ToString(Formatting.None);
        private static string Event() => Json(Corpus()["cases"][0]["steps"][2]["envelope"]);
        private static void Failed(ReceiveInbox inbox,string code)
        {
            Assert.That(inbox.State,Is.EqualTo(ReceiveInboxState.Faulted));
            Assert.That(inbox.Count,Is.Zero);Assert.That(inbox.QueuedBytes,Is.Zero);
            Assert.That(inbox.Completion.IsCompleted,Is.True);
            Assert.That(inbox.Completion.Result.State,Is.EqualTo(ReceiveInboxState.Faulted));
            Assert.That(inbox.Completion.Result.Code,Is.EqualTo(code));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.TryTake(out _)).Code,Is.EqualTo("INBOX_FAULTED"));
        }
        [Test] public void PreservesFifoAndDropsDuplicatesWithoutTakingASlot()
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true);
            string snapshot=Json(Snapshot());Assert.That(inbox.Enqueue(snapshot),Is.True);
            Assert.That(inbox.Enqueue(Snapshot().ToString()),Is.False);
            Assert.That(inbox.Enqueue(Event()),Is.True);Assert.That(inbox.Count,Is.EqualTo(2));
            Assert.That(inbox.TryTake(out var first),Is.True);
            using(first)Assert.That((string)WireEnvelope.Parse(first.ReadJson())["message_type"],Is.EqualTo("snapshot"));
            Assert.That(inbox.TryTake(out var second),Is.True);
            using(second)Assert.That((string)WireEnvelope.Parse(second.ReadJson())["message_type"],Is.EqualTo("event"));
            Assert.That(inbox.Count,Is.Zero);Assert.That(inbox.QueuedBytes,Is.Zero);
            Assert.That(inbox.TryTake(out var empty),Is.False);Assert.That(empty,Is.Null);
        }
        [Test] public void CountOverflowClearsDataAndSignalsOwnerToPreserveCommandUncertainty()
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true,maximumMessages:1);
            using var tracker=new CommandTracker("fixture-session","one");
            var command=new JObject { ["wire_version"]=1,["message_type"]="command",["message_id"]="pending",
                ["body"]=new JObject { ["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=7,
                    ["decision_id"]="decision",["operation"]="perform",["action_id"]="action" } };
            tracker.Begin(Json(command));
            var ownerStop=inbox.Completion.ContinueWith(_=>tracker.Disconnect(),TaskScheduler.Default);
            inbox.Enqueue(Json(Snapshot()));Assert.That(inbox.Enqueue(Json(Snapshot())),Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.Enqueue(Event())).Code,Is.EqualTo("INBOX_OVERFLOW"));
            Failed(inbox,"INBOX_OVERFLOW");Assert.That(ownerStop.Wait(5000),Is.True);
            Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));Assert.That(tracker.CanSubmit,Is.False);
        }
        [Test] public void ByteBudgetCountsUtf8RatherThanCharacters()
        {
            var snapshot=Snapshot();snapshot["body"]["snapshot"]["players"][0]["name"]="Café 🂡";
            string text=Json(snapshot);int size=Encoding.UTF8.GetByteCount(text);
            Assert.That(size,Is.GreaterThan(text.Length));
            using var inbox=new ReceiveInbox("fixture-session","one",true,maximumBytes:size);
            inbox.Enqueue(text);Assert.That(inbox.QueuedBytes,Is.EqualTo(size));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.Enqueue(Event())).Code,Is.EqualTo("INBOX_OVERFLOW"));
            Failed(inbox,"INBOX_OVERFLOW");
        }
        [Test] public void CancellationClearsQueuedPacketsAndSignalsTheOwner()
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true);inbox.Enqueue(Json(Snapshot()));
            inbox.Cancel();inbox.Cancel();
            Assert.That(inbox.State,Is.EqualTo(ReceiveInboxState.Cancelled));
            Assert.That(inbox.Count,Is.Zero);Assert.That(inbox.QueuedBytes,Is.Zero);
            Assert.That(inbox.Completion.Result.Code,Is.EqualTo("INBOX_CANCELLED"));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.TryTake(out _)).Code,Is.EqualTo("INBOX_CANCELLED"));
        }
        [Test] public void NormalCompletionAllowsDrainingButCancellationCanRevokeTheQueue()
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true);inbox.Enqueue(Json(Snapshot()));inbox.FinishInput();
            Assert.That(inbox.Completion.Result.State,Is.EqualTo(ReceiveInboxState.Completed));
            Assert.That(inbox.TryTake(out var packet),Is.True);using(packet)Assert.That(packet.ReadJson(),Is.Not.Empty);
            Assert.That(inbox.TryTake(out _),Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.Enqueue(Event())).Code,Is.EqualTo("INBOX_COMPLETE"));
            inbox.Cancel();Assert.That(inbox.State,Is.EqualTo(ReceiveInboxState.Cancelled));
            Assert.That(inbox.Completion.Result.State,Is.EqualTo(ReceiveInboxState.Completed),"First input termination remains immutable");
        }
        [TestCase("viewer","RECEIVE_VIEWER")]
        [TestCase("private","RECEIVE_SHAPE")]
        [TestCase("mode","RECEIVE_MODE")]
        public void InvalidInputRevokesPreviouslyQueuedViewerData(string defect,string code)
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true);inbox.Enqueue(Json(Snapshot()));
            var bad=Snapshot();bad["message_id"]="bad";
            if(defect=="viewer")bad["body"]["snapshot"]["viewer_id"]="two";
            if(defect=="mode")bad["body"]["fixture_only"]=false;
            if(defect=="private") {
                var hidden=bad["body"]["snapshot"]["objects"].First(o=>(bool)o["hidden"]);
                hidden["card_identity"]=new JObject{["oracle_id"]="private",["printing_id"]="private",["deck_entry_id"]=JValue.CreateNull()};
            }
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.Enqueue(Json(bad))).Code,Is.EqualTo(code));Failed(inbox,code);
        }
        [Test] public void ConcurrentConsumersCannotTakeTheSamePacket()
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true);inbox.Enqueue(Json(Snapshot()));
            var consumers=Enumerable.Range(0,8).Select(_=>Task.Run(()=> {
                if(!inbox.TryTake(out var packet))return false;
                using(packet)Assert.That(packet.ReadJson(),Is.Not.Empty);return true;
            })).ToArray();
            Assert.That(Task.WaitAll(consumers,5000),Is.True);Assert.That(consumers.Count(task=>task.Result),Is.EqualTo(1));
            Assert.That(inbox.QueuedBytes,Is.Zero);
        }
        [Test] public void MalformedInputDoesNotEchoThePayload()
        {
            using var inbox=new ReceiveInbox("fixture-session","one",true);inbox.Enqueue(Json(Snapshot()));
            var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.Enqueue("private looked-at card"));
            Assert.That(error.Message,Is.EqualTo(error.Code));Failed(inbox,error.Code);
        }
        [TestCase(0,1)] [TestCase(1025,1)] [TestCase(1,0)] [TestCase(1,67108865)]
        public void InvalidBoundsCannotDisableProtection(int count,int bytes) =>
            Assert.Throws<ArgumentException>(()=>new ReceiveInbox("fixture-session","one",true,count,bytes));
        [Test] public void DequeueTransfersPacketOwnershipAndDisposalRevokesItsBytes()
        {
            var inbox=new ReceiveInbox("fixture-session","one",true);inbox.Enqueue(Json(Snapshot()));
            Assert.That(inbox.TryTake(out var packet),Is.True);inbox.Dispose();inbox.Dispose();
            Assert.That(inbox.Completion.Result.State,Is.EqualTo(ReceiveInboxState.Disposed));
            Assert.That(inbox.Count,Is.Zero);Assert.That(packet.ReadJson(),Is.Not.Empty,"Consumer must release packets it already took");
            packet.Dispose();packet.Dispose();Assert.Throws<ObjectDisposedException>(()=>packet.ReadJson());
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>inbox.TryTake(out _)).Code,Is.EqualTo("INBOX_CLOSED"));
        }
    }
}

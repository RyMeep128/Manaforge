using System;
using System.Linq;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
namespace Manaforge.Play.Tests
{
    public sealed class CommandTrackerTests
    {
        private static string Command(string id="c1",long revision=7)=>new JObject
        { ["wire_version"]=1,["message_type"]="command",["message_id"]=id,["body"]=new JObject
          { ["session_id"]="session",["viewer_id"]="one",["revision"]=revision,["operation"]="perform",["decision_id"]="decision",["action_id"]="action" } }.ToString();
        private static string Ack(string outcome="submitted",string code=null,string id="c1",long revision=7,string viewer="one")=>new JObject
        { ["wire_version"]=1,["message_type"]="ack",["message_id"]="reply",["body"]=new JObject
          { ["session_id"]="session",["viewer_id"]=viewer,["command_id"]=id,["request_revision"]=revision,["outcome"]=outcome,["code"]=code==null?JValue.CreateNull():new JValue(code) } }.ToString();
        [Test] public void ReceiptLookupIsReadOnlyAndRetainsImmutableSnapshots()
        {
            var tracker=new CommandTracker("session","one");tracker.Begin(Command());Assert.That(tracker.Find(null),Is.Null);Assert.That(tracker.Find("unknown"),Is.Null);var before=tracker.Find("c1");Assert.That(before.State,Is.EqualTo(CommandState.AwaitingAck));Assert.That(before.DecisionId,Is.EqualTo("decision"));tracker.Accept(Ack("confirmed"));Assert.That(tracker.Find("c1").State,Is.EqualTo(CommandState.Confirmed));Assert.That(before.State,Is.EqualTo(CommandState.AwaitingAck));tracker.Dispose();Assert.That(tracker.Find("c1"),Is.Null);
        }
        [Test] public void LookingUpAnOldTerminalReceiptCannotReleaseANewPendingCommand()
        {
            using var tracker=new CommandTracker("session","one");tracker.Begin(Command());tracker.Accept(Ack("confirmed"));tracker.Begin(Command("c2"));Assert.That(tracker.Find("c1").State,Is.EqualTo(CommandState.Confirmed));Assert.That(tracker.Current.CommandId,Is.EqualTo("c2"));Assert.That(tracker.CanSubmit,Is.False);tracker.Disconnect();Assert.That(tracker.Find("c2").State,Is.EqualTo(CommandState.Uncertain));
        }
        [Test] public void SubmittedKeepsTheCommandPendingUntilCorrelatedTerminalReceipt()
        {
            using var tracker=new CommandTracker("session","one");var initial=tracker.Begin(Command());
            Assert.That(initial.State,Is.EqualTo(CommandState.AwaitingAck));
            Assert.That(tracker.Accept(Ack()).State,Is.EqualTo(CommandState.Submitted));
            Assert.That(tracker.CanSubmit,Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command("c2"))).Code,Is.EqualTo("COMMAND_PENDING"));
            Assert.That(tracker.Accept(Ack("confirmed")).State,Is.EqualTo(CommandState.Confirmed));
            Assert.That(tracker.CanSubmit,Is.True);
            Assert.That(initial.State,Is.EqualTo(CommandState.AwaitingAck),"Returned receipts are immutable snapshots");
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command())).Code,Is.EqualTo("COMMAND_ID_REUSED"));
        }
        [Test] public void DisconnectBeforeAckCannotBlindlyReplayAfterReconnect()
        {
            using var tracker=new CommandTracker("session","one");tracker.Begin(Command());tracker.Disconnect();tracker.AuthenticatedReconnect();
            Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command("c2"))).Code,Is.EqualTo("COMMAND_UNCERTAIN"));
            Assert.That(tracker.Accept(Ack()).State,Is.EqualTo(CommandState.Uncertain),"Late submitted cannot resolve uncertainty");
            Assert.That(tracker.Accept(Ack("rejected","ENGINE_REJECTED")).State,Is.EqualTo(CommandState.Rejected));
            Assert.That(tracker.CanSubmit,Is.True);
        }
        [Test] public void ExplicitUncertainAckAlsoBlocksNewCommands()
        {
            using var tracker=new CommandTracker("session","one");tracker.Begin(Command());
            tracker.Accept(Ack("uncertain","COMMAND_UNCERTAIN"));Assert.That(tracker.CanSubmit,Is.False);
            Assert.That(tracker.Current.Code,Is.EqualTo("COMMAND_UNCERTAIN"));
        }
        [TestCase("viewer")] [TestCase("revision")] [TestCase("unknown")] [TestCase("malformed")]
        public void BadReceiptPoisonsTheConnectionAndPreservesUncertainty(string defect)
        {
            using var tracker=new CommandTracker("session","one");tracker.Begin(Command());
            string ack=defect=="viewer"?Ack(viewer:"two"):defect=="revision"?Ack(revision:8):defect=="unknown"?Ack(id:"other"):"{}";
            Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Accept(ack));
            Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));Assert.That(tracker.CanSubmit,Is.False);
            Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.AuthenticatedReconnect());
        }
        [Test] public void DuplicateOldReceiptCannotReleaseANewerPendingCommand()
        {
            using var tracker=new CommandTracker("session","one");tracker.Begin(Command());tracker.Accept(Ack("confirmed"));
            tracker.Begin(Command("c2"));tracker.Accept(Ack("confirmed"));
            Assert.That(tracker.Current.CommandId,Is.EqualTo("c2"));Assert.That(tracker.CanSubmit,Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Accept(Ack("rejected","ENGINE_REJECTED"))).Code,Is.EqualTo("ACK_CONFLICT"));
            Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));
        }
        [Test] public void HistoryCapacityNeverEvictsAnIdToAllowReplay()
        {
            using var tracker=new CommandTracker("session","one",1);tracker.Begin(Command());tracker.Accept(Ack("confirmed"));
            Assert.That(tracker.CanSubmit,Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command("c2"))).Code,Is.EqualTo("COMMAND_HISTORY_FULL"));
        }
        [Test] public void ConcurrentBeginsPermitAtMostOneInFlightCommand()
        {
            using var tracker=new CommandTracker("session","one");int[] successes=new int[2];
            Parallel.For(0,2,i=> { try {tracker.Begin(Command("c"+i));successes[i]=1;}catch(WireEnvelope.EnvelopeException error){Assert.That(error.Code,Is.EqualTo("COMMAND_PENDING"));} });
            Assert.That(successes.Sum(),Is.EqualTo(1));
        }
        [Test] public void DisposalClearsPendingRecordsAndPreventsReuse()
        {
            var tracker=new CommandTracker("session","one");tracker.Begin(Command());tracker.Dispose();tracker.Dispose();
            Assert.That(tracker.Current,Is.Null);Assert.That(tracker.CanSubmit,Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command("c2"))).Code,Is.EqualTo("TRACKER_CLOSED"));
        }
        [Test] public void ChoiceCommandsUseTheSamePendingAndUncertainLifecycle()
        {
            var command=JObject.Parse(Command());command["body"]["operation"]="choose";((JObject)command["body"]).Remove("action_id");command["body"]["option_id"]="engine-option";
            using var tracker=new CommandTracker("session","one");tracker.Begin(command.ToString());tracker.Accept(Ack());tracker.Disconnect();tracker.AuthenticatedReconnect();
            Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));Assert.That(tracker.CanSubmit,Is.False);
        }
    }
}

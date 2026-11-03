using System.IO;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class SessionErrorTests
    {
        private static JObject Corpus() => JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/wire-errors-v1.json")));
        [Test] public void SharedTerminalErrorsReturnOnlySafeCategories()
        {
            foreach (var test in Corpus()["positive"])
                Assert.That(SessionErrors.Parse(test["envelope"].ToString(), (string)test["session"], (string)test["viewer"]),
                    Is.EqualTo((string)test["envelope"]["body"]["code"]), (string)test["name"]);
        }
        [Test] public void SharedInvalidErrorsFailClosedWithoutReflectingPrivateContent()
        {
            foreach (var test in Corpus()["negative"])
            {
                var error = Assert.Throws<WireEnvelope.EnvelopeException>(() => SessionErrors.Parse(
                    test["envelope"].ToString(), (string)test["session"], (string)test["viewer"]), (string)test["name"]);
                Assert.That(error.Code, Is.EqualTo((string)test["code"]), (string)test["name"]);
                Assert.That(error.Message, Is.EqualTo(error.Code));
            }
        }
        [TestCase("valid")] [TestCase("viewer")] [TestCase("private")]
        public void ChannelFailurePreservesUncertaintyAndForbidsReconnect(string variant)
        {
            using var tracker = new CommandTracker("session", "seat-one");
            var command = new JObject { ["wire_version"] = 1, ["message_type"] = "command", ["message_id"] = "c1",
                ["body"] = new JObject { ["session_id"] = "session", ["viewer_id"] = "seat-one", ["revision"] = 7,
                    ["decision_id"] = "decision", ["operation"] = "perform", ["action_id"] = "action" } };
            var original = tracker.Begin(command.ToString());
            var error = (JObject)Corpus()["positive"][0]["envelope"].DeepClone();
            if (variant == "viewer") error["body"]["viewer_id"] = "other";
            if (variant == "private") error["body"]["message"] = "private looked-at card";
            if (variant == "valid") Assert.That(tracker.AcceptSessionError(error.ToString()), Is.EqualTo("PROTOCOL_INCOMPATIBLE"));
            else Assert.Throws<WireEnvelope.EnvelopeException>(() => tracker.AcceptSessionError(error.ToString()));
            Assert.That(original.State, Is.EqualTo(CommandState.AwaitingAck));
            Assert.That(tracker.Current.State, Is.EqualTo(CommandState.Uncertain));
            Assert.That(tracker.Current.CommandId, Is.EqualTo("c1"));
            Assert.That(tracker.CanSubmit, Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(() => tracker.AuthenticatedReconnect()).Code, Is.EqualTo("TRACKER_FAULTED"));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(() => tracker.Begin(command.ToString())).Code, Is.EqualTo("TRACKER_FAULTED"));
        }
        [Test] public void TerminalFailureWithoutPendingCommandDoesNotCreateAGameOutcome()
        {
            using var tracker = new CommandTracker("session", "seat-one");
            tracker.AcceptSessionError(Corpus()["positive"][0]["envelope"].ToString());
            Assert.That(tracker.Current, Is.Null);
            Assert.That(tracker.CanSubmit, Is.False);
        }
    }
}

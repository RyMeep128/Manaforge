using System.IO;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class WireMessageTests
    {
        private static JObject Corpus() => JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/wire-messages-v1.json")));
        [Test] public void SharedBodiesPreserveAllFourOutcomesAndShutdown()
        {
            foreach (var test in Corpus()["positive"])
                Assert.That(JToken.DeepEquals(WireMessages.Parse(test["envelope"].ToString()), test["envelope"]), Is.True, (string)test["name"]);
        }
        [Test] public void SharedInvalidBodiesAreRejectedWithSafeCodes()
        {
            foreach (var test in Corpus()["negative"])
            {
                var error = Assert.Throws<WireEnvelope.EnvelopeException>(() => WireMessages.Parse(test["envelope"].ToString()), (string)test["name"]);
                Assert.That(error.Code, Is.EqualTo((string)test["code"]), (string)test["name"]);
                Assert.That(error.Message, Is.EqualTo(error.Code));
            }
        }
        [Test] public void OnlyCurrentViewerDecisionAndProvidedActionPassComparison()
        {
            foreach (var test in Corpus()["current"])
                Assert.That(WireMessages.CheckCurrent(test["envelope"].ToString(), "session", "seat-one", 7, "decision", new[] { "action" }),
                    Is.EqualTo((string)test["code"]), (string)test["name"]);
        }
        [Test] public void ChoiceBindingsNeverImplyPerformAuthorization()
        {
            foreach(var test in Corpus()["bindings"])
            {
                Assert.That(WireMessages.CheckBinding(test["envelope"].ToString(),"session","seat-one",7,"decision"),Is.EqualTo((string)test["code"]),(string)test["name"]);
                var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>WireMessages.CheckCurrent(test["envelope"].ToString(),"session","seat-one",7,"decision",new[]{"action"}));
                Assert.That(error.Code,Is.EqualTo("MESSAGE_UNSUPPORTED"));
            }
        }
        [Test] public void AmountVectorCapIsTransportOnlyAndPreservesSignedValues()
        {
            var corpus=Corpus();Assert.That((int)corpus["max_amount_values"],Is.EqualTo(WireMessages.MaxAmountValues));
            var message=(JObject)corpus["positive"].Single(test=>(string)test["name"]=="choose_amounts")["envelope"].DeepClone();
            var values=new JArray(Enumerable.Repeat(0,WireMessages.MaxAmountValues));message["body"]["values"]=values;
            Assert.DoesNotThrow(()=>WireMessages.Parse(message.ToString()));values.Add(0);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>WireMessages.Parse(message.ToString())).Code,Is.EqualTo("MESSAGE_INVALID"));
        }
    }
}

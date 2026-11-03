using System.IO;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class ReceiveMessageTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
        private static JObject Parse(JToken test)=>ReceiveMessages.Parse(test["envelope"].ToString(),(string)test["session"],(string)test["viewer"],(long)test["minimum_revision"],(bool)test["fixture_mode"]);
        [Test] public void SharedReceiveBodiesValidateWithoutLosingFields()
        {
            foreach(var test in Corpus()["positive"])
                Assert.That(JToken.DeepEquals(Parse(test),test["envelope"]),Is.True,(string)test["name"]);
        }
        [Test] public void WrongViewerStaleFixtureSpoofAndPrivateDataFailBeforeDeserialization()
        {
            foreach(var test in Corpus()["negative"])
            {
                var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>Parse(test),(string)test["name"]);
                Assert.That(error.Code,Is.EqualTo((string)test["code"]),(string)test["name"]);
                Assert.That(error.Message,Is.EqualTo(error.Code));
            }
        }
    }
}

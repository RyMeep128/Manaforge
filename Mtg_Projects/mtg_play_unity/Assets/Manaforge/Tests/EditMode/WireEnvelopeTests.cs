using System.IO;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class WireEnvelopeTests
    {
        [Test] public void SharedPositiveEnvelopesPreserveValues()
        {
            var corpus = Corpus();
            Assert.That((int)corpus["max_depth"], Is.EqualTo(WireEnvelope.MaxDepth));
            foreach (var test in corpus["positive"])
            {
                string text = (string)test["text"];
                using var expectedReader = new JsonTextReader(new StringReader(text)) { DateParseHandling = DateParseHandling.None };
                Assert.That(JToken.DeepEquals(WireEnvelope.Parse(text), JToken.ReadFrom(expectedReader)), Is.True, (string)test["name"]);
            }
        }
        [Test] public void SharedInvalidEnvelopesProduceOnlySafeCodes()
        {
            foreach (var test in Corpus()["negative"])
            {
                var error = Assert.Throws<WireEnvelope.EnvelopeException>(() => WireEnvelope.Parse((string)test["text"]), (string)test["name"]);
                Assert.That(error.Code, Is.EqualTo((string)test["code"]), (string)test["name"]);
                Assert.That(error.Message, Is.EqualTo(error.Code));
            }
        }
        private static JObject Corpus() => JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,
            "../../mtg_play/protocol/fixtures/wire-envelopes-v1.json")));
    }
}

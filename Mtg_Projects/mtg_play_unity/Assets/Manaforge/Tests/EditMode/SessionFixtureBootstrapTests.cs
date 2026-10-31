using System.IO;
using System.Text;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class SessionFixtureBootstrapTests
    {
        private static JObject Example(){var value=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/viewer-bootstrap-v1.json")))["positive"][0].DeepClone();value["viewer_id"]="one";return value;}
        private static ViewerBootstrap Parse(JObject value)=>ViewerBootstrap.Parse(Encoding.UTF8.GetBytes(value.ToString()));
        [Test] public void ReissuesOnlyPublicKeyAndRetainsValidatedDynamicPort()
        {
            var value=Example();value["endpoint"]["port"]=54321;var original=Parse(value);using var copy=SessionFixtureBootstrap.ValidateAndReissue(original);
            Assert.That(copy,Is.Not.Null);Assert.That(copy.Port,Is.EqualTo(54321));Assert.Throws<IOException>(()=>original.TakeViewerKey());var key=copy.TakeViewerKey();try{for(int i=0;i<32;i++)Assert.That(key[i],Is.EqualTo((byte)i));}finally{System.Array.Clear(key,0,key.Length);}
        }
        [TestCase("viewer")] [TestCase("engine")] [TestCase("pin")] [TestCase("key")] [TestCase("artwork")]
        public void RefusesNonFixtureInputAndDisposesItsOwnedKey(string field)
        {
            var value=Example();if(field=="viewer")value["viewer_id"]="other";if(field=="engine")value["engine_version"]="other";if(field=="pin")value["artifact_manifest_sha256"]=new string('b',64);if(field=="key")value["viewer_key_hex"]=new string('b',64);
            if(field=="artwork")value["artwork"]=new JObject{["directory"]=Path.GetTempPath(),["manifest_sha256"]=new string('b',64)};
            var original=Parse(value);Assert.That(SessionFixtureBootstrap.ValidateAndReissue(original),Is.Null);Assert.Throws<IOException>(()=>original.TakeViewerKey());
        }
    }
}

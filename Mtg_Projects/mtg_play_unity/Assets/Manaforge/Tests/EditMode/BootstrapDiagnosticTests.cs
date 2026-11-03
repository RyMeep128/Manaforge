using System.IO;
using System.Text;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class BootstrapDiagnosticTests
    {
        private static JObject Example()=>(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/viewer-bootstrap-v1.json")))["positive"][0].DeepClone();
        private static ViewerBootstrap Parse(JObject value)=>ViewerBootstrap.Parse(Encoding.UTF8.GetBytes(value.ToString()));
        [Test] public void DiagnosticAcceptsOnlyPublicFixtureAndConsumesItsKeyOnce()
        {using var bootstrap=Parse(Example());Assert.That(BootstrapDiagnosticScene.IsPublicFixture(bootstrap),Is.True);Assert.That(BootstrapDiagnosticScene.IsPublicFixture(bootstrap),Is.False);}
        [TestCase("key")] [TestCase("viewer")] [TestCase("artwork")]
        public void DiagnosticRefusesNonFixtureContext(string field)
        {
            var value=Example();if(field=="key")value["viewer_key_hex"]=new string('b',64);
            if(field=="viewer")value["viewer_id"]="different-seat";
            if(field=="artwork")value["artwork"]=new JObject{["directory"]=Path.GetTempPath(),["manifest_sha256"]=new string('b',64)};
            using var bootstrap=Parse(value);Assert.That(BootstrapDiagnosticScene.IsPublicFixture(bootstrap),Is.False);
        }
    }
}

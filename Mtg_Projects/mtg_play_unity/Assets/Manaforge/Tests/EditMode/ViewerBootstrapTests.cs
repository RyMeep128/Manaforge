using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerBootstrapTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/viewer-bootstrap-v1.json")));
        private static JObject Example()=>(JObject)Corpus()["positive"][0].DeepClone();
        private static byte[] Bytes(JToken value)=>Encoding.UTF8.GetBytes(value.ToString());
        private static void Invalid(byte[] bytes){var error=Assert.Throws<IOException>(()=>ViewerBootstrap.Parse(bytes));Assert.That(error.Message,Is.EqualTo("VIEWER_BOOTSTRAP_INVALID"));}
        [Test] public void PythonFixtureParsesWithSingleUseOwnedKeyAndNoPublicDeckPayload()
        {
            var input=Bytes(Example());var before=(byte[])input.Clone();using(var bootstrap=ViewerBootstrap.Parse(input)) {
                Assert.That(bootstrap.Host,Is.EqualTo("127.0.0.1"));Assert.That(bootstrap.Port,Is.EqualTo(43210));
                Assert.That(bootstrap.SessionId,Is.EqualTo("fixture-session"));Assert.That(bootstrap.ViewerId,Is.EqualTo("seat-one"));
                Assert.That(bootstrap.ArtworkDirectory,Is.Null);Assert.That(bootstrap.ToString(),Is.EqualTo("ViewerBootstrap(private)"));
                var key=bootstrap.TakeViewerKey();Assert.That(key,Is.EqualTo(Enumerable.Range(0,32).Select(i=>(byte)i).ToArray()));
                Assert.Throws<IOException>(()=>bootstrap.TakeViewerKey());bootstrap.Dispose();Assert.That(key[1],Is.EqualTo(1));Array.Clear(key,0,key.Length);
            }
            Assert.That(input,Is.EqualTo(before));
        }
        [TestCase("freeform")][TestCase("commander")][TestCase("unrestricted_commander")]
        public void ExplicitFormatSurvivesPrivateBootstrap(string format)
        {
            var value=Example();value["format"]=format;using var bootstrap=ViewerBootstrap.Parse(Bytes(value));
            Assert.That(bootstrap.GameplayFormat,Is.EqualTo(format));
            Assert.That(GameplayPlayerHud.HasCommanderContent(format),Is.EqualTo(format!="freeform"));
        }
        [Test] public void UnknownOrMissingFormatCannotInventCommanderContent()
        {
            using(var old=ViewerBootstrap.Parse(Bytes(Example())))Assert.That(old.GameplayFormat,Is.Null);
            foreach(var format in new JToken[]{JValue.CreateNull(),new JValue("Commander"),new JValue(40),new JObject()}){var value=Example();value["format"]=format;Invalid(Bytes(value));}
            Assert.That(GameplayPlayerHud.HasCommanderContent(null),Is.False);
        }
        [Test] public void SharedNegativeCorpusRejectsEveryInvalidShape()
        {foreach(var item in Corpus()["negative"])Invalid(Bytes(item["value"]));}
        [Test] public void ArtworkMetadataIsPinnedAndRequiresAnAbsolutePath()
        {
            var value=Example();value["artwork"]=new JObject{["directory"]=Path.GetTempPath(),["manifest_sha256"]=new string('b',64)};
            using(var bootstrap=ViewerBootstrap.Parse(Bytes(value)))Assert.That(bootstrap.ArtworkManifestSha256,Is.EqualTo(new string('b',64)));
            value["artwork"]["directory"]="relative/private";Invalid(Bytes(value));value["artwork"]["directory"]=Path.GetTempPath();value["artwork"]["manifest_sha256"]="private invalid hash";Invalid(Bytes(value));
            value["artwork"]["manifest_sha256"]=new string('b',64);value["artwork"]["directory"]="\\\\server\\private";Invalid(Bytes(value));
        }
        [Test] public void RawFramingLimitsDuplicatesAndMalformedUtf8FailWithoutInputDetails()
        {
            Invalid(null);Invalid(new byte[0]);Invalid(new byte[ViewerBootstrap.MaximumBytes+1]);Invalid(new byte[]{255});
            var text=Example().ToString();Invalid(Encoding.UTF8.GetBytes(text.Replace("\"viewer_bootstrap_version\": 1","\"viewer_bootstrap_version\": 1, \"viewer_bootstrap_version\": 1")));
            Invalid(Encoding.UTF8.GetBytes("\ufeff"+text));
        }
        [Test] public void OrganizationOptInIsExplicitAndDoesNotChangeAuthenticationVersion()
        {
            using(var legacy=ViewerBootstrap.Parse(Bytes(Example())))Assert.That(legacy.OrganizationVersion,Is.Zero);
            var value=Example();value["organization_version"]=2;using(var current=ViewerBootstrap.Parse(Bytes(value)))Assert.That(current.OrganizationVersion,Is.EqualTo(2));
            value["organization_version"]=3;using(var drawers=ViewerBootstrap.Parse(Bytes(value)))Assert.That(drawers.OrganizationVersion,Is.EqualTo(3));
            foreach(JToken version in new JToken[]{new JValue(1),new JValue(4),new JValue(true),new JValue("2")}){value["organization_version"]=version;Invalid(Bytes(value));}
        }
        [Test] public void DisposeRevokesUnclaimedKeyAndConcurrentTransfersHaveOneWinner()
        {
            using(var disposed=ViewerBootstrap.Parse(Bytes(Example()))){disposed.Dispose();Assert.Throws<IOException>(()=>disposed.TakeViewerKey());}
            using(var bootstrap=ViewerBootstrap.Parse(Bytes(Example()))) {
                int won=0;Parallel.For(0,16,i=>{try{var key=bootstrap.TakeViewerKey();System.Threading.Interlocked.Increment(ref won);Array.Clear(key,0,key.Length);}catch(IOException){}});
                Assert.That(won,Is.EqualTo(1));
            }
        }
    }
}

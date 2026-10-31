using System;
using System.IO;
using System.Text;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;

namespace Manaforge.Play.Tests
{
    public sealed class DeckPreviewTests
    {
        private static JObject Document()=>JObject.Parse(File.ReadAllText(Path.Combine(UnityEngine.Application.dataPath,"../../mtg_play/protocol/fixtures/deck-preview-v1.json")));
        private static byte[] Bytes(JObject value)=>Encoding.UTF8.GetBytes(value.ToString());
        [Test] public void SharedPythonProjectionValidatesWithoutGameState(){DeckPreview.ValidateDocument(Bytes(Document()));}
        [TestCase("mode","game")][TestCase("format","standard")][TestCase("deck_preview_version",2)]
        public void InvalidPreviewModeFails(string field,object value){var doc=Document();doc[field]=JToken.FromObject(value);Assert.Throws<IOException>(()=>DeckPreview.ValidateDocument(Bytes(doc)));}
        [Test] public void DuplicateEntriesAndInjectedGameStateFail(){var doc=Document();((JArray)doc["cards"]).Add(doc["cards"][0].DeepClone());Assert.Throws<IOException>(()=>DeckPreview.ValidateDocument(Bytes(doc)));doc=Document();doc["legal_actions"]=new JArray();Assert.Throws<IOException>(()=>DeckPreview.ValidateDocument(Bytes(doc)));}
        [Test] public void BadQuantitiesAndOversizedRowsFail(){var doc=Document();doc["cards"][0]["quantity"]=true;Assert.Throws<IOException>(()=>DeckPreview.ValidateDocument(Bytes(doc)));doc=Document();doc["cards"][0]["name"]=new string('x',20000);Assert.Throws<IOException>(()=>DeckPreview.ValidateDocument(Bytes(doc)));}
        [Test] public void BootstrapIsSeparateFromAuthenticatedGameBootstrap(){var doc=new JObject{["deck_preview_version"]=1,["mode"]="deck_preview",["directory"]=Path.GetTempPath(),["deck_sha256"]=new string('a',64),["artwork_sha256"]=new string('b',64),["preview_id"]=new string('c',32)};Assert.That(DeckPreview.Startup.Parse(Bytes(doc)),Is.Not.Null);Assert.Throws<IOException>(()=>ViewerBootstrap.Parse(Bytes(doc)));doc["directory"]="relative";Assert.Throws<IOException>(()=>DeckPreview.Startup.Parse(Bytes(doc)));}
    }
}

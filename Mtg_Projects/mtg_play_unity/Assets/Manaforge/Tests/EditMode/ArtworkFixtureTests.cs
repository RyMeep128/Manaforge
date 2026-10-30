using System;
using System.IO;
using System.Security.Cryptography;
using System.Collections;
using UnityEngine.TestTools;
using Newtonsoft.Json.Linq;
using NUnit.Framework;

namespace Manaforge.Play.Tests
{
    public sealed class ArtworkFixtureTests
    {
        private string directory;
        private JObject manifest;
        private string assetId;
        private static string Hash(byte[] bytes)
        { using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }
        [SetUp]
        public void SetUp()
        {
            directory = Path.Combine(Path.GetTempPath(), "manaforge-art-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            byte[] pixels = { 255, 0, 0, 255 };
            byte[] identity = { 0, 0, 0, 1, 0, 0, 0, 1, 255, 0, 0, 255 };
            assetId = Hash(identity);
            File.WriteAllBytes(Path.Combine(directory, assetId + ".rgba"), pixels);
            manifest = JObject.Parse(@"{
              'fixture_version':1,'fixture_only':true,'description':'test',
              'assets':[], 'cards':[{
                'oracle_id':'oracle','selected_printing_id':'selected','selected_face':'front',
                'values_source':'printed_reference_mock',
                'mock_values':{'name':'Demo','mana_cost':null,'type_line':null,'oracle_text':null,'power':'2','toughness':'2'},
                'candidates':[
                  {'oracle_id':'oracle','printing_id':'selected','face_key':'front','face_index':0,'standard_compatible':false,'cached':true,'asset_id':null},
                  {'oracle_id':'oracle','printing_id':'standard','face_key':'front','face_index':0,'standard_compatible':true,'cached':true,'asset_id':null}
                ]}]}");
            ((JArray)manifest["assets"]).Add(new JObject {
                ["asset_id"] = assetId, ["file"] = assetId + ".rgba", ["width"] = 1, ["height"] = 1,
                ["byte_length"] = 4, ["sha256"] = Hash(pixels), ["pixel_format"] = "RGBA8", ["row_origin"] = "bottom_left"
            });
            foreach (var candidate in manifest["cards"][0]["candidates"]) candidate["asset_id"] = assetId;
        }
        [TearDown]
        public void TearDown() => Directory.Delete(directory, true);
        private void Publish() => File.WriteAllText(Path.Combine(directory, "manifest.json"), manifest.ToString());
        [UnityTest]
        public IEnumerator ResolvesStandardArtworkAndKeepsPrintedMockExplicit()
        {
            Publish();
            var loading = ArtworkFixture.LoadAsync(directory);
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (!loading.IsCompleted && DateTime.UtcNow < deadline) yield return null;
            Assert.That(loading.IsCompleted, Is.True, "Fixture worker timed out");
            var fixture = loading.GetAwaiter().GetResult();
            Assert.That(fixture.RawBytes, Is.EqualTo(4));
            Assert.That(fixture.Cards[0].Identity.SelectedPrintingId, Is.EqualTo("selected"));
            Assert.That(fixture.Cards[0].Identity.RenderedPrintingId, Is.EqualTo("standard"));
            Assert.That(fixture.Cards[0].MockValues.Status, Is.EqualTo("PRINTED MOCK"));
            var copy = fixture.Cards[0].Artwork.CopyPixels(); copy[0] = 0;
            Assert.That(fixture.Cards[0].Artwork.CopyPixels()[0], Is.EqualTo(255));
        }
        [UnityTest]
        public IEnumerator TextureOwnerSharesUploadsEnforcesBudgetAndDestroysResources()
        {
            Publish();
            var loading = ArtworkFixture.LoadAsync(directory);
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (!loading.IsCompleted && DateTime.UtcNow < deadline) yield return null;
            Assert.That(loading.IsCompleted, Is.True);
            var asset = loading.GetAwaiter().GetResult().Cards[0].Artwork;
            var insufficient = new FixtureTextures(3);
            Assert.Throws<InvalidOperationException>(() => insufficient.Get(asset));
            Assert.That(insufficient.Count, Is.Zero);
            insufficient.Dispose();
            var owner = new FixtureTextures(4);
            var texture = owner.Get(asset);
            try
            {
                Assert.That(owner.Get(asset), Is.SameAs(texture));
                Assert.That(owner.Count, Is.EqualTo(1));
                Assert.That(owner.Bytes, Is.EqualTo(4));
                Assert.That(texture.isReadable, Is.False);
            }
            finally { owner.Dispose(); }
            yield return null;
            Assert.That(texture == null, Is.True);
            Assert.Throws<ObjectDisposedException>(() => owner.Get(asset));
        }

        [UnityTest]
        public IEnumerator LayoutGalleryCapacitySharesAssetsWithoutRemovingBounds()
        {
            var cards=(JArray)manifest["cards"];
            while(cards.Count<32)cards.Add(cards[0].DeepClone());
            Publish();var loading=ArtworkFixture.LoadAsync(directory);
            var deadline=DateTime.UtcNow.AddSeconds(15);
            while(!loading.IsCompleted && DateTime.UtcNow<deadline)yield return null;
            Assert.That(loading.IsCompleted,Is.True);
            var fixture=loading.GetAwaiter().GetResult();
            Assert.That(fixture.Cards.Count,Is.EqualTo(32));Assert.That(fixture.RawBytes,Is.EqualTo(4));
            Assert.That(fixture.Cards[0].Artwork,Is.SameAs(fixture.Cards[31].Artwork));
        }
        [TestCase("card_limit")]
        [TestCase("live")]
        [TestCase("path")]
        [TestCase("dimensions")]
        [TestCase("hash")]
        [TestCase("identity")]
        [TestCase("face")]
        [TestCase("cache")]
        public void RejectsInvalidBundle(string mutation)
        {
            switch (mutation)
            {
                case "card_limit": while(((JArray)manifest["cards"]).Count<33)((JArray)manifest["cards"]).Add(manifest["cards"][0].DeepClone()); break;
                case "live": manifest["fixture_only"] = false; break;
                case "path": manifest["assets"][0]["file"] = "../outside.rgba"; break;
                case "dimensions": manifest["assets"][0]["width"] = 1025; break;
                case "hash": File.WriteAllBytes(Path.Combine(directory, assetId + ".rgba"), new byte[4]); break;
                case "identity": manifest["assets"][0]["asset_id"] = new string('0', 64); break;
                case "face": manifest["cards"][0]["candidates"][0]["face_key"] = "back"; break;
                case "cache": manifest["cards"][0]["candidates"][0]["cached"] = false; break;
            }
            Publish();
            var loading = ArtworkFixture.LoadAsync(directory);
            Assert.Throws<IOException>(() => loading.GetAwaiter().GetResult());
        }
        [UnityTest]
        public IEnumerator InstalledPublicArtworkBundleLoadsWhenAvailable()
        {
            var path = Path.Combine(UnityEngine.Application.dataPath, "../Artifacts/CardFixture-20261030-bounded");
            if (!Directory.Exists(path)) Assert.Ignore("Optional local public-artwork diagnostic bundle absent");
            var loading = ArtworkFixture.LoadAsync(path);
            var deadline = DateTime.UtcNow.AddSeconds(15);
            while (!loading.IsCompleted && DateTime.UtcNow < deadline) yield return null;
            Assert.That(loading.IsCompleted, Is.True, "Fixture worker timed out");
            var fixture = loading.GetAwaiter().GetResult();
            Assert.That(fixture.Cards.Count, Is.EqualTo(7));
            Assert.That(fixture.RawBytes, Is.EqualTo(48219136));
            foreach (var card in fixture.Cards) Assert.That(card.Artwork, Is.Not.Null);
        }
    }
}

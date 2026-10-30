using System;
using System.Collections.Generic;
using NUnit.Framework;

namespace Manaforge.Play.Tests
{
    public sealed class VisualPrintingPolicyTests
    {
        private static VisualPrintingCandidate Card(string id, bool standard = false, bool cached = true,
            string oracle = "oracle", string face = "front") =>
            new VisualPrintingCandidate(oracle, id, face, standard, cached);

        [Test]
        public void SelectedCachedStandardWinsWithoutChangingItsIdentity()
        {
            var result = VisualPrintingPolicy.Resolve(false, Card("selected", true), new[] { Card("a", true) });
            Assert.That(result.SelectedPrintingId, Is.EqualTo("selected"));
            Assert.That(result.RenderedPrintingId, Is.EqualTo("selected"));
            Assert.That(result.LayoutProfileId, Is.EqualTo("standard-v1"));
        }

        [Test]
        public void CachedStandardFallbackIsOrdinalAndPreservesSelection()
        {
            var candidates = new[] { Card("z", true), Card("a", true), Card("0", true, false) };
            foreach (var ordered in new[] { candidates, new[] { candidates[2], candidates[1], candidates[0] } })
            {
                var result = VisualPrintingPolicy.Resolve(false, Card("special"), ordered);
                Assert.That(result.SelectedPrintingId, Is.EqualTo("special"));
                Assert.That(result.RenderedPrintingId, Is.EqualTo("a"));
            }
        }

        [Test]
        public void WrongOracleOrFaceCannotSubstitute()
        {
            var result = VisualPrintingPolicy.Resolve(false, Card("selected", face: "back"),
                new[] { Card("a", true), Card("b", true, oracle: "other", face: "back") });
            Assert.That(result.RenderedPrintingId, Is.EqualTo("selected"));
            Assert.That(result.RenderedFace, Is.EqualTo("back"));
            Assert.That(result.LayoutProfileId, Is.EqualTo("authentic-image-v1"));
        }

        [Test]
        public void AvailableSelectedAuthenticImageSurvivesUncachedStandard()
        {
            var result = VisualPrintingPolicy.Resolve(false, Card("special"), new[] { Card("a", true, false) });
            Assert.That(result.RenderedPrintingId, Is.EqualTo("special"));
        }

        [Test]
        public void AnotherAuthenticSameFaceImageBeatsMissingAsset()
        {
            var result = VisualPrintingPolicy.Resolve(false, Card("missing", cached: false), new[] { Card("real") });
            Assert.That(result.RenderedPrintingId, Is.EqualTo("real"));
            Assert.That(result.SelectedPrintingId, Is.EqualTo("missing"));
        }

        [Test]
        public void MissingAssetDoesNotInventRenderedFaceOrLayout()
        {
            var result = VisualPrintingPolicy.Resolve(false, Card("missing", cached: false), Array.Empty<VisualPrintingCandidate>());
            Assert.That(result.MissingAsset, Is.True);
            Assert.That(result.SelectedPrintingId, Is.EqualTo("missing"));
            Assert.That(result.RenderedFace, Is.Null);
            Assert.That(result.LayoutProfileId, Is.Null);
        }

        [Test]
        public void ConcealmentDoesNotEnumerateOrRetainPrivateIdentity()
        {
            Assert.That(VisualPrintingPolicy.Resolve(true, Card("private"), Forbidden()), Is.Null);
        }

        private static IEnumerable<VisualPrintingCandidate> Forbidden()
        {
            throw new AssertionException("Concealed candidates must not be inspected");
#pragma warning disable CS0162
            yield break;
#pragma warning restore CS0162
        }

        [Test]
        public void InvalidPublicIdentityIsRejected()
        {
            Assert.Throws<ArgumentException>(() => Card(""));
            Assert.Throws<ArgumentNullException>(() => VisualPrintingPolicy.Resolve(false, null, Array.Empty<VisualPrintingCandidate>()));
        }
    }
}

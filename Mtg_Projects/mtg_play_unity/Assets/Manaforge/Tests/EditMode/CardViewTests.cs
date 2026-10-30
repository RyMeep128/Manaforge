using System;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class CardViewTests
    {
        private Texture2D texture;
        private CardView view;
        private static CardVisualIdentity Identity(bool standard = true) =>
            VisualPrintingPolicy.Resolve(false, new VisualPrintingCandidate("oracle", "selected", "front", standard, true),
                Array.Empty<VisualPrintingCandidate>());
        private static CardDisplayValues Values(string pt = "2/2", string rules = "Explicit mock text") =>
            new CardDisplayValues("Mock creature", "{X}{G}", "Creature — Example", rules, pt, "1 counter");
        [SetUp] public void Setup()
        {
            texture = new Texture2D(4, 4);
            view = new CardView();
            view.Bind(Identity(), texture, new Rect(0, 0.4f, 1, 0.5f));
        }
        [TearDown] public void Cleanup() { view.Dispose(); UnityEngine.Object.DestroyImmediate(texture); }

        [Test] public void DynamicValuesChangeWithoutReplacingArtworkOrElements()
        {
            var stats = view.Q<Label>("stats");
            var rules = view.Q<Label>("rules");
            view.UpdateValues(Values()); view.UpdateValues(Values("5/5", "Supplied flying"));
            Assert.That(view.Q<Label>("stats"), Is.SameAs(stats));
            Assert.That(stats.text, Is.EqualTo("5/5"));
            Assert.That(rules.text, Is.EqualTo("Supplied flying"));
            Assert.That(view.Artwork, Is.SameAs(texture));
        }
        [Test] public void ModesAndResizeRetainTextureAndUseSeparateLayouts()
        {
            view.SetPresentation(CardPresentationMode.Full, 600);
            Assert.That(view.Q<Label>("rules").style.display.value, Is.EqualTo(DisplayStyle.Flex));
            Assert.That(view.style.height.value.value, Is.EqualTo(840));
            view.SetPresentation(CardPresentationMode.Compact, 300);
            Assert.That(view.Q<Label>("rules").style.display.value, Is.EqualTo(DisplayStyle.None));
            Assert.That(view.style.height.value.value, Is.EqualTo(234).Within(0.01));
            Assert.That(view.Artwork, Is.SameAs(texture));
        }
        [Test] public void ObjectsSharingArtworkKeepIndependentCharacteristics()
        {
            using (var other = new CardView())
            {
                other.Bind(Identity(), texture, new Rect(0, 0, 1, 1));
                other.UpdateValues(Values("9/9")); view.UpdateValues(Values("1/1"));
                Assert.That(other.Q<Label>("stats").text, Is.EqualTo("9/9"));
                Assert.That(view.Q<Label>("stats").text, Is.EqualTo("1/1"));
            }
            Assert.That(texture == null, Is.False, "Borrowed texture survives view disposal");
        }
        [Test] public void ConcealmentClearsIdentityTextureTextAndTooltip()
        {
            view.UpdateValues(Values()); view.tooltip = "Private"; view.Conceal();
            view.UpdateValues(Values("SECRET"));
            Assert.That(view.Identity, Is.Null); Assert.That(view.Artwork, Is.Null);
            Assert.That(view.tooltip, Is.Null.Or.Empty);
            foreach(var image in view.Query<Image>().ToList())Assert.That(image.image,Is.Null);
            Assert.That(view.Q<ManaCostView>().Cost,Is.Empty);
            foreach (var label in view.Query<Label>().ToList()) Assert.That(label.text, Is.Empty);
        }
        [Test] public void RebindingClearsOldValuesAndAuthenticFullImageAvoidsFakeDynamicFrame()
        {
            view.UpdateValues(Values()); view.Bind(Identity(false), texture, new Rect(0, 0, 1, 1));
            view.SetPresentation(CardPresentationMode.Full, 300);
            Assert.That(view.Q<Label>("stats").text, Is.Empty);
            Assert.That(view.Q<Label>("name").style.display.value, Is.EqualTo(DisplayStyle.None));
            Assert.That(view.Q<Image>("artwork").uv, Is.EqualTo(new Rect(0, 0, 1, 1)));
        }
        [Test] public void SpecializedCompactCardsKeepTheWholePrintingWithoutStandardOverlays()
        {
            view.Bind(Identity(false),texture,new Rect(.08f,.45f,.84f,.42f));
            view.UpdateValues(Values());view.SetPresentation(CardPresentationMode.Compact,160);
            Assert.That(view.Q<Image>("artwork").uv,Is.EqualTo(new Rect(0,0,1,1)));
            Assert.That(view.Q<Image>("artwork").scaleMode,Is.EqualTo(ScaleMode.ScaleToFit));
            foreach(var name in new[]{"name","stats","rules"})Assert.That(view.Q<Label>(name).style.display.value,Is.EqualTo(DisplayStyle.None));
            Assert.That(view.Q<VisualElement>("printed-stats-mask").style.display.value,Is.EqualTo(DisplayStyle.None));
            Assert.That(view.Q<Image>("printing-frame").style.display.value,Is.EqualTo(DisplayStyle.None));
        }
        [Test] public void LandscapePrintingInspectionPreservesItsAspectRatio()
        {
            var landscape=new Texture2D(8,4);
            try{view.Bind(Identity(false),landscape,new Rect(0,0,1,1));view.SetPresentation(CardPresentationMode.Full,300);
                Assert.That(view.style.height.value.value,Is.EqualTo(150));}
            finally{UnityEngine.Object.DestroyImmediate(landscape);}
        }
        [Test] public void MissingAssetIsExplicitAndNoStatsAreInvented()
        {
            var identity = VisualPrintingPolicy.Resolve(false,
                new VisualPrintingCandidate("oracle", "missing", "front", true, false), Array.Empty<VisualPrintingCandidate>());
            view.Bind(identity, null, new Rect(0, 0, 1, 1));
            view.UpdateValues(new CardDisplayValues("Land", null, null, null, null, null));
            Assert.That(view.Q<Label>("asset-status").text, Is.EqualTo("Artwork unavailable"));
            Assert.That(view.Q<Label>("stats").text, Is.Empty);
            Assert.That(view.Q<CardPlate>("pt-plate").style.display.value,Is.EqualTo(DisplayStyle.None));
            Assert.Throws<ArgumentException>(() => view.Bind(identity, texture, new Rect(0, 0, 1, 1)));
        }
        [Test] public void SuppliedTextCannotInjectRichText()
        {
            view.UpdateValues(Values(rules: "<size=0>supplied</size>"));
            Assert.That(view.Q<Label>("rules").enableRichText, Is.False);
            Assert.That(view.Q<Label>("rules").text, Is.EqualTo("<size=0>supplied</size>"));
        }
        [Test] public void FullCardStatsSlotTracksSuppliedCharacteristicsWithoutRebinding()
        {
            view.SetPresentation(CardPresentationMode.Full,300);
            foreach(var pt in new string[]{null,"3/3",null,"0/1"}) {
                view.UpdateValues(Values(pt));var expected=pt==null?DisplayStyle.None:DisplayStyle.Flex;
                Assert.That(view.Q<CardPlate>("pt-plate").style.display.value,Is.EqualTo(expected));
                Assert.That(view.Q<VisualElement>("printed-stats-mask").style.display.value,Is.EqualTo(expected));
                Assert.That(view.Artwork,Is.SameAs(texture));
            }
        }
        [Test] public void InvalidLayoutInputIsRejected()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => view.SetPresentation(CardPresentationMode.Full, float.NaN));
            Assert.Throws<ArgumentOutOfRangeException>(() => view.Bind(Identity(), texture, new Rect(0, 0, 2, 1)));
        }
    }
}

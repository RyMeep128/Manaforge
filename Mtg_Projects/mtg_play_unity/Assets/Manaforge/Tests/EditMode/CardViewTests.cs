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
            Assert.That(view.style.height.value.value, Is.EqualTo(300*BattlefieldFrame.Aspect).Within(0.01));
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
            Assert.That(view.Q<RulesTextView>().SourceText,Is.Empty);
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
        [TestCase("normal","Legendary Planeswalker — Jace")]
        [TestCase("saga","Enchantment — Saga")]
        [TestCase("transform","Battle — Siege")]
        [TestCase("token","Token Creature — Soldier")]
        [TestCase("split","Enchantment — Room")]
        [TestCase("class","Enchantment — Class")]
        [TestCase("modal_dfc","Land")]
        [TestCase("prototype","Artifact Creature")]
        [TestCase("meld","Creature")]
        [TestCase("vanguard","Vanguard")]
        public void KnownProfilesUseCroppedArtworkAndCustomTextInBothPresentations(string layout,string typeLine)
        {
            view.Bind(Identity(false),texture,new Rect(0,0,1,1));
            view.UpdateValues(new CardDisplayValues("Mini",null,typeLine,null,null,null,CardCompactProfile.FromMetadata(layout,typeLine)));
            view.SetPresentation(CardPresentationMode.Compact,160);
            Assert.That(view.Q<Label>("name").style.display.value,Is.EqualTo(DisplayStyle.Flex));
            Assert.That(view.Q<Image>("artwork").uv,Is.Not.EqualTo(new Rect(0,0,1,1)));
            Assert.That(view.Q<Label>("rules").style.display.value,Is.EqualTo(DisplayStyle.None));
            view.SetPresentation(CardPresentationMode.Full,300);
            Assert.That(view.Q<Image>("artwork").uv,Is.Not.EqualTo(new Rect(0,0,1,1)));
            Assert.That(view.Q<Label>("name").style.display.value,Is.EqualTo(DisplayStyle.Flex));
            Assert.That(view.Q<VisualElement>("rules-scroll").style.display.value,Is.EqualTo(DisplayStyle.Flex));
        }
        [TestCase("Instant",false)] [TestCase("Sorcery",false)] [TestCase("Instant // Instant",false)]
        [TestCase("Token Creature — Soldier",true)] [TestCase("Artifact",true)] [TestCase("Enchantment — Room",true)]
        [TestCase("Legendary Planeswalker — Jace",true)] [TestCase("Battle — Siege",true)] [TestCase("Land",true)]
        [TestCase("Emblem",false)] [TestCase("Dungeon",false)] [TestCase("Plane — Ravnica",false)]
        public void FixtureGridContainsPermanentExamplesAndKeepsOtherCardsForInspection(string typeLine,bool expected)
        {Assert.That(CardCompactProfile.IsFixturePermanent(typeLine),Is.EqualTo(expected));}
        [TestCase("Instant")] [TestCase("Sorcery")]
        public void NonPermanentSpellsDoNotReceiveBattlefieldProfiles(string typeLine)
        {Assert.That(CardCompactProfile.FromMetadata("normal",typeLine),Is.Null);}
        [Test] public void LoyaltyBadgeUpdatesWithoutInventingAMissingValue()
        {
            view.Bind(Identity(false),texture,new Rect(0,0,1,1));var profile=CardCompactProfile.FromMetadata("normal","Planeswalker");
            foreach(var loyalty in new string[]{"3","5",null}) {
                view.UpdateValues(new CardDisplayValues("PW",null,"Planeswalker",null,null,null,profile,loyalty));
                Assert.That(view.Q<LoyaltyCounterView>().Value,Is.EqualTo(loyalty??""));
                Assert.That(view.Q<Label>("stats").text,Is.Empty);
                Assert.That(view.Q<LoyaltyCounterView>().style.display.value,Is.EqualTo(loyalty==null?DisplayStyle.None:DisplayStyle.Flex));
            }
        }
        [Test] public void SplitMinisBorrowOnePrintingForBothArtPanesAndClearBoth()
        {
            view.Bind(Identity(false),texture,new Rect(0,0,1,1));
            view.UpdateValues(new CardDisplayValues("Split",null,"Instant",null,null,null,CardCompactProfile.FromMetadata("split","Enchantment — Room")));
            Assert.That(view.Q<VisualElement>("second-art-window").style.display.value,Is.EqualTo(DisplayStyle.Flex));
            Assert.That(view.Q<Image>("second-artwork").image,Is.SameAs(view.Artwork));
            view.Conceal();Assert.That(view.Q<Image>("second-artwork").image,Is.Null);
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

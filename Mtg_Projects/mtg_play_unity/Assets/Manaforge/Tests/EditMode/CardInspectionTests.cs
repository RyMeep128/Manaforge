using System;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class CardInspectionTests
    {
        private Texture2D texture;
        private CardView view;
        private CardInspectionFlip flip;
        private void Bind(string name="Front",string layout="normal",string type="Creature",bool ability=false)
        {
            var identity=VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate("oracle","printing",name,false,true),Array.Empty<VisualPrintingCandidate>());
            view.Bind(identity,texture,new Rect(.08f,.45f,.84f,.42f));
            view.UpdateValues(new CardDisplayValues(name,null,type,"Supplied effect text",null,null,CardCompactProfile.FromMetadata(layout,type),isAbility:ability));
            view.SetPresentation(CardPresentationMode.Full,400);
        }
        [SetUp] public void Setup(){texture=new Texture2D(4,6);view=new CardView();flip=new CardInspectionFlip(view);Bind();}
        [TearDown] public void Cleanup(){flip.Dispose();view.Dispose();UnityEngine.Object.DestroyImmediate(texture);}
        [TestCase("transform","Battle — Siege")]
        [TestCase("split","Enchantment — Room")]
        public void CustomLandscapeCardsHaveUnrotatedLabelsAndCroppedArt(string layout,string type)
        {
            Bind(layout:layout,type:type);
            Assert.That(view.style.width.value.value,Is.GreaterThan(view.style.height.value.value));
            Assert.That(view.Q<Label>("name").text,Is.EqualTo("Front"));
            Assert.That(view.Q<Image>("artwork").uv,Is.Not.EqualTo(new Rect(0,0,1,1)));
            Assert.That(view.Q<VisualElement>("rules-scroll").style.display.value,Is.EqualTo(DisplayStyle.Flex));
        }
        [TestCase("scheme","Scheme",false)]
        [TestCase("normal","Plane — Iquatana",true)]
        [TestCase("normal","Dungeon",false)]
        [TestCase("vanguard","Vanguard",true)]
        public void OriginalPrintingProfilesKeepAllPrintedContent(string layout,string type,bool landscape)
        {
            Bind(layout:layout,type:type);
            Assert.That(view.style.width.value.value>view.style.height.value.value,Is.EqualTo(landscape));
            Assert.That(view.Q<Image>("artwork").uv,Is.EqualTo(new Rect(0,0,1,1)));
            Assert.That(view.Q<Image>("artwork").scaleMode,Is.EqualTo(ScaleMode.ScaleToFit));
            Assert.That(view.Q<Label>("name").style.display.value,Is.EqualTo(DisplayStyle.None));
            Assert.That(view.Q<VisualElement>("rules-scroll").style.display.value,Is.EqualTo(DisplayStyle.None));
        }
        [Test] public void DungeonCompactAlsoKeepsTheOriginalPrinting()
        {
            Bind(type:"Dungeon");view.SetPresentation(CardPresentationMode.Compact,160);
            Assert.That(view.Q<Image>("artwork").uv,Is.EqualTo(new Rect(0,0,1,1)));
            Assert.That(view.Q<Label>("name").style.display.value,Is.EqualTo(DisplayStyle.None));
        }
        [Test] public void AbilityUsesSuppliedSourceNameTypeTextAndRoundedBottomWithoutCardStats()
        {
            Bind("Source card",type:"Ability",ability:true);
            Assert.That(view.Q<Label>("name").text,Is.EqualTo("Source card"));
            Assert.That(view.Q<Label>("type").text,Is.EqualTo("Ability"));
            Assert.That(view.Q<Label>("rules").text,Is.EqualTo("Supplied effect text"));
            Assert.That(view.style.borderBottomLeftRadius.value.value,Is.GreaterThan(view.style.borderTopLeftRadius.value.value*5));
            Assert.That(view.Q<ManaCostView>().style.display.value,Is.EqualTo(DisplayStyle.None));
            Assert.That(view.Q<CardPlate>("pt-plate").style.display.value,Is.EqualTo(DisplayStyle.None));
            view.Conceal();foreach(var label in view.Query<Label>().ToList())Assert.That(label.text,Is.Empty);
        }
        [Test] public void FlipSwapsOnceAtMidpointAndReturnsToFullWidth()
        {
            int swaps=0;Assert.That(flip.Begin(()=>{swaps++;Bind("Back");}),Is.True);
            flip.Advance(.25f);Assert.That(view.Q<Label>("name").text,Is.EqualTo("Front"));
            flip.Advance(.5f);Assert.That(view.Q<Label>("name").text,Is.EqualTo("Back"));
            flip.Advance(.75f);flip.Advance(1);Assert.That(swaps,Is.EqualTo(1));Assert.That(flip.Running,Is.False);
            Assert.That(view.style.scale.value.value,Is.EqualTo(Vector3.one));
        }
        [Test] public void ConcealThenRebindTheSameIdentityStillCancelsTheOldFlip()
        {
            int swaps=0;flip.Begin(()=>swaps++);var identity=view.Identity;
            view.Conceal();view.Bind(identity,texture,new Rect(0,0,1,1));flip.Advance(.75f);
            Assert.That(swaps,Is.Zero);Assert.That(flip.Running,Is.False);
        }
        [Test] public void ReducedMotionAndDisposeHaveNoDelayedFaceSwap()
        {
            int swaps=0;Assert.That(flip.Begin(()=>swaps++,true),Is.True);Assert.That(swaps,Is.EqualTo(1));
            Assert.That(flip.Running,Is.False);flip.Begin(()=>swaps++);flip.Dispose();flip.Advance(1);
            Assert.That(swaps,Is.EqualTo(1));Assert.That(flip.Begin(()=>swaps++),Is.False);
        }
    }
}

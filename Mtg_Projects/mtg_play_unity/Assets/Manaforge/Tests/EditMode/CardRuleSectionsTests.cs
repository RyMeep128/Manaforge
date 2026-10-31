using System;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class CardRuleSectionsTests
    {
        [Test] public void LoyaltyRowsKeepStaticTextAndAllSignedCosts()
        {
            var rows=CardRuleSection.FromPrintedText("Planeswalker","Static text\n+2: Draw.\n0: Look.\n−X: Return.\n-12: Exile.");
            Assert.That(rows.Count,Is.EqualTo(5));Assert.That(rows[0].Text,Is.EqualTo("Static text"));
            Assert.That(rows[1].Heading,Is.EqualTo("+2"));Assert.That(rows[3].Heading,Is.EqualTo("−X"));
            Assert.That(rows[4].Text,Is.EqualTo("Exile."));
        }
        [Test] public void ClassCostsAndLevelerRangesRemainDifferentPrintedStructures()
        {
            var classes=CardRuleSection.FromPrintedText("Class","Base.\n{1}{G}: Level 2\nSecond.\n{3}{G}: Level 3\nThird.");
            Assert.That(classes.Count,Is.EqualTo(3));Assert.That(classes[1].Heading,Is.EqualTo("{1}{G}: Level 2"));
            var levels=CardRuleSection.FromPrintedText("Level up","Level up {W}\nLEVEL 2-6\n3/3\nFirst strike\nLEVEL 7+\n4/4");
            Assert.That(levels[1].Text,Is.EqualTo("3/3\nFirst strike"));Assert.That(levels[2].Heading,Is.EqualTo("LEVEL 7+"));
        }
        [Test] public void UnrecognizedMarkersAndLiteralMarkupSurviveWithoutLevelInference()
        {
            const string text="LEVEL unknown\n<b>Literal</b>\n+1: Remains plain.";
            var rows=CardRuleSection.FromPrintedText("Class",text);
            Assert.That(rows.Count,Is.EqualTo(1));Assert.That(rows[0].Text,Is.EqualTo(text));
            var view=new CardRuleSections();view.SetText("Class",text);view.Resize(14);
            foreach(var label in view.Query<Label>().ToList())Assert.That(label.enableRichText,Is.False);
            view.Conceal();Assert.That(view.childCount,Is.Zero);
        }
        [Test] public void RoomInspectionSwitchesOnlyDisplayMetadataAndClearsCallbacksOnHandoff()
        {
            var texture=new Texture2D(4,8);var profile=CardCompactProfile.FromMetadata("split","Enchantment — Room");
            var identity=VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate("oracle","printing","front",false,true),Array.Empty<VisualPrintingCandidate>());
            using(var view=new CardView()) {
                view.Bind(identity,texture,new Rect(0,0,1,1));view.SetPresentation(CardPresentationMode.Full,300);
                view.UpdateValues(new CardDisplayValues("First","{W}","Enchantment — Room","First text",null,null,profile,roomDoors:new[]{new RoomDoorDisplay("First","{W}","First text"),new RoomDoorDisplay("Second","{2}{U}","Second text")}));
                var buttons=view.Q<VisualElement>("room-doors").Query<Button>().ToList();Assert.That(buttons.Count,Is.EqualTo(2));
                view.InspectRoomDoor(1);
                Assert.That(view.Q<Label>("name").text,Is.EqualTo("Second"));
                Assert.That(view.Q<Label>("rules").text,Is.EqualTo("Second text"));Assert.That(view.Identity,Is.SameAs(identity));
                Assert.That(view.Q<Image>("artwork").uv,Is.EqualTo(profile.SecondaryCrop.Value));
                view.Conceal();Assert.That(view.Q<VisualElement>("room-doors").childCount,Is.Zero);
                view.InspectRoomDoor(0);
                Assert.That(view.Q<Label>("name").text,Is.Empty);
            }
            UnityEngine.Object.DestroyImmediate(texture);
        }
        [TestCase("meld","Creature")]
        [TestCase("class","Enchantment — Class")]
        [TestCase("leveler","Creature")]
        [TestCase("normal","Planeswalker")]
        public void KnownLayoutsRetainSharedPrintingFrame(string layout,string typeLine)
        {
            var texture=new Texture2D(4,8);
            using(var view=new CardView()) {
                view.Bind(VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate("o","p","f",false,true),Array.Empty<VisualPrintingCandidate>()),texture,new Rect(0,0,1,1));
                view.UpdateValues(new CardDisplayValues("Title",null,typeLine,"Text",null,null,CardCompactProfile.FromMetadata(layout,typeLine)));
                view.SetPresentation(CardPresentationMode.Full,300);
                Assert.That(view.Q<Image>("printing-frame").style.display.value,Is.EqualTo(DisplayStyle.Flex));
                Assert.That(view.Q<Label>("name").style.left.value.value,Is.EqualTo(9));
            }
            UnityEngine.Object.DestroyImmediate(texture);
        }
    }
}

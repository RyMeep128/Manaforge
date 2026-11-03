using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ManaCostViewTests
    {
        [TestCase("W",0xe600)] [TestCase("U",0xe601)] [TestCase("B",0xe602)]
        [TestCase("R",0xe603)] [TestCase("G",0xe604)] [TestCase("0",0xe605)]
        [TestCase("15",0xe614)] [TestCase("16",0xe62a)] [TestCase("20",0xe62e)]
        [TestCase("T",0xe61a)] [TestCase("Q",0xe61b)] [TestCase("E",0xe907)]
        [TestCase("X",0xe615)] [TestCase("S",0xe619)] [TestCase("C",0xe904)]
        public void CostNotationUsesPinnedFontGlyphs(string token,int expected)
        {Assert.That(ManaCostView.TryGlyph(token,out var glyph),Is.True);Assert.That((int)glyph,Is.EqualTo(expected));}
        [Test] public void OfflineSymbolsReplaceBracesAndConcealmentClearsThem()
        {
            Assert.That(Resources.Load<Font>("Mana"),Is.Not.Null);
            var cost=new ManaCostView();cost.SetCost("{2}{G}{W/U}");Assert.That(cost.SymbolCount,Is.EqualTo(3));
            foreach(var label in cost.Query<Label>().ToList())Assert.That(label.text,Does.Not.Contain("{"));
            cost.Conceal();Assert.That(cost.childCount,Is.Zero);Assert.That(cost.Cost,Is.Empty);Assert.That(cost.tooltip,Is.Null.Or.Empty);
        }
        [Test] public void UnsupportedNotationRemainsVisibleRatherThanInventingASymbol()
        {
            var cost=new ManaCostView();cost.SetCost("{UNKNOWN}");Assert.That(cost.SymbolCount,Is.Zero);
            Assert.That(cost.Q<Label>().text,Is.EqualTo("{UNKNOWN}"));Assert.That(cost.Q<Label>().enableRichText,Is.False);
            cost.SetCost("<size=0>bad</size>");Assert.That(cost.Q<Label>().text,Is.EqualTo("<size=0>bad</size>"));
        }
    }
}

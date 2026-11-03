using System.Linq;
using NUnit.Framework;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class RulesTextViewTests
    {
        [TestCase("{T}: Add {C}{C}.",3)]
        [TestCase("{Q}: Add {W}{U}{B}{R}{G} or {2/W}.",7)]
        public void KnownSymbolsAreInlineAndSourceTextRemainsExact(string text,int count)
        {
            var view=new RulesTextView();view.SetText(text);view.Resize(13);
            Assert.That(view.SymbolCount,Is.EqualTo(count));Assert.That(view.SourceText,Is.EqualTo(text));
            Assert.That(view.Query<ManaSymbolView>().ToList().Count,Is.EqualTo(count));
        }
        [Test] public void UnknownTokensAndMarkupStayLiteral()
        {
            var view=new RulesTextView();view.SetText("Pay {UNKNOWN} <size=0> {G}.");
            Assert.That(view.SymbolCount,Is.EqualTo(1));
            var labels=view.Query<Label>().ToList();
            Assert.That(string.Concat(labels.Select(l=>l.text)),Does.Contain("{UNKNOWN}"));
            Assert.That(string.Concat(labels.Select(l=>l.text)),Does.Contain("<size=0>"));
            foreach(var label in labels)Assert.That(label.enableRichText,Is.False);
        }
        [Test] public void ReuseAndConcealmentRemoveOldSymbolNodes()
        {
            var view=new RulesTextView();view.SetText("{T}: Add {C}.");view.SetText("Plain text");
            Assert.That(view.SymbolCount,Is.Zero);Assert.That(view.childCount,Is.Zero);
            view.SetText("{G}");view.Conceal();Assert.That(view.SourceText,Is.Empty);Assert.That(view.childCount,Is.Zero);
        }
        [Test] public void LongRunsFallBackToTheIntactSourceWithoutUnboundedElements()
        {
            var text=string.Concat(Enumerable.Repeat("{G} ",200));var view=new RulesTextView();view.SetText(text);
            Assert.That(view.SourceText,Is.EqualTo(text));Assert.That(view.SymbolCount,Is.Zero);Assert.That(view.childCount,Is.Zero);
        }
    }
}

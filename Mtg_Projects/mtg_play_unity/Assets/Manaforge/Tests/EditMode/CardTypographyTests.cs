using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class CardTypographyTests
    {
        [Test] public void InstalledLocalPackAppliesRealFacesAndEmphasisWithoutChangingText()
        {
            if(Resources.Load<Font>(CardTypography.ResourceName(CardTextRole.Title))==null)
                Assert.Ignore("Optional owner-supplied local typography pack is absent");
            var label=new Label("Literal <b>text</b>"){enableRichText=false};
            foreach(var style in new[]{FontStyle.Normal,FontStyle.Bold,FontStyle.Italic,FontStyle.BoldAndItalic}) {
                var expected=Resources.Load<Font>(CardTypography.ResourceName(CardTextRole.Rules,style));
                Assert.That(expected,Is.Not.Null);Assert.That(CardTypography.Apply(label,CardTextRole.Rules,style),Is.True);
                Assert.That(label.style.unityFontDefinition.value.font,Is.SameAs(expected));
                Assert.That(label.text,Is.EqualTo("Literal <b>text</b>"));Assert.That(label.enableRichText,Is.False);
            }
        }
        [Test] public void InstalledSymbolPackUsesSharedFullSpriteRatherThanFontGlyphLabels()
        {
            if(!CardSymbolSprites.TryLoad("U",out var texture))Assert.Ignore("Optional local SVG sprite pack is absent");
            Assert.That(texture.width,Is.EqualTo(128));Assert.That(texture.height,Is.EqualTo(128));
            Assert.That(CardSymbolSprites.TryLoad("U",out var again),Is.True);Assert.That(again,Is.SameAs(texture));
            Assert.That(new ManaSymbolView("U").Q<Image>().image,Is.SameAs(texture));
            Assert.That(CardSymbolSprites.TryLoad("../../outside",out _),Is.False);
        }
    }
}

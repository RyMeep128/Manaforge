using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class OpeningHandFanTests
    {
        [TestCase("Mulligan <font color='#ffff00'>down to 6 cards</font>?","Mulligan down to 6 cards?")]
        [TestCase("Choose<BR />[W] <unknown>literal</unknown>","Choose\n[W] <unknown>literal</unknown>")]
        public void FormattingDoesNotChangeEngineWordingOrUnknownTokens(string raw,string plain){Assert.That(OpeningHandFan.PlainPrompt(raw),Is.EqualTo(plain));}
        [TestCase(1,500)][TestCase(2,800)][TestCase(7,1200)][TestCase(10,900)][TestCase(20,640)]
        public void CardsRemainOrderedAndInsideTheHandSurface(int count,float width)
        {
            var cards=OpeningHandFan.Arrange(count,width);Assert.That(cards.Length,Is.EqualTo(count));
            float previous=float.NegativeInfinity;
            foreach(var card in cards){
                float angle=card.Angle*Mathf.Deg2Rad;
                float half=(card.Width*Mathf.Cos(angle)+card.Width*1.4f*Mathf.Abs(Mathf.Sin(angle)))*.5f;
                float center=card.Left+card.Width*.5f;
                Assert.That(center-half,Is.GreaterThanOrEqualTo(-.01f));Assert.That(center+half,Is.LessThanOrEqualTo(width+.01f));
                Assert.That(center,Is.GreaterThan(previous));previous=center;
            }
        }
        [Test] public void SevenCardOpeningHasTheReferenceFanComposition()
        {
            var cards=OpeningHandFan.Arrange(7,1200);
            Assert.That(cards[0].Angle,Is.LessThan(0));Assert.That(cards[6].Angle,Is.GreaterThan(0));Assert.That(cards[3].Angle,Is.Zero);
            Assert.That(cards[0].Top,Is.GreaterThan(cards[3].Top));Assert.That(cards[0].Top,Is.EqualTo(cards[6].Top).Within(.01f));
            Assert.That(cards[6].Angle-cards[0].Angle,Is.LessThanOrEqualTo(30));
        }
        [Test] public void EmptyHandDoesNotInventCards(){Assert.That(OpeningHandFan.Arrange(0,1200),Is.Empty);}
        [TestCase(-1,100)][TestCase(257,100)][TestCase(7,0)][TestCase(7,-1)]
        public void InvalidGeometryFailsExplicitly(int count,float width){Assert.Throws<System.ArgumentOutOfRangeException>(()=>OpeningHandFan.Arrange(count,width));}
    }
}

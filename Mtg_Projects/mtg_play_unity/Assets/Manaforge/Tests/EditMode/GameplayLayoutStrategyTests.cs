using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayLayoutStrategyTests
    {
        private readonly IGameplayLayoutStrategy strategy=new LegacyGameplayLayoutStrategy();
        private static void RectIs(Rect actual,float x,float y,float width,float height)
        {
            Assert.That(actual.x,Is.EqualTo(x).Within(.002));Assert.That(actual.y,Is.EqualTo(y).Within(.002));
            Assert.That(actual.width,Is.EqualTo(width).Within(.002));Assert.That(actual.height,Is.EqualTo(height).Within(.002));
        }
        // Frozen expectations from the pre-extraction Arena layout, not a second resolver.
        [TestCase(1280,720,340,572,600,1060,259.2f,328,538,650)]
        [TestCase(1366,768,340,620,686,1146,276.48f,376,586,698)]
        [TestCase(1920,1080,510,932,900,1700,388.8f,688,898,1010)]
        [TestCase(2560,1440,830,1292,900,2340,518.4f,1048,1258,1370)]
        public void NormalTableRetainsLegacyGeometry(float width,float height,float handX,float handY,float handSpan,
            float stackX,float stackY,float bank,float zoneHeight,float hudHeight)
        {
            var plan=strategy.Resolve(new GameplayLayoutContext(width,height,false,false,false));
            RectIs(plan.HandBounds,handX,handY,handSpan,203);
            RectIs(plan.StackBounds,stackX,stackY,200,140);
            Assert.That(plan.HandSize,Is.EqualTo(145));Assert.That(plan.HandNavigationY,Is.EqualTo(height-30));
            Assert.That(plan.ZoneBankSeparation,Is.EqualTo(bank));Assert.That(plan.ZoneMaxHeight,Is.EqualTo(zoneHeight));
            Assert.That(plan.PlayerHudHeight,Is.EqualTo(hudHeight));
            Assert.That(plan.ActionViewportWidth,Is.EqualTo(275));Assert.That(plan.ActionViewportRight,Is.Zero);
            Assert.That(plan.ActionViewportTop,Is.Null);Assert.That(plan.ActionViewportBottom,Is.EqualTo(32));
            Assert.That(plan.ActionMaxHeight,Is.EqualTo(285));
        }
        [TestCase(1280,720,1040,172.8f,748,194.4f,512)]
        [TestCase(1366,768,1126,184.32f,826,207.36f,520)]
        [TestCase(1920,1080,1680,259.2f,1380,291.6f,520)]
        [TestCase(2560,1440,2320,345.6f,2020,388.8f,520)]
        public void OpeningAndFocusedStackRetainLegacyGeometry(float width,float height,float span,float handY,
            float stackX,float stackY,float stackSpan)
        {
            var plan=strategy.Resolve(new GameplayLayoutContext(width,height,true,true,false));
            RectIs(plan.HandBounds,120,handY,span,294);
            RectIs(plan.StackBounds,stackX,stackY,stackSpan,266);
            RectIs(plan.StackToolbarBounds,stackX,stackY-38,stackSpan,0);
            RectIs(plan.StackBackdropBounds,stackX-10,stackY-46,stackSpan+20,341);
            Assert.That(plan.HandSize,Is.EqualTo(210));Assert.That(plan.StackCardSize,Is.EqualTo(190));
            Assert.That(plan.ActionViewportWidth,Is.EqualTo(520));
            Assert.That(plan.ActionViewportRight,Is.EqualTo(width*.5f-280));
            Assert.That(plan.ActionMaxHeight,Is.EqualTo(170));
        }
        [TestCase(1280,720,896,172,-525.4f,436,472,244.8f,920)]
        [TestCase(1366,768,956.2f,184.9f,-564.76f,467.2f,505.6f,261.12f,1006)]
        [TestCase(1920,1080,1344,268,-820.6f,670,724,367.2f,1560)]
        [TestCase(2560,1440,1792,364,-1115.8f,904,976,489.6f,2200)]
        public void OrderingAndPublicBrowserRetainLegacyGeometry(float width,float height,float actionWidth,float right,
            float top,float maxHeight,float priorityHeight,float browserY,float browserWidth)
        {
            foreach(bool opening in new[]{false,true}){
                var plan=strategy.Resolve(new GameplayLayoutContext(width,height,opening,false,true));
                Assert.That(plan.ActionViewportWidth,Is.EqualTo(actionWidth).Within(.002));
                Assert.That(plan.ActionViewportRight,Is.EqualTo(right).Within(.002));
                Assert.That(plan.ActionViewportTop,Is.EqualTo(top).Within(.002));Assert.That(plan.ActionViewportBottom,Is.Null);
                Assert.That(plan.ActionMaxHeight,Is.EqualTo(maxHeight).Within(.002));
                Assert.That(plan.PriorityMaxHeight,Is.EqualTo(priorityHeight).Within(.002));
                RectIs(plan.PublicZoneBounds,180,browserY,browserWidth,259);
            }
        }
        [Test] public void LogicalAdaptersUseTheResolvedPlanWithoutOwningCards()
        {
            var plan=strategy.Resolve(new GameplayLayoutContext(1920,1080,false,false,false));
            Assert.That(new GameplayHudLayoutAdapter(GameplayLayoutSlot.Hand).Bounds(plan),Is.EqualTo(plan.HandBounds));
            Assert.That(new GameplayHudLayoutAdapter(GameplayLayoutSlot.GameStack).Bounds(plan),Is.EqualTo(plan.StackBounds));
            RectIs(new GameplayHudLayoutAdapter(GameplayLayoutSlot.Battlefield).Bounds(plan),280,78,1616,830);
        }
    }
}

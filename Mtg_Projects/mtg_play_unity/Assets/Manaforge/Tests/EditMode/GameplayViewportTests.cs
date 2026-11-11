using System;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayViewportTests
    {
        [TestCase(1024,768)] [TestCase(1280,720)] [TestCase(1366,768)]
        [TestCase(1920,1080)] [TestCase(2560,1440)] [TestCase(3440,1440)]
        public void HeaderBodyAndGripsUseOneGeometryInsideTheViewport(int width,int height)
        {
            var viewport=new GameplayViewportContext(new Rect(0,0,width,height));Assert.That(viewport.SupportsCustomization,Is.True);
            foreach(float x in new[]{-100f,0,width*.5f,width+50})foreach(float y in new[]{-100f,0,height*.5f,height+50}){
                var geometry=GameplayDrawerGeometry.Resolve(new Rect(x,y,720,30),900,viewport);var header=geometry.Header;
                Assert.That(header.xMin,Is.GreaterThanOrEqualTo(0));Assert.That(header.yMin,Is.GreaterThanOrEqualTo(0));
                Assert.That(header.xMax,Is.LessThanOrEqualTo(width));Assert.That(header.yMax,Is.LessThanOrEqualTo(height));
                float bodyTop=geometry.BodyBelow?header.y+32:header.y-32-geometry.BodyHeight;
                Assert.That(bodyTop,Is.GreaterThanOrEqualTo(0));Assert.That(bodyTop+geometry.BodyHeight,Is.LessThanOrEqualTo(height));
                var grip=header.position+geometry.GripPosition;Assert.That(grip.x,Is.GreaterThanOrEqualTo(0));Assert.That(grip.y,Is.GreaterThanOrEqualTo(0));
                Assert.That(grip.x+48,Is.LessThanOrEqualTo(width));Assert.That(grip.y+28,Is.LessThanOrEqualTo(height));
            }
        }
        [TestCase(1024,768)] [TestCase(1280,720)] [TestCase(1366,768)] [TestCase(1920,1080)] [TestCase(2560,1440)] [TestCase(3440,1440)]
        public void DesktopScaleRetainsSupportedUiBounds(int width,int height)
        {
            float scale=GameplayViewportContext.ScaleForPixels(new Vector2(width,height));
            Assert.That(scale,Is.GreaterThanOrEqualTo(1));Assert.That(new GameplayViewportContext(new Rect(0,0,width/scale,height/scale),scale).SupportsCustomization,Is.True);
        }
        [TestCase(800,600)] [TestCase(1024,720)] [TestCase(1280,600)]
        public void BelowSupportedProfilesDisablesEditingWithoutInventingScreenPixels(int width,int height)
        {Assert.That(new GameplayViewportContext(new Rect(0,0,width,height),2).SupportsCustomization,Is.False);}
        [Test] public void ScaleChangesAreDetectedWithoutChangingLogicalGeometry()
        {
            var one=new GameplayViewportContext(new Rect(0,0,1280,720),1);var two=new GameplayViewportContext(one.Bounds,2);
            Assert.That(one.Equals(two),Is.False);Assert.That(GameplayDrawerGeometry.Resolve(new Rect(1200,650,300,30),400,one).Header,
                Is.EqualTo(GameplayDrawerGeometry.Resolve(new Rect(1200,650,300,30),400,two).Header));
            Assert.Throws<ArgumentException>(()=>new GameplayViewportContext(new Rect(0,0,float.NaN,720)));
            Assert.Throws<ArgumentException>(()=>new GameplayViewportContext(one.Bounds,0));
        }
    }
}

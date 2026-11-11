using System;
using System.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class ContainerLayoutTests
    {
        private const GameplayHudCapabilities All=GameplayHudCapabilities.Move|GameplayHudCapabilities.Resize|GameplayHudCapabilities.Dock|GameplayHudCapabilities.ConvertDrawer;
        private static ContainerConstraints Limits(GameplayHudCapabilities caps=All,bool host=true,string[] targets=null)
            =>new ContainerConstraints(new Vector2(180,120),new Vector2(900,700),caps,host,targets);
        private static ContainerLayoutController Model()
        {
            var c=new ContainerLayoutController(new Vector2(1000,600));
            c.Register(new ContainerLayoutState("a",new Rect(.1f,.1f,.2f,.3f)),Limits());
            c.Register(new ContainerLayoutState("b",new Rect(.5f,.4f,.2f,.3f)),Limits());return c;
        }
        [Test] public void FloatingGeometryScalesAndConstraintsPreserveScrollableMinimums()
        {
            var c=Model();Assert.That(c.Resolved["a"],Is.EqualTo(new Rect(100,60,200,180)));
            c.SetViewport(new Vector2(2000,1200));Assert.That(c.Resolved["a"],Is.EqualTo(new Rect(200,120,400,360)));
            c.SetViewport(new Vector2(100,80));Assert.That(c.Resolved["a"].size,Is.EqualTo(new Vector2(180,120)));
            Assert.That(c.Resolved["a"].position,Is.EqualTo(Vector2.zero));Assert.That(c.Resolved.Extent.x,Is.GreaterThanOrEqualTo(180));
            Assert.That(c.Resolved.Extent.y,Is.GreaterThanOrEqualTo(120));
        }
        [TestCase(ContainerDockEdge.Left,0,0)] [TestCase(ContainerDockEdge.Right,800,0)]
        [TestCase(ContainerDockEdge.Top,0,0)] [TestCase(ContainerDockEdge.Bottom,0,420)]
        public void ViewportDockingUsesEachEdgeAndUndockRetainsFloatingRect(ContainerDockEdge edge,float x,float y)
        {
            var c=Model();var original=c.State("a").FloatingRect;
            Assert.That(c.TrySet(new ContainerLayoutState("a",original,edge:edge)),Is.True);
            Assert.That(c.Resolved["a"].position,Is.EqualTo(new Vector2(x,y)));
            Assert.That(c.Undock("a"),Is.True);Assert.That(c.State("a").FloatingRect,Is.EqualTo(original));
            Assert.That(c.Resolved["a"].position,Is.EqualTo(new Vector2(100,60)));
        }
        [Test] public void DockRailsReorderAtomicallyAndScrollInsteadOfShrinking()
        {
            var c=Model();foreach(string id in c.Ids.ToArray())c.TrySet(new ContainerLayoutState(id,c.State(id).FloatingRect,edge:ContainerDockEdge.Left));
            Assert.That(c.Resolved["a"].y,Is.Zero);Assert.That(c.Resolved["b"].y,Is.EqualTo(188));
            Assert.That(c.Reorder("b",-1),Is.True);Assert.That(c.Resolved["b"].y,Is.Zero);Assert.That(c.Resolved["a"].y,Is.EqualTo(188));
            c.SetViewport(new Vector2(100,80));Assert.That(c.Resolved.Extent.y,Is.GreaterThan(240));
            Assert.That(c.Resolved["a"].height,Is.EqualTo(120));
        }
        [Test] public void ContainerDockCyclesRejectWithoutChangingAnyCommittedState()
        {
            var c=Model();Assert.That(c.TrySet(new ContainerLayoutState("a",c.State("a").FloatingRect,dockTarget:"b",edge:ContainerDockEdge.Right)),Is.True);
            Assert.That(c.Resolved["a"].x,Is.EqualTo(708));
            var before=c.State("b");var bounds=c.Resolved["b"];
            Assert.That(c.TrySet(new ContainerLayoutState("b",before.FloatingRect,dockTarget:"a",edge:ContainerDockEdge.Bottom)),Is.False);
            Assert.That(c.State("b"),Is.SameAs(before));Assert.That(c.Resolved["b"],Is.EqualTo(bounds));
            Assert.That(c.TrySet(new ContainerLayoutState("a",before.FloatingRect,dockTarget:"a",edge:ContainerDockEdge.Left)),Is.False);
        }
        [Test] public void RemovingTargetFloatsDependentsAtTheirLastResolvedPosition()
        {
            var c=Model();c.TrySet(new ContainerLayoutState("a",c.State("a").FloatingRect,dockTarget:"b",edge:ContainerDockEdge.Right));
            var before=c.Resolved["a"];c.Remove("b");Assert.That(c.State("a").Edge,Is.EqualTo(ContainerDockEdge.None));
            Assert.That(c.Resolved["a"],Is.EqualTo(before));
        }
        [Test] public void InvalidNumbersTargetsAndUnsupportedOperationsRejectAtomically()
        {
            var c=Model();var initial=c.State("a");
            foreach(float bad in new[]{float.NaN,float.PositiveInfinity,float.NegativeInfinity})
                Assert.That(c.TrySet(new ContainerLayoutState("a",new Rect(bad,0,.2f,.3f))),Is.False);
            Assert.That(c.TrySet(new ContainerLayoutState("a",initial.FloatingRect,dockTarget:"missing",edge:ContainerDockEdge.Left)),Is.False);
            Assert.That(c.TrySet(new ContainerLayoutState(null,initial.FloatingRect)),Is.False);
            Assert.That(c.State("a"),Is.SameAs(initial));
            c.Register(new ContainerLayoutState("fixed",new Rect(0,0,.2f,.3f)),Limits(GameplayHudCapabilities.None,false));
            Assert.That(c.TrySet(new ContainerLayoutState("fixed",new Rect(.2f,.2f,.2f,.3f))),Is.False);
            Assert.That(c.TrySet(new ContainerLayoutState("fixed",new Rect(0,0,.4f,.3f))),Is.False);
            Assert.That(c.TrySet(new ContainerLayoutState("fixed",new Rect(0,0,.2f,.3f),ContainerMode.Drawer)),Is.False);
            Assert.That(c.TrySet(new ContainerLayoutState("a",initial.FloatingRect,dockTarget:"fixed",edge:ContainerDockEdge.Left)),Is.False);
            c.Register(new ContainerLayoutState("limited",new Rect(0,0,.2f,.3f)),Limits(All,false,new[]{"$viewport"}));
            Assert.That(c.TrySet(new ContainerLayoutState("limited",new Rect(0,0,.2f,.3f),dockTarget:"b",edge:ContainerDockEdge.Left)),Is.False);
        }
        [Test] public void PreviewDoesNotCommitOrNotifyAndInvalidRegistrationDoesNotLeaveEntries()
        {
            var c=Model();int changes=0;c.Changed+=()=>changes++;
            var old=c.State("a");var preview=c.Preview(new ContainerLayoutState("a",new Rect(.3f,.2f,.4f,.3f)));
            Assert.That(preview["a"].x,Is.EqualTo(300));Assert.That(c.State("a"),Is.SameAs(old));Assert.That(changes,Is.Zero);
            Assert.Throws<ArgumentException>(()=>c.Register(new ContainerLayoutState("bad",new Rect(0,0,float.NaN,.2f)),Limits()));
            Assert.That(c.Ids,Does.Not.Contain("bad"));Assert.That(changes,Is.Zero);
        }
    }
}

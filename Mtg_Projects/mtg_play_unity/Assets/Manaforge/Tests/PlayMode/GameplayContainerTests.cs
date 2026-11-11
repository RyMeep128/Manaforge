using System;
using System.Collections;
using System.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayContainerTests
    {
        private static UIDocument Document(out GameObject node,out PanelSettings settings)
        {
            node=new GameObject("Synthetic container workspace");settings=ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;return doc;
        }
        private static void Down(VisualElement handle)
        {
            using var ev=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=handle.worldBound.center});
            ev.target=handle;handle.SendEvent(ev);
        }
        [UnityTest] public IEnumerator ConversionPreservesContentStateAndDrawerFocusPolicy()
        {
            var doc=Document(out var node,out var settings);using var workspace=new GameplayLayoutWorkspace();
            workspace.style.width=1000;workspace.style.height=650;doc.rootVisualElement.Add(workspace);
            try{
                for(int i=0;i<5;i++)yield return null;var shell=workspace.Shell("drawer");var field=shell.BorrowedContent.Q<TextField>();
                field.value="Kept across conversions";field.Focus();yield return null;
                var original=shell.BorrowedContent;var state=workspace.Controller.State("drawer");
                workspace.Controller.TrySet(new ContainerLayoutState("drawer",state.FloatingRect,ContainerMode.Drawer));yield return null;
                Assert.That(shell.Drawer.Content.Contains(original),Is.True);Assert.That(field.value,Is.EqualTo("Kept across conversions"));
                shell.Drawer.SetReducedMotion(true);shell.Drawer.SetOpen(false);yield return null;
                Assert.That(field.pickingMode,Is.EqualTo(PickingMode.Ignore));Assert.That(field.focusable,Is.False);
                Assert.That(doc.rootVisualElement.panel.focusController.focusedElement,Is.SameAs(shell.Drawer.Tab));
                workspace.Controller.TrySet(new ContainerLayoutState("drawer",state.FloatingRect));yield return null;
                Assert.That(field.pickingMode,Is.EqualTo(PickingMode.Position));
                workspace.Controller.TrySet(new ContainerLayoutState("drawer",state.FloatingRect,ContainerMode.Drawer));yield return null;
                Assert.That(shell.Drawer.IsOpen,Is.False);Assert.That(shell.BorrowedContent,Is.SameAs(original));
                workspace.Dispose();Assert.That(original.parent,Is.Null);Assert.That(field.pickingMode,Is.EqualTo(PickingMode.Position));
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [Test] public void GesturePreviewCommitCancelAndResizeUseOneTransaction()
        {
            using var workspace=new GameplayLayoutWorkspace();var c=workspace.Controller;var old=c.State("panel");
            Assert.That(workspace.Gestures.Begin("panel",new Vector2(100,100)),Is.True);
            workspace.Gestures.Move(new Vector2(105,105));Assert.That(workspace.Gestures.Commit(),Is.False);
            workspace.Gestures.Begin("panel",new Vector2(100,100));workspace.Gestures.Move(new Vector2(160,150));
            Assert.That(c.State("panel"),Is.SameAs(old));workspace.Gestures.Cancel();Assert.That(c.State("panel"),Is.SameAs(old));
            workspace.Gestures.Begin("panel",new Vector2(100,100));workspace.Gestures.Move(new Vector2(160,150));
            Assert.That(workspace.Gestures.Commit(),Is.True);Assert.That(c.State("panel").FloatingRect.x,Is.GreaterThan(old.FloatingRect.x));
            workspace.Gestures.Begin("panel",Vector2.zero,true,Vector2.one);workspace.Gestures.Move(new Vector2(-10000,-10000));
            workspace.Gestures.Commit();Assert.That(c.Resolved["panel"].size,Is.EqualTo(c.Constraints("panel").Minimum));
            Assert.That(workspace.Gestures.Begin("restricted",Vector2.zero),Is.False);
            workspace.Gestures.Begin("panel",Vector2.zero);c.SetViewport(new Vector2(500,400));Assert.That(workspace.Gestures.IsActive,Is.False);
        }
        [UnityTest] public IEnumerator PointerCaptureEscapeDetachAndDisposalLeaveNoGesture()
        {
            var doc=Document(out var node,out var settings);using var workspace=new GameplayLayoutWorkspace();
            workspace.style.width=1000;workspace.style.height=650;doc.rootVisualElement.Add(workspace);
            try{
                for(int i=0;i<5;i++)yield return null;var handle=workspace.Shell("panel").MoveHandle;
                var state=workspace.Controller.State("panel");Down(handle);yield return null;
                Assert.That(workspace.Gestures.IsActive,Is.True);Assert.That(handle.HasPointerCapture(PointerId.mousePointerId),Is.True);
                using(var esc=KeyDownEvent.GetPooled('\0',KeyCode.Escape,EventModifiers.None)){esc.target=handle;handle.SendEvent(esc);}yield return null;
                Assert.That(workspace.Gestures.IsActive,Is.False);Assert.That(handle.HasPointerCapture(PointerId.mousePointerId),Is.False);
                Down(handle);yield return null;handle.ReleasePointer(PointerId.mousePointerId);yield return null;
                Assert.That(workspace.Gestures.IsActive,Is.False);Assert.That(workspace.Controller.State("panel"),Is.SameAs(state));
                Down(handle);yield return null;workspace.Shell("panel").RemoveFromHierarchy();yield return null;
                Assert.That(workspace.Gestures.IsActive,Is.False);
                workspace.Canvas.Add(workspace.Shell("panel"));yield return null;Down(handle);yield return null;
                workspace.Remove("panel");yield return null;Assert.That(workspace.Gestures.IsActive,Is.False);
                Down(handle);Assert.That(workspace.Gestures.IsActive,Is.False,"Removed handles no longer have gesture callbacks");
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator EmbeddedControlsAndKeyboardToolbarDoNotStartDrags()
        {
            var doc=Document(out var node,out var settings);using var workspace=new GameplayLayoutWorkspace();
            workspace.style.width=1000;workspace.style.height=650;doc.rootVisualElement.Add(workspace);
            try{
                for(int i=0;i<5;i++)yield return null;var field=workspace.Shell("panel").BorrowedContent.Q<TextField>();Down(field);
                Assert.That(workspace.Gestures.IsActive,Is.False);
                var before=workspace.Controller.State("panel").FloatingRect;var move=workspace.Query<Button>().ToList().First(b=>b.text=="Move →");
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=move;move.SendEvent(submit);}
                Assert.That(workspace.Controller.State("panel").FloatingRect.x,Is.EqualTo(before.x+8/workspace.Controller.Viewport.x).Within(.0001));
                var selector=workspace.Q<PopupField<string>>("layout-component-selector");selector.value="restricted";
                Assert.That(move.enabledSelf,Is.False);Assert.That(workspace.Query<Button>().ToList().First(b=>b.text=="Panel / drawer").enabledSelf,Is.False);
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [Test] public void ExtraComponentUsesGenericShellRegistryAndGestureInfrastructure()
        {
            var c=new ContainerLayoutController(new Vector2(1000,600));var canvas=new VisualElement();using var registry=new GameplayHudRegistry();
            var limits=new ContainerConstraints(new Vector2(180,120),new Vector2(800,600),GameplayHudCapabilities.Move);
            c.Register(new ContainerLayoutState("extra",new Rect(.1f,.1f,.3f,.3f)),limits);var content=new TextField{value="Borrowed"};
            using var shell=new GameplayContainerShell("extra","Extra",content,limits);canvas.Add(shell);
            using var registration=registry.Register(new GameplayHudDescriptor("extra","Extra","workspace",limits.Capabilities),shell);
            using var gestures=new ContainerGestureController(c,canvas,result=>shell.Apply(result["extra"],c.State("extra"),limits,c.Viewport));
            using var attachment=gestures.Attach(shell);gestures.Begin("extra",Vector2.zero);gestures.Move(new Vector2(80,80));gestures.Commit();
            Assert.That(c.Resolved["extra"].x,Is.EqualTo(180));attachment.Dispose();shell.Dispose();
            Assert.That(content.value,Is.EqualTo("Borrowed"));Assert.That(content.parent,Is.Null);
        }
    }
}

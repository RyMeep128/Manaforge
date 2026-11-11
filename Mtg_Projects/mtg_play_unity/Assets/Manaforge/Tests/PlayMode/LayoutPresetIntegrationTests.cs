using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class LayoutPresetIntegrationTests
    {
        private sealed class ObservedStore : ILayoutPresetStore
        {
            internal readonly MemoryLayoutPresetStore Inner=new MemoryLayoutPresetStore();
            internal int Writes;internal bool Fail;
            public Task<PresetStoreResult> ReadAsync(CancellationToken cancellation=default)=>Inner.ReadAsync(cancellation);
            public Task<PresetStoreResult> WriteAsync(LayoutPresetLibrary library,string revision,CancellationToken cancellation=default)
            {Writes++;return Fail?Task.FromResult(new PresetStoreResult(PresetStoreStatus.IoError)):Inner.WriteAsync(library,revision,cancellation);}
        }
        [Test] public void BatchApplicationValidatesTheProspectiveGraphAndNotItsIntermediateStates()
        {
            var controller=new ContainerLayoutController(new Vector2(1000,600));var caps=GameplayHudCapabilities.Move|GameplayHudCapabilities.Resize|GameplayHudCapabilities.Dock;
            var limits=new ContainerConstraints(new Vector2(180,120),new Vector2(900,700),caps,true);
            var rect=new Rect(.1f,.1f,.3f,.4f);controller.Register(new ContainerLayoutState("a",rect),limits);controller.Register(new ContainerLayoutState("b",rect),limits);
            controller.TrySet(new ContainerLayoutState("a",rect,dockTarget:"b",edge:ContainerDockEdge.Right));int notifications=0;controller.Changed+=()=>notifications++;
            Assert.That(controller.TryApplyLayout(new[]{new ContainerLayoutState("b",rect,dockTarget:"a",edge:ContainerDockEdge.Bottom),new ContainerLayoutState("a",rect)}),Is.True);
            Assert.That(notifications,Is.EqualTo(1));var before=controller.State("a");
            Assert.That(controller.TryApplyLayout(new[]{new ContainerLayoutState("a",rect,dockTarget:"b",edge:ContainerDockEdge.Left),controller.State("b")}),Is.False);
            Assert.That(controller.State("a"),Is.SameAs(before));Assert.That(notifications,Is.EqualTo(1));
        }
        [Test] public void StableKeysExcludeRuntimeIdentityAndReconcileMissingTargetsCapabilitiesAndAvailability()
        {
            using var workspace=new GameplayLayoutWorkspace();var binding=workspace.PresetBinding;
            var saved=binding.Capture("custom","Custom");var entries=saved.Components.ToDictionary(e=>e.Key,e=>e.Value);
            entries["fixture.panel"]=new HudComponentSnapshot(new Rect(.2f,.2f,.4f,.5f),ContainerMode.Panel,"unknown.host",ContainerDockEdge.Right,0,true);
            entries["fixture.restricted"]=new HudComponentSnapshot(new Rect(.8f,.8f,.5f,.5f),ContainerMode.Drawer,null,ContainerDockEdge.None,0,false);
            var application=binding.Prepare(new HudLayoutPreset("custom","Custom",entries));Assert.That(application.Adjustments.Count,Is.EqualTo(2));
            Assert.That(binding.Apply(application),Is.True);Assert.That(workspace.Controller.State("panel").Edge,Is.EqualTo(ContainerDockEdge.None));
            Assert.That(workspace.Controller.State("restricted").Mode,Is.EqualTo(ContainerMode.Panel));
            var registration=workspace.Registry.Find("fixture/panel");registration.Available=false;var before=workspace.Controller.State("panel");
            Assert.That(binding.Apply(binding.Prepare(binding.BuiltInDefault())),Is.True);Assert.That(workspace.Controller.State("panel"),Is.SameAs(before));
            var plain=new VisualElement();workspace.Registry.Register(new GameplayHudDescriptor("session-secret","Private seat","rail"),plain);
            string json=binding.Capture("private-check","Private check",saved).ToJson().ToString();Assert.That(json,Does.Not.Contain("session-secret"));
            Assert.That(json,Does.Contain("fixture.panel"));
            Assert.Throws<InvalidOperationException>(()=>workspace.Registry.Register(new GameplayHudDescriptor("duplicate","Duplicate","rail",presetKey:"fixture.panel"),plain));
        }
        [TestCase(1280,720)] [TestCase(1366,768)] [TestCase(1920,1080)] [TestCase(2560,1440)]
        public void PresetsRestoreNormalizedIntentAtDifferentViewportSizes(int width,int height)
        {
            using var workspace=new GameplayLayoutWorkspace();var state=workspace.Controller.State("panel");
            workspace.Controller.TrySet(new ContainerLayoutState("panel",new Rect(.8f,.8f,.25f,.38f)));
            var preset=workspace.PresetBinding.Capture("viewport","Viewport");workspace.Controller.SetViewport(new Vector2(width,height));
            Assert.That(workspace.PresetBinding.Apply(workspace.PresetBinding.Prepare(preset)),Is.True);
            var bounds=workspace.Controller.Resolved["panel"];
            Assert.That(workspace.Controller.State("panel").FloatingRect.x,Is.EqualTo(.8f));
            Assert.That(bounds.x,Is.GreaterThanOrEqualTo(0));Assert.That(bounds.y,Is.GreaterThanOrEqualTo(0));
            Assert.That(bounds.xMax,Is.LessThanOrEqualTo(width+.01f));Assert.That(bounds.yMax,Is.LessThanOrEqualTo(height+.01f));
        }
        [UnityTest] public IEnumerator ExplicitSaveLoadRenameDeleteAndRestartPreserveDrawerPreferences()
        {
            var store=new ObservedStore();string id;
            using(var first=new GameplayLayoutWorkspace(store)){
                yield return new WaitUntil(()=>first.Presets.Initialization.IsCompleted);
                first.Nudge(8,0,false);Assert.That(first.Presets.Dirty,Is.True);Assert.That(store.Writes,Is.Zero);
                var old=first.Controller.State("drawer");first.Controller.TrySet(new ContainerLayoutState("drawer",old.FloatingRect,ContainerMode.Drawer));
                first.Shell("drawer").Drawer.SetOpen(false);
                var save=first.Presets.SaveAsync("Compact",true);yield return new WaitUntil(()=>save.IsCompleted);Assert.That(save.Result,Is.True);
                id=first.Presets.SelectedId;Assert.That(first.Presets.Dirty,Is.False);
                first.Nudge(8,0,false);Assert.That(first.Presets.RestoreDefault(),Is.False);Assert.That(first.Presets.HasPendingConfirmation,Is.True);
                var cancel=first.Q<Button>("preset-cancel");using(var ev=NavigationSubmitEvent.GetPooled()){ev.target=cancel;cancel.SendEvent(ev);}
                Assert.That(first.Presets.Dirty,Is.True);
                Assert.That(first.Presets.RestoreDefault(true),Is.True);Assert.That(first.Presets.Dirty,Is.False);
                var load=first.Presets.LoadAsync(id);yield return new WaitUntil(()=>load.IsCompleted);Assert.That(load.Result,Is.True);
            }
            using(var reopened=new GameplayLayoutWorkspace(store)){
                yield return new WaitUntil(()=>reopened.Presets.Initialization.IsCompleted);
                Assert.That(reopened.Presets.SelectedId,Is.EqualTo(id));Assert.That(reopened.Controller.State("drawer").Mode,Is.EqualTo(ContainerMode.Drawer));
                Assert.That(reopened.Shell("drawer").DrawerExpandedPreference,Is.False);
                var rename=reopened.Presets.RenameAsync("Renamed");yield return new WaitUntil(()=>rename.IsCompleted);Assert.That(rename.Result,Is.True);
                var pending=reopened.Presets.DeleteAsync();yield return new WaitUntil(()=>pending.IsCompleted);Assert.That(reopened.Presets.HasPendingConfirmation,Is.True);
                var button=reopened.Q<Button>("preset-confirm");using(var ev=NavigationSubmitEvent.GetPooled()){ev.target=button;button.SendEvent(ev);}
                yield return new WaitUntil(()=>!reopened.Presets.Busy);
                Assert.That(reopened.Presets.SelectedId,Is.Null);Assert.That(reopened.Presets.Dirty,Is.True);
            }
        }
        [UnityTest] public IEnumerator FailedLoadLeavesLayoutAndUnsavedWorkIntact()
        {
            var store=new ObservedStore();using var workspace=new GameplayLayoutWorkspace(store);
            yield return new WaitUntil(()=>workspace.Presets.Initialization.IsCompleted);
            var save=workspace.Presets.SaveAsync("Saved",true);yield return new WaitUntil(()=>save.IsCompleted);string id=workspace.Presets.SelectedId;
            workspace.Nudge(24,0,false);var before=workspace.Controller.State("panel");store.Fail=true;
            var load=workspace.Presets.LoadAsync(id,true);yield return new WaitUntil(()=>load.IsCompleted);
            Assert.That(load.Result,Is.False);Assert.That(workspace.Controller.State("panel"),Is.SameAs(before));Assert.That(workspace.Presets.Dirty,Is.True);
            Assert.That(workspace.Presets.LastStatus,Is.EqualTo(PresetStoreStatus.IoError));
        }
        [UnityTest] public IEnumerator DeletingActivePresetKeepsDormantDataForSaveAs()
        {
            var store=new MemoryLayoutPresetStore();HudLayoutPreset original;
            using(var source=new GameplayLayoutWorkspace())original=source.PresetBinding.Capture("source","Source");
            var entries=original.Components.ToDictionary(e=>e.Key,e=>e.Value);entries["future.component"]=entries["fixture.panel"];
            var read=store.ReadAsync().Result;
            store.WriteAsync(read.Library.Save(new HudLayoutPreset("source","Source",entries)),read.Revision).GetAwaiter().GetResult();
            using var workspace=new GameplayLayoutWorkspace(store);yield return new WaitUntil(()=>workspace.Presets.Initialization.IsCompleted);
            var delete=workspace.Presets.DeleteAsync(true);yield return new WaitUntil(()=>delete.IsCompleted);Assert.That(delete.Result,Is.True);
            var save=workspace.Presets.SaveAsync("Copy",true);yield return new WaitUntil(()=>save.IsCompleted);Assert.That(save.Result,Is.True);
            Assert.That(store.ReadAsync().Result.Library.Find(workspace.Presets.SelectedId).Components.ContainsKey("future.component"),Is.True);
        }
        private sealed class DelayedStore : ILayoutPresetStore
        {
            internal readonly TaskCompletionSource<PresetStoreResult> Read=new TaskCompletionSource<PresetStoreResult>();
            public Task<PresetStoreResult> ReadAsync(CancellationToken cancellation=default)=>Read.Task;
            public Task<PresetStoreResult> WriteAsync(LayoutPresetLibrary library,string revision,CancellationToken cancellation=default)=>Task.FromResult(new PresetStoreResult(PresetStoreStatus.Ready,library,"new"));
        }
        [UnityTest] public IEnumerator BusyControlsAndUnsupportedVersionsDoNotWriteOrMutateTheFile()
        {
            var store=new DelayedStore();using var workspace=new GameplayLayoutWorkspace(store);
            Assert.That(workspace.Presets.Busy,Is.True);Assert.That(workspace.Canvas.enabledSelf,Is.False);
            var attempt=workspace.Presets.SaveAsync("Blocked",true);Assert.That(attempt.Result,Is.False);
            store.Read.SetResult(new PresetStoreResult(PresetStoreStatus.UnsupportedVersion,LayoutPresetLibrary.Empty,"newer"));
            yield return new WaitUntil(()=>workspace.Presets.Initialization.IsCompleted);
            Assert.That(workspace.Presets.Busy,Is.False);Assert.That(workspace.Canvas.enabledSelf,Is.True);
            var save=workspace.Presets.SaveAsync("Blocked",true);Assert.That(save.Result,Is.False);
            Assert.That(workspace.Presets.RestoreDefault(true),Is.True);
        }
    }
}

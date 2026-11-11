using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using TrackedCommand=Manaforge.Play.Protocol.TrackedCommand;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class LiveHudLayoutEditorTests
    {
        private sealed class ObservedStore : ILayoutPresetStore
        {
            internal readonly MemoryLayoutPresetStore Inner=new MemoryLayoutPresetStore();
            internal int Writes;internal bool Fail;internal TaskCompletionSource<PresetStoreResult> DelayedRead;
            public Task<PresetStoreResult> ReadAsync(CancellationToken cancellation=default)=>DelayedRead?.Task??Inner.ReadAsync(cancellation);
            public Task<PresetStoreResult> WriteAsync(LayoutPresetLibrary library,string revision,CancellationToken cancellation=default)
            {Writes++;return Fail?Task.FromResult(new PresetStoreResult(PresetStoreStatus.IoError)):Inner.WriteAsync(library,revision,cancellation);}
        }
        private sealed class Harness : IDisposable
        {
            internal readonly VisualElement Root=new VisualElement(),Canvas=new VisualElement();
            internal readonly GameplayHudRegistry Registry=new GameplayHudRegistry();
            internal readonly Dictionary<string,GameplayDrawer> Drawers=new Dictionary<string,GameplayDrawer>();
            internal readonly ObservedStore Store;
            internal readonly HudLayoutEditor Editor;
            internal bool Gated,Blocked;
            internal int Inputs;
            internal Harness(ObservedStore store=null)
            {
                Store=store??new ObservedStore();Root.Add(Canvas);Canvas.style.width=1280;Canvas.style.height=720;
                foreach(var id in new[]{GameplayHudIds.Priority,GameplayHudIds.Actions,GameplayHudIds.Zones,GameplayHudIds.Commanders}){
                    var drawer=new GameplayDrawer(id,open:true){name=id};drawer.style.position=Position.Absolute;drawer.style.left=30;drawer.style.top=80;drawer.style.width=260;drawer.style.height=30;
                    drawer.Content.Add(new Button(()=>Inputs++){text="Existing command"});Canvas.Add(drawer);Drawers.Add(id,drawer);
                    Registry.Register(new GameplayHudDescriptor(id,id,id,GameplayHudCapabilities.Drawer,presetKey:"hud."+id),drawer,available:id!=GameplayHudIds.Commanders);
                }
                Editor=new HudLayoutEditor(Root,Canvas,Registry,Drawers.Select(p=>(p.Key,p.Key,p.Value)),Store,()=>{},()=>{},value=>Gated=value,()=>Blocked);
                Editor.Observe("session","viewer",false,false);
            }
            public void Dispose(){Editor.Dispose();foreach(var drawer in Drawers.Values)drawer.Dispose();Registry.Dispose();}
        }
        private static void Capture(RenderTexture target,string name)
        {
            string folder=Path.Combine(Application.dataPath,"../Artifacts/LayoutRecovery");Directory.CreateDirectory(folder);
            var previous=RenderTexture.active;var pixels=new Texture2D(target.width,target.height,TextureFormat.RGBA32,false);
            try{RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,target.width,target.height),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(folder,name+".png"),pixels.EncodeToPNG());}
            finally{RenderTexture.active=previous;UnityEngine.Object.Destroy(pixels);}
        }
        [Test] public void DraftApplyCancelAndInterruptionAreSeparateFromPersistence()
        {
            using var h=new Harness();var e=h.Editor;Assert.That(e.Open(),Is.True);Assert.That(h.Gated,Is.True);
            var before=e.Controller.State(GameplayHudIds.Actions).FloatingRect;e.Adjust(GameplayHudIds.Actions,-48,-16,false);var edited=e.Controller.State(GameplayHudIds.Actions).FloatingRect;
            Assert.That(edited,Is.Not.EqualTo(before));Assert.That(e.NeedsApply,Is.True);Assert.That(h.Store.Writes,Is.Zero);
            e.BeforeDecisionTick(true);Assert.That(e.IsEditing,Is.False);Assert.That(e.HasRetainedDraft,Is.True);Assert.That(h.Gated,Is.False);
            Assert.That(e.Controller.State(GameplayHudIds.Actions).FloatingRect,Is.EqualTo(before));
            h.Blocked=true;Assert.That(e.Open(),Is.False);h.Blocked=false;Assert.That(e.Open(),Is.True);
            Assert.That(e.Controller.State(GameplayHudIds.Actions).FloatingRect,Is.EqualTo(edited));Assert.That(e.Apply(),Is.True);Assert.That(e.NeedsApply,Is.False);
            e.Adjust(GameplayHudIds.Actions,24,0,false);e.Cancel();Assert.That(h.Gated,Is.False);Assert.That(e.Controller.State(GameplayHudIds.Actions).FloatingRect,Is.EqualTo(edited));Assert.That(h.Store.Writes,Is.Zero);
            e.Open();e.Adjust(GameplayHudIds.Actions,-16,0,false);e.Suspend();e.EndSession();Assert.That(e.HasRetainedDraft,Is.False);Assert.That(e.CanOpen,Is.False);
        }
        [Test] public void DefaultIsStagedAndCapabilityMetadataMatchesOnlySupportedOperations()
        {
            using var h=new Harness();var e=h.Editor;var descriptor=h.Registry.Find(GameplayHudIds.Actions).Descriptor;
            Assert.That(descriptor.Capabilities.HasFlag(GameplayHudCapabilities.Resize),Is.True);Assert.That(descriptor.Capabilities.HasFlag(GameplayHudCapabilities.ConvertDrawer),Is.False);
            e.Open();e.Dock(GameplayHudIds.Actions,ContainerDockEdge.Left);e.Apply();e.RestoreDefault();
            Assert.That(e.OwnsGeometry(GameplayHudIds.Actions),Is.False);Assert.That(e.NeedsApply,Is.True);e.Cancel();Assert.That(e.OwnsGeometry(GameplayHudIds.Actions),Is.True);
            e.Open();e.RestoreDefault();e.Apply();e.Cancel();Assert.That(e.OwnsGeometry(GameplayHudIds.Actions),Is.False);
            Assert.That(e.Controller.TrySet(new ContainerLayoutState(GameplayHudIds.Actions,new Rect(.1f,.2f,.3f,.4f),ContainerMode.Panel)),Is.False);
            e.Dispose();Assert.That(h.Registry.Find(GameplayHudIds.Actions).Container,Is.Null);Assert.That(h.Registry.Find(GameplayHudIds.Actions).Descriptor.Capabilities,Is.EqualTo(GameplayHudCapabilities.Drawer));
            Assert.That(h.Drawers[GameplayHudIds.Actions].parent,Is.SameAs(h.Canvas));
        }
        [UnityTest] public IEnumerator SaveRequiresApplyAndRestartRestoresOnlyExplicitOverrides()
        {
            var store=new ObservedStore();
            using(var h=new Harness(store)){
                yield return new WaitUntil(()=>h.Editor.Initialization.IsCompleted);h.Editor.Open();h.Editor.Adjust(GameplayHudIds.Actions,-64,0,false);
                var invalid=h.Editor.SaveAsync(true);yield return new WaitUntil(()=>invalid.IsCompleted);Assert.That(invalid.Result,Is.False);Assert.That(store.Writes,Is.Zero);
                h.Editor.Apply();var save=h.Editor.SaveAsync(true,"My layout");yield return new WaitUntil(()=>save.IsCompleted);Assert.That(save.Result,Is.True);
                var read=store.ReadAsync();yield return new WaitUntil(()=>read.IsCompleted);var preset=read.Result.Library.Presets.Single();
                Assert.That(preset.Components.Keys,Is.EquivalentTo(new[]{"hud.actions"}));Assert.That(read.Result.Library.LastSelectedId,Is.EqualTo(preset.Id));
            }
            using(var h=new Harness(store)){
                yield return new WaitUntil(()=>h.Editor.Initialization.IsCompleted);Assert.That(h.Editor.OwnsGeometry(GameplayHudIds.Actions),Is.True);Assert.That(h.Editor.OwnsGeometry(GameplayHudIds.Zones),Is.False);
                h.Editor.Open();h.Editor.RestoreDefault();h.Editor.Cancel();Assert.That(h.Editor.OwnsGeometry(GameplayHudIds.Actions),Is.True);
                store.Fail=true;h.Editor.Open();h.Editor.Adjust(GameplayHudIds.Actions,-16,0,false);h.Editor.Apply();var before=h.Editor.Controller.State(GameplayHudIds.Actions);
                var save=h.Editor.SaveAsync(false);yield return new WaitUntil(()=>save.IsCompleted);Assert.That(save.Result,Is.False);Assert.That(h.Editor.Controller.State(GameplayHudIds.Actions),Is.SameAs(before));
            }
        }
        [UnityTest] public IEnumerator DormantCommanderAndUnknownComponentsSurviveStartupAndSave()
        {
            var store=new ObservedStore();var read=store.ReadAsync();yield return new WaitUntil(()=>read.IsCompleted);
            var entries=new Dictionary<string,HudComponentSnapshot>{
                ["hud.commanders"]=new HudComponentSnapshot(new Rect(.3f,.2f,.4f,.5f),ContainerMode.Drawer,null,ContainerDockEdge.None,0,false),
                ["future.component"]=new HudComponentSnapshot(new Rect(.2f,.3f,.4f,.5f),ContainerMode.Panel,null,ContainerDockEdge.None,0,true)};
            var seed=store.WriteAsync(LayoutPresetLibrary.Empty.Save(new HudLayoutPreset("saved","Saved",entries)),read.Result.Revision);yield return new WaitUntil(()=>seed.IsCompleted);
            using var h=new Harness(store);yield return new WaitUntil(()=>h.Editor.Initialization.IsCompleted);
            h.Registry.Find(GameplayHudIds.Commanders).Available=true;h.Editor.AfterLegacyLayout();
            Assert.That(h.Editor.Controller.State(GameplayHudIds.Commanders).FloatingRect,Is.EqualTo(entries["hud.commanders"].FloatingRect));Assert.That(h.Drawers[GameplayHudIds.Commanders].IsOpen,Is.False);
            h.Editor.Open();h.Editor.Apply();var save=h.Editor.SaveAsync(false);yield return new WaitUntil(()=>save.IsCompleted);Assert.That(save.Result,Is.True);
            var final=store.ReadAsync();yield return new WaitUntil(()=>final.IsCompleted);Assert.That(final.Result.Library.Find("saved").Components.ContainsKey("future.component"),Is.True);
        }
        [UnityTest] public IEnumerator ExistingContentHierarchyInputAndFocusRemainOwnedByTheDrawer()
        {
            var node=new GameObject("Live drawer layout test");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            using var h=new Harness();document.rootVisualElement.Add(h.Root);var drawer=h.Drawers[GameplayHudIds.Actions];var content=drawer.Content;var command=content.Q<Button>();
            try{
                for(int i=0;i<5;i++)yield return null;h.Editor.AfterLegacyLayout();var originalParent=drawer.parent;var originalLeft=drawer.style.left;
                h.Editor.Open(command);h.Editor.Adjust(GameplayHudIds.Actions,-80,-60,false);h.Editor.Adjust(GameplayHudIds.Actions,40,48,true);yield return null;
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=command;command.SendEvent(submit);}Assert.That(h.Inputs,Is.Zero);
                Assert.That(drawer.Content,Is.SameAs(content));Assert.That(drawer.parent,Is.SameAs(originalParent));h.Editor.Cancel();yield return null;
                Assert.That(drawer.style.left,Is.EqualTo(originalLeft));Assert.That(h.Root.panel.focusController.focusedElement,Is.SameAs(command));
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=command;command.SendEvent(submit);}Assert.That(h.Inputs,Is.EqualTo(1));
                h.Editor.Open();h.Editor.Dispose();using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=command;command.SendEvent(submit);}Assert.That(h.Inputs,Is.EqualTo(2));
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator OptedInArenaKeepsLegacyPlacementAndMenuEntryUntilAnExplicitEdit()
        {
            var node=new GameObject("Live Arena layout integration");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            var root=document.rootVisualElement;root.style.width=1280;root.style.height=720;
            using var arena=new ArenaGameplayPresentation(root,capabilities:new GameplayPresentationCapabilities(privateLayout:true),layoutPresetStore:new MemoryLayoutPresetStore());
            var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();
            var snapshot=envelope["body"]["snapshot"];snapshot["turn"]=2;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["priority_player_id"]="one";snapshot["actions_complete"]=true;snapshot["decision"]["is_priority"]=true;snapshot["decision"]["options"]=new JArray();
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);using var host=new ViewerSessionHost(arena.Surface,peer.Bootstrap(),owner.Task,true);arena.Bind(host);
            using var menu=new GameplayMenuOverlay(root,()=>false,()=>Task.FromResult<TrackedCommand>(null),id=>null);menu.SetLayoutEditor(arena.LayoutEditor);
            RenderTexture target=null;var captures=new JArray();
            try{
                float deadline=Time.realtimeSinceStartup+10;while(host.PresentedDecision==null && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                Assert.That(host.PresentedDecision,Is.Not.Null);arena.Decisions.Tick();arena.Present(host.PresentedDecision.Frame);yield return null;
                var customize=root.Q<Button>("game-menu-customize-layout");Assert.That(customize,Is.Not.Null);
                menu.Open();using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=customize;customize.SendEvent(submit);}
                Assert.That(menu.IsOpen,Is.False);Assert.That(arena.LayoutEditor.IsEditing,Is.True);
                var editorControl=root.Q<PopupField<string>>("layout-editor-component");
                using(var escape=KeyDownEvent.GetPooled('\0',KeyCode.Escape,EventModifiers.None)){escape.target=editorControl;editorControl.SendEvent(escape);}
                using(var release=KeyUpEvent.GetPooled('\0',KeyCode.Escape,EventModifiers.None)){release.target=editorControl;editorControl.SendEvent(release);}
                Assert.That(arena.LayoutEditor.IsEditing,Is.False);Assert.That(menu.IsOpen,Is.False,"Cancelling customization must not reopen the Escape Menu");
                foreach(var size in new[]{new Vector2(1024,768),new Vector2(1280,720),new Vector2(1366,768),new Vector2(1920,1080),new Vector2(2560,1440),new Vector2(3440,1440)}){
                    target=new RenderTexture((int)size.x,(int)size.y,24);target.Create();settings.targetTexture=target;root.style.width=size.x;root.style.height=size.y;for(int i=0;i<3;i++)yield return null;arena.Present(host.PresentedDecision.Frame);yield return null;
                    var canvas=root.Q("arena-table");var action=root.Q<GameplayDrawer>("action-drawer");var zones=root.Q<GameplayDrawer>("zones-drawer");var before=action.Tab.worldBound;Capture(target,$"default-{size.x}x{size.y}");
                    Assert.That(canvas.WorldToLocal(before).x,Is.EqualTo(size.x-295).Within(2));Assert.That(canvas.WorldToLocal(before).y,Is.EqualTo(size.y-65).Within(2));
                    Assert.That(canvas.WorldToLocal(zones.Tab.worldBound).x,Is.EqualTo(16).Within(2));Assert.That(canvas.WorldToLocal(zones.Tab.worldBound).y,Is.EqualTo(size.y-122).Within(2));
                    var cards=new Dictionary<CardView,Rect>();arena.Surface.VisitPresented((card,view)=>cards[view]=view.worldBound);
                    Assert.That(arena.LayoutEditor.Open(),Is.True);Assert.That(arena.Decisions.LayoutEditing,Is.True);arena.LayoutEditor.Adjust(GameplayHudIds.Actions,-64,-24,false);yield return null;
                    Assert.That(action.Tab.worldBound,Is.Not.EqualTo(before));Capture(target,$"custom-{size.x}x{size.y}");arena.LayoutEditor.Cancel();yield return null;
                    Assert.That(action.Tab.worldBound,Is.EqualTo(before));Assert.That(arena.Decisions.LayoutEditing,Is.False);
                    foreach(var pair in cards)Assert.That(pair.Key.worldBound,Is.EqualTo(pair.Value));
                    Capture(target,$"restored-{size.x}x{size.y}");captures.Add(new JObject{["requested_width"]=(int)size.x,["requested_height"]=(int)size.y,["rendered_width"]=target.width,["rendered_height"]=target.height,["ui_width"]=canvas.resolvedStyle.width,["ui_height"]=canvas.resolvedStyle.height,["method"]="RenderTexture"});
                    settings.targetTexture=null;target.Release();UnityEngine.Object.Destroy(target);target=null;
                }
                File.WriteAllText(Path.Combine(Application.dataPath,"../Artifacts/LayoutRecovery/resolution-proof.json"),new JObject{["captures"]=captures}.ToString());
                arena.LayoutEditor.Open();arena.LayoutEditor.Adjust(GameplayHudIds.Actions,-16,0,false);arena.LayoutEditor.Suspend();Assert.That(arena.LayoutEditor.HasRetainedDraft,Is.True);
                host.Cancel();host.Tick();Assert.That(arena.LayoutEditor.HasRetainedDraft,Is.False);Assert.That(arena.Decisions.LayoutEditing,Is.False);
            }finally{settings.targetTexture=null;if(target!=null){target.Release();UnityEngine.Object.Destroy(target);}host.Cancel();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator ResizeSuspendsDraftAndScaleChangeCancelsCapturedGestureWithoutSaving()
        {
            var node=new GameObject("Viewport recovery");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            using var h=new Harness();doc.rootVisualElement.Add(h.Root);
            try{
                for(int i=0;i<4;i++)yield return null;h.Editor.AfterLegacyLayout();Assert.That(h.Editor.Open(),Is.True);
                int displayKeys=0;EventCallback<KeyDownEvent> display=ev=>{if(ev.keyCode==KeyCode.F11)displayKeys++;};h.Root.RegisterCallback(display,TrickleDown.TrickleDown);
                using(var key=KeyDownEvent.GetPooled('\0',KeyCode.F11,EventModifiers.None)){var field=h.Root.Q("layout-editor-component");key.target=field;field.SendEvent(key);}
                h.Root.UnregisterCallback(display,TrickleDown.TrickleDown);Assert.That(displayKeys,Is.EqualTo(1),"F11 must reach display controls while editing");
                var handle=h.Root.Q("layout-move-actions");
                using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=handle.worldBound.center})){down.target=handle;handle.SendEvent(down);}
                Assert.That(h.Editor.GestureActive,Is.True);var viewport=h.Editor.Viewport;
                h.Editor.UpdateViewport(new GameplayViewportContext(viewport.Bounds,viewport.PixelsPerUnit*2));
                Assert.That(h.Editor.GestureActive,Is.False);Assert.That(handle.HasPointerCapture(PointerId.mousePointerId),Is.False);Assert.That(h.Editor.NeedsApply,Is.False);
                h.Editor.Adjust(GameplayHudIds.Actions,-32,-24,false);var draft=h.Editor.Controller.State(GameplayHudIds.Actions).FloatingRect;
                h.Canvas.style.width=800;h.Canvas.style.height=600;yield return null;
                h.Editor.UpdateViewport(new GameplayViewportContext(new Rect(0,0,800,600)));
                Assert.That(h.Editor.IsEditing,Is.False);Assert.That(h.Editor.HasRetainedDraft,Is.True);Assert.That(h.Gated,Is.False);Assert.That(h.Editor.CanOpen,Is.False);
                Assert.That(h.Root.Q<Label>("layout-viewport-warning").style.display.value,Is.EqualTo(DisplayStyle.Flex));
                h.Canvas.style.width=1280;h.Canvas.style.height=720;yield return null;h.Editor.UpdateViewport(viewport);
                Assert.That(h.Editor.IsEditing,Is.False);Assert.That(h.Editor.CanOpen,Is.True);h.Editor.Open();
                Assert.That(h.Editor.Controller.State(GameplayHudIds.Actions).FloatingRect,Is.EqualTo(draft));Assert.That(h.Store.Writes,Is.Zero);
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator RecoveryKeepsPresetsStartupSelectionAndRequiredDrawerAttention()
        {
            using var h=new Harness();h.Editor.Open();h.Editor.Adjust(GameplayHudIds.Actions,-32,0,false);h.Editor.Apply();
            var save=h.Editor.SaveAsync(true,"Kept preset");yield return new WaitUntil(()=>save.IsCompleted);Assert.That(save.Result,Is.True);
            var before=h.Store.ReadAsync();yield return new WaitUntil(()=>before.IsCompleted);int writes=h.Store.Writes;
            h.Editor.Adjust(GameplayHudIds.Actions,-24,0,false);h.Editor.Suspend();h.Blocked=true;h.Editor.Observe("session","viewer",true,false);
            var drawer=h.Drawers[GameplayHudIds.Actions];drawer.SetOpen(true);drawer.SetAttention(true,"Choice required");
            h.Editor.ResetForGame();Assert.That(h.Editor.HasRetainedDraft,Is.False);Assert.That(h.Editor.OwnsGeometry(GameplayHudIds.Actions),Is.False);Assert.That(h.Gated,Is.False);
            Assert.That(drawer.IsOpen,Is.True);Assert.That(drawer.NeedsAttention,Is.True);Assert.That(h.Store.Writes,Is.EqualTo(writes));
            var after=h.Store.ReadAsync();yield return new WaitUntil(()=>after.IsCompleted);Assert.That(after.Result.Library.ToJson().ToString(),Is.EqualTo(before.Result.Library.ToJson().ToString()));
        }
        [UnityTest] public IEnumerator MenuRecoveryWorksDuringBlockedEditingAndStorageInitialization()
        {
            var delayed=new TaskCompletionSource<PresetStoreResult>();var store=new ObservedStore{DelayedRead=delayed};using var h=new Harness(store);
            var node=new GameObject("Recovery menu");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;doc.rootVisualElement.Add(h.Root);
            using var menu=new GameplayMenuOverlay(h.Root,()=>false,()=>Task.FromResult<TrackedCommand>(null),id=>null);menu.SetLayoutEditor(h.Editor);
            try{
                h.Root.style.width=800;h.Root.style.height=600;h.Canvas.style.width=800;h.Canvas.style.height=600;yield return null;
                h.Editor.UpdateViewport(new GameplayViewportContext(new Rect(0,0,800,600)));h.Blocked=true;h.Editor.Observe("session","viewer",true,false);Assert.That(h.Editor.CanOpen,Is.False);
                menu.Open();var reset=h.Root.Q<Button>("game-menu-reset-layout");Assert.That(reset.enabledInHierarchy,Is.True);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=reset;reset.SendEvent(submit);}
                var confirm=h.Root.Q<Button>("game-menu-confirm-reset-layout");using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=confirm;confirm.SendEvent(submit);}
                Assert.That(menu.IsOpen,Is.False);Assert.That(h.Gated,Is.False);Assert.That(store.Writes,Is.Zero);
                delayed.SetResult(new PresetStoreResult(PresetStoreStatus.UnsupportedVersion));yield return new WaitUntil(()=>h.Editor.Initialization.IsCompleted);
                menu.Open();Assert.That(reset.enabledInHierarchy,Is.True);Assert.That(h.Root.Q<Button>("game-menu-customize-layout").enabledSelf,Is.False);
            }finally{delayed.TrySetResult(new PresetStoreResult(PresetStoreStatus.UnsupportedVersion));UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
        [TestCase(1024,768)] [TestCase(1280,720)] [TestCase(1366,768)] [TestCase(1920,1080)] [TestCase(2560,1440)] [TestCase(3440,1440)]
        public void LiveHeadersRemainReachableWhenDocksOverflow(int width,int height)
        {
            using var h=new Harness();h.Editor.Controller.SetViewport(new Vector2(width,height));h.Editor.Open();
            foreach(string id in h.Editor.Controller.Ids){h.Registry.Find(id).Available=true;h.Editor.Adjust(id,1000,0,true);h.Editor.Dock(id,ContainerDockEdge.Bottom);}
            foreach(string id in h.Editor.Controller.Ids){var rect=h.Editor.Controller.Resolved[id];Assert.That(rect.xMin,Is.GreaterThanOrEqualTo(0));Assert.That(rect.yMin,Is.GreaterThanOrEqualTo(0));Assert.That(rect.xMax,Is.LessThanOrEqualTo(width));Assert.That(rect.yMax,Is.LessThanOrEqualTo(height));foreach(string other in h.Editor.Controller.Ids.Where(o=>o!=id))Assert.That(rect.Overlaps(h.Editor.Controller.Resolved[other]),Is.False);}
        }
    }
}

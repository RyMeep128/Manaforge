using System;
using System.Collections;
using System.IO;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
using GameObject=UnityEngine.GameObject;
namespace Manaforge.Play.Tests
{
    public sealed class VisualHudEditorTests
    {
        private static IEnumerator Until(Func<bool> ready,Action tick=null){float end=Time.realtimeSinceStartup+12;while(!ready() && Time.realtimeSinceStartup<end){tick?.Invoke();yield return null;}Assert.That(ready(),Is.True,"Visual layout timed out");}
        private static void Capture(RenderTexture target,string name)
        {
            string directory=Path.Combine(Application.dataPath,"../Artifacts/VisualHudEditor");Directory.CreateDirectory(directory);var previous=RenderTexture.active;var texture=new Texture2D(target.width,target.height,TextureFormat.RGBA32,false);
            try{RenderTexture.active=target;texture.ReadPixels(new Rect(0,0,target.width,target.height),0,0);texture.Apply();File.WriteAllBytes(Path.Combine(directory,name+".png"),texture.EncodeToPNG());}finally{RenderTexture.active=previous;UnityEngine.Object.Destroy(texture);}
        }
        private static void Submit(VisualElement element){Assert.That(element,Is.Not.Null);using(var ev=NavigationSubmitEvent.GetPooled()){ev.target=element;element.SendEvent(ev);}}
        [UnityTest] public IEnumerator ZonesStayVisibleAndBrowsableWhileHeadersDragAndBodiesResize()
        {
            var node=new GameObject("Visual HUD editor");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.width=1280;root.style.height=720;var target=new RenderTexture(1280,720,24);target.Create();settings.targetTexture=target;
            using var arena=new ArenaGameplayPresentation(root,capabilities:new GameplayPresentationCapabilities(privateLayout:true),layoutPresetStore:new MemoryLayoutPresetStore());
            var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();var snapshot=envelope["body"]["snapshot"];snapshot["turn"]=2;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["priority_player_id"]="one";snapshot["actions_complete"]=true;snapshot["decision"]["is_priority"]=true;snapshot["decision"]["options"]=new JArray();
            var visible=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0].DeepClone();visible["face_down"]=false;visible["characteristics"]["name"]="Visual preview card";snapshot["objects"][0]=visible;
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);using var host=new ViewerSessionHost(arena.Surface,peer.Bootstrap(),owner.Task,true);arena.Bind(host);
            try{
                yield return Until(()=>host.PresentedDecision!=null,()=>host.Tick());arena.Decisions.Tick();arena.Present(host.PresentedDecision.Frame);yield return null;
                var editor=arena.LayoutEditor;yield return Until(()=>editor.Initialization.IsCompleted);var zones=root.Q<GameplayDrawer>("zones-drawer");bool originalOpen=zones.IsOpen;var originalParent=zones.parent;var originalContent=zones.Content;
                Assert.That(editor.Open(),Is.True);for(int i=0;i<3;i++)yield return null;
                Assert.That(zones.IsOpen,Is.True,"Zones open as a temporary visual preview");Assert.That(root.Q("layout-editor-move-left"),Is.Null,"Mouse placement must not be a button grid");Assert.That(root.Q<Foldout>("layout-editor-presets").value,Is.False);
                yield return new WaitForEndOfFrame();Capture(target,"zones-preview-open");
                foreach(string zone in new[]{"library","graveyard","exile"})Assert.That(root.Q<ZonePile>("local-"+zone),Is.Not.Null);
                var handle=root.Q("layout-move-zones");Vector2 start=handle.worldBound.center,end=start+new Vector2(320,-170);
                using(var ev=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=start})){ev.target=handle;handle.SendEvent(ev);}using(var ev=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=end})){ev.target=handle;handle.SendEvent(ev);}using(var ev=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=end})){ev.target=handle;handle.SendEvent(ev);}for(int i=0;i<3;i++)yield return null;
                Assert.That(editor.OwnsGeometry(GameplayHudIds.Zones),Is.True);Assert.That(zones.Viewport.resolvedStyle.height,Is.GreaterThan(60));Assert.That(zones.Content.resolvedStyle.height,Is.GreaterThan(60));Assert.That(root.Q<ScrollView>("zone-panel-scroll").resolvedStyle.height,Is.GreaterThan(60));
                float beforeResize=zones.Viewport.resolvedStyle.height;var grip=root.Q("layout-resize-zones");start=grip.worldBound.center;end=start+new Vector2(50,40);using(var ev=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=start})){ev.target=grip;grip.SendEvent(ev);}using(var ev=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=end})){ev.target=grip;grip.SendEvent(ev);}using(var ev=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=end})){ev.target=grip;grip.SendEvent(ev);}yield return null;
                Assert.That(zones.Viewport.resolvedStyle.height,Is.Not.EqualTo(beforeResize).Within(2),"Resize starts at the visible body, not an off-screen stored height");
                yield return new WaitForEndOfFrame();Capture(target,"zones-dragged-and-resized");
                Submit(root.Q<ZonePile>("local-graveyard"));yield return null;Assert.That(root.Q<ZoneBrowser>("public-zone-drawer").Zone,Is.EqualTo("graveyard"));Assert.That(editor.IsEditing,Is.True);Submit(root.Q<Button>("close-public-zone"));
                CardView cardView=null;arena.Surface.VisitPresented((card,view)=>{if(!card.Hidden)cardView=view;});Assert.That(cardView,Is.Not.Null);using(var ev=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=1,mousePosition=cardView.worldBound.center})){ev.target=cardView;cardView.SendEvent(ev);}Assert.That(arena.Surface.InspectionView.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(editor.IsEditing,Is.True);Submit(root.Q<Button>("close-inspection"));
                Submit(root.Q<Button>("layout-preview-zones"));yield return null;Assert.That(zones.IsOpen,Is.False);Submit(root.Q<Button>("layout-preview-zones"));yield return null;Assert.That(zones.IsOpen,Is.True);Assert.That(peer.PendingCommandBytes,Is.Zero,"Preview gestures must not send game commands");
                Assert.That(editor.Apply(),Is.True);var saved=editor.SaveAsync(true,"Visual zones");yield return Until(()=>saved.IsCompleted);Assert.That(saved.Result,Is.True);editor.Cancel();yield return null;Assert.That(zones.IsOpen,Is.EqualTo(originalOpen),"Preview expansion must not overwrite the game preference");Assert.That(zones.parent,Is.SameAs(originalParent));Assert.That(zones.Content,Is.SameAs(originalContent));
                zones.SetOpen(true);yield return null;Assert.That(zones.Viewport.resolvedStyle.height,Is.GreaterThan(60),"Applied geometry must not lose zones on return to play");Assert.That(root.Q<ZonePile>("local-library").resolvedStyle.display,Is.Not.EqualTo(DisplayStyle.None));
            }finally{owner.TrySetResult(true);host.Dispose();arena.Dispose();settings.targetTexture=null;target.Release();UnityEngine.Object.Destroy(target);UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}
        }
    }
}

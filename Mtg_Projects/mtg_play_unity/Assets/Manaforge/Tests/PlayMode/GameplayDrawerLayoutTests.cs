using System.Collections;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayDrawerLayoutTests
    {
        [UnityTest] public IEnumerator DrawerTabsAndExpandedRegionsRemainInsideAllDesktopViewports()
        {
            var node=new GameObject("HUD drawer viewport review");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            using var arena=new ArenaGameplayPresentation(doc.rootVisualElement);
            RenderTexture target=null;var previous=RenderTexture.active;
            try{
                var message=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["turn"]=2;
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=arena.Surface.BeginViewer(session,viewer);arena.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));var frame=ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true);
                var root=doc.rootVisualElement;var action=root.Q<GameplayDrawer>("action-drawer");var priority=root.Q<GameplayDrawer>("priority-drawer");var zones=root.Q<GameplayDrawer>("zones-drawer");
                action.Content.Add(new Button{text="Fixture action"});priority.Content.Add(new Toggle("Fixture preference"));
                foreach(var size in new[]{new Vector2Int(1280,720),new Vector2Int(1366,768),new Vector2Int(1920,1080),new Vector2Int(2560,1440)}){
                    target=new RenderTexture(size.x,size.y,24);target.Create();settings.targetTexture=target;root.style.width=size.x;root.style.height=size.y;yield return null;arena.Present(frame);yield return null;
                    var cardBounds=arena.Surface.CardsRoot.worldBound;
                    foreach(var drawer in new[]{action,priority,zones}){
                        drawer.SetReducedMotion(true);drawer.SetOpen(false);yield return null;
                        Assert.That(drawer.Tab.worldBound.width,Is.GreaterThan(100));Assert.That(drawer.Tab.enabledInHierarchy,Is.True);
                        var picked=root.panel.Pick(drawer.Tab.worldBound.center);Assert.That(picked==drawer.Tab || drawer.Tab.Contains(picked),Is.True,"Closed tab remains clickable: "+drawer.name);
                        drawer.SetOpen(true);yield return null;
                        Assert.That(drawer.Tab.worldBound.xMin,Is.GreaterThanOrEqualTo(root.worldBound.xMin));Assert.That(drawer.Tab.worldBound.xMax,Is.LessThanOrEqualTo(root.worldBound.xMax+1));
                        Assert.That(drawer.Tab.worldBound.yMin,Is.GreaterThanOrEqualTo(root.worldBound.yMin));Assert.That(drawer.worldBound.yMax,Is.LessThanOrEqualTo(root.worldBound.yMax+1));
                        Assert.That(arena.Surface.CardsRoot.worldBound,Is.EqualTo(cardBounds),"Drawers must not resize the battlefield");
                    }
                    var pile=root.Q<ZonePile>("opponent-library");Assert.That(pile.worldBound.xMin-root.worldBound.xMin,Is.EqualTo(22).Within(2));Assert.That(pile.worldBound.yMin-root.worldBound.yMin,Is.EqualTo(150).Within(2));
                    Assert.That(pile.Q<Image>("zone-art").image,Is.Null);Assert.That(pile.Q<Label>("zone-fallback").text,Is.Empty);
                    string directory=Path.Combine(Application.dataPath,"../Artifacts/HudDrawers");Directory.CreateDirectory(directory);
                    yield return null;yield return null;var pixels=new Texture2D(size.x,size.y,TextureFormat.RGBA32,false);
                    try{RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,size.x,size.y),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(directory,$"expanded-{size.x}x{size.y}.png"),pixels.EncodeToPNG());}finally{UnityEngine.Object.Destroy(pixels);}
                    settings.targetTexture=null;RenderTexture.active=previous;target.Release();UnityEngine.Object.Destroy(target);target=null;
                }
                arena.Surface.ClearViewer(ticket);Assert.That(root.Query<PlayerPanel>().ToList(),Is.Empty);Assert.That(root.Query<ZonePile>().ToList(),Is.Empty);
                foreach(var drawer in new[]{action,priority,zones})Assert.That(drawer.IsOpen,Is.False);
            }finally{settings.targetTexture=null;RenderTexture.active=previous;if(target!=null){target.Release();UnityEngine.Object.Destroy(target);}UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
    }
}

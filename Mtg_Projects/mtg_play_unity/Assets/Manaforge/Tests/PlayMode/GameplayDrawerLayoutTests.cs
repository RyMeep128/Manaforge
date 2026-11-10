using System.Collections;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayDrawerLayoutTests
    {
        private static void Capture(RenderTexture target,string name)
        {
            string directory=Path.Combine(Application.dataPath,"../Artifacts/HudDrawers");Directory.CreateDirectory(directory);
            var previous=RenderTexture.active;var pixels=new Texture2D(target.width,target.height,TextureFormat.RGBA32,false);
            try{RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,target.width,target.height),0,0);pixels.Apply();File.WriteAllBytes(Path.Combine(directory,name+".png"),pixels.EncodeToPNG());}
            finally{RenderTexture.active=previous;Object.Destroy(pixels);}
        }
        [TestCase(1280,720)] [TestCase(1366,768)] [TestCase(1920,1080)] [TestCase(2560,1440)]
        public void BattlefieldUsesRecoveredWidthAndKeepsRowsAboveHand(int width,int height)
        {
            var geometry=new GameplayCardLayout.BattlefieldGeometry(width,height);
            Assert.That(geometry.Span,Is.GreaterThan(width-445));
            Assert.That(geometry.CardWidth,Is.InRange(62,110));
            Assert.That(geometry.OpponentPermanents-geometry.OpponentLands,Is.GreaterThanOrEqualTo(geometry.CardWidth));
            Assert.That(geometry.LocalPermanents-geometry.OpponentPermanents,Is.GreaterThan(geometry.CardWidth));
            Assert.That(geometry.LocalLands+geometry.CardWidth,Is.LessThanOrEqualTo(geometry.HandTop-24+1));
            Assert.That(Mathf.FloorToInt(geometry.Span/(geometry.CardWidth+18)),Is.GreaterThan(Mathf.FloorToInt((width-445)/(Mathf.Clamp((width-445)/7f,85,125)+18))));
        }
        [UnityTest] public IEnumerator DrawerTabsAndExpandedRegionsRemainInsideAllDesktopViewports()
        {
            var node=new GameObject("HUD drawer viewport review");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            using var arena=new ArenaGameplayPresentation(doc.rootVisualElement);
            RenderTexture target=null;var previous=RenderTexture.active;
            try{
                var message=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["turn"]=2;
                var extra=snapshot["players"][1].DeepClone();extra["player_id"]="third-seat";((JArray)snapshot["players"]).Add(extra);
                snapshot["commanders"]=new JArray(Enumerable.Range(0,3).Select(i=>new JObject{["commander_id"]="commander-"+i,["owner_id"]=i<2?"one":"third-seat",["name"]="Partner "+i,["card_identity"]=null,["command_zone_plays"]=i,["additional_cast_cost"]="{2}",["damage_dealt"]=new JArray(new JArray("one",0),new JArray("two",7),new JArray("third-seat",3))}));
                var prototype=snapshot["objects"][0].DeepClone();var dense=new JArray();
                var players=snapshot["players"].Select(player=>(string)player["player_id"]).ToArray();
                for(int i=0;i<96;i++){
                    var card=prototype.DeepClone();card["object_id"]="dense-"+i;card["owner_id"]=players[i%players.Length];card["controller_id"]=players[i%players.Length];
                    card["zone"]="battlefield";card["hidden"]=false;card["face_down"]=false;card["tapped"]=i%3==0;card["attachments"]=new JArray();card["attached_to"]=null;
                    card["characteristics"]["name"]="Permanent "+i;card["characteristics"]["type_line"]=i%4<2?"Basic Land":i%4==2?"Creature":"Artifact";dense.Add(card);
                }
                for(int i=0;i<8;i++){var card=prototype.DeepClone();card["object_id"]="support-"+i;card["owner_id"]=(string)snapshot["viewer_id"];card["controller_id"]=(string)snapshot["viewer_id"];card["zone"]=i==7?"stack":"hand";card["hidden"]=false;card["face_down"]=false;card["attached_to"]=null;card["attachments"]=new JArray();dense.Add(card);}
                snapshot["objects"]=dense;
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=arena.Surface.BeginViewer(session,viewer);arena.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));var frame=ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true);
                var root=doc.rootVisualElement;var action=root.Q<GameplayDrawer>("action-drawer");var priority=root.Q<GameplayDrawer>("priority-drawer");var zones=root.Q<GameplayDrawer>("zones-drawer");
                action.Content.Add(new Button{text="Fixture action"});priority.Content.Add(new Toggle("Fixture preference"));
                foreach(var size in new[]{new Vector2Int(1280,720),new Vector2Int(1366,768),new Vector2Int(1920,1080),new Vector2Int(2560,1440)}){
                    target=new RenderTexture(size.x,size.y,24);target.Create();settings.targetTexture=target;root.style.width=size.x;root.style.height=size.y;yield return null;arena.Present(frame);root.Q<GameplayPlayerHud>().Present(frame,arena.Surface,"commander");yield return null;
                    foreach(var drawer in new[]{action,priority,zones}){drawer.SetReducedMotion(true);drawer.SetOpen(false);}yield return null;
                    Capture(target,$"battlefield-collapsed-{size.x}x{size.y}");
                    // Reproduce the former geometry with the same views and dense fixture for comparison.
                    var oldCards=new List<(ProjectedCard card,CardView view)>();arena.Surface.VisitPresented((card,view)=>{view.style.display=DisplayStyle.None;oldCards.Add((card,view));});
                    var oldNavigation=new VisualElement();var oldPages=new Dictionary<string,int>();float oldSpan=size.x-445,oldSize=Mathf.Clamp(oldSpan/7,85,125);
                    foreach(bool local in new[]{false,true}){
                        var seat=oldCards.Where(item=>item.card.Zone=="battlefield" && (item.card.ControllerId==viewer)==local).ToList();
                        var lands=seat.Where(item=>item.card.Characteristics.TypeLine.Contains("Land")).ToList();
                        GameplayCardLayout.LandRow(lands,oldNavigation,oldPages,()=>{},size.x,size.y*(local?.72f:.15f),280,oldSpan,Mathf.Min(oldSize,110),local?"local-lands":"opponent-lands",new Vector2(size.x*.5f-90,size.x*.5f+90));
                        GameplayCardLayout.Row(seat.Except(lands).ToList(),oldNavigation,oldPages,()=>{},size.x,size.y*(local?.53f:.30f),280,oldSpan,oldSize,key:local?"local-permanents":"opponent-permanents");
                    }
                    yield return null;Capture(target,$"battlefield-previous-fixed-margins-{size.x}x{size.y}");
                    arena.Present(frame);root.Q<GameplayPlayerHud>().Present(frame,arena.Surface,"commander");yield return null;
                    var localSeat=root.Q<PlayerPanel>("local-seat");
                    Assert.That(localSeat.parent.name,Is.EqualTo("hud-local-player"));
                    Assert.That(localSeat.worldBound.xMin-root.worldBound.xMin,Is.LessThan(24));
                    Assert.That(root.worldBound.yMax-localSeat.worldBound.yMax,Is.InRange(12,24));
                    Assert.That(root.Q("hud-players").worldBound.yMax,Is.LessThan(localSeat.worldBound.yMin));
                    var cardBounds=arena.Surface.CardsRoot.worldBound;
                    var placements=new Dictionary<CardView,(float x,float y,float width,float height,DisplayStyle display)>();
                    arena.Surface.VisitPresented((card,view)=>placements[view]=(view.style.left.value.value,view.style.top.value.value,view.style.width.value.value,view.style.height.value.value,view.style.display.value));
                    var pagination=root.Query<Label>().ToList().Where(label=>label.parent?.ClassListContains("row-navigation")==true).Select(label=>label.text).ToArray();
                    foreach(var drawer in new[]{action,priority,zones}){
                        drawer.SetReducedMotion(true);drawer.SetOpen(false);yield return null;
                        Assert.That(drawer.Tab.worldBound.width,Is.GreaterThan(100));Assert.That(drawer.Tab.enabledInHierarchy,Is.True);
                        var picked=root.panel.Pick(drawer.Tab.worldBound.center);Assert.That(picked==drawer.Tab || drawer.Tab.Contains(picked),Is.True,"Closed tab remains clickable: "+drawer.name);
                        drawer.SetOpen(true);yield return null;
                        foreach(var pair in placements){var view=pair.Key;Assert.That((view.style.left.value.value,view.style.top.value.value,view.style.width.value.value,view.style.height.value.value,view.style.display.value),Is.EqualTo(pair.Value),drawer.name);}
                        Assert.That(root.Query<Label>().ToList().Where(label=>label.parent?.ClassListContains("row-navigation")==true).Select(label=>label.text).ToArray(),Is.EqualTo(pagination));
                        Assert.That(drawer.Tab.worldBound.xMin,Is.GreaterThanOrEqualTo(root.worldBound.xMin));Assert.That(drawer.Tab.worldBound.xMax,Is.LessThanOrEqualTo(root.worldBound.xMax+1));
                        Assert.That(drawer.Tab.worldBound.yMin,Is.GreaterThanOrEqualTo(root.worldBound.yMin));Assert.That(drawer.worldBound.yMax,Is.LessThanOrEqualTo(root.worldBound.yMax+1));
                        Assert.That(arena.Surface.CardsRoot.worldBound,Is.EqualTo(cardBounds),"Drawers must not resize the battlefield");
                        Capture(target,$"battlefield-{drawer.name}-{size.x}x{size.y}");
                        drawer.SetOpen(false);yield return null;
                        foreach(var pair in placements){var view=pair.Key;Assert.That((view.style.left.value.value,view.style.top.value.value,view.style.width.value.value,view.style.height.value.value,view.style.display.value),Is.EqualTo(pair.Value),"Closing "+drawer.name);}
                    }
                    foreach(var drawer in new[]{action,priority,zones}){
                        var handle=drawer.Tab.worldBound;
                        drawer.Content.style.minHeight=40;yield return null;drawer.Content.style.minHeight=180;yield return null;
                        Assert.That(drawer.Tab.worldBound,Is.EqualTo(handle),"Content growth must not move the handle: "+drawer.name);
                        drawer.SetOpen(false);yield return null;Assert.That(drawer.Tab.worldBound,Is.EqualTo(handle));drawer.SetOpen(true);drawer.Content.style.minHeight=StyleKeyword.Null;
                        Assert.That(drawer.Tab.Q("drawer-glyph"),Is.Not.Null);
                    }
                    Assert.That(zones.Q<ScrollView>("zone-panel-scroll").horizontalScrollerVisibility,Is.EqualTo(ScrollerVisibility.Hidden));
                    Assert.That(zones.Q<ScrollView>("zone-panel-scroll").contentViewport.resolvedStyle.width,Is.GreaterThanOrEqualTo(232));
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

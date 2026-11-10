using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;
namespace Manaforge.Play.Tests
{
    public sealed class GameplayElementTests
    {
        [Test] public void ExplicitSeatsAndZonesDoNotLeakAcrossRebindOrDisposal()
        {
            var a=new PlayerPanel();var b=new PlayerPanel();string activated=null;
            a.Bind("seat-b","Same name");b.Bind("seat-c","Same name");a.Activated+=id=>activated=id;b.Activated+=id=>activated=id;
            a.Present(20,true,true,true);b.Present(null,false,false,true);
            b.Activate();Assert.That(activated,Is.Null);a.Activate();Assert.That(activated,Is.EqualTo("seat-b"));
            Assert.That(b.Q<Label>("seat-life").text,Is.EqualTo("?"));
            a.Bind("seat-d","New seat");a.Activate();Assert.That(activated,Is.EqualTo("seat-b"),"Rebind must revoke old targeting");
            a.Present(7,false,true,true);a.Activate();Assert.That(activated,Is.EqualTo("seat-d"));
            var pile=new ZonePile("library");string request=null;pile.BrowseRequested+=(zone,id)=>request=id+"/"+zone;
            pile.Bind("seat-c");var image=new Texture2D(1,1);pile.Present(null,image,"Forbidden library name",false);
            Assert.That(pile.Q<Image>("zone-art").image,Is.Null);Assert.That(pile.Q<Label>("zone-fallback").text,Is.Empty);
            Assert.That(pile.Q<Label>("zone-count").text,Is.EqualTo("?"));pile.Browse();Assert.That(request,Is.EqualTo("seat-c/library"));
            pile.Bind("seat-b");pile.Browse();Assert.That(request,Is.EqualTo("seat-b/library"));
            pile.ClearBinding();pile.Browse();Assert.That(pile.Q<Label>("zone-count").text,Is.EqualTo("?"));
            pile.Dispose();a.Dispose();b.Dispose();activated=null;a.Activate();Assert.That(activated,Is.Null);UnityEngine.Object.DestroyImmediate(image);
        }
        [UnityTest] public IEnumerator SameComponentsMountUnderIndependentRootsAndClearBorrowedArt()
        {
            var node=new GameObject("Reusable component test");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            var owned=new List<IDisposable>();
            try{
                var horizontal=new VisualElement{name="horizontal"};var vertical=new VisualElement{name="vertical"};doc.rootVisualElement.Add(horizontal);doc.rootVisualElement.Add(vertical);
                horizontal.style.width=1200;vertical.style.width=600;
                GameplayStyleReviewScene.Populate(horizontal,owned,2);GameplayStyleReviewScene.Populate(vertical,owned,3,true);
                yield return null;yield return null;
                Assert.That(horizontal.Query<PlayerPanel>().ToList().Count,Is.EqualTo(2));Assert.That(vertical.Query<PlayerPanel>().ToList().Count,Is.EqualTo(3));
                Assert.That(horizontal.Query<PlayerPanel>().First().resolvedStyle.width,Is.EqualTo(84).Within(1));
                Assert.That(vertical.Query<PlayerPanel>().First().resolvedStyle.width,Is.EqualTo(84).Within(1));
                Assert.That(vertical.Query<ZonePile>().First().resolvedStyle.height,Is.EqualTo(92).Within(1));
                Assert.That(doc.rootVisualElement.Q("arena-table"),Is.Null,"Shared styles must not need the default composition root");
                var graveyard=new ZonePile("graveyard");horizontal.Add(graveyard);owned.Add(graveyard);graveyard.Bind("seat-b");var art=new Texture2D(1,1);
                graveyard.Present(1,art,"Known",true);graveyard.ClearArtwork();Assert.That(graveyard.Q<Image>("zone-art").image,Is.Null);Assert.That(art,Is.Not.Null);
                UnityEngine.Object.Destroy(art);
            }finally{foreach(var item in owned)item.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator UnifiedHudRetainsEveryExplicitSeat()
        {
            var node=new GameObject("Topology test");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            var table=new ArenaGameplayPresentation(doc.rootVisualElement);
            try{
                var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
                var snapshot=envelope["body"]["snapshot"];var players=(JArray)snapshot["players"];var extra=players[1].DeepClone();extra["player_id"]="third-seat";players.Add(extra);
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                Assert.That(doc.rootVisualElement.Query<PlayerPanel>().ToList().Count,Is.EqualTo(3));
                Assert.That(table.Surface.CardsRoot.style.display.value,Is.EqualTo(DisplayStyle.Flex));
                Assert.That(doc.rootVisualElement.Q<GameplayPlayerHud>().Player("third-seat").PlayerId,Is.EqualTo("third-seat"));
            }finally{table.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator OverlayDismissalRestoresFocusAndClearDoesNotReviveIt()
        {
            var node=new GameObject("Overlay test");var settings=ScriptableObject.CreateInstance<PanelSettings>();var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            var origin=new Button();var content=new VisualElement();var close=new Button();doc.rootVisualElement.Add(origin);doc.rootVisualElement.Add(content);doc.rootVisualElement.Add(close);var overlay=new GameplayOverlay(content,close);
            try{
                yield return null;origin.Focus();overlay.Show(true,origin);close.Focus();overlay.Place(new Rect(0,0,800,600),new Vector2(290,406),new Vector2(10,100));
                Assert.That(content.style.left.value.value,Is.GreaterThan(400));overlay.Hide(true);yield return null;
                Assert.That(origin.focusController.focusedElement,Is.SameAs(origin));overlay.Show(true,origin);origin.RemoveFromHierarchy();overlay.Hide(false);overlay.Dispose();
                Assert.That(content.style.display.value,Is.EqualTo(DisplayStyle.None));
            }finally{overlay.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
    }
}

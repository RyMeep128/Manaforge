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
    public sealed class ArenaTablePresentationTests
    {
        [UnityTest] public IEnumerator AttackArrowFollowsDefendingPlayerPanelWithoutNewSnapshots()
        {
            var node=new GameObject("Moving combat endpoint");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var target=new RenderTexture(1280,720,24);target.Create();settings.targetTexture=target;
            var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;var root=doc.rootVisualElement;root.style.width=1280;root.style.height=720;using var table=new ArenaGameplayPresentation(root);
            try{
                var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();var snapshot=wire["body"]["snapshot"];
                snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();snapshot["turn"]=2;
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"],defender=(string)snapshot["players"][1]["player_id"];
                var attacker=(JObject)snapshot["objects"][0].DeepClone();attacker["object_id"]="attacker";attacker["zone"]="battlefield";attacker["hidden"]=false;attacker["face_down"]=false;attacker["tapped"]=true;attacker["owner_id"]=viewer;attacker["controller_id"]=viewer;attacker["attached_to"]=null;attacker["attachments"]=new JArray();attacker["characteristics"]["type_line"]="Creature";
                snapshot["objects"]=new JArray(attacker);snapshot["combat"]=new JArray(new JObject{["attackers"]=new JArray("attacker"),["blockers"]=new JArray(),["defender_id"]=defender,["blocked"]=false});
                var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));
                var lines=root.Q<BattlefieldLinks>();var hud=root.Q<GameplayPlayerHud>();var players=root.Q<GameplayDrawer>("player-life-drawer");players.SetReducedMotion(true);
                yield return new WaitForSecondsRealtime(.08f);yield return null;yield return null;Assert.That(lines.CurrentLinks.Count,Is.EqualTo(1));
                Rect Destination(){var bounds=lines.WorldToLocal(hud.Player(defender).worldBound);bounds.xMin-=8;bounds.yMin-=8;bounds.xMax+=8;bounds.yMax+=8;return bounds;}
                Assert.That(Destination().Contains(lines.CurrentLinks[0].To),Is.True,"Attack must point to its explicit defending player");var before=lines.CurrentLinks[0];
                players.style.translate=new Translate(-320,110);yield return new WaitForSecondsRealtime(.08f);yield return null;yield return null;
                Assert.That(Destination().Contains(lines.CurrentLinks[0].To),Is.True);Assert.That(Vector2.Distance(lines.CurrentLinks[0].To,before.To),Is.GreaterThan(100));Assert.That(Vector2.Distance(lines.CurrentLinks[0].From,before.From),Is.LessThan(1),"Moving Players does not move the attacker");
                root.style.width=1366;root.style.height=768;yield return new WaitForSecondsRealtime(.08f);yield return null;yield return null;Assert.That(Destination().Contains(lines.CurrentLinks[0].To),Is.True,"Resize must use the final panel position");
                players.SetOpen(false);yield return new WaitForSecondsRealtime(.08f);yield return null;yield return null;var header=lines.WorldToLocal(players.Tab.worldBound);header.xMin-=8;header.yMin-=8;header.xMax+=8;header.yMax+=8;Assert.That(header.Contains(lines.CurrentLinks[0].To),Is.True,"Collapsed Players uses its visible header");
                players.SetOpen(true);yield return new WaitForSecondsRealtime(.08f);yield return null;yield return null;Assert.That(Destination().Contains(lines.CurrentLinks[0].To),Is.True);
                table.Surface.ClearViewer(ticket);yield return null;yield return null;Assert.That(lines.CurrentLinks,Is.Empty,"Session clearing removes combat arrows");LogAssert.NoUnexpectedReceived();
            }finally{settings.targetTexture=null;target.Release();Object.Destroy(target);Object.Destroy(node);Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator PhaseOnlyUpdatesRetainCardsFocusArtworkAndBoundedHand()
        {
            var node=new GameObject("Phase continuity");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=node.AddComponent<UIDocument>();document.panelSettings=settings;var root=document.rootVisualElement;root.style.width=1280;root.style.height=720;
            var table=new ArenaGameplayPresentation(root);
            try{
                var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
                var snapshot=wire["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();snapshot["turn"]=2;
                var template=(JObject)snapshot["objects"][0].DeepClone();template["hidden"]=false;template["face_down"]=false;template["owner_id"]="one";template["controller_id"]="one";template["attachments"]=new JArray();template["attached_to"]=null;
                template["characteristics"]["type_line"]="Creature";template["card_identity"]=new JObject{["oracle_id"]="oracle",["printing_id"]="exact-printing",["deck_entry_id"]=null};
                var objects=new JArray();for(int i=0;i<15;i++){var card=(JObject)template.DeepClone();card["object_id"]="continuity-"+i;card["presentation_id"]="stable-"+i;card["zone"]=i==0?"battlefield":"hand";card["tapped"]=i==0;objects.Add(card);}snapshot["objects"]=objects;
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=table.Surface.BeginViewer(session,viewer,new ViewerArtworkScope());
                yield return null;yield return null;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));yield return null;
                CardView permanent=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="continuity-0")permanent=view;});Assert.That(permanent,Is.Not.Null);
                var request=table.Surface.RequestArtwork(ticket,"continuity-0");var catalog=new CatalogArtworkFace("oracle","exact-printing","front","normal",1,true,"Creature");
                Assert.That(table.Surface.TryApplyArtwork(ticket,PreparedCardArtwork.Prepare(request,catalog,2,2,new byte[16])),Is.True);
                var texture=permanent.Artwork;permanent.Focus();using(var enter=PointerEnterEvent.GetPooled()){enter.target=permanent;permanent.SendEvent(enter);}yield return null;
                yield return new WaitForSecondsRealtime(.5f);var position=permanent.worldBound;Assert.That(root.Q<ScrollView>("card-scroll-hand"),Is.Null);Assert.That(root.Q<Button>("hand-next"),Is.Null);
                foreach(string step in new[]{"UPKEEP","DRAW","PRECOMBAT_MAIN","BEGIN_COMBAT"}){
                    snapshot["revision"]=(long)snapshot["revision"]+1;objects[0]["object_id"]="current-"+step;snapshot["step"]=step;snapshot["phase"]=step=="BEGIN_COMBAT"?"COMBAT":step=="PRECOMBAT_MAIN"?"PRECOMBAT_MAIN":"BEGINNING";
                    Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);
                    table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));yield return null;
                    Assert.That(table.Surface.CurrentObjectId(permanent),Is.EqualTo("current-"+step));Assert.That(permanent.Artwork,Is.SameAs(texture));Assert.That(permanent.style.rotate.value.angle.value,Is.EqualTo(90));
                    Assert.That(permanent.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(permanent.style.scale.value.value.x,Is.EqualTo(1.12f).Within(.001f));
                    Assert.That(root.panel.focusController.focusedElement,Is.SameAs(permanent));Assert.That(permanent.worldBound.position,Is.EqualTo(position.position));Assert.That(root.Q<ScrollView>("card-scroll-hand"),Is.Null);
                }
                var hand=new List<CardView>();table.Surface.VisitPresented((card,view)=>{if(card.Zone=="hand")hand.Add(view);});
                foreach(var card in hand){Assert.That(card.resolvedStyle.left,Is.GreaterThan(0));Assert.That(card.resolvedStyle.left+card.resolvedStyle.width,Is.LessThan(1280));}
                var middle=hand[hand.Count/2];float before=hand[hand.Count/2+1].resolvedStyle.left;using(var leave=PointerLeaveEvent.GetPooled()){leave.target=permanent;permanent.SendEvent(leave);}middle.Focus();yield return null;
                Assert.That(hand[hand.Count/2+1].resolvedStyle.left,Is.GreaterThan(before),"Focus spreads the crowded fan without a scrollbar");
                Assert.That(root.Q<Button>("hand-previous"),Is.Null);
            }finally{table.Dispose();Object.Destroy(node);Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator CastingHoveredFocusedCardCannotReinsertRetiredViewsOrCorruptPicking()
        {
            var node=new GameObject("Cast hierarchy regression");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            var root=document.rootVisualElement;root.style.width=1280;root.style.height=720;using var table=new ArenaGameplayPresentation(root);
            try{
                var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
                var snapshot=wire["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();snapshot["turn"]=2;
                var spell=(JObject)snapshot["objects"][0].DeepClone();spell["object_id"]="dork";spell["presentation_id"]="dork-hand";spell["zone"]="hand";spell["owner_id"]="one";spell["controller_id"]="one";spell["hidden"]=false;spell["face_down"]=false;spell["attachments"]=new JArray();spell["attached_to"]=null;spell["characteristics"]["name"]="Whisperer of the Wilds";spell["characteristics"]["type_line"]="Creature — Human Shaman";
                var other=(JObject)spell.DeepClone();other["object_id"]="other";other["presentation_id"]="other-hand";snapshot["objects"]=new JArray(spell,other);
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));yield return null;
                foreach(string zone in new[]{"stack","battlefield"}){
                    CardView retiring=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="dork")retiring=view;});retiring.Focus();using(var enter=PointerEnterEvent.GetPooled()){enter.target=retiring;retiring.SendEvent(enter);}yield return null;
                    snapshot["revision"]=(long)snapshot["revision"]+1;spell["zone"]=zone;spell["presentation_id"]="dork-"+zone;
                    Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));yield return null;yield return null;
                    Assert.That(retiring.parent,Is.Null,"A detached card must never be re-added by the previous hand layout");Assert.That(table.Surface.CardsRoot.Query<CardView>().ToList().Count,Is.EqualTo(2));
                    CardView current=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="dork")current=view;});Assert.That(current,Is.Not.SameAs(retiring));Assert.That(current.panel,Is.SameAs(root.panel));
                    for(int pick=0;pick<4;pick++)Assert.DoesNotThrow(()=>root.panel.Pick(current.worldBound.center));
                    LogAssert.NoUnexpectedReceived();
                }
            }finally{Object.Destroy(node);Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator ZoneBrowserBackOutsideClickAndEscapeRemainUsable()
        {
            var node=new GameObject("Zone dismissal");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;
            var root=doc.rootVisualElement;root.style.width=1280;root.style.height=720;using var table=new ArenaGameplayPresentation(root);
            try{
                var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
                var snapshot=wire["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();snapshot["turn"]=2;
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];
                snapshot["objects"]=new JArray();var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));yield return null;
                var browser=root.Q<ZoneBrowser>();var back=root.Q<Button>("close-public-zone");
                var turns=root.Q<GameplayDrawer>("turns-panel");Assert.That(table.HudRegistry.Find(GameplayHudIds.Turns).Element,Is.SameAs(turns));Assert.That(turns.Content.Contains(root.Q("table-phase-strip")),Is.True);Assert.That(turns.Content.Contains(root.Q("table-phase")),Is.True);
                Assert.That(root.Q<Button>("close-turns-panel"),Is.Null);using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=turns.Tab;turns.Tab.SendEvent(submit);}yield return null;Assert.That(turns.IsOpen,Is.False);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=turns.Tab;turns.Tab.SendEvent(submit);}yield return null;Assert.That(turns.IsOpen,Is.True);
                Assert.That(table.BrowsePublicZone("graveyard",viewer),Is.True);yield return null;
                // Reproduce a passive preview covering the close button: descendants must all pass input through.
                var preview=table.Surface.InspectionView;var previewClose=root.Q<Button>("close-inspection");
                using(var overlay=new GameplayOverlay(preview,previewClose)){
                    overlay.Show(false);preview.style.left=back.worldBound.x-10;preview.style.top=back.worldBound.y-10;preview.style.width=300;preview.style.height=420;yield return null;
                    var picked=root.panel.Pick(back.worldBound.center);Assert.That(picked==back || back.Contains(picked),Is.True,"Passive card preview must not block Back to battlefield");
                    using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=back;back.SendEvent(submit);}yield return null;
                    Assert.That(browser.style.display.value,Is.EqualTo(DisplayStyle.None));
                }
                table.BrowsePublicZone("graveyard",viewer);yield return null;
                var zones=root.Q<GameplayDrawer>("zones-drawer");zones.SetOpen(true);
                using(var escape=KeyDownEvent.GetPooled('\0',KeyCode.Escape,EventModifiers.None)){escape.target=zones.Tab;zones.Tab.SendEvent(escape);}yield return null;
                Assert.That(browser.style.display.value,Is.EqualTo(DisplayStyle.None),"Escape must reach the active zone browser before a child drawer consumes it");
                table.BrowsePublicZone("graveyard",viewer);yield return null;
                using(var outside=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=new Vector2(2,2)})){outside.target=root;root.SendEvent(outside);}yield return null;
                Assert.That(browser.style.display.value,Is.EqualTo(DisplayStyle.None));
                Assert.That(zones.IsOpen,Is.True,"Dismissing the browser preserves the normal HUD drawer state");
                var original=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0].DeepClone();
                original["object_id"]="known-search-card";original["zone"]="library";original["owner_id"]=viewer;original["hidden"]=false;original["face_down"]=false;original["attached_to"]=null;original["attachments"]=new JArray();snapshot["objects"]=new JArray(original);
                var decision=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"]["body"]["snapshot"]["decision"].DeepClone();
                decision["family"]="selection";decision["is_priority"]=false;decision["options"]=new JArray(new JObject{["option_id"]="known-search-option",["label"]="Known card",["object_id"]="known-search-card",["player_id"]=null,["selected"]=false});snapshot["decision"]=decision;
                for(int revision=0;revision<2;revision++){
                    snapshot["revision"]=(long)snapshot["revision"]+1;Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true)),Is.True);
                    table.Present(ViewerDecisionProjection.ParseSnapshot(wire.ToString(),session,viewer,0,true));yield return null;
                    if(revision==0){Assert.That(browser.style.display.value,Is.EqualTo(DisplayStyle.Flex));table.ClosePublicZone();}
                    else Assert.That(browser.style.display.value,Is.EqualTo(DisplayStyle.None),"A repeated snapshot of the same decision must respect dismissal");
                }

            }finally{Object.Destroy(node);Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator ExileBrowserCardSubmitsItsExactEngineOfferedAction()
        {
            var node=new GameObject("Playable exile");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            document.rootVisualElement.style.width=1280;document.rootVisualElement.style.height=720;
            using var table=new ArenaGameplayPresentation(document.rootVisualElement);
            var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();var snapshot=envelope["body"]["snapshot"];
            var card=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0].DeepClone();
            card["object_id"]="permitted-exile";card["zone"]="exile";card["owner_id"]="one";card["controller_id"]=null;card["hidden"]=false;card["face_down"]=false;snapshot["objects"]=new JArray(card);
            snapshot["turn"]=2;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["priority_player_id"]="one";snapshot["actions_complete"]=true;
            snapshot["decision"]["is_priority"]=true;snapshot["decision"]["options"]=new JArray();
            snapshot["actions"]=new JArray(new JObject{["action_id"]="cast-permitted-exile",["kind"]="cast_spell",["object_id"]="permitted-exile",["label"]="Cast from exile",["priority_class"]="meaningful"});
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new System.Threading.Tasks.TaskCompletionSource<bool>(System.Threading.Tasks.TaskCreationOptions.RunContinuationsAsynchronously);
            using var host=new ViewerSessionHost(table.Surface,peer.Bootstrap(),owner.Task,true);table.Bind(host);
            try{
                float deadline=Time.realtimeSinceStartup+10;while(host.PresentedDecision==null && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                Assert.That(host.PresentedDecision,Is.Not.Null);table.Decisions.Tick();table.Present(host.PresentedDecision.Frame);yield return null;
                Assert.That(table.BrowsePublicZone("exile","one"),Is.True);yield return null;
                CardView view=null;table.Surface.VisitPresented((projected,presented)=>{if(projected.ObjectId=="permitted-exile")view=presented;});
                Assert.That(view,Is.Not.Null);Assert.That(view.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(view.ClassListContains("actionable"),Is.True);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=view;view.SendEvent(submit);}
                var read=System.Threading.Tasks.Task.Run(()=>Manaforge.Play.Protocol.WireMessages.Parse(peer.ReadCommandForFixture()));while(!read.IsCompleted && Time.realtimeSinceStartup<deadline)yield return null;
                Assert.That(read.IsCompleted,Is.True);Assert.That((string)read.GetAwaiter().GetResult()["body"]["action_id"],Is.EqualTo("cast-permitted-exile"));
            }finally{host.Cancel();Object.Destroy(node);Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator AuraSitsWithItsHostAndCountOpensTheAttachmentBrowser()
        {
            var node=new GameObject("Attachment presentation");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;document.rootVisualElement.style.width=1280;document.rootVisualElement.style.height=720;var table=new ArenaGameplayPresentation(document.rootVisualElement);
            try{
                var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));var message=(JObject)corpus["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();snapshot["turn"]=2;
                var host=(JObject)snapshot["objects"][0].DeepClone();host["object_id"]="enchanted-host";host["zone"]="battlefield";host["hidden"]=false;host["face_down"]=false;host["tapped"]=false;host["characteristics"]["name"]="Enchanted creature";host["characteristics"]["type_line"]="Creature";host["attachments"]=new JArray("public-aura");host["attached_to"]=null;
                var aura=(JObject)host.DeepClone();aura["object_id"]="public-aura";aura["characteristics"]["name"]="Public Aura";aura["characteristics"]["type_line"]="Enchantment — Aura";aura["attachments"]=new JArray();aura["attached_to"]="enchanted-host";snapshot["objects"]=new JArray(host,aura);
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));yield return null;table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));
                CardView parent=null,attached=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="enchanted-host")parent=view;if(card.ObjectId=="public-aura")attached=view;});Assert.That(parent,Is.Not.Null);Assert.That(attached,Is.Not.Null);Assert.That(attached.style.left.value.value,Is.GreaterThan(parent.style.left.value.value));Assert.That(attached.style.top.value.value,Is.GreaterThan(parent.style.top.value.value));
                var badge=document.rootVisualElement.Q<Button>("attachment-count-enchanted-host");Assert.That(badge,Is.Not.Null);using(var click=NavigationSubmitEvent.GetPooled()){click.target=badge;badge.SendEvent(click);}Assert.That(document.rootVisualElement.Q<Label>("public-zone-title").text,Does.Contain("Attachments"));Assert.That(attached.Mode,Is.EqualTo(CardPresentationMode.Full));
                table.ClosePublicZone();snapshot["revision"]=(long)snapshot["revision"]+1;host["attachments"]=new JArray();aura["attached_to"]=null;table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));Assert.That(document.rootVisualElement.Q<Button>("attachment-count-enchanted-host"),Is.Null);
            }finally{table.Dispose();Object.Destroy(node);Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator StackAutomaticallyExpandsAndClearsItsToolbar()
        {
            var node=new GameObject("Stack focus presentation");var settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;document.rootVisualElement.style.width=1280;document.rootVisualElement.style.height=720;
            var table=new ArenaGameplayPresentation(document.rootVisualElement);
            try{
                var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));var message=(JObject)corpus["positive"][0]["envelope"].DeepClone();var snapshot=message["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();snapshot["commanders"]=null;snapshot["stack_targets"]=new JArray();var card=snapshot["objects"][0];card["zone"]="stack";card["hidden"]=false;card["face_down"]=false;card["characteristics"]["type_line"]="Ability";
                string session=(string)snapshot["session_id"],viewer=(string)snapshot["viewer_id"];var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;
                table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));yield return null;
                var toggle=document.rootVisualElement.Q<Button>("stack-focus-toggle");Assert.That(toggle.text,Is.EqualTo("Minimize"));Assert.That(document.rootVisualElement.Q<Button>("stack-resolve-all").style.display.value,Is.EqualTo(DisplayStyle.Flex));
                using(var click=NavigationSubmitEvent.GetPooled()){click.target=toggle;toggle.SendEvent(click);}Assert.That(toggle.text,Is.EqualTo("View"));
                snapshot["revision"]=(long)snapshot["revision"]+1;snapshot["objects"]=new JArray();table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));table.Present(ViewerDecisionProjection.ParseSnapshot(message.ToString(),session,viewer,0,true));
                Assert.That(document.rootVisualElement.Q<VisualElement>("stack-toolbar").style.display.value,Is.EqualTo(DisplayStyle.None));
            }finally{table.Dispose();Object.Destroy(node);Object.Destroy(settings);}
        }
        [UnityTest] public IEnumerator HoverReturnsToKeyboardPreviewAndRevocationClearsItWithoutACommand()
        {
            var node=new GameObject("Authenticated Arena focus test");var settings=ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var document=node.AddComponent<UIDocument>();document.panelSettings=settings;
            var table=new ArenaGameplayPresentation(document.rootVisualElement);ViewerSessionHost host=null;
            try{
                string fixtures=Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures");
                var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(fixtures,"receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();
                var snapshot=envelope["body"]["snapshot"];
                var card=JObject.Parse(File.ReadAllText(Path.Combine(fixtures,"wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0].DeepClone();
                card["object_id"]=snapshot["objects"][0]["object_id"];card["zone"]="hand";card["owner_id"]="one";card["controller_id"]="one";
                var grave=card.DeepClone();grave["object_id"]="grave-card";grave["zone"]="graveyard";
                snapshot["objects"]=new JArray(card,grave);
                using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());
                var owner=new System.Threading.Tasks.TaskCompletionSource<bool>(System.Threading.Tasks.TaskCreationOptions.RunContinuationsAsynchronously);
                host=new ViewerSessionHost(table.Surface,peer.Bootstrap(),owner.Task,true);table.Bind(host);
                float deadline=Time.realtimeSinceStartup+10;
                while(host.PresentedDecision==null && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                Assert.That(host.PresentedDecision,Is.Not.Null);table.Decisions.Tick();table.Present(host.PresentedDecision.Frame);yield return null;
                CardView view=null;table.Surface.VisitPresented((projected,presented)=>{if(projected.Zone=="hand")view=presented;});Assert.That(view,Is.Not.Null);
                view.Focus();yield return null;
                using(var enter=PointerEnterEvent.GetPooled()){enter.target=view;view.SendEvent(enter);}
                using(var leave=PointerLeaveEvent.GetPooled()){leave.target=view;view.SendEvent(leave);}
                Assert.That(table.Surface.InspectionView.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));
                Assert.That(table.Surface.InspectionView.Q<Label>("name").text,Is.Not.Empty);
                Assert.That(peer.PendingCommandBytes,Is.Zero,"Focus and hover are presentation-only");
                Assert.That(table.BrowsePublicZone("graveyard","one"),Is.True);yield return null;
                table.Present(host.PresentedDecision.Frame);yield return null;
                Assert.That(document.rootVisualElement.Q<Label>("board-input-hint"),Is.Null,"The table must not mount instructional hints");
                owner.TrySetResult(true);deadline=Time.realtimeSinceStartup+10;
                while(!host.Completion.IsCompleted && Time.realtimeSinceStartup<deadline)yield return null;
                Assert.That(host.Completion.IsCompleted,Is.True);host.Tick();yield return null;
                Assert.That(table.Surface.InspectionView.Q<Label>("name").text,Is.Empty);
                Assert.That(table.Surface.CardsRoot.childCount,Is.Zero);
            }finally{host?.Dispose();table.Dispose();Object.Destroy(node);Object.Destroy(settings);}
            yield return null;
        }
        [UnityTest] public IEnumerator AuthenticatedZonesRemainDistinctAtDesktopSizesAndClearOnHandoff()
        {
            var gameObject=new GameObject("Arena table test");var settings=ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=gameObject.AddComponent<UIDocument>();doc.panelSettings=settings;
            var table=new ArenaGameplayPresentation(doc.rootVisualElement);
            try {
                var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
                var snapshot=envelope["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();
                snapshot["players"][0]["library_count"]=40;string viewer=(string)snapshot["viewer_id"],session=(string)snapshot["session_id"],other=(string)snapshot["players"][1]["player_id"];
                var original=snapshot["objects"][0].DeepClone();var cards=new JArray();
                for(int i=0;i<4;i++){
                    var card=original.DeepClone();card["object_id"]="table-"+i;card["owner_id"]=i==3?other:viewer;card["controller_id"]=i==3?other:viewer;
                    card["zone"]=i==0?"hand":"battlefield";card["characteristics"]["name"]="Same visible name";card["characteristics"]["type_line"]=i==1?"Basic Land":"Artifact Creature";card["tapped"]=i==1;
                    cards.Add(card);
                }
                snapshot["objects"]=cards;
                var ticket=table.Surface.BeginViewer(session,viewer);yield return null;yield return null;
                var cardFrame=ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true);
                Assert.That(table.Surface.TryPresent(ticket,cardFrame),Is.True);
                var frame=ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true);
                var views=new Dictionary<string,CardView>();table.Surface.VisitPresented((c,v)=>views.Add(c.ObjectId,v));
                foreach(var size in new[]{new Vector2(1280,720),new Vector2(1366,768),new Vector2(1920,1080),new Vector2(2560,1440)}){
                    doc.rootVisualElement.style.width=size.x;doc.rootVisualElement.style.height=size.y;yield return null;table.Present(frame);yield return null;
                    Assert.That(views["table-3"].resolvedStyle.top,Is.LessThan(views["table-2"].resolvedStyle.top));
                    Assert.That(views["table-2"].resolvedStyle.top,Is.LessThan(views["table-1"].resolvedStyle.top));
                    Assert.That(views["table-1"].style.rotate.value.angle.value,Is.EqualTo(90));Assert.That(views["table-1"].Q<Label>("status").resolvedStyle.display,Is.EqualTo(DisplayStyle.None));
                    var localSeat=doc.rootVisualElement.Q<Label>("local-seat");var opposingSeat=doc.rootVisualElement.Q<Label>("opponent-seat");
                    Assert.That(doc.rootVisualElement.Query<PlayerPanel>().ToList().Count,Is.EqualTo(2));
                    Assert.That(doc.rootVisualElement.worldBound.Contains(localSeat.worldBound.center),Is.True);Assert.That(doc.rootVisualElement.worldBound.Contains(opposingSeat.worldBound.center),Is.True);
                    Assert.That(localSeat.worldBound.Overlaps(opposingSeat.worldBound),Is.False);
                    Assert.That(views["table-1"].worldBound.Overlaps(localSeat.worldBound),Is.False,"Tapped lands must leave the life medallion visible");

                    foreach(var view in views.Values){Assert.That(view.resolvedStyle.left,Is.GreaterThanOrEqualTo(0));Assert.That(view.resolvedStyle.left+view.resolvedStyle.width,Is.LessThanOrEqualTo(size.x));}
                }
                doc.rootVisualElement.style.width=1280;doc.rootVisualElement.style.height=720;yield return null;
                // Pointer focus temporarily overrides keyboard focus and returns to it on leave.
                views["table-2"].Focus();yield return null;
                using(var enter=PointerEnterEvent.GetPooled()){enter.target=views["table-3"];views["table-3"].SendEvent(enter);}yield return null;
                Assert.That(views["table-3"].style.scale.value.value.x,Is.EqualTo(1.12f));
                Assert.That(views["table-2"].style.scale.value.value.x,Is.EqualTo(1));
                using(var leave=PointerLeaveEvent.GetPooled()){leave.target=views["table-3"];views["table-3"].SendEvent(leave);}yield return null;
                Assert.That(views["table-2"].style.scale.value.value.x,Is.EqualTo(1.12f));
                Assert.That(views["table-3"].style.scale.value.value.x,Is.EqualTo(1));
                for(int i=4;i<64;i++){var extra=cards[2].DeepClone();extra["object_id"]="crowd-"+i;cards.Add(extra);}
                snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                var rowScroll=doc.rootVisualElement.Q<ScrollView>("card-scroll-local-permanents");Assert.That(rowScroll,Is.Not.Null);Assert.That(doc.rootVisualElement.Q<Button>("local-permanents-next"),Is.Null);
                Assert.That(rowScroll.horizontalScrollerVisibility,Is.EqualTo(ScrollerVisibility.Hidden));Assert.That(rowScroll.verticalScrollerVisibility,Is.EqualTo(ScrollerVisibility.Hidden));
                using(var wheel=WheelEvent.GetPooled(new Event{type=EventType.ScrollWheel,delta=new Vector2(0,3)})){wheel.target=rowScroll;rowScroll.SendEvent(wheel);}yield return null;
                Assert.That(rowScroll.scrollOffset.x,Is.GreaterThan(0));Assert.That(views["table-2"].resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));
                for(int i=0;i<2;i++){var commander=original.DeepClone();commander["object_id"]="command-"+i;commander["zone"]="command";commander["owner_id"]=i==0?viewer:other;commander["controller_id"]=null;cards.Add(commander);}
                snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.Zone=="command")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex),"Both public command zones remain available for inspection and native offers");});
                // With a normal (non-opening) hand, rotated cards leave the action rail clear.
                snapshot["turn"]=2;
                // Large hands stay selectable through a fitted, focusable fan; public-zone browsing
                // preserves authenticated ownership even when every card has the same name.
                for(int i=0;i<30;i++){var extra=cards[0].DeepClone();extra["object_id"]="hand-"+i;cards.Add(extra);}
                for(int i=0;i<2;i++){var extra=original.DeepClone();extra["object_id"]="grave-"+i;extra["zone"]="graveyard";extra["owner_id"]=i==0?viewer:other;extra["controller_id"]=null;cards.Add(extra);}
                snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                var handScroll=doc.rootVisualElement.Q<ScrollView>("card-scroll-hand");Assert.That(handScroll,Is.Null);Assert.That(doc.rootVisualElement.Q<Button>("hand-next"),Is.Null);
                table.Surface.VisitPresented((card,view)=>{if(card.Zone=="hand"){Assert.That(view.resolvedStyle.left,Is.GreaterThanOrEqualTo(0));Assert.That(view.resolvedStyle.left+view.resolvedStyle.width,Is.LessThanOrEqualTo(1280));}});Assert.That(views["table-0"].resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));
                doc.rootVisualElement.Q<GameplayDrawer>("zones-drawer").SetOpen(true);yield return null;
                var graveButton=doc.rootVisualElement.Q<Label>("opponent-graveyard");Assert.That(graveButton,Is.Not.Null);
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=graveButton;graveButton.SendEvent(submit);}yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="grave-1")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));if(card.ObjectId=="grave-0")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None));});
                CardView graveView=null;table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="grave-1")graveView=view;if(card.Zone=="battlefield" || card.Zone=="hand")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None));});
                Assert.That(graveView,Is.Not.Null);
                Assert.That(doc.rootVisualElement.Q<VisualElement>("board-navigation").childCount,Is.Zero,"No zone or battlefield pagination is created");
                var picked=doc.rootVisualElement.panel.Pick(graveView.worldBound.center);
                Assert.That(picked==graveView || picked!=null && graveView.Contains(picked),Is.True,"The drawer must not cover the displayed card's pointer target");
                Assert.That(table.BrowsePublicZone("hand",viewer),Is.False,"Private zones cannot be requested through public navigation");
                Assert.That(table.BrowsePublicZone("exile",other),Is.True,"Empty zones remain discoverable without fabricating cards");
                yield return null;
                Assert.That(doc.rootVisualElement.Q<Label>("zone-browser-summary").text,Does.Contain("No viewer-visible cards"));
                Assert.That(table.BrowsePublicZone("library","unknown-player"),Is.False);
                Assert.That(table.BrowsePublicZone("library",viewer),Is.True);yield return null;
                Assert.That(doc.rootVisualElement.Q<VisualElement>("zone-browser-back").resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));
                Assert.That(doc.rootVisualElement.Q<Label>("zone-browser-summary").text,Does.Contain("0 known"));
                table.Surface.VisitPresented((card,view)=>Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None),"Browsing a hidden library must not expose the hand or other zones"));
                var closeZone=doc.rootVisualElement.Q<Button>("close-public-zone");
                using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=closeZone;closeZone.SendEvent(submit);}yield return null;
                table.Surface.VisitPresented((card,view)=>{if(card.Zone=="graveyard")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.None));});
                // A library search browser opens only for admitted engine-offered objects.
                var known=original.DeepClone();known["object_id"]="known-library-card";known["zone"]="library";known["owner_id"]=viewer;known["controller_id"]=JValue.CreateNull();cards.Add(known);
                var offered=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"]["body"]["snapshot"]["decision"].DeepClone();
                offered["family"]="selection";offered["is_priority"]=false;offered["can_finish"]=true;
                offered["options"]=new JArray(new JObject{["option_id"]="known-library-option",["label"]="Known card",["object_id"]="known-library-card",["player_id"]=JValue.CreateNull(),["selected"]=false});
                snapshot["decision"]=offered;snapshot["revision"]=(long)snapshot["revision"]+1;
                Assert.That(table.Surface.TryPresent(ticket,ViewerCardProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true)),Is.True);
                table.Present(ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),session,viewer,0,true));yield return null;
                Assert.That(doc.rootVisualElement.Q<Label>("public-zone-title").text,Does.Contain("Library"));
                Assert.That(doc.rootVisualElement.Q<Label>("zone-browser-summary").text,Does.Contain("1 known"));
                Assert.That(doc.rootVisualElement.Q<VisualElement>("zone-browser-back").resolvedStyle.display,Is.EqualTo(DisplayStyle.None));
                table.Surface.VisitPresented((card,view)=>{if(card.ObjectId=="known-library-card")Assert.That(view.resolvedStyle.display,Is.EqualTo(DisplayStyle.Flex));});
                Assert.That(table.Surface.ClearViewer(ticket),Is.True);int visited=0;table.Surface.VisitPresented((c,v)=>visited++);Assert.That(visited,Is.Zero);Assert.That(table.Surface.CardsRoot.childCount,Is.Zero);
            }finally{table.Dispose();Object.Destroy(gameObject);Object.Destroy(settings);}
            yield return null;
        }
    }
}

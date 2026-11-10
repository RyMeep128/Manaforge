using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayHudDrawerTests
    {
        private static JObject Fixture(string file="wire-receive-v1.json")
        {
            var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures",file)));
            return (JObject)(file=="wire-receive-v1.json"?corpus["positive"][0]["envelope"]:corpus["cases"][0]["steps"][0]["envelope"]).DeepClone();
        }
        private static ProjectedDecisionFrame Frame(JObject envelope)
        {
            var snapshot=envelope["body"]["snapshot"];
            return ViewerDecisionProjection.ParseSnapshot(envelope.ToString(),(string)snapshot["session_id"],(string)snapshot["viewer_id"],0,true);
        }
        private static UIDocument Document(out GameObject node,out PanelSettings settings)
        {
            node=new GameObject("Reusable HUD/drawers");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;return doc;
        }
        [Test] public void DrawerCyclesKeepChildrenAndNeverEnableDisabledCommands()
        {
            using var drawer=new GameplayDrawer("Independent",GameplayDrawerDirection.Left);
            var button=new Button();button.SetEnabled(false);drawer.Content.Add(button);drawer.RefreshInput();
            Assert.That(button.pickingMode,Is.EqualTo(PickingMode.Ignore));Assert.That(button.focusable,Is.False);
            for(int i=0;i<30;i++){drawer.SetOpen(true);Assert.That(button.enabledSelf,Is.False);drawer.SetOpen(false);}
            var replacement=new Button();button.RemoveFromHierarchy();drawer.Content.Add(replacement);drawer.RefreshInput();drawer.SetOpen(true);
            Assert.That(replacement.focusable,Is.True);Assert.That(replacement.pickingMode,Is.EqualTo(PickingMode.Position));
            drawer.SetAttention(true,"Choice required");drawer.Reset();Assert.That(drawer.NeedsAttention,Is.False);Assert.That(drawer.Tab.enabledInHierarchy,Is.True);
            drawer.Dispose();drawer.SetOpen(true);Assert.That(drawer.IsOpen,Is.False);
        }
        [UnityTest] public IEnumerator HudUsesFormatAndExplicitSeatIdentityUnderAlternativeRoot()
        {
            var doc=Document(out var node,out var settings);var alternate=new VisualElement();doc.rootVisualElement.Add(alternate);
            using var surface=new ViewerCardSurface(alternate);using var hud=new GameplayPlayerHud();alternate.Add(hud);hud.style.width=340;hud.style.height=400;using var zones=new GameplayZonePanel();alternate.Add(zones);
            try{
                var envelope=Fixture();var snapshot=envelope["body"]["snapshot"];snapshot["decision"]=null;snapshot["actions"]=new JArray();
                foreach(var player in snapshot["players"]){player["name"]="Same name";player["life"]=40;}
                var extra=snapshot["players"][1].DeepClone();extra["player_id"]="third-seat";((JArray)snapshot["players"]).Add(extra);
                snapshot["commanders"]=new JArray(Enumerable.Range(0,3).Select(i=>new JObject{["commander_id"]="commander-"+i,["owner_id"]=i<2?"one":"third-seat",["name"]="Partner "+i,["card_identity"]=null,["command_zone_plays"]=i,["additional_cast_cost"]="{2}",["damage_dealt"]=new JArray(new JArray("one",0),new JArray("two",7),new JArray("third-seat",3))}));
                var frame=Frame(envelope);hud.Present(frame,surface,"freeform");zones.Present(frame,surface,180);yield return null;
                Assert.That(zones.Query<ZonePile>().ToList().Count,Is.EqualTo(9));Assert.That(zones.Pile("third-seat","library").OwnerId,Is.EqualTo("third-seat"));
                Assert.That(hud.CommanderDrawer.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(hud.Players.Count(),Is.EqualTo(3));Assert.That(hud.Q("commander-tile"),Is.Null,"Life 40 and commander data must not override format");
                string activated=null;hud.PlayerActivated+=id=>activated=id;hud.SetTargetable(id=>id=="third-seat");hud.Player("one").Activate();Assert.That(activated,Is.Null);hud.Player("third-seat").Activate();Assert.That(activated,Is.EqualTo("third-seat"));
                foreach(string format in new[]{"commander","unrestricted_commander"}){
                    hud.Present(frame,surface,format);Assert.That(hud.CommanderDrawer.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(hud.CommanderDrawer.IsOpen,Is.False);hud.CommanderDrawer.SetReducedMotion(true);hud.CommanderDrawer.SetOpen(true);Assert.That(hud.Q("hud-commanders").parent,Is.SameAs(hud.CommanderDrawer.Content));hud.CommanderDrawer.SetOpen(false);Assert.That(hud.Query<VisualElement>("commander-tile").ToList().Count,Is.EqualTo(3));
                    Assert.That(hud.Q<CommanderDashboard>("commander-info-one").Query<VisualElement>("commander-tile").ToList().Count,Is.EqualTo(2));
                    Assert.That(hud.Query<ProgressBar>().ToList().Count,Is.EqualTo(9));
                }
                hud.Present(frame,surface,null);Assert.That(hud.Q("commander-tile"),Is.Null);
                var retired=hud.Player("third-seat");snapshot["session_id"]="replacement-session";snapshot["commanders"]=null;((JArray)snapshot["players"]).RemoveAt(2);
                hud.Present(Frame(envelope),surface,"freeform");zones.Present(Frame(envelope),surface,180);Assert.That(zones.Pile("third-seat","library"),Is.Null);activated=null;retired.Activate();Assert.That(activated,Is.Null);Assert.That(hud.Player("third-seat"),Is.Null);
                Assert.That(doc.rootVisualElement.Q("arena-table"),Is.Null);hud.ClearPresentation();Assert.That(hud.Players,Is.Empty);
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator DrawerRestoresKeyboardFocusAndReducedMotionHasNoPendingSlide()
        {
            var doc=Document(out var node,out var settings);using var drawer=new GameplayDrawer("Actions",GameplayDrawerDirection.Down);doc.rootVisualElement.Add(drawer);drawer.style.width=250;drawer.style.top=20;
            var field=new TextField();drawer.Content.Add(field);
            try{
                drawer.SetReducedMotion(true);drawer.SetOpen(true);yield return null;field.Focus();yield return null;
                drawer.SetOpen(false);yield return null;Assert.That(drawer.focusController.focusedElement,Is.SameAs(drawer.Tab));
                Assert.That(drawer.Content.style.visibility.value,Is.EqualTo(Visibility.Hidden));Assert.That(field.focusable,Is.False);
                using(var key=KeyDownEvent.GetPooled('\0',KeyCode.RightArrow,EventModifiers.None)){key.target=drawer.Tab;drawer.Tab.SendEvent(key);}yield return null;
                Assert.That(drawer.IsOpen,Is.True);Assert.That(drawer.focusController.focusedElement==field || field.Contains(drawer.focusController.focusedElement as VisualElement),Is.True);
                drawer.SetReducedMotion(false);drawer.SetOpen(false);drawer.SetOpen(true);yield return new WaitForSecondsRealtime(.3f);
                Assert.That(drawer.Content.style.visibility.value,Is.EqualTo(Visibility.Visible),"A retired close must not hide a reopened drawer");
                drawer.RemoveFromHierarchy();doc.rootVisualElement.Add(drawer);drawer.Reset();Assert.That(drawer.IsOpen,Is.False);
            }finally{UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator IndependentlyMountedHudTargetsTheExplicitPlayerThroughExistingCommands()
        {
            var envelope=Fixture("receive-history-v1.json");var snapshot=envelope["body"]["snapshot"];snapshot["decision"]["family"]="selection";snapshot["decision"]["is_priority"]=false;snapshot["actions"]=new JArray();
            snapshot["decision"]["options"]=new JArray(new JObject{["option_id"]="target-two",["label"]="Same name",["object_id"]=null,["player_id"]="two",["selected"]=false});
            var doc=Document(out var node,out var settings);using var surface=new ViewerCardSurface(doc.rootVisualElement);using var hud=new GameplayPlayerHud();doc.rootVisualElement.Add(hud);hud.style.width=232;hud.style.height=120;
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);
            using var panel=new ViewerDecisionPanel(doc.rootVisualElement,host);using var targeting=new ViewerTargetingController(doc.rootVisualElement,surface,panel,()=>hud.Players);
            try{
                float deadline=Time.realtimeSinceStartup+10;while(host.PresentedDecision==null && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                Assert.That(host.PresentedDecision,Is.Not.Null);panel.Tick();var frame=host.PresentedDecision.Frame;hud.Present(frame,surface,"freeform");hud.SetTargetable(id=>id=="two");targeting.Observe(frame);
                hud.PlayerActivated+=id=>panel.TryActivatePlayer(host.PresentedDecision,id);hud.Player("one").Activate();Assert.That(peer.PendingCommandBytes,Is.Zero);hud.Player("two").Activate();
                var read=Task.Run(()=>Manaforge.Play.Protocol.WireMessages.Parse(peer.ReadCommandForFixture()));while(!read.IsCompleted && Time.realtimeSinceStartup<deadline)yield return null;
                Assert.That(read.IsCompleted,Is.True);Assert.That((string)read.GetAwaiter().GetResult()["body"]["option_id"],Is.EqualTo("target-two"));
            }finally{host.Cancel();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [Test] public void RepeatedHudFramesDoNotCancelLifeAnimation()
        {
            using var seat=new PlayerPanel();seat.Bind("one","One");seat.Present(20,false,false,false);seat.Present(19,true,false,false,true);seat.Present(19,true,false,false,true);
            Assert.That(seat.Q<Label>("seat-life").ClassListContains("life-changed"),Is.True);Assert.That(seat.ClassListContains("is-active"),Is.True);
            seat.Present(19,true,false,true,true);Assert.That(seat.Q<Label>("seat-life").ClassListContains("life-changed"),Is.False);
        }
        [UnityTest] public IEnumerator AutomaticPassingStillDispatchesExactlyOnceWithBothDrawersCollapsed()
        {
            var envelope=Fixture("receive-history-v1.json");var snapshot=envelope["body"]["snapshot"];snapshot["phase"]="BEGINNING";snapshot["step"]="UPKEEP";snapshot["decision"]["family"]="selection";
            snapshot["actions"]=new JArray(new JObject{["action_id"]="pass-offered",["kind"]="pass",["label"]="Pass",["object_id"]=null,["priority_class"]="unknown"});
            var doc=Document(out var node,out var settings);using var surface=new ViewerCardSurface(doc.rootVisualElement);
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);
            using var actions=new GameplayDrawer("Actions");doc.rootVisualElement.Add(actions);using var panel=new ViewerDecisionPanel(actions.Content,host);
            var priorityDrawer=new GameplayDrawer("Priority");doc.rootVisualElement.Add(priorityDrawer);using var priority=new GameplayPriorityDrawer(priorityDrawer,panel);
            try{
                float deadline=Time.realtimeSinceStartup+10;
                while(peer.PendingCommandBytes==0 && Time.realtimeSinceStartup<deadline){host.Tick();panel.Tick();priority.Refresh();actions.RefreshInput();yield return null;}
                Assert.That(peer.PendingCommandBytes,Is.GreaterThan(0));Assert.That(actions.IsOpen,Is.False);Assert.That(priorityDrawer.IsOpen,Is.False);
                var read=Task.Run(()=>Manaforge.Play.Protocol.WireMessages.Parse(peer.ReadCommandForFixture()));
                while(!read.IsCompleted && Time.realtimeSinceStartup<deadline)yield return null;
                Assert.That(read.IsCompleted,Is.True);Assert.That((string)read.GetAwaiter().GetResult()["body"]["action_id"],Is.EqualTo("pass-offered"));
                for(int i=0;i<4;i++){host.Tick();panel.Tick();yield return null;}Assert.That(peer.PendingCommandBytes,Is.Zero,"No duplicate pass may be created by hidden controls");
            }finally{host.Cancel();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator AfterCastingManaOnlyOfferDispatchesPassWithoutManualInput()
        {
            var envelope=Fixture("receive-history-v1.json");var snapshot=envelope["body"]["snapshot"];snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["actions_complete"]=true;snapshot["decision"]["family"]="selection";
            snapshot["actions"]=new JArray(new JObject{["action_id"]="pass-offered",["kind"]="pass",["label"]="Pass",["object_id"]=null,["priority_class"]="unknown"});
            ((JArray)snapshot["actions"]).Add(new JObject{["action_id"]="remaining-mana",["kind"]="activate",["label"]="Activate",["object_id"]=null,["priority_class"]="basic_mana"});
            var spell=Fixture("wire-receive-v1.json")["body"]["snapshot"]["objects"][0].DeepClone();spell["object_id"]="just-cast";spell["zone"]="stack";snapshot["objects"]=new JArray(spell);
            var doc=Document(out var node,out var settings);using var surface=new ViewerCardSurface(doc.rootVisualElement);
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);
            using var actions=new GameplayDrawer("Actions");doc.rootVisualElement.Add(actions);using var panel=new ViewerDecisionPanel(actions.Content,host);
            var priorityDrawer=new GameplayDrawer("Priority");doc.rootVisualElement.Add(priorityDrawer);using var priority=new GameplayPriorityDrawer(priorityDrawer,panel);
            try{
                float deadline=Time.realtimeSinceStartup+10;
                while(peer.PendingCommandBytes==0 && Time.realtimeSinceStartup<deadline){host.Tick();panel.Tick();priority.Refresh();actions.RefreshInput();yield return null;}
                Assert.That(peer.PendingCommandBytes,Is.GreaterThan(0));Assert.That(actions.IsOpen,Is.False);Assert.That(priorityDrawer.IsOpen,Is.False);
                var read=Task.Run(()=>Manaforge.Play.Protocol.WireMessages.Parse(peer.ReadCommandForFixture()));
                while(!read.IsCompleted && Time.realtimeSinceStartup<deadline)yield return null;
                Assert.That(read.IsCompleted,Is.True);Assert.That((string)read.GetAwaiter().GetResult()["body"]["action_id"],Is.EqualTo("pass-offered"));
                for(int i=0;i<4;i++){host.Tick();panel.Tick();yield return null;}Assert.That(peer.PendingCommandBytes,Is.Zero,"No duplicate pass may be created by hidden controls");
            }finally{host.Cancel();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
        [UnityTest] public IEnumerator MandatoryChoiceReopensOnceAndCollapsedPriorityRetainsPreferences()
        {
            var envelope=Fixture("receive-history-v1.json");var snapshot=envelope["body"]["snapshot"];snapshot["phase"]="BEGINNING";snapshot["step"]="UPKEEP";snapshot["decision"]["family"]="selection";
            snapshot["actions"]=new JArray(new JObject{["action_id"]="pass-offered",["kind"]="pass",["label"]="Pass",["object_id"]=null,["priority_class"]="unknown"});
            var doc=Document(out var node,out var settings);using var surface=new ViewerCardSurface(doc.rootVisualElement);
            using var peer=new ViewerSessionHostTests.Peer(envelope.ToString());var owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);
            using var actionDrawer=new GameplayDrawer("Actions");doc.rootVisualElement.Add(actionDrawer);using var panel=new ViewerDecisionPanel(actionDrawer.Content,host);
            using var action=new GameplayActionDrawer(actionDrawer,panel);var priorityDrawer=new GameplayDrawer("Priority");doc.rootVisualElement.Add(priorityDrawer);using var priority=new GameplayPriorityDrawer(priorityDrawer,panel);
            try{
                float deadline=Time.realtimeSinceStartup+10;while(host.PresentedDecision==null && Time.realtimeSinceStartup<deadline){host.Tick();yield return null;}
                Assert.That(host.PresentedDecision,Is.Not.Null);panel.Tick();var frame=host.PresentedDecision.Frame;
                panel.Priority.Current.Automatic=false;panel.Priority.Current.Manual=true;panel.Priority.SetStop("step","DRAW",true);
                priorityDrawer.SetOpen(true);priority.Controls.Root.Q<Foldout>().value=true;Assert.That(panel.PriorityControlsOpen,Is.True);
                priorityDrawer.SetOpen(false);Assert.That(panel.PriorityControlsOpen,Is.False);Assert.That(panel.Priority.Current.Manual,Is.True);Assert.That(panel.Priority.Current.Stops,Does.Contain("step:DRAW"));
                priorityDrawer.SetOpen(true);Assert.That(priority.Controls.Root.Q<Foldout>().value,Is.True);Assert.That(panel.PriorityControlsOpen,Is.True);priorityDrawer.SetOpen(false);
                panel.Priority.Current.Manual=false;panel.Priority.Current.Automatic=true;Assert.That(panel.Priority.Evaluate(frame),Is.Not.Null,"Collapsed controls must allow the existing auto-pass policy");
                snapshot["decision"]["is_priority"]=false;snapshot["decision"]["decision_id"]="mandatory-choice";snapshot["actions"]=new JArray();snapshot["revision"]=(long)snapshot["revision"]+1;
                var mandatory=Frame(envelope);action.Refresh(mandatory);Assert.That(actionDrawer.IsOpen,Is.True);actionDrawer.SetOpen(false);action.Refresh(mandatory);Assert.That(actionDrawer.IsOpen,Is.False);Assert.That(actionDrawer.NeedsAttention,Is.True);
                snapshot["decision"]["decision_id"]="next-choice";action.Refresh(Frame(envelope));Assert.That(actionDrawer.IsOpen,Is.True);
                panel.Priority.Failed();priority.Refresh();Assert.That(priorityDrawer.NeedsAttention,Is.True);Assert.That(priorityDrawer.Tab.text,Does.Contain("Paused"));
                Assert.That(peer.PendingCommandBytes,Is.Zero,"Presentation toggles cannot dispatch game commands");
                action.Reset();Assert.That(actionDrawer.NeedsAttention,Is.False);
            }finally{host.Cancel();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);}yield return null;
        }
    }
}

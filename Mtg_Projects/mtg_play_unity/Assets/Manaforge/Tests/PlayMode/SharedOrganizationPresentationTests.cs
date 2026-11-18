using System;
using System.Collections;
using System.IO;
using System.Linq;
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
    // Two authenticated fixture sockets. Native authority is verified separately by Java CI.
    public sealed class SharedOrganizationPresentationTests
    {
        private static JObject Game(string viewer,string reference)
        {
            var envelope=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"];var snapshot=envelope["body"]["snapshot"];snapshot["session_id"]="fixture-session";snapshot["viewer_id"]=viewer;snapshot["turn"]=3;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["active_player_id"]="one";snapshot["priority_player_id"]="one";
            var card=snapshot["objects"][0];card["object_id"]=reference;card["zone"]="battlefield";card["face_down"]=false;card["tapped"]=false;card["damage"]=0;card["attachments"]=new JArray();card["characteristics"]["name"]="Public permanent";
            var attachment=(JObject)card.DeepClone();attachment["object_id"]=reference+"-attachment";attachment["tapped"]=true;attachment["attached_to"]=reference;attachment["characteristics"]["name"]="Attached permanent";attachment["characteristics"]["counters"]=new JArray(new JArray("+1/+1",2));((JArray)snapshot["objects"]).Add(attachment);card["attachments"]=new JArray(reference+"-attachment");return envelope;
        }
        private static JObject Envelope(string kind,JObject body,int version=2)=>new JObject{["wire_version"]=1,["organization_version"]=version,["message_type"]="organization_"+kind,["message_id"]=Guid.NewGuid().ToString("N"),["body"]=body};
        private static JObject BaseSnapshot(string viewer,string reference,long revision=0,string name="Engine",bool grouped=true)=>Envelope("snapshot",new JObject{["match_epoch"]="match",["viewer_id"]=viewer,["gameplay_revision"]=1,["basis_revision"]=1,["organization_revision"]=revision,["seats"]=new JArray(new JObject{["seat_id"]="one",["root"]=grouped?new JArray():new JArray("handle-"+viewer),["groups"]=grouped?new JArray(new JObject{["group_id"]="g",["name"]=name,["x"]=100000,["y"]=100000,["members"]=new JArray("handle-"+viewer)}):new JArray()},new JObject{["seat_id"]="two",["root"]=new JArray(),["groups"]=new JArray()}),["mappings"]=new JArray(new JObject{["handle"]="handle-"+viewer,["object_reference"]=reference,["seat_id"]="one"})});
        private static JObject Snapshot(string viewer,string reference,long revision=0,string name="Engine",bool grouped=true,int version=2,string mode="panel")
        {
            var result=BaseSnapshot(viewer,reference,revision,name,grouped);result["organization_version"]=version;var body=result["body"];if(version>=3)foreach(var seat in body["seats"])foreach(var group in seat["groups"])group["presentation_mode"]=mode;
            if(version==4)foreach(JObject seat in body["seats"])seat["placements"]=new JArray();
            ((JArray)body["mappings"]).Add(new JObject{["handle"]="attachment-"+viewer,["object_reference"]=reference+"-attachment",["seat_id"]="one"});
            ((JArray)(grouped?body["seats"][0]["groups"][0]["members"]:body["seats"][0]["root"])).Add("attachment-"+viewer);return result;
        }
        private sealed class View : IDisposable
        {
            internal readonly RenderTexture Target;internal readonly GameObject Node;internal readonly PanelSettings Settings;internal readonly ArenaGameplayPresentation Arena;internal readonly ViewerSessionHost Host;internal readonly ViewerSessionHostTests.Peer Peer;internal readonly VisualElement Root;internal readonly JObject Source;internal readonly string Viewer,Reference;
            private readonly TaskCompletionSource<bool> owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            internal View(string viewer,string reference,int width,int height,int version=2,bool actionable=false,int extra=0,string family="priority",bool privateLayout=false)
            {
                Viewer=viewer;Reference=reference;Source=Game(viewer,reference);if(actionable){var priority=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"]["body"]["snapshot"];Source["body"]["snapshot"]["decision"]=priority["decision"].DeepClone();Source["body"]["snapshot"]["actions"]=priority["actions"].DeepClone();Source["body"]["snapshot"]["actions"][0]["object_id"]=reference;if(family!="priority"){var snapshot=Source["body"]["snapshot"];snapshot["decision"]["family"]=family;snapshot["decision"]["is_priority"]=false;snapshot["actions"]=new JArray();if(family=="selection"){snapshot["decision"]["targeting"]=new JObject{["source_id"]=reference+"-attachment",["minimum"]=1,["maximum"]=1,["selected"]=new JArray(),["complete"]=true};snapshot["decision"]["options"]=new JArray(new JObject{["option_id"]="member-target",["object_id"]=reference,["player_id"]=null,["label"]="Choose permanent",["selected"]=false});}}}for(int i=0;i<extra;i++){var copy=(JObject)Source["body"]["snapshot"]["objects"][0].DeepClone();copy["object_id"]=reference+"-extra-"+i;copy["attachments"]=new JArray();copy["tapped"]=i%2==0;((JArray)Source["body"]["snapshot"]["objects"]).Add(copy);}Peer=new ViewerSessionHostTests.Peer(Source.ToString(),viewer:viewer);Node=new GameObject("Shared organization "+viewer);Settings=ScriptableObject.CreateInstance<PanelSettings>();Settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=Node.AddComponent<UIDocument>();doc.panelSettings=Settings;Root=doc.rootVisualElement;Root.style.width=width;Root.style.height=height;Target=new RenderTexture(width,height,24);Target.Create();Settings.targetTexture=Target;Arena=new ArenaGameplayPresentation(Root,capabilities:new GameplayPresentationCapabilities(privateLayout:privateLayout,sharedOrganization:true),layoutPresetStore:new MemoryLayoutPresetStore());Host=new ViewerSessionHost(Arena.Surface,Peer.Bootstrap(organizationVersion:version),owner.Task,true);Arena.Bind(Host);
            }
            internal void Tick(){Host.Tick();Arena.BeforeDecisionTick();Arena.Decisions.Tick();var frame=Host.PresentedDecision?.Frame??ViewerDecisionProjection.Project((JObject)Source["body"]["snapshot"]);if(Host.HasPresentedRevision(frame.Context.Revision)){Arena.PresentOrganization(Host.OrganizationFor(frame.Context.Revision));Arena.Present(frame);}}
            public void Dispose(){owner.TrySetResult(true);Host.Dispose();Arena.Dispose();Peer.Dispose();UnityEngine.Object.Destroy(Node);UnityEngine.Object.Destroy(Settings);Target.Release();UnityEngine.Object.Destroy(Target);}
        }
        private static IEnumerator Until(Func<bool> ready,Action tick=null){double end=Time.realtimeSinceStartupAsDouble+12;while(!ready() && Time.realtimeSinceStartupAsDouble<end){tick?.Invoke();yield return null;}Assert.That(ready(),Is.True,"Organization fixture timed out");}
        private static void Capture(RenderTexture target,string name)
        {
            string directory=Path.Combine(Application.dataPath,"../Artifacts/SharedOrganization");Directory.CreateDirectory(directory);var previous=RenderTexture.active;var texture=new Texture2D(target.width,target.height,TextureFormat.RGBA32,false);
            try{RenderTexture.active=target;texture.ReadPixels(new Rect(0,0,target.width,target.height),0,0);texture.Apply();File.WriteAllBytes(Path.Combine(directory,name+".png"),texture.EncodeToPNG());}finally{RenderTexture.active=previous;UnityEngine.Object.Destroy(texture);}
        }
        private static void Submit(VisualElement target)
        {Assert.That(target,Is.Not.Null);using(var ev=NavigationSubmitEvent.GetPooled()){ev.target=target;target.SendEvent(ev);}}
        private static Task Reply(View view,JObject message)=>Task.Run(()=>view.Peer.ReplyForFixture(message));
        [UnityTest] public IEnumerator TwoAuthenticatedViewsRenderSharedEditsAndKeepViewsSurfaceOwned()
        {
            using var a=new View("one","a-object",1280,720);using var b=new View("two","b-object",1280,720);Action tick=()=>{a.Tick();b.Tick();};yield return Until(()=>a.Host.HasPresentedRevision(1) && b.Host.HasPresentedRevision(1),tick);
            var cap=Envelope("capabilities",new JObject{["versions"]=new JArray(2)});var sent=Task.WhenAll(Reply(a,cap),Reply(b,cap));yield return Until(()=>sent.IsCompleted,tick);sent.GetAwaiter().GetResult();
            var capA=Task.Run(()=>a.Peer.ReadCommandForFixture());var capB=Task.Run(()=>b.Peer.ReadCommandForFixture());yield return Until(()=>capA.IsCompleted && capB.IsCompleted,tick);Assert.That((string)JObject.Parse(capA.Result)["message_type"],Is.EqualTo("organization_capabilities"));Assert.That((string)JObject.Parse(capB.Result)["message_type"],Is.EqualTo("organization_capabilities"));
            sent=Task.WhenAll(Reply(a,Snapshot("one","a-object")),Reply(b,Snapshot("two","b-object")));yield return Until(()=>sent.IsCompleted,tick);sent.GetAwaiter().GetResult();yield return Until(()=>a.Root.Q("organization-group-g")!=null && b.Root.Q("organization-group-g")!=null,tick);
            CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId==a.Reference)card=v;});var parent=card.parent;int count=a.Arena.Surface.CardsRoot.childCount;Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));
            int attached=0;a.Arena.Surface.VisitPresented((c,v)=>{if(c.AttachedTo==a.Reference){attached++;Assert.That(c.Tapped,Is.True);Assert.That(c.Characteristics.Counters.Single().Amount,Is.EqualTo(2));Assert.That(v.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(v.style.rotate.value.angle.value,Is.EqualTo(90));}});Assert.That(attached,Is.EqualTo(1));
            Assert.That(a.Root.Q("organization-group-g").Query<Label>().ToList().Any(label=>label.text.Contains("2, 1 untapped")),Is.True);
            yield return new WaitForEndOfFrame();Capture(a.Target,"owner");Capture(b.Target,"opponent");
            Assert.That(b.Root.Q<Button>("organization-edit-g").style.display.value,Is.EqualTo(DisplayStyle.None),"Opponent has no edit menu");
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,modifiers=EventModifiers.Shift,mousePosition=card.worldBound.center})){down.target=card;card.SendEvent(down);}using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,modifiers=EventModifiers.Shift,mousePosition=card.worldBound.center})){up.target=card;card.SendEvent(up);}Assert.That(card.ClassListContains("organization-selected"),Is.True);Assert.That(a.Peer.PendingCommandBytes,Is.Zero,"Selection cannot submit a native action");
            Assert.That(a.Root.Q("organization-controls").style.display.value,Is.EqualTo(DisplayStyle.None),"No permanent organization toolbar");
            var table=a.Root.Q("arena-table");using(var context=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=1,mousePosition=table.LocalToWorld(new Vector2(500,180))})){context.target=table;table.SendEvent(context);}Assert.That(a.Root.Q("organization-controls").style.display.value,Is.EqualTo(DisplayStyle.None));
            using(var key=KeyDownEvent.GetPooled('g',KeyCode.G,EventModifiers.None)){key.target=table;table.SendEvent(key);}Assert.That(a.Root.Q("organization-controls").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Root.Q<Button>("battlefield-groups"),Is.Null);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            Assert.That(a.Root.Q<GameplayDrawer>("zones-drawer").IsOpen,Is.True,"Decks and zones are visible by default");
            // Editing uses the independent organization channel and broadcasts authoritative geometry.
            Submit(a.Root.Q("organization-group-g").Q<Button>());
            Submit(a.Root.Q<Button>("organization-rename"));a.Root.Q<TextField>("organization-name").value="Renamed";
            Submit(a.Root.Q<Button>("organization-confirm"));var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,tick);var request=JObject.Parse(read.Result);Assert.That((string)request["message_type"],Is.EqualTo("organization_command"));Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("rename"));
            var receipt=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=request["body"]["command_id"],["outcome"]="applied",["organization_revision"]=1,["basis_revision"]=1,["reason_code"]=JValue.CreateNull()});sent=Task.Run(()=>{a.Peer.ReplyForFixture(receipt);a.Peer.ReplyForFixture(Snapshot("one","a-object",1,"Renamed"));b.Peer.ReplyForFixture(Snapshot("two","b-object",1,"Renamed"));});yield return Until(()=>sent.IsCompleted && !a.Host.OrganizationPending,tick);sent.GetAwaiter().GetResult();yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==1 && b.Host.OrganizationFor(1)?.Revision==1,tick);tick();
            Assert.That(a.Root.Q("organization-group-g").Query<Label>().ToList().Any(label=>label.text.StartsWith("Renamed")),Is.True);Assert.That(b.Root.Q("organization-group-g").Query<Label>().ToList().Any(label=>label.text.StartsWith("Renamed")),Is.True);Assert.That(card.parent,Is.SameAs(parent));Assert.That(a.Arena.Surface.CardsRoot.childCount,Is.EqualTo(count));
            foreach(var size in new[]{new Vector2(1280,720),new Vector2(1366,768),new Vector2(1920,1080),new Vector2(2560,1440)}){a.Root.style.width=size.x;a.Root.style.height=size.y;yield return null;tick();Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(float.IsNaN(card.style.left.value.value),Is.False);Assert.That(a.Root.Q("organization-group-g"),Is.Not.Null);}
            // A rejected UI edit leaves authoritative geometry and membership intact.
            Submit(a.Root.Q<Button>("organization-edit-g"));Submit(a.Root.Q<Button>("organization-remove-selected"));read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,tick);request=JObject.Parse(read.Result);
            Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("move"));Assert.That(request["body"]["operation"]["members"].Values<string>(),Is.EquivalentTo(new[]{"handle-one"}));
            var rejected=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=request["body"]["command_id"],["outcome"]="rejected",["organization_revision"]=1,["basis_revision"]=1,["reason_code"]="STALE_BASIS_REVISION"});
            sent=Reply(a,rejected);yield return Until(()=>sent.IsCompleted && !a.Host.OrganizationPending,tick);yield return new WaitForSecondsRealtime(.1f);tick();Assert.That(a.Root.Q("organization-group-g"),Is.Not.Null);Assert.That(card.parent,Is.SameAs(parent));
            // Header movement submits only one organization operation, after the drag threshold.
            var header=a.Root.Q("organization-group-g");var start=header.worldBound.center;var end=start+new Vector2(24,12);
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=start})){down.target=header;header.SendEvent(down);}
            using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseMove,button=0,mousePosition=end})){move.target=a.Root;a.Root.SendEvent(move);}
            using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=end})){up.target=a.Root;a.Root.SendEvent(up);}
            read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,tick);request=JObject.Parse(read.Result);Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("position"));Assert.That((long)request["body"]["operation"]["x"],Is.InRange(0L,1000000L));
            rejected["message_id"]=Guid.NewGuid().ToString("N");rejected["body"]["command_id"]=request["body"]["command_id"];sent=Reply(a,rejected);yield return Until(()=>sent.IsCompleted && !a.Host.OrganizationPending,tick);yield return new WaitForSecondsRealtime(.1f);
            // A temporary correlation gap keeps the admitted arrangement visible.
            a.Arena.PresentOrganization(null);Assert.That(a.Root.Q("organization-group-g").style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(BattlefieldCardAnchorResolver.TryCenter(a.Root,card,out _),Is.True);tick();
            Assert.That(a.Arena.OpenBattlefieldGroups(),Is.True);Assert.That(a.Root.Q<Toggle>("organization-default"),Is.Null,"Groups coexist with the default arrangement");Assert.That(card.parent,Is.SameAs(parent));
            a.Host.Cancel();a.Host.Tick();Assert.That(a.Root.Q("organization-group-g"),Is.Null);Assert.That(a.Root.Q("organization-controls").contentContainer.childCount,Is.Zero);
        }
        [Test] public void DisplayRemapDropsDepartedCardsAndRetainsOriginalCommandRevision()
        {
            var original=new ProjectedOrganizationFrame((JObject)Snapshot("one","a-object",version:3)["body"]);
            var display=new ProjectedOrganizationFrame(original,id=>id=="a-object"?"new-reference":null);
            Assert.That(display.GameplayRevision,Is.EqualTo(original.GameplayRevision));Assert.That(display.Revision,Is.EqualTo(original.Revision));
            Assert.That(display.Groups.Single().Objects,Is.EqualTo(new[]{"new-reference"}));Assert.That(display.Handles.ContainsKey("a-object"),Is.False);Assert.That(display.Handles.ContainsKey("a-object-attachment"),Is.False);
            Assert.That(display.Handles["new-reference"],Is.EqualTo("handle-one"));
        }
        [UnityTest] public IEnumerator PhaseRevisionGapKeepsCollapsedGroupInsteadOfFlashingDefaultRows()
        {
            using var a=new View("one","a-object",1280,720,3);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);
            var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            sent=Reply(a,Snapshot("one","a-object",version:3,mode:"drawer"));yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");drawer.SetOpen(false);a.Tick();
            CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId=="a-object")card=v;});Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.None));
            var group=a.Root.Q("organization-group-g");var position=group.worldBound.position;
            a.Source["body"]["snapshot"]["revision"]=2;a.Source["body"]["snapshot"]["phase"]="COMBAT";a.Source["body"]["snapshot"]["step"]="BEGIN_COMBAT";a.Source["message_id"]="phase-gap";
            sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);
            for(int i=0;i<3;i++){a.Tick();yield return null;Assert.That(a.Root.Q<GameplayDrawer>("organization-drawer-g"),Is.SameAs(drawer));Assert.That(group.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(drawer.IsOpen,Is.False);Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(group.worldBound.position,Is.EqualTo(position));}
            var aligned=Snapshot("one","a-object",revision:1,version:3,mode:"drawer");aligned["body"]["gameplay_revision"]=2;aligned["body"]["basis_revision"]=2;
            sent=Reply(a,aligned);yield return Until(()=>a.Host.OrganizationFor(2)!=null,a.Tick);a.Tick();Assert.That(a.Root.Q<GameplayDrawer>("organization-drawer-g"),Is.SameAs(drawer));Assert.That(drawer.IsOpen,Is.False);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        private static void Pointer(VisualElement target,EventType type,Vector2 point,EventModifiers modifiers=EventModifiers.None)
        {
            var input=new Event{type=type,button=0,modifiers=modifiers,mousePosition=point};
            if(type==EventType.MouseDown){using var ev=PointerDownEvent.GetPooled(input);ev.target=target;target.SendEvent(ev);}
            else if(type==EventType.MouseUp){using var ev=PointerUpEvent.GetPooled(input);ev.target=target;target.SendEvent(ev);}
            else{using var ev=PointerMoveEvent.GetPooled(input);ev.target=target;target.SendEvent(ev);}
        }
        [UnityTest] public IEnumerator PermanentDragSurvivesPriorityGapAndDropUsesFreshBasisOnce()
        {
            using var a=new View("one","a-object",1280,720,4,true,family:"selection");yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(4)},4));yield return Until(()=>sent.IsCompleted,a.Tick);
            var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            sent=Reply(a,Snapshot("one","a-object",version:4,grouped:false));yield return Until(()=>a.Host.OrganizationFor(1)!=null,a.Tick);a.Tick();yield return null;
            CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId=="a-object")card=v;});
            var table=a.Root.Q("arena-table");var start=card.worldBound.center;var end=table.LocalToWorld(new Vector2(700,330));
            Pointer(card,EventType.MouseDown,start,EventModifiers.Alt);Pointer(table,EventType.MouseDrag,end,EventModifiers.Alt);yield return null;
            var layer=a.Root.Q("organization-drag-layer");Assert.That(card.parent,Is.SameAs(layer));var position=new Vector2(card.style.left.value.value,card.style.top.value.value);
            a.Source["message_id"]="drag-priority-change";var snapshot=a.Source["body"]["snapshot"];snapshot["revision"]=2;snapshot["priority_player_id"]="two";snapshot["decision"]=JValue.CreateNull();snapshot["actions"]=new JArray();
            sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);
            for(int i=0;i<3;i++){a.Tick();yield return null;Assert.That(card.parent,Is.SameAs(layer));Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(new Vector2(card.style.left.value.value,card.style.top.value.value),Is.EqualTo(position));}
            Pointer(table,EventType.MouseUp,end);yield return null;Assert.That(a.Peer.PendingCommandBytes,Is.Zero,"A presentation remap cannot authorize a stale command");Assert.That(card.parent,Is.SameAs(layer),"Keep the dropped preview while waiting for the current basis");
            var aligned=Snapshot("one","a-object",revision:1,version:4,grouped:false);aligned["body"]["gameplay_revision"]=2;aligned["body"]["basis_revision"]=2;
            sent=Reply(a,aligned);yield return Until(()=>a.Host.OrganizationFor(2)!=null,a.Tick);
            read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var command=JObject.Parse(read.Result);
            Assert.That((string)command["message_type"],Is.EqualTo("organization_command"));Assert.That((long)command["body"]["basis_revision"],Is.EqualTo(2));Assert.That((string)command["body"]["operation"]["kind"],Is.EqualTo("place"));
            Assert.That(command["body"]["operation"]["members"].Values<string>(),Is.EqualTo(new[]{"handle-one"}));
            var placed=Snapshot("one","a-object",revision:2,version:4,grouped:false);placed["body"]["gameplay_revision"]=2;placed["body"]["basis_revision"]=2;
            placed["body"]["seats"][0]["placements"]=new JArray(new JObject{["handle"]="handle-one",["x"]=command["body"]["operation"]["x"],["y"]=command["body"]["operation"]["y"]});
            var receipt=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=command["body"]["command_id"],["outcome"]="applied",["organization_revision"]=2,["basis_revision"]=2,["reason_code"]=JValue.CreateNull()},4);
            sent=Task.Run(()=>{a.Peer.ReplyForFixture(receipt);a.Peer.ReplyForFixture(placed);});yield return Until(()=>a.Host.OrganizationFor(2)?.Revision==2 && !a.Host.OrganizationPending,a.Tick);
            yield return Until(()=>card.parent!=layer,a.Tick);yield return null;
            Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(Vector2.Distance(position,new Vector2(card.style.left.value.value,card.style.top.value.value)),Is.LessThan(2));Assert.That(a.Peer.PendingCommandBytes,Is.Zero,"Priority updates must never replay the drop or invoke a native action");
        }
        [UnityTest] public IEnumerator LiveTurnsDragContinuesWhilePriorityChanges()
        {
            using var a=new View("one","a-object",1280,720,privateLayout:true);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            yield return Until(()=>a.Arena.LayoutEditor.Initialization.IsCompleted,a.Tick);a.Tick();yield return null;
            var turns=a.Root.Q<GameplayDrawer>("turns-panel");var table=a.Root.Q("arena-table");var start=turns.Tab.worldBound.center;var end=start+new Vector2(140,120);
            Pointer(turns.Tab,EventType.MouseDown,start);Pointer(table,EventType.MouseDrag,end);yield return null;
            Assert.That(a.Arena.LayoutEditor.OwnsGeometry(GameplayHudIds.Turns),Is.True);
            var before=turns.Tab.worldBound.position;
            a.Source["message_id"]="turns-drag-priority-change";a.Source["body"]["snapshot"]["revision"]=2;a.Source["body"]["snapshot"]["priority_player_id"]="two";
            var sent=Reply(a,a.Source);
            yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);a.Tick();yield return null;
            Assert.That(a.Arena.LayoutEditor.OwnsGeometry(GameplayHudIds.Turns),Is.True);Assert.That(turns.Tab.worldBound.position,Is.EqualTo(before));
            end+=new Vector2(50,20);Pointer(table,EventType.MouseDrag,end);Pointer(table,EventType.MouseUp,end);yield return null;
            Assert.That(turns.Tab.worldBound.position.x,Is.GreaterThan(before.x+30));Assert.That(a.Arena.LayoutEditor.OwnsGeometry(GameplayHudIds.Turns),Is.True);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator DepartedPermanentCancelsDragWithoutResurrectingViewOrSendingCommand()
        {
            using var a=new View("one","a-object",1280,720,4);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(4)},4));yield return Until(()=>sent.IsCompleted,a.Tick);
            var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            sent=Reply(a,Snapshot("one","a-object",version:4,grouped:false));yield return Until(()=>a.Host.OrganizationFor(1)!=null,a.Tick);a.Tick();yield return null;
            CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId=="a-object")card=v;});var table=a.Root.Q("arena-table");
            var end=card.worldBound.center+new Vector2(90,-40);Pointer(card,EventType.MouseDown,card.worldBound.center);Pointer(table,EventType.MouseDrag,end);yield return null;
            a.Source["message_id"]="drag-permanent-left";a.Source["body"]["snapshot"]["revision"]=2;a.Source["body"]["snapshot"]["objects"]=new JArray();
            sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);a.Tick();Pointer(table,EventType.MouseUp,end);yield return null;
            Assert.That(card.parent,Is.Null);Assert.That(a.Root.Q("organization-drag-layer").childCount,Is.Zero);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator DrawerHeaderDragSurvivesPriorityAndOrganizationRefresh()
        {
            using var a=new View("one","a-object",1280,720,3);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);
            var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            sent=Reply(a,Snapshot("one","a-object",version:3,mode:"drawer"));yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);a.Tick();yield return null;
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");var table=a.Root.Q("arena-table");var end=drawer.Tab.worldBound.center+new Vector2(150,90);
            Pointer(drawer.Tab,EventType.MouseDown,drawer.Tab.worldBound.center);Pointer(table,EventType.MouseDrag,end);
            a.Source["message_id"]="drawer-priority-change";a.Source["body"]["snapshot"]["revision"]=2;a.Source["body"]["snapshot"]["priority_player_id"]="two";
            sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);
            var aligned=Snapshot("one","a-object",revision:1,version:3,mode:"drawer");aligned["body"]["gameplay_revision"]=2;aligned["body"]["basis_revision"]=2;
            sent=Reply(a,aligned);yield return Until(()=>a.Host.OrganizationFor(2)!=null,a.Tick);a.Tick();
            Assert.That(a.Root.Q("organization-drag-ghost").style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(a.Root.Q<GameplayDrawer>("organization-drawer-g"),Is.SameAs(drawer));
            Pointer(table,EventType.MouseUp,end);read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var command=JObject.Parse(read.Result);
            Assert.That((string)command["body"]["operation"]["kind"],Is.EqualTo("position"));Assert.That((long)command["body"]["basis_revision"],Is.EqualTo(2));
        }
        [UnityTest] public IEnumerator DrawerExpansionIsLocalAndBindingsSurviveUpdatesAndTemporaryGaps()
        {
            using var a=new View("one","a-object",1280,720,3);using var b=new View("two","b-object",1280,720,3);Action tick=()=>{a.Tick();b.Tick();};yield return Until(()=>a.Host.HasPresentedRevision(1) && b.Host.HasPresentedRevision(1),tick);
            var caps=Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3);var sent=Task.WhenAll(Reply(a,caps),Reply(b,caps));yield return Until(()=>sent.IsCompleted,tick);
            var readA=Task.Run(()=>a.Peer.ReadCommandForFixture());var readB=Task.Run(()=>b.Peer.ReadCommandForFixture());yield return Until(()=>readA.IsCompleted && readB.IsCompleted,tick);
            sent=Task.WhenAll(Reply(a,Snapshot("one","a-object",version:3,mode:"drawer")),Reply(b,Snapshot("two","b-object",version:3,mode:"drawer")));yield return Until(()=>sent.IsCompleted && a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null && b.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,tick);
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");var other=b.Root.Q<GameplayDrawer>("organization-drawer-g");Assert.That(drawer.IsOpen && other.IsOpen,Is.True);CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId==a.Reference)card=v;});var parent=card.parent;
            var layer=a.Root.Q("organization-layer-g");Assert.That(layer.Contains(card),Is.True);Assert.That(layer.Contains(drawer),Is.True);
            drawer.SetOpen(true);tick();yield return null;
            var table=a.Root.Q("arena-table");var zones=a.Root.Q<GameplayDrawer>("zones-drawer");
            Assert.That(table.IndexOf(layer),Is.GreaterThan(table.IndexOf(a.Arena.Surface.CardsRoot)));
            zones.SetOpen(true);Assert.That(table.IndexOf(zones),Is.GreaterThan(table.IndexOf(layer)));
            drawer.SetOpen(true);tick();yield return null;Assert.That(table.IndexOf(layer),Is.GreaterThan(table.IndexOf(zones)),"Layout updates must retain the last active drawer in front");Assert.That(card.parent,Is.SameAs(parent));
            drawer.SetOpen(false);tick();yield return null;Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(other.IsOpen,Is.True);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            sent=Reply(a,Snapshot("one","a-object",1,"Mana Rocks",version:3,mode:"drawer"));yield return Until(()=>sent.IsCompleted && a.Host.OrganizationFor(1)?.Revision==1,tick);tick();Assert.That(a.Root.Q<GameplayDrawer>("organization-drawer-g"),Is.SameAs(drawer));Assert.That(drawer.IsOpen,Is.False);Assert.That(drawer.Tab.text,Does.StartWith("Mana Rocks"));
            a.Arena.PresentOrganization(null);Assert.That(a.Root.Q("organization-group-g").style.display.value,Is.EqualTo(DisplayStyle.Flex));tick();Assert.That(drawer.IsOpen,Is.False);
            sent=Reply(a,Snapshot("one","a-object",2,version:3,mode:"panel"));yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==2,tick);tick();Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));
            sent=Reply(a,Snapshot("one","a-object",3,version:3,mode:"drawer"));yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==3,tick);tick();Assert.That(drawer.IsOpen,Is.False);Assert.That(card.parent,Is.SameAs(parent));
            sent=Reply(a,Snapshot("one","a-object",4,grouped:false,version:3));yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==4,tick);tick();Assert.That(a.Root.Q("organization-group-g"),Is.Null);
            sent=Reply(a,Snapshot("one","a-object",5,version:3,mode:"drawer"));yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==5,tick);tick();Assert.That(a.Root.Q<GameplayDrawer>("organization-drawer-g").IsOpen,Is.True,"Deleted state must not be inherited by a new group");
            a.Host.Cancel();a.Host.Tick();Assert.That(a.Root.Q("organization-group-g"),Is.Null);Assert.That(a.Root.Query<CardView>().ToList(),Is.Empty);
        }
        [UnityTest] public IEnumerator CollapsedChooserUsesCanonicalViewsAndExistingActionAdmission()
        {
            using var a=new View("one","a-object",1280,720,3,true);yield return Until(()=>a.Host.PresentedDecision!=null,a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            sent=Reply(a,Snapshot("one","a-object",version:3,mode:"drawer"));yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");a.Root.Q<Toggle>("table-motion").value=true;drawer.SetOpen(false);a.Tick();yield return null;
            CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId==a.Reference)card=v;});var parent=card.parent;Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(drawer.NeedsAttention,Is.True);Assert.That(a.Arena.ResolveCardAnchor(a.Reference).HasValue,Is.True);Assert.That(Vector2.Distance(a.Arena.ResolveCardAnchor(a.Reference).Value,a.Arena.Surface.CardsRoot.parent.WorldToLocal(drawer.Tab.worldBound.center)),Is.LessThan(1));Assert.That(drawer.ReducedMotion,Is.True);Assert.That(a.Arena.ResolveCardAnchor("not-admitted"),Is.Null);
            Submit(a.Root.Q<Button>("organization-members-g"));yield return null;a.Tick();Assert.That(drawer.IsOpen,Is.False);Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(Card(a,a.Reference),Is.SameAs(card));Assert.That(a.Root.Q("organization-member-chooser").style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            using(var inspect=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=1,mousePosition=card.worldBound.center})){inspect.target=card;card.SendEvent(inspect);}Assert.That(a.Arena.Surface.InspectionView.style.display.value,Is.EqualTo(DisplayStyle.Flex));
            using(var inside=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0})){inside.target=a.Arena.Surface.InspectionView;a.Arena.Surface.InspectionView.SendEvent(inside);}Assert.That(a.Arena.Surface.InspectionView.style.display.value,Is.EqualTo(DisplayStyle.Flex),"Inspection controls must remain usable");
            using(var outside=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0})){outside.target=a.Root;a.Root.SendEvent(outside);}Assert.That(a.Arena.Surface.InspectionView.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            Submit(a.Root.Q<Button>("organization-members-close"));yield return null;Assert.That(drawer.IsOpen,Is.False);Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Root.focusController.focusedElement,Is.SameAs(drawer.Tab));
            Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.True);yield return new WaitForEndOfFrame();Capture(a.Target,"collapsed-member-chooser");
            var offer=a.Host.PresentedDecision;Submit(card);read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var command=JObject.Parse(read.Result);Assert.That((string)command["message_type"],Is.EqualTo("command"));Assert.That((string)command["body"]["operation"],Is.EqualTo("perform"));Assert.That((string)command["body"]["action_id"],Is.EqualTo("fixture-action"));Assert.That(drawer.IsOpen,Is.False);Assert.That(a.Arena.Decisions.TryActivateObject(offer,a.Reference),Is.False,"Pending commands cannot be repeated through the chooser");
            a.Arena.CloseBattlefieldMembers();a.Host.Cancel();a.Host.Tick();Assert.That(a.Root.Query<CardView>().ToList(),Is.Empty);
        }
        [UnityTest] public IEnumerator ChooserClosesForMenuZoneAndOfferRetirementWithoutReopeningDrawer()
        {
            using var a=new View("one","a-object",1280,720,3,true);yield return Until(()=>a.Host.PresentedDecision!=null,a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);sent=Reply(a,Snapshot("one","a-object",version:3,mode:"drawer"));yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");drawer.SetOpen(false);Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.True);
            using(var menu=new GameplayMenuOverlay(a.Root,()=>false,()=>Task.FromResult<TrackedCommand>(null),_=>null,a.Arena.InterruptGestures)){menu.Open();Assert.That(a.Root.Q("organization-member-chooser").style.display.value,Is.EqualTo(DisplayStyle.None));menu.Close();}
            Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.True);Assert.That(a.Arena.BrowsePublicZone("graveyard","one"),Is.True);Assert.That(a.Root.Q("organization-member-chooser").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.False);a.Arena.ClosePublicZone();
            Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.True);var captured=a.Host.PresentedDecision;var next=a.Source["body"]["snapshot"];next["revision"]=2;next["decision"]=null;next["actions"]=new JArray();next["objects"][0]["zone"]="graveyard";next["objects"][0]["attachments"]=new JArray();next["objects"][1]["attached_to"]=JValue.CreateNull();a.Source["message_id"]="retired-member";sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);a.Tick();
            Assert.That(a.Root.Q("organization-member-chooser").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.False);Assert.That(a.Arena.Decisions.TryActivateObject(captured,a.Reference),Is.False);Assert.That(drawer.IsOpen,Is.False);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator DenseCollapsedGroupsExposeEveryMemberWithoutPagesOrScrollbars()
        {
            using var a=new View("one","a-object",1280,720,3,false,39);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            var snapshot=Snapshot("one","a-object",version:3,mode:"drawer");for(int i=0;i<39;i++){((JArray)snapshot["body"]["seats"][0]["groups"][0]["members"]).Add("extra-"+i);((JArray)snapshot["body"]["mappings"]).Add(new JObject{["handle"]="extra-"+i,["object_reference"]="a-object-extra-"+i,["seat_id"]="one"});}
            sent=Reply(a,snapshot);yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");drawer.SetOpen(false);Assert.That(a.Arena.OpenBattlefieldMembers("g"),Is.True);yield return null;
            var seen=new System.Collections.Generic.HashSet<string>();a.Arena.Surface.VisitPresented((c,v)=>{if(v.style.display.value!=DisplayStyle.None)seen.Add(c.ObjectId);});
            var memberScroll=a.Root.Q<ScrollView>("card-scroll-group-$chooser-g");Assert.That(memberScroll,Is.Not.Null);Assert.That(a.Root.Q("organization-page-$chooser-g"),Is.Null);Assert.That(memberScroll.horizontalScrollerVisibility,Is.EqualTo(ScrollerVisibility.Hidden));Assert.That(memberScroll.verticalScrollerVisibility,Is.EqualTo(ScrollerVisibility.Hidden));using(var wheel=WheelEvent.GetPooled(new Event{type=EventType.ScrollWheel,delta=new Vector2(0,3)})){wheel.target=memberScroll;memberScroll.SendEvent(wheel);}yield return null;
            Assert.That(memberScroll.scrollOffset.x,Is.GreaterThan(0));float priorOffset=memberScroll.scrollOffset.x;
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=2,mousePosition=new Vector2(500,300)})){down.target=memberScroll;memberScroll.SendEvent(down);}
            using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=2,mousePosition=new Vector2(400,300)})){move.target=memberScroll;memberScroll.SendEvent(move);}
            using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=2,mousePosition=new Vector2(400,300)})){up.target=memberScroll;memberScroll.SendEvent(up);}yield return null;
            Assert.That(memberScroll.scrollOffset.x,Is.GreaterThan(priorOffset));a.Tick();yield return null;Assert.That(memberScroll.scrollOffset.x,Is.GreaterThanOrEqualTo(priorOffset));
            Assert.That(seen.Count,Is.EqualTo(41));Assert.That(drawer.IsOpen,Is.False);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            foreach(var size in new[]{new Vector2(1280,720),new Vector2(1366,768),new Vector2(1920,1080),new Vector2(2560,1440)}){a.Root.style.width=size.x;a.Root.style.height=size.y;yield return null;a.Tick();Assert.That(a.Root.Q("organization-member-chooser").style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(drawer.IsOpen,Is.False);}
            a.Arena.CloseBattlefieldMembers();a.Arena.Surface.VisitPresented((c,v)=>Assert.That(v.style.display.value,Is.EqualTo(DisplayStyle.None)));
        }
        [UnityTest] public IEnumerator CollapsedManaAndTargetChoicesUseTheirExistingDecisionPaths()
        {
            foreach(string family in new[]{"mana","selection"}){
                using var a=new View("one","a-object",1280,720,3,true,family:family);yield return Until(()=>a.Host.PresentedDecision?.CanSubmit==true,a.Tick);
                var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);sent=Reply(a,Snapshot("one","a-object",version:3,mode:"drawer"));yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);
                var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");drawer.SetOpen(false);a.Tick();Assert.That(drawer.NeedsAttention,Is.True);Submit(a.Root.Q<Button>("organization-drawer-edit-g"));Assert.That(a.Root.Q<Button>("organization-inspect-members").enabledSelf,Is.True,"Mandatory choices retain the ellipsis member route");Submit(a.Root.Q<Button>("organization-inspect-members"));yield return null;
                CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId==a.Reference)card=v;});Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Submit(card);read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var command=JObject.Parse(read.Result);Assert.That((string)command["body"]["operation"],Is.EqualTo(family=="mana"?"select_mana_source":"choose"));if(family=="mana")Assert.That((string)command["body"]["object_id"],Is.EqualTo(a.Reference));else Assert.That((string)command["body"]["option_id"],Is.EqualTo("member-target"));Assert.That(drawer.IsOpen,Is.False);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator NamingDraftSurvivesGameplayRevisionAndUsesFreshOrganizationBasis()
        {
            using var a=new View("one","a-object",1280,720,4,true);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(4)},4));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);sent=Reply(a,Snapshot("one","a-object",grouped:false,version:4));yield return Until(()=>a.Host.OrganizationFor(1)!=null,a.Tick);a.Tick();
            yield return null;yield return Drag(a,Card(a,a.Reference),Card(a,a.Reference+"-attachment").worldBound.center);var input=a.Root.Q<TextField>("organization-name");input.value="Keep my draft";
            a.Source["body"]["snapshot"]["revision"]=2;a.Source["message_id"]="priority-progress";sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);a.Tick();Assert.That(a.Root.Q<TextField>("organization-name"),Is.SameAs(input));Assert.That(input.value,Is.EqualTo("Keep my draft"));Assert.That(a.Root.Q<Button>("organization-confirm").enabledSelf,Is.False);
            var latest=Snapshot("one","a-object",1,grouped:false,version:4);latest["body"]["gameplay_revision"]=2;latest["body"]["basis_revision"]=2;sent=Reply(a,latest);yield return Until(()=>a.Host.OrganizationFor(2)!=null,a.Tick);a.Tick();Assert.That(a.Root.Q<TextField>("organization-name"),Is.SameAs(input));Submit(a.Root.Q<Button>("organization-confirm"));read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var command=JObject.Parse(read.Result);Assert.That((long)command["body"]["basis_revision"],Is.EqualTo(2));Assert.That((string)command["body"]["operation"]["name"],Is.EqualTo("Keep my draft"));
        }
        [UnityTest] public IEnumerator OpenGroupToolsRouteLeftClickToMembershipInsteadOfNativeAction()
        {
            using var a=new View("one","a-object",1280,720,3,true);yield return Until(()=>a.Host.PresentedDecision!=null,a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            var empty=Snapshot("one","a-object",grouped:false,version:3);((JArray)empty["body"]["seats"][0]["groups"]).Add(new JObject{["group_id"]="g",["name"]="Rocks",["x"]=0,["y"]=0,["presentation_mode"]="drawer",["members"]=new JArray()});sent=Reply(a,empty);yield return Until(()=>a.Root.Q("organization-group-g")!=null,a.Tick);
            Assert.That(a.Root.Q<Button>("battlefield-groups"),Is.Null);Submit(a.Root.Q<Button>("organization-drawer-edit-g"));Submit(a.Root.Q<Button>("organization-add-cards"));CardView card=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId==a.Reference)card=v;});
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=card.worldBound.center})){down.target=card;card.SendEvent(down);}read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var request=JObject.Parse(read.Result);Assert.That((string)request["message_type"],Is.EqualTo("organization_command"));Assert.That((string)request["body"]["operation"]["group_id"],Is.EqualTo("g"));Assert.That(request["body"]["operation"]["members"].Values<string>(),Is.EqualTo(new[]{"handle-one"}));
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=card.worldBound.center})){down.target=card;card.SendEvent(down);}Assert.That(a.Peer.PendingCommandBytes,Is.Zero,"Pending membership must not turn the next click into a native action");Submit(a.Root.Q<Button>("organization-close"));
        }
        [UnityTest] public IEnumerator OnlyCardOnCardOpensFocusedCreationPromptAndCancelKeepsBothCards(){
            using var a=new View("one","a-object",1280,720,4,true);yield return Until(()=>a.Host.PresentedDecision!=null,a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(4)},4));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            sent=Reply(a,Snapshot("one","a-object",grouped:false,version:4));yield return Until(()=>a.Host.OrganizationFor(1)!=null,a.Tick);a.Tick();yield return null;
            var first=Card(a,a.Reference);var other=Card(a,a.Reference+"-attachment");var origin=new Vector2(first.resolvedStyle.left,first.resolvedStyle.top);var firstParent=first.parent;var otherParent=other.parent;
            Assert.That(a.Arena.OpenBattlefieldGroups(),Is.True);Assert.That(a.Root.Q<Button>("organization-new-group"),Is.Null);Assert.That(a.Root.Q<Button>("organization-new-drawer"),Is.Null);Submit(a.Root.Q<Button>("organization-close"));
            foreach(var card in new[]{first,other}){
                using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,modifiers=EventModifiers.Shift,mousePosition=card.worldBound.center})){down.target=card;card.SendEvent(down);}
                using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=card.worldBound.center})){up.target=card;card.SendEvent(up);}
            }
            yield return Drag(a,first,a.Root.Q("arena-table").LocalToWorld(new Vector2(900,230)));a.Tick();Assert.That(a.Root.Q<TextField>("organization-name"),Is.Null,"Empty-space selection drops cannot create groups");Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            using(var escape=KeyDownEvent.GetPooled('\0',KeyCode.Escape,EventModifiers.None)){escape.target=first;first.SendEvent(escape);}a.Tick();yield return null;
            yield return Drag(a,first,other.worldBound.center);var input=a.Root.Q<TextField>("organization-name");Assert.That(input,Is.Not.Null);Assert.That(a.Root.Q<Label>("organization-prompt-summary").text,Does.StartWith("2 cards"));
            using(var hover=PointerEnterEvent.GetPooled()){hover.target=other;other.SendEvent(hover);}yield return null;var tools=a.Root.Q("organization-controls");Assert.That(tools.parent.IndexOf(tools),Is.GreaterThan(tools.parent.IndexOf(a.Arena.Surface.CardsRoot)),"Card hover cannot cover the naming form");
            Assert.That(a.Root.Q<Button>("organization-confirm").text,Is.EqualTo("Create drawer"));Assert.That(a.Root.Q<Button>("organization-delete-group"),Is.Null);Assert.That(a.Root.Q<Toggle>("organization-default"),Is.Null);
            input.value="   ";Assert.That(a.Root.Q<Button>("organization-confirm").enabledSelf,Is.False);input.value="Pair";Assert.That(a.Root.Q<Button>("organization-confirm").enabledSelf,Is.True);
            Submit(a.Root.Q<Button>("organization-cancel"));a.Tick();yield return null;Assert.That(a.Root.Q("organization-controls").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(first.resolvedStyle.left,Is.EqualTo(origin.x).Within(1));Assert.That(first.resolvedStyle.top,Is.EqualTo(origin.y).Within(1));Assert.That(first.parent,Is.SameAs(firstParent));Assert.That(other.parent,Is.SameAs(otherParent));Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            using var menu=new GameplayMenuOverlay(a.Root,()=>false,()=>Task.FromResult<TrackedCommand>(null),_=>null);menu.SetOrganizationTools(a.Arena.OpenBattlefieldGroups,a.Arena.DismissBattlefieldPrompt);
            yield return Drag(a,first,other.worldBound.center);input=a.Root.Q<TextField>("organization-name");using(var escape=KeyDownEvent.GetPooled('\0',KeyCode.Escape,EventModifiers.None)){escape.target=input;input.SendEvent(escape);}a.Tick();Assert.That(menu.IsOpen,Is.False,"Escape cancels naming before opening the game menu");Assert.That(a.Root.Q("organization-controls").style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator DrawerHeaderCanDragOutsideItsSeatLaneAndStillToggleLocally()
        {
            using var a=new View("one","a-object",1280,720,3);yield return Until(()=>a.Host.HasPresentedRevision(1),a.Tick);var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(3)},3));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);sent=Reply(a,Snapshot("one","a-object",version:3,mode:"drawer"));yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);yield return null;
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");var table=a.Root.Q("arena-table");var start=drawer.Tab.worldBound.center;var end=table.LocalToWorld(new Vector2(1000,30));
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=start})){down.target=drawer.Tab;drawer.Tab.SendEvent(down);}yield return null;
            using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=Vector2.Lerp(start,end,.5f)})){move.target=drawer.Tab;drawer.Tab.SendEvent(move);}yield return null;
            Assert.That(table.HasPointerCapture(PointerId.mousePointerId),Is.True,"Presentation capture survives targeting cleanup between frames");a.Tick();yield return null;
            using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=end})){move.target=table;table.SendEvent(move);}using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=end})){up.target=table;table.SendEvent(up);}
            read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var request=JObject.Parse(read.Result);Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("position"));Assert.That(drawer.IsOpen,Is.True,"Dragging a title must not collapse it");
            var state=Snapshot("one","a-object",1,version:3,mode:"drawer");state["body"]["seats"][0]["groups"][0]["x"]=800000;state["body"]["seats"][0]["groups"][0]["y"]=0;var receipt=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=request["body"]["command_id"],["outcome"]="applied",["organization_revision"]=1,["basis_revision"]=1,["reason_code"]=null},3);sent=Task.Run(()=>{a.Peer.ReplyForFixture(receipt);a.Peer.ReplyForFixture(state);});yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==1,a.Tick);a.Tick();yield return null;Assert.That(a.Root.Q("organization-group-g").worldBound.y,Is.EqualTo(table.worldBound.y).Within(1));
            Submit(drawer.Tab);Assert.That(drawer.IsOpen,Is.False);Submit(drawer.Tab);Assert.That(drawer.IsOpen,Is.True);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        private static IEnumerator Drag(View a,CardView card,Vector2 end){
            var table=a.Root.Q("arena-table");var start=card.worldBound.center;
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,mousePosition=start})){down.target=card;card.SendEvent(down);}yield return null;
            using(var move=PointerMoveEvent.GetPooled(new Event{type=EventType.MouseDrag,button=0,mousePosition=end})){move.target=card;card.SendEvent(move);}yield return null;
            using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,mousePosition=end})){up.target=table;table.SendEvent(up);}
        }
        private static Task Apply(View a,JObject request,JObject snapshot){
            var receipt=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=request["body"]["command_id"],["outcome"]="applied",["organization_revision"]=snapshot["body"]["organization_revision"],["basis_revision"]=snapshot["body"]["basis_revision"].DeepClone(),["reason_code"]=null},4);
            return Task.Run(()=>{a.Peer.ReplyForFixture(receipt);a.Peer.ReplyForFixture(snapshot);});
        }
        private static CardView Card(View a,string id){CardView result=null;a.Arena.Surface.VisitPresented((c,v)=>{if(c.ObjectId==id)result=v;});return result;}
        [UnityTest] public IEnumerator DirectCardDragPersistsAndDropsIntoCollapsedDrawerWithoutNativeActions(){
            using var a=new View("one","a-object",1280,720,4,true);yield return Until(()=>a.Host.PresentedDecision!=null,a.Tick);
            var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(4)},4));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            var state=Snapshot("one","a-object",grouped:false,version:4);sent=Reply(a,state);yield return Until(()=>a.Host.OrganizationFor(1)!=null,a.Tick);a.Tick();yield return null;
            var card=Card(a,a.Reference);var parent=card.parent;var table=a.Root.Q("arena-table");yield return Drag(a,card,table.LocalToWorld(new Vector2(900,230)));
            read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var request=JObject.Parse(read.Result);Assert.That((string)request["message_type"],Is.EqualTo("organization_command"));Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("place"));Assert.That(request["body"]["operation"]["members"].Values<string>(),Is.EqualTo(new[]{"handle-one"}));
            state["message_id"]="placed";state["body"]["organization_revision"]=1;((JArray)state["body"]["seats"][0]["placements"]).Add(new JObject{["handle"]="handle-one",["x"]=request["body"]["operation"]["x"],["y"]=request["body"]["operation"]["y"]});sent=Apply(a,request,state);yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==1,a.Tick);a.Tick();yield return null;float left=card.resolvedStyle.left;a.Tick();yield return null;Assert.That(card.resolvedStyle.left,Is.EqualTo(left).Within(1));Assert.That(left,Is.GreaterThan(700));Assert.That(card.parent,Is.SameAs(parent));Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
            state["message_id"]="drawer";state["body"]["organization_revision"]=2;((JArray)state["body"]["seats"][0]["groups"]).Add(new JObject{["group_id"]="g",["name"]="Only name",["x"]=200000,["y"]=200000,["presentation_mode"]="drawer",["members"]=new JArray()});sent=Reply(a,state);yield return Until(()=>a.Root.Q<GameplayDrawer>("organization-drawer-g")!=null,a.Tick);a.Tick();yield return null;
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-g");drawer.SetOpen(false);a.Tick();yield return null;Assert.That(drawer.Tab.text,Is.EqualTo("Only name"));Assert.That(a.Root.Q("organization-members-g").parent.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(a.Root.Q("organization-drawer-edit-g").resolvedStyle.left,Is.GreaterThan(drawer.Tab.resolvedStyle.width));
            yield return Drag(a,card,drawer.Tab.worldBound.center);read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);request=JObject.Parse(read.Result);Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("move"));Assert.That((string)request["body"]["operation"]["group_id"],Is.EqualTo("g"));Assert.That(drawer.IsOpen,Is.False);
            state["message_id"]="member";state["body"]["organization_revision"]=3;state["body"]["seats"][0]["placements"]=new JArray();state["body"]["seats"][0]["root"]=new JArray("attachment-one");state["body"]["seats"][0]["groups"][0]["members"]=new JArray("handle-one");sent=Apply(a,request,state);yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==3,a.Tick);a.Tick();Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.None));Submit(drawer.Tab);a.Tick();Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(Card(a,a.Reference),Is.SameAs(card));Assert.That(a.Peer.PendingCommandBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator CardOnCardCreatesNamedDrawerAtStationaryCardAndMovesBothMembers()=>CreatePair(false);
        [UnityTest] public IEnumerator CardOnCardKeepsBothMembersWhenGameplayAdvancesDuringCreation()=>CreatePair(true);
        private IEnumerator CreatePair(bool advanceGameplay){
            using var a=new View("one","a-object",1280,720,4,true);yield return Until(()=>a.Host.PresentedDecision!=null,a.Tick);var sent=Reply(a,Envelope("capabilities",new JObject{["versions"]=new JArray(4)},4));yield return Until(()=>sent.IsCompleted,a.Tick);var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);
            var state=Snapshot("one","a-object",grouped:false,version:4);sent=Reply(a,state);yield return Until(()=>a.Host.OrganizationFor(1)!=null,a.Tick);a.Tick();yield return null;var first=Card(a,a.Reference);var other=Card(a,a.Reference+"-attachment");var anchor=new Vector2(other.resolvedStyle.left,other.resolvedStyle.top);
            yield return Drag(a,first,other.worldBound.center);Assert.That(a.Root.Q<TextField>("organization-name"),Is.Not.Null);Assert.That(a.Peer.PendingCommandBytes,Is.Zero);a.Root.Q<TextField>("organization-name").value="Named pair";if(advanceGameplay){var input=a.Root.Q<TextField>("organization-name");using(var enter=KeyDownEvent.GetPooled('\n',KeyCode.Return,EventModifiers.None)){enter.target=input;input.SendEvent(enter);}}else Submit(a.Root.Q<Button>("organization-confirm"));read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var create=JObject.Parse(read.Result);string id=(string)create["body"]["operation"]["group_id"];Assert.That((long)create["body"]["operation"]["x"],Is.EqualTo((long)Math.Round(anchor.x/(a.Root.Q("arena-table").resolvedStyle.width-320)*1000000)).Within(2));
            state["message_id"]="created-pair";state["body"]["organization_revision"]=1;((JArray)state["body"]["seats"][0]["groups"]).Add(new JObject{["group_id"]=id,["name"]="Named pair",["x"]=create["body"]["operation"]["x"],["y"]=create["body"]["operation"]["y"],["presentation_mode"]="panel",["members"]=new JArray()});sent=Apply(a,create,state);read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var convert=JObject.Parse(read.Result);Assert.That((string)convert["body"]["operation"]["presentation_mode"],Is.EqualTo("drawer"));
            if(advanceGameplay){
                a.Source["body"]["snapshot"]["revision"]=2;a.Source["message_id"]="pair-priority-progress";sent=Reply(a,a.Source);yield return Until(()=>a.Host.HasPresentedRevision(2),a.Tick);a.Tick();
                state["body"]["gameplay_revision"]=2;state["body"]["basis_revision"]=2;
            }
            state["message_id"]="pair-drawer";state["body"]["organization_revision"]=2;state["body"]["seats"][0]["groups"][0]["presentation_mode"]="drawer";sent=Apply(a,convert,state);read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,a.Tick);var membership=JObject.Parse(read.Result);Assert.That((string)membership["body"]["operation"]["kind"],Is.EqualTo("move"));Assert.That(membership["body"]["operation"]["members"].Values<string>(),Is.EquivalentTo(new[]{"handle-one","attachment-one"}));
            long gameplay=advanceGameplay?2:1;Assert.That((long)membership["body"]["basis_revision"],Is.EqualTo(gameplay));
            state["message_id"]="pair-members";state["body"]["organization_revision"]=3;state["body"]["seats"][0]["root"]=new JArray();state["body"]["seats"][0]["groups"][0]["members"]=membership["body"]["operation"]["members"].DeepClone();
            sent=Apply(a,membership,state);yield return Until(()=>a.Host.OrganizationFor(gameplay)?.Revision==3,a.Tick);a.Tick();yield return null;
            var drawer=a.Root.Q<GameplayDrawer>("organization-drawer-"+id);Assert.That(drawer,Is.Not.Null);Assert.That(drawer.IsOpen,Is.True);
            Assert.That(a.Host.OrganizationFor(gameplay).Groups.Single().Objects,Is.EquivalentTo(new[]{a.Reference,a.Reference+"-attachment"}));
            var firstParent=first.parent;var otherParent=other.parent;
            drawer.SetOpen(false);a.Tick();Assert.That(first.style.display.value,Is.EqualTo(DisplayStyle.None));Assert.That(other.style.display.value,Is.EqualTo(DisplayStyle.None));
            drawer.SetOpen(true);a.Tick();Assert.That(first.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(other.style.display.value,Is.EqualTo(DisplayStyle.Flex));
            Assert.That(first.parent,Is.SameAs(firstParent));Assert.That(other.parent,Is.SameAs(otherParent));Assert.That(a.Peer.PendingCommandBytes,Is.Zero,"Creating a pair must not dispatch native rules actions");
        }
    }
}

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
        private static JObject Envelope(string kind,JObject body)=>new JObject{["wire_version"]=1,["organization_version"]=2,["message_type"]="organization_"+kind,["message_id"]=Guid.NewGuid().ToString("N"),["body"]=body};
        private static JObject BaseSnapshot(string viewer,string reference,long revision=0,string name="Engine",bool grouped=true)=>Envelope("snapshot",new JObject{["match_epoch"]="match",["viewer_id"]=viewer,["gameplay_revision"]=1,["basis_revision"]=1,["organization_revision"]=revision,["seats"]=new JArray(new JObject{["seat_id"]="one",["root"]=grouped?new JArray():new JArray("handle-"+viewer),["groups"]=grouped?new JArray(new JObject{["group_id"]="g",["name"]=name,["x"]=100000,["y"]=100000,["members"]=new JArray("handle-"+viewer)}):new JArray()},new JObject{["seat_id"]="two",["root"]=new JArray(),["groups"]=new JArray()}),["mappings"]=new JArray(new JObject{["handle"]="handle-"+viewer,["object_reference"]=reference,["seat_id"]="one"})});
        private static JObject Snapshot(string viewer,string reference,long revision=0,string name="Engine",bool grouped=true)
        {
            var result=BaseSnapshot(viewer,reference,revision,name,grouped);var body=result["body"];
            ((JArray)body["mappings"]).Add(new JObject{["handle"]="attachment-"+viewer,["object_reference"]=reference+"-attachment",["seat_id"]="one"});
            ((JArray)(grouped?body["seats"][0]["groups"][0]["members"]:body["seats"][0]["root"])).Add("attachment-"+viewer);return result;
        }
        private sealed class View : IDisposable
        {
            internal readonly RenderTexture Target;internal readonly GameObject Node;internal readonly PanelSettings Settings;internal readonly ArenaGameplayPresentation Arena;internal readonly ViewerSessionHost Host;internal readonly ViewerSessionHostTests.Peer Peer;internal readonly VisualElement Root;internal readonly JObject Source;internal readonly string Viewer,Reference;
            private readonly TaskCompletionSource<bool> owner=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            internal View(string viewer,string reference,int width,int height)
            {
                Viewer=viewer;Reference=reference;Source=Game(viewer,reference);Peer=new ViewerSessionHostTests.Peer(Source.ToString(),viewer:viewer);Node=new GameObject("Shared organization "+viewer);Settings=ScriptableObject.CreateInstance<PanelSettings>();Settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=Node.AddComponent<UIDocument>();doc.panelSettings=Settings;Root=doc.rootVisualElement;Root.style.width=width;Root.style.height=height;Target=new RenderTexture(width,height,24);Target.Create();Settings.targetTexture=Target;Arena=new ArenaGameplayPresentation(Root,capabilities:new GameplayPresentationCapabilities(sharedOrganization:true));Host=new ViewerSessionHost(Arena.Surface,Peer.Bootstrap(organizationVersion:2),owner.Task,true);Arena.Bind(Host);
            }
            internal void Tick(){Host.Tick();if(Host.HasPresentedRevision(1)){Arena.PresentOrganization(Host.OrganizationFor(1));Arena.Present(ViewerDecisionProjection.Project((JObject)Source["body"]["snapshot"]));}}
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
            Assert.That(b.Root.Q("organization-group-g").Query<Button>().ToList(),Is.Empty,"Opponent has no edit menu");
            using(var down=PointerDownEvent.GetPooled(new Event{type=EventType.MouseDown,button=0,modifiers=EventModifiers.Shift,mousePosition=card.worldBound.center})){down.target=card;card.SendEvent(down);}using(var up=PointerUpEvent.GetPooled(new Event{type=EventType.MouseUp,button=0,modifiers=EventModifiers.Shift,mousePosition=card.worldBound.center})){up.target=card;card.SendEvent(up);}Assert.That(card.ClassListContains("organization-selected"),Is.True);Assert.That(a.Peer.PendingCommandBytes,Is.Zero,"Selection cannot submit a native action");
            // Editing uses the independent organization channel and broadcasts authoritative geometry.
            Submit(a.Root.Q("organization-group-g").Q<Button>());
            Submit(a.Root.Q<Button>("organization-rename"));a.Root.Q<TextField>("organization-name").value="Renamed";
            Submit(a.Root.Q<Button>("organization-confirm"));var read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,tick);var request=JObject.Parse(read.Result);Assert.That((string)request["message_type"],Is.EqualTo("organization_command"));Assert.That((string)request["body"]["operation"]["kind"],Is.EqualTo("rename"));
            var receipt=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=request["body"]["command_id"],["outcome"]="applied",["organization_revision"]=1,["basis_revision"]=1,["reason_code"]=JValue.CreateNull()});sent=Task.Run(()=>{a.Peer.ReplyForFixture(receipt);a.Peer.ReplyForFixture(Snapshot("one","a-object",1,"Renamed"));b.Peer.ReplyForFixture(Snapshot("two","b-object",1,"Renamed"));});yield return Until(()=>sent.IsCompleted && !a.Host.OrganizationPending,tick);sent.GetAwaiter().GetResult();yield return Until(()=>a.Host.OrganizationFor(1)?.Revision==1 && b.Host.OrganizationFor(1)?.Revision==1,tick);tick();
            Assert.That(a.Root.Q("organization-group-g").Query<Label>().ToList().Any(label=>label.text.StartsWith("Renamed")),Is.True);Assert.That(b.Root.Q("organization-group-g").Query<Label>().ToList().Any(label=>label.text.StartsWith("Renamed")),Is.True);Assert.That(card.parent,Is.SameAs(parent));Assert.That(a.Arena.Surface.CardsRoot.childCount,Is.EqualTo(count));
            foreach(var size in new[]{new Vector2(1280,720),new Vector2(1366,768),new Vector2(1920,1080),new Vector2(2560,1440)}){a.Root.style.width=size.x;a.Root.style.height=size.y;yield return null;tick();Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(float.IsNaN(card.style.left.value.value),Is.False);Assert.That(a.Root.Q("organization-group-g"),Is.Not.Null);}
            // A rejected UI edit leaves authoritative geometry and membership intact.
            Submit(a.Root.Q<Button>("organization-remove-selected"));read=Task.Run(()=>a.Peer.ReadCommandForFixture());yield return Until(()=>read.IsCompleted,tick);request=JObject.Parse(read.Result);
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
            // Missing/coherence-revoked organization restores legacy placement immediately.
            a.Arena.PresentOrganization(null);Assert.That(a.Root.Q("organization-group-g"),Is.Null);Assert.That(card.style.display.value,Is.EqualTo(DisplayStyle.Flex));Assert.That(BattlefieldCardAnchorResolver.TryCenter(a.Root,card,out _),Is.True);tick();
            var fallback=a.Root.Q<Toggle>("organization-default");Assert.That(fallback,Is.Not.Null);fallback.value=true;yield return null;tick();Assert.That(a.Root.Q("organization-group-g"),Is.Null);Assert.That(card.parent,Is.SameAs(parent));Assert.That(card.ClassListContains("organization-selected"),Is.False);a.Host.Cancel();a.Host.Tick();Assert.That(a.Root.Q("organization-group-g"),Is.Null);Assert.That(a.Root.Q("organization-controls").childCount,Is.Zero);
        }
    }
}

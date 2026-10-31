using System;
using System.Collections;
using System.IO;
using System.Net;
using System.Net.Sockets;
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
    public sealed class ViewerSessionReceiverTests
    {
        private GameObject host;private PanelSettings settings;private ViewerCardSurface surface;
        private JObject corpus,history;
        private sealed class Pair:IDisposable
        {
            public readonly TcpClient Peer;public readonly LoopbackFrameReader Transport;public readonly ClientSessionChannel Channel;
            public Pair(){var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();try{Peer=new TcpClient();Peer.ReceiveTimeout=2000;Peer.Connect(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port);Transport=new LoopbackFrameReader(listener.AcceptSocket());Channel=new ClientSessionChannel(Transport,"fixture-session","one",true);}finally{listener.Stop();}}
            public void Send(JObject value){TextFrame.Write(Peer.GetStream(),value.ToString());Peer.GetStream().Flush();}
            public void Dispose(){Channel.Dispose();Peer.Dispose();}
        }
        private JObject Frame(long revision=7,string id="snapshot")
        {
            var value=(JObject)corpus["positive"][0]["envelope"].DeepClone();value["message_id"]=id;var snapshot=value["body"]["snapshot"];
            snapshot["session_id"]="fixture-session";snapshot["revision"]=revision;snapshot["decision"]=history["body"]["snapshot"]["decision"].DeepClone();snapshot["actions"]=history["body"]["snapshot"]["actions"].DeepClone();
            var card=snapshot["objects"][0];card["characteristics"]["name"]="Private before loss";card["face_down"]=false;card["card_identity"]=new JObject{["oracle_id"]="oracle",["printing_id"]="exact-printing",["deck_entry_id"]=JValue.CreateNull()};return value;
        }
        private static IEnumerator Until(Func<bool> done){double end=Time.realtimeSinceStartupAsDouble+10;while(!done() && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(done(),Is.True,"Session receiver timed out");}
        private static IEnumerator Read(ViewerSessionReceiver receiver,Action<bool> result=null){var task=Task.Run(()=>receiver.ReceiveOnce(2000));yield return Until(()=>task.IsCompleted);result?.Invoke(task.GetAwaiter().GetResult());}
        [UnitySetUp] public IEnumerator Setup()
        {
            string root=Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures");corpus=JObject.Parse(File.ReadAllText(Path.Combine(root,"wire-receive-v1.json")));history=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(root,"receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"];
            host=new GameObject("Session receiver tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=host.AddComponent<UIDocument>();doc.panelSettings=settings;surface=new ViewerCardSurface(doc.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator OrderedPacketsSurviveRenderCoalescingAndResultSummarySurvivesGracefulRevocation()
        {
            using var pair=new Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);yield return null;yield return null;
            pair.Send(Frame());yield return Read(receiver,ok=>Assert.That(ok,Is.True));
            var ev=(JObject)corpus["positive"][6]["envelope"].DeepClone();ev["body"]["session_id"]="fixture-session";ev["body"]["event"]["revision"]=8;pair.Send(ev);yield return Read(receiver);
            Assert.That(ticket.Mailbox.MinimumRevision,Is.EqualTo(8));
            var result=(JObject)corpus["positive"][5]["envelope"].DeepClone();result["message_id"]="result";result["body"]["snapshot"]["session_id"]="fixture-session";result["body"]["snapshot"]["revision"]=9;pair.Send(result);yield return Read(receiver);
            Assert.That(receiver.Count,Is.EqualTo(3));surface.Pump(ticket);
            foreach(string type in new[]{"snapshot","event","result"}){Assert.That(receiver.TryTake(out var update),Is.True);using(update){Assert.That(update.Receive.Type,Is.EqualTo(type));Assert.That(update.Packet.ReadJson(),Is.Not.Empty);}}
            var shutdown=Task.Run(()=>pair.Channel.RequestShutdown("client_close"));yield return Until(()=>shutdown.IsCompleted);shutdown.GetAwaiter().GetResult();var reply=WireMessages.Parse(TextFrame.Read(pair.Peer.GetStream()));pair.Send(reply);yield return Read(receiver,ok=>Assert.That(ok,Is.False));yield return Until(()=>receiver.Completion.IsCompleted);
            Assert.That(receiver.Completion.Result.Graceful,Is.True);Assert.That(receiver.Completion.Result.Outcome.Context.Revision,Is.EqualTo(9));Assert.That(receiver.Completion.Result.Outcome.Status,Is.EqualTo((string)result["body"]["snapshot"]["status"]));Assert.That(receiver.Count,Is.Zero);surface.Pump(ticket);Assert.That(surface.CardsRoot.childCount,Is.Zero);
        }
        [UnityTest] public IEnumerator OwnerCancellationUnblocksReceiveClearsPrivateAssetsAndPreservesUncertainty()
        {
            using var pair=new Pair();var ticket=surface.BeginViewer("fixture-session","one",new ViewerArtworkScope());using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);yield return null;yield return null;
            surface.CreateArtworkJobs(ticket,(request,cancel)=>Task.FromResult(PreparedCardArtwork.Prepare(request,new CatalogArtworkFace("oracle","exact-printing","front","normal",1,true,"Creature"),2,2,new byte[16])));
            pair.Send(Frame());yield return Read(receiver);surface.Pump(ticket);yield return Until(()=>ticket.Mailbox.ArtworkCount==1);surface.Pump(ticket);Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.True);var texture=surface.InspectionView.Q<Image>("artwork").image;Assert.That(texture,Is.Not.Null);
            var command=new JObject{["wire_version"]=1,["message_type"]="command",["message_id"]="c1",["body"]=new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=7,["decision_id"]="fixture-decision",["operation"]="perform",["action_id"]="fixture-action"}};
            var send=Task.Run(()=>pair.Channel.Submit(command.ToString()));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();TextFrame.Read(pair.Peer.GetStream());
            var read=Task.Run(()=>receiver.ReceiveOnce(5000));yield return Until(()=>pair.Transport.ReadInProgress);receiver.Cancel();yield return Until(()=>read.IsCompleted && receiver.Completion.IsCompleted);Assert.That(read.Result,Is.False);
            Assert.That(receiver.Completion.Result.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(pair.Channel.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(pair.Channel.CanSubmit,Is.False);Assert.That(receiver.QueuedBytes,Is.Zero);
            surface.Pump(ticket);Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.That(surface.InspectionView.Q<Image>("artwork").image,Is.Null);yield return null;yield return null;Assert.That(texture==null,Is.True);
        }
        [UnityTest] public IEnumerator CountAndByteOverflowRevokeInsteadOfDroppingOrderedUpdates()
        {
            for(int mode=0;mode<2;mode++)using(var pair=new Pair()) {
                var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true,mode==0?1:128,mode==0?8*1024*1024:1);yield return null;yield return null;
                pair.Send(Frame());yield return Read(receiver);
                if(mode==0){pair.Send(Frame(8,"second"));yield return Read(receiver,ok=>Assert.That(ok,Is.False));}
                yield return Until(()=>receiver.Completion.IsCompleted);Assert.That(receiver.Completion.Result.Code,Is.EqualTo("VIEWER_RECEIVE_OVERFLOW"));Assert.That(receiver.Count,Is.Zero);Assert.That(ticket.Mailbox.IsStopped,Is.True);surface.Pump(ticket);Assert.That(surface.CardsRoot.childCount,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator RetiredReceiverCannotClearOrPopulateTheNextViewer()
        {
            using var pair=new Pair();var first=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,first,true);yield return null;yield return null;pair.Send(Frame());yield return Read(receiver);surface.Pump(first);
            var next=surface.BeginViewer("fixture-session","two");receiver.Cancel();next.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame("two",session:"fixture-session",name:"Next viewer"));yield return null;yield return null;
            Assert.That(surface.Pump(first),Is.Zero);surface.Pump(next);Assert.That(surface.CardsRoot.Q<Label>("name").text,Is.EqualTo("Next viewer"));Assert.That(next.Mailbox.IsStopped,Is.False);Assert.That(receiver.ReceiveOnce(),Is.False);
        }
        [UnityTest] public IEnumerator ContextAndPrivacyFailureCannotLeakAQueuedFrame()
        {
            using var pair=new Pair();var other=surface.BeginViewer("fixture-session","two");Assert.Throws<ArgumentException>(()=>new ViewerSessionReceiver(pair.Channel,other,true));Assert.That(pair.Channel.State,Is.EqualTo(ClientChannelState.Active));
            var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);Assert.Throws<ArgumentOutOfRangeException>(()=>receiver.ReceiveOnce(0));
            var frame=Frame();frame["body"]["snapshot"]["objects"][0]["hidden"]=true;pair.Send(frame);yield return Read(receiver,ok=>Assert.That(ok,Is.False));yield return Until(()=>receiver.Completion.IsCompleted);Assert.That(receiver.Completion.Result.Code,Is.EqualTo("VIEWER_RECEIVE_FAILED").Or.EqualTo("VIEWER_CHANNEL_STOPPED"));Assert.That(ticket.Mailbox.HasPendingFrame,Is.False);surface.Pump(ticket);Assert.That(surface.CardsRoot.childCount,Is.Zero);
        }
        [UnityTest] public IEnumerator SubmittedAndConfirmedReceiptsStayOrderedAndConfirmedIsNotTurnedUncertain()
        {
            using var pair=new Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);pair.Send(Frame());yield return Read(receiver);Assert.That(receiver.TryTake(out var snapshot),Is.True);snapshot.Dispose();
            var command=new JObject{["wire_version"]=1,["message_type"]="command",["message_id"]="c1",["body"]=new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=7,["decision_id"]="fixture-decision",["operation"]="perform",["action_id"]="fixture-action"}};
            var send=Task.Run(()=>pair.Channel.Submit(command.ToString()));yield return Until(()=>send.IsCompleted);send.GetAwaiter().GetResult();TextFrame.Read(pair.Peer.GetStream());
            foreach(string outcome in new[]{"submitted","confirmed"}) {
                pair.Send(new JObject{["wire_version"]=1,["message_type"]="ack",["message_id"]="ack-"+outcome,["body"]=new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["command_id"]="c1",["request_revision"]=7,["outcome"]=outcome,["code"]=JValue.CreateNull()}});yield return Read(receiver);
            }
            Assert.That(receiver.Count,Is.EqualTo(2));Assert.That(receiver.QueuedBytes,Is.Zero);
            foreach(var state in new[]{CommandState.Submitted,CommandState.Confirmed}){Assert.That(receiver.TryTake(out var update),Is.True);using(update){Assert.That(update.Receive.Receipt.State,Is.EqualTo(state));Assert.That(update.Packet,Is.Null);}}
            receiver.Cancel();yield return Until(()=>receiver.Completion.IsCompleted);Assert.That(receiver.Completion.Result.Pending,Is.Null);Assert.That(receiver.Completion.Result.LastReceipt.State,Is.EqualTo(CommandState.Confirmed));
        }
        [UnityTest] public IEnumerator ConcurrentReceiveAttemptsRevokeAndReleaseTheFirstReader()
        {
            using var pair=new Pair();var ticket=surface.BeginViewer("fixture-session","one");using var receiver=new ViewerSessionReceiver(pair.Channel,ticket,true);
            var first=Task.Run(()=>receiver.ReceiveOnce(5000));yield return Until(()=>pair.Transport.ReadInProgress);
            var second=Task.Run(()=>receiver.ReceiveOnce(1000));yield return Until(()=>first.IsCompleted && second.IsCompleted && receiver.Completion.IsCompleted);
            Assert.That(first.Result,Is.False);Assert.That(second.Result,Is.False);Assert.That(receiver.Completion.Result.Code,Is.EqualTo("VIEWER_RECEIVE_CONCURRENT"));Assert.That(ticket.Mailbox.IsStopped,Is.True);
        }
    }
}

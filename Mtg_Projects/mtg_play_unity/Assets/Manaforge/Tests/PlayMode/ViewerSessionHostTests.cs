using System;
using System.Collections;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
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
    public sealed class ViewerSessionHostTests
    {
        private GameObject node;private PanelSettings settings;private ViewerCardSurface surface;private JObject source;
        private static TaskCompletionSource<bool> Signal()=>new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        internal sealed class Peer:IDisposable
        {
            private readonly TcpListener listener=new TcpListener(IPAddress.Loopback,0);private readonly TaskCompletionSource<bool> release=Signal();private readonly Task work;
            private TcpClient client;private int disposed;public readonly TaskCompletionSource<bool> Accepted=Signal();public int Port {get;}
            public Peer(string frame,bool silent=false,bool wrongPin=false)
            {
                listener.Start();Port=((IPEndPoint)listener.LocalEndpoint).Port;
                work=Task.Run(async()=>{
                    try {
                        client=await listener.AcceptTcpClientAsync().ConfigureAwait(false);client.ReceiveTimeout=3000;var stream=client.GetStream();Accepted.TrySetResult(true);
                        if(!silent) {
                            string server=new string('1',64);TextFrame.Write(stream,ViewerChallengeHandshake.Challenge(server));stream.Flush();string nonce=ViewerChallengeHandshake.ReadResponse(TextFrame.Read(stream),server);
                            var expected=Hello("client",server,nonce,false);byte[] key=new byte[32];for(int i=0;i<32;i++)key[i]=(byte)i;
                            try {
                                using(var verifier=new ViewerAuthentication.Verifier(expected.ToString(),key))Assert.That(verifier.Verify(TextFrame.Read(stream)),Is.True);
                                var gateway=Hello("gateway",server,nonce,wrongPin);gateway["body"]["proof"]=ViewerAuthentication.ComputeProof(gateway.ToString(),key);TextFrame.Write(stream,gateway.ToString());TextFrame.Write(stream,frame);stream.Flush();
                            }finally{Array.Clear(key,0,key.Length);}
                        }
                        await release.Task.ConfigureAwait(false);
                    }catch(Exception error){if(Volatile.Read(ref disposed)==0 && !(wrongPin && (error is IOException || error is SocketException)))throw;}
                });
            }
            private static JObject Hello(string role,string server,string nonce,bool wrong)=>new JObject{["wire_version"]=1,["message_type"]="hello",["message_id"]="auth-"+role,["body"]=new JObject{["protocol_version"]=1,["engine_version"]="fixture-engine",["artifact_manifest_sha256"]=new string(wrong?'b':'a',64),["session_id"]="fixture-session",["viewer_id"]="one",["server_nonce"]=server,["client_nonce"]=nonce,["role"]=role,["proof"]=new string('0',64)}};
            public ViewerBootstrap Bootstrap(string artworkDirectory=null,string artworkPin=null)
            {
                byte[] key=new byte[32];for(int i=0;i<32;i++)key[i]=(byte)i;string hex=BitConverter.ToString(key).Replace("-","").ToLowerInvariant();Array.Clear(key,0,key.Length);
                var value=new JObject{["viewer_bootstrap_version"]=1,["protocol_version"]=1,["endpoint"]=new JObject{["host"]="127.0.0.1",["port"]=Port},["session_id"]="fixture-session",["viewer_id"]="one",["engine_version"]="fixture-engine",["artifact_manifest_sha256"]=new string('a',64),["viewer_key_hex"]=hex,["artwork"]=artworkDirectory==null?JValue.CreateNull():(JToken)new JObject{["directory"]=artworkDirectory,["manifest_sha256"]=artworkPin}};return ViewerBootstrap.Parse(Encoding.UTF8.GetBytes(value.ToString()));
            }
            public void Dispose(){if(Interlocked.Exchange(ref disposed,1)!=0)return;release.TrySetResult(true);client?.Dispose();listener.Stop();Assert.That(SpinWait.SpinUntil(()=>work.IsCompleted,3000),Is.True);work.GetAwaiter().GetResult();}
        }
        private string Frame(string name)
        {var value=(JObject)source.DeepClone();value["body"]["snapshot"]["session_id"]="fixture-session";value["body"]["snapshot"]["objects"][0]["characteristics"]["name"]=name;return value.ToString();}
        private static IEnumerator Until(Func<bool> done){double end=Time.realtimeSinceStartupAsDouble+10;while(!done() && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(done(),Is.True,"Session host timed out");}
        private IEnumerator Mount(ViewerSessionHost host,string name)=>Until(()=>{host.Tick();return surface.CardsRoot.Q<Label>("name")?.text==name;});
        [UnitySetUp] public IEnumerator Setup()
        {
            source=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"];
            node=new GameObject("Authenticated host test");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;surface=new ViewerCardSurface(doc.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator AuthenticatedConnectionMountsThenOwnerLossRevokesBeforeTheNextUiUpdate()
        {
            using var peer=new Peer(Frame("Mounted fixture"));var owner=Signal();using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);
            yield return Mount(host,"Mounted fixture");Assert.That(host.Authenticated,Is.True);
            Assert.That(host.Inspect("fixture-0002"),Is.True);Assert.That(surface.InspectionView.Q<Label>("name").text,Is.EqualTo("Mounted fixture"));
            var take=Task.Run(()=>{if(!host.TryTake(out var update))return false;using(update)return update.Receive.Type=="snapshot";});yield return Until(()=>take.IsCompleted);Assert.That(take.Result,Is.True);
            owner.TrySetResult(true);host.Tick();Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.That(host.Authenticated,Is.False);Assert.That(surface.InspectionView.Q<Label>("name").text,Is.Empty);Assert.That(host.Inspect("fixture-0002"),Is.False);
            yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_OWNER_ENDED"));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);
        }
        [UnityTest] public IEnumerator OwnerLossDuringAuthenticationClosesTheAttemptAndDisposesBootstrap()
        {
            using var peer=new Peer(Frame("Never mounted"),silent:true);var owner=Signal();var bootstrap=peer.Bootstrap();using var host=new ViewerSessionHost(surface,bootstrap,owner.Task,true);
            yield return Until(()=>peer.Accepted.Task.IsCompleted);owner.TrySetResult(true);host.Tick();yield return Until(()=>host.Completion.IsCompleted);
            Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_OWNER_ENDED"));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.Throws<IOException>(()=>bootstrap.TakeViewerKey());
        }
        [UnityTest] public IEnumerator WrongPinProofCannotMountItsFollowingSnapshot()
        {
            using var peer=new Peer(Frame("Untrusted snapshot"),wrongPin:true);var owner=Signal();using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);
            yield return Until(()=>host.Completion.IsCompleted);host.Tick();Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_CONNECT_FAILED"));Assert.That(host.Authenticated,Is.False);Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.That(host.TryTake(out _),Is.False);
        }
        [UnityTest] public IEnumerator LateOwnerLossAndDisposalOfOldHostCannotClearReplacementEpoch()
        {
            using var firstPeer=new Peer(Frame("First epoch"));var firstOwner=Signal();using var first=new ViewerSessionHost(surface,firstPeer.Bootstrap(),firstOwner.Task,true);yield return Mount(first,"First epoch");
            using var nextPeer=new Peer(Frame("Replacement epoch"));var nextOwner=Signal();using var next=new ViewerSessionHost(surface,nextPeer.Bootstrap(),nextOwner.Task,true);yield return Mount(next,"Replacement epoch");
            firstOwner.TrySetResult(true);first.Tick();first.Dispose();yield return Until(()=>first.Completion.IsCompleted);next.Tick();Assert.That(surface.CardsRoot.Q<Label>("name").text,Is.EqualTo("Replacement epoch"));Assert.That(next.Authenticated,Is.True);
            next.Cancel();next.Tick();yield return Until(()=>next.Completion.IsCompleted);Assert.That(next.Completion.Result.CleanupConfirmed,Is.True);
        }
        [UnityTest] public IEnumerator AlreadyEndedOwnerNeverConnectsAndBootstrapIsStillReleased()
        {
            using var peer=new Peer(Frame("Never connected"),silent:true);var bootstrap=peer.Bootstrap();using var host=new ViewerSessionHost(surface,bootstrap,Task.CompletedTask,true);
            yield return Until(()=>host.Completion.IsCompleted);host.Tick();Assert.That(peer.Accepted.Task.IsCompleted,Is.False);Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_OWNER_ENDED"));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);Assert.Throws<IOException>(()=>bootstrap.TakeViewerKey());
        }
        [UnityTest] public IEnumerator RefusedConnectionDisposesAttemptWithoutMountingAnyView()
        {
            using var peer=new Peer(Frame("Never connected"),silent:true);var bootstrap=peer.Bootstrap();peer.Dispose();var owner=Signal();using var host=new ViewerSessionHost(surface,bootstrap,owner.Task,true,connectionMilliseconds:500);
            yield return Until(()=>host.Completion.IsCompleted);host.Tick();Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_CONNECT_FAILED"));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);Assert.That(surface.CardsRoot.childCount,Is.Zero);
        }
        [UnityTest] public IEnumerator HostExposesOnlyItsCurrentOfferAndOwnerLossRevokesItBeforeTick()
        {
            var frame=JObject.Parse(Frame("Decision fixture"));var priority=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"]["body"]["snapshot"];
            frame["body"]["snapshot"]["decision"]=priority["decision"].DeepClone();frame["body"]["snapshot"]["actions"]=priority["actions"].DeepClone();
            using var peer=new Peer(frame.ToString());var owner=Signal();using var host=new ViewerSessionHost(surface,peer.Bootstrap(),owner.Task,true);yield return Until(()=>host.CurrentDecision!=null);var offer=host.CurrentDecision;Assert.That(offer.CanSubmit,Is.True);
            owner.TrySetResult(true);Assert.That(host.CurrentDecision,Is.Null);Assert.That(offer.Frame,Is.Null);Assert.That(offer.CanSubmit,Is.False);host.Tick();yield return Until(()=>host.Completion.IsCompleted);
        }
    }
}

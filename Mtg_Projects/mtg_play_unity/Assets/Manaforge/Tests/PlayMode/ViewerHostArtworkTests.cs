using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerHostArtworkTests
    {
        private GameObject node;private PanelSettings settings;private ViewerCardSurface surface;private JObject source,manifest;
        private string directory,pin,file;private readonly List<ViewerSessionHost> hosts=new List<ViewerSessionHost>();
        private static TaskCompletionSource<bool> Signal()=>new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        private static string Hash(byte[] bytes){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
        private void Publish(){byte[] bytes=Encoding.UTF8.GetBytes(manifest.ToString());File.WriteAllBytes(Path.Combine(directory,"manifest.json"),bytes);pin=Hash(bytes);}
        private string Frame(bool hidden=false,bool faceDown=false)
        {
            var value=(JObject)source.DeepClone();value["body"]["snapshot"]["session_id"]="fixture-session";var card=value["body"]["snapshot"]["objects"][0];card["hidden"]=hidden;
            card["face_down"]=hidden?JValue.CreateNull():new JValue(faceDown);card["card_identity"]=hidden?JValue.CreateNull():(JToken)new JObject{["oracle_id"]="oracle",["printing_id"]="exact-printing",["deck_entry_id"]=JValue.CreateNull()};
            if(hidden)card["characteristics"]=JValue.CreateNull();return value.ToString();
        }
        private ViewerSessionHost Start(ViewerSessionHostTests.Peer peer,Task owner,string digest=null,string path=null)
        {var host=new ViewerSessionHost(surface,peer.Bootstrap(path??directory,digest??pin),owner,true);hosts.Add(host);return host;}
        private static IEnumerator Until(Func<bool> done){double end=Time.realtimeSinceStartupAsDouble+10;while(!done() && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(done(),Is.True,"Host artwork timed out");}
        private IEnumerator Loaded(ViewerSessionHost host)=>Until(()=>{host.Tick();return host.Inspect("fixture-0002") && surface.InspectionView.Q<Image>("artwork").image!=null;});
        [UnitySetUp] public IEnumerator Setup()
        {
            source=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"];
            directory=Path.Combine(Path.GetTempPath(),"ManaforgeHostArtworkTest-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(directory);byte[] raw={255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255};string digest=Hash(raw);file=Path.Combine(directory,digest+".rgba");File.WriteAllBytes(file,raw);
            manifest=new JObject{["artwork_bundle_version"]=1,["source"]="manaforge_core_cache",["session_id"]="fixture-session",["viewer_id"]="one",["entries"]=new JArray(new JObject{["oracle_id"]="oracle",["printing_id"]="exact-printing",["face_key"]="front",["layout"]="normal",["face_count"]=1,["standard_compatible"]=true,["printed_type_line"]="Creature",["file"]=digest+".rgba",["width"]=2,["height"]=2,["byte_length"]=16,["sha256"]=digest,["pixel_format"]="RGBA8",["row_origin"]="bottom_left"}),["unavailable"]=new JArray()};Publish();
            node=new GameObject("Host artwork test");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;surface=new ViewerCardSurface(doc.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup()
        {
            foreach(var host in hosts)host.Dispose();yield return Until(()=>hosts.TrueForAll(host=>host.Completion.IsCompleted));hosts.Clear();surface.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);
            string full=Path.GetFullPath(directory);Assert.That(Path.GetDirectoryName(full),Is.EqualTo(Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar)));Assert.That(Path.GetFileName(full),Does.StartWith("ManaforgeHostArtworkTest-"));Directory.Delete(full,true);yield return null;
        }
        [UnityTest] public IEnumerator PinnedSidecarReachesPrivateTextureAndOwnerLossRetiresJobsBeforeCleanup()
        {
            using var peer=new ViewerSessionHostTests.Peer(Frame());var owner=Signal();var host=Start(peer,owner.Task);yield return Loaded(host);var texture=surface.InspectionView.Q<Image>("artwork").image;Assert.That(texture,Is.Not.Null);
            owner.TrySetResult(true);host.Tick();Assert.That(surface.CardsRoot.childCount,Is.Zero);yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);
            using(var exclusive=new FileStream(file,FileMode.Open,FileAccess.ReadWrite,FileShare.None))Assert.That(exclusive.Length,Is.EqualTo(16));
            yield return null;yield return null;Assert.That(texture==null,Is.True);
        }
        [UnityTest] public IEnumerator WrongPinAndWrongViewerMetadataFailBeforeMountingFrames()
        {
            for(int mode=0;mode<2;mode++)using(var peer=new ViewerSessionHostTests.Peer(Frame())) {
                if(mode==1){manifest["viewer_id"]="two";Publish();}var owner=Signal();var host=Start(peer,owner.Task,mode==0?new string('0',64):pin);
                yield return Until(()=>host.Completion.IsCompleted);host.Tick();Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_ARTWORK_FAILED"));Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);Assert.That(surface.CardsRoot.childCount,Is.Zero);
            }
        }
        [UnityTest] public IEnumerator CorruptPixelsRemainUnavailableWithoutInventingAnotherPrinting()
        {
            File.WriteAllBytes(file,new byte[16]);using var peer=new ViewerSessionHostTests.Peer(Frame());var owner=Signal();var host=Start(peer,owner.Task);
            yield return Until(()=>{host.Tick();return surface.CardsRoot.childCount==1;});for(int i=0;i<30;i++){host.Tick();yield return null;}
            Assert.That(host.Authenticated,Is.True);Assert.That(host.Completion.IsCompleted,Is.False);Assert.That(host.Inspect("fixture-0002"),Is.True);Assert.That(surface.InspectionView.Q<Image>("artwork").image,Is.Null);
            host.Cancel();host.Tick();yield return Until(()=>host.Completion.IsCompleted);Assert.That(host.Completion.Result.CleanupConfirmed,Is.True);
        }
        [UnityTest] public IEnumerator HiddenAndFaceDownObjectsNeverReceiveSidecarArtwork()
        {
            for(int mode=0;mode<2;mode++)using(var peer=new ViewerSessionHostTests.Peer(Frame(hidden:mode==0,faceDown:mode==1))) {
                var owner=Signal();var host=Start(peer,owner.Task);yield return Until(()=>{host.Tick();return surface.CardsRoot.childCount==1;});for(int i=0;i<5;i++){host.Tick();yield return null;}
                Assert.That(host.Inspect("fixture-0002"),Is.EqualTo(mode!=0));Assert.That(surface.InspectionView.Q<Image>("artwork").image,Is.Null);host.Dispose();yield return Until(()=>host.Completion.IsCompleted);
            }
        }
        [UnityTest] public IEnumerator ReplacementEpochCreatesItsOwnTextureAndRetiresThePreviousCache()
        {
            using var firstPeer=new ViewerSessionHostTests.Peer(Frame());var firstOwner=Signal();var first=Start(firstPeer,firstOwner.Task);yield return Loaded(first);var previous=surface.InspectionView.Q<Image>("artwork").image;
            using var nextPeer=new ViewerSessionHostTests.Peer(Frame());var nextOwner=Signal();var next=Start(nextPeer,nextOwner.Task);yield return Loaded(next);var current=surface.InspectionView.Q<Image>("artwork").image;Assert.That(current,Is.Not.SameAs(previous));
            first.Tick();yield return Until(()=>first.Completion.IsCompleted);yield return null;yield return null;Assert.That(previous==null,Is.True);Assert.That(current==null,Is.False);next.Tick();Assert.That(next.Authenticated,Is.True);
            next.Dispose();yield return Until(()=>next.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator AuthenticationFailurePrecedesAnySidecarOpen()
        {
            using var peer=new ViewerSessionHostTests.Peer(Frame(),wrongPin:true);var owner=Signal();var host=Start(peer,owner.Task,new string('0',64),Path.Combine(directory,"missing"));
            yield return Until(()=>host.Completion.IsCompleted);host.Tick();Assert.That(host.Completion.Result.Code,Is.EqualTo("VIEWER_CONNECT_FAILED"));Assert.That(surface.CardsRoot.childCount,Is.Zero);
        }
    }
}

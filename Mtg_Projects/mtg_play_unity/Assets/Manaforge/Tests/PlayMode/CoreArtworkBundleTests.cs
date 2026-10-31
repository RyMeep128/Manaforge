using System;
using System.Collections;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class CoreArtworkBundleTests
    {
        private string root,pin,file;private JObject manifest;
        private GameObject host;private PanelSettings settings;private ViewerCardSurface surface;
        private static string Digest(byte[] bytes){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
        private void Publish(){var bytes=Encoding.UTF8.GetBytes(manifest.ToString());File.WriteAllBytes(Path.Combine(root,"manifest.json"),bytes);pin=Digest(bytes);}
        private static IEnumerator Until(Task task){double end=Time.realtimeSinceStartupAsDouble+10;while(!task.IsCompleted && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(task.IsCompleted,Is.True,"Asset worker timed out");}
        [UnitySetUp] public IEnumerator Setup()
        {
            root=Path.Combine(Path.GetTempPath(),"ManaforgeCoreArtworkTest-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            var pixels=new byte[]{255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,255};var hash=Digest(pixels);file=hash+".rgba";File.WriteAllBytes(Path.Combine(root,file),pixels);
            manifest=new JObject{["artwork_bundle_version"]=1,["source"]="manaforge_core_cache",["session_id"]="fixture-0001",["viewer_id"]="one",
                ["entries"]=new JArray(new JObject{["oracle_id"]="oracle",["printing_id"]="exact-printing",["face_key"]="front",["layout"]="normal",["face_count"]=1,["standard_compatible"]=true,["printed_type_line"]="Creature",["file"]=file,["width"]=2,["height"]=2,["byte_length"]=16,["sha256"]=hash,["pixel_format"]="RGBA8",["row_origin"]="bottom_left"}),["unavailable"]=new JArray()};Publish();
            host=new GameObject("Core asset provider test");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=host.AddComponent<UIDocument>();document.panelSettings=settings;surface=new ViewerCardSurface(document.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup()
        {
            surface.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);
            var path=Path.GetFullPath(root);Assert.That(Path.GetDirectoryName(path),Is.EqualTo(Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar)));
            Assert.That(Path.GetFileName(path),Does.StartWith("ManaforgeCoreArtworkTest-"));Directory.Delete(path,true);yield return null;
        }
        [UnityTest] public IEnumerator PinnedPixelsReachTheOwnedRendererThroughJobs()
        {
            // Optional local cross-language evidence; synthetic checks always run without it.
            var external=Environment.GetEnvironmentVariable("MANAFORGE_CORE_ARTWORK_PROOF");
            var directory=string.IsNullOrEmpty(external)?root:external;
            var digest=string.IsNullOrEmpty(external)?pin:Environment.GetEnvironmentVariable("MANAFORGE_CORE_ARTWORK_PROOF_PIN");
            var open=CoreArtworkBundle.OpenAsync(directory,digest,"fixture-0001","one");yield return Until(open);
            using(var bundle=open.GetAwaiter().GetResult()) {
                Assert.That(bundle.EntryCount,Is.EqualTo(1));var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
                Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true)),Is.True);
                var jobs=surface.CreateArtworkJobs(ticket,bundle.LoadAsync);Assert.That(jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-0002")),Is.True);
                double end=Time.realtimeSinceStartupAsDouble+10;while(ticket.Mailbox.ArtworkCount==0 && Time.realtimeSinceStartupAsDouble<end)yield return null;
                Assert.That(ticket.Mailbox.ArtworkCount,Is.EqualTo(1));surface.DrainMailbox(ticket);
                Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.True);
                Assert.That(surface.InspectionView.Q<Image>("artwork").image,Is.Not.Null);
                jobs.Dispose();yield return Until(jobs.Completion);
            }
        }
        [UnityTest] public IEnumerator PinContextAndUnsafeMetadataFailWithSanitizedErrors()
        {
            var wrongPin=CoreArtworkBundle.OpenAsync(root,new string('0',64),"fixture-0001","one");yield return Until(wrongPin);AssertInvalid(wrongPin);
            var wrongViewer=CoreArtworkBundle.OpenAsync(root,pin,"fixture-0001","two");yield return Until(wrongViewer);AssertInvalid(wrongViewer);
            manifest["entries"][0]["file"]="../private.rgba";Publish();var traversal=CoreArtworkBundle.OpenAsync(root,pin,"fixture-0001","one");yield return Until(traversal);AssertInvalid(traversal);
            manifest["entries"][0]["file"]=file;manifest["entries"][0]["byte_length"]=15;Publish();var length=CoreArtworkBundle.OpenAsync(root,pin,"fixture-0001","one");yield return Until(length);AssertInvalid(length);
        }
        private static void AssertInvalid(Task task){Assert.That(task.IsFaulted,Is.True);Assert.That(task.Exception.GetBaseException().Message,Is.EqualTo("CORE_ARTWORK_BUNDLE_INVALID"));}
        [UnityTest] public IEnumerator PixelCorruptionCancellationAndDisposalNeverReturnArtwork()
        {
            var open=CoreArtworkBundle.OpenAsync(root,pin,"fixture-0001","one");yield return Until(open);
            using(var bundle=open.GetAwaiter().GetResult()) {
                var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));var request=surface.RequestArtwork(ticket,"fixture-0002");
                File.WriteAllBytes(Path.Combine(root,file),new byte[16]);var corrupt=bundle.LoadAsync(request,CancellationToken.None);yield return Until(corrupt);AssertInvalid(corrupt);
                using(var cancel=new CancellationTokenSource()){cancel.Cancel();var canceled=bundle.LoadAsync(request,cancel.Token);yield return Until(canceled);Assert.That(canceled.IsCanceled,Is.True);}
                bundle.Dispose();var disposed=bundle.LoadAsync(request,CancellationToken.None);yield return Until(disposed);AssertInvalid(disposed);
            }
        }
        [UnityTest] public IEnumerator MissingPrintingIsExplicitAndForeignViewerCannotReadIt()
        {
            manifest["entries"]=new JArray();manifest["unavailable"]=new JArray(new JObject{["printing_id"]="exact-printing",["code"]="ARTWORK_MISSING"});Publish();
            var open=CoreArtworkBundle.OpenAsync(root,pin,"fixture-0001","one");yield return Until(open);
            using(var bundle=open.GetAwaiter().GetResult()) {
                var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));
                var missing=bundle.LoadAsync(surface.RequestArtwork(ticket,"fixture-0002"),CancellationToken.None);yield return Until(missing);Assert.That(missing.GetAwaiter().GetResult(),Is.Null);
                var foreign=surface.BeginViewer("fixture-0001","two",new ViewerArtworkScope());yield return null;yield return null;yield return null;surface.TryPresent(foreign,ViewerCardSurfaceTests.Frame("two",artwork:true));
                var denied=bundle.LoadAsync(surface.RequestArtwork(foreign,"fixture-0002"),CancellationToken.None);yield return Until(denied);AssertInvalid(denied);
            }
        }
    }
}

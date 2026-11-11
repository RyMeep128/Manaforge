using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class LayoutPresetStoreTests
    {
        private string directory;
        private string FilePath=>Path.Combine(directory,"presets.json");
        private static HudLayoutPreset Preset(string name="Compact",string id="preset-one")=>new HudLayoutPreset(id,name,new[]{
            new System.Collections.Generic.KeyValuePair<string,HudComponentSnapshot>("fixture.panel",
                new HudComponentSnapshot(new Rect(.1f,.2f,.3f,.4f),ContainerMode.Drawer,null,ContainerDockEdge.Left,2,false))});
        [SetUp] public void Setup(){directory=Path.Combine(Path.GetTempPath(),"manaforge-presets-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(directory);}
        [TearDown] public void Cleanup(){
            string full=Path.GetFullPath(directory),prefix=Path.Combine(Path.GetFullPath(Path.GetTempPath()),"manaforge-presets-");
            if(!full.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("UNSAFE_TEST_DIRECTORY");
            if(Directory.Exists(full))Directory.Delete(full,true);
        }
        [Test] public async Task CrudSelectionAndProfileIsolationRoundTripAcrossStoreInstances()
        {
            var store=new JsonLayoutPresetStore(directory);var initial=await store.ReadAsync();Assert.That(initial.Status,Is.EqualTo(PresetStoreStatus.Missing));
            var saved=await store.WriteAsync(initial.Library.Save(Preset()),initial.Revision);Assert.That(saved.Success,Is.True);
            var reopened=await new JsonLayoutPresetStore(directory).ReadAsync();Assert.That(reopened.Library.LastSelectedId,Is.EqualTo("preset-one"));
            var entry=reopened.Library.Find("preset-one").Components["fixture.panel"];
            Assert.That(entry.FloatingRect,Is.EqualTo(new Rect(.1f,.2f,.3f,.4f)));Assert.That(entry.DrawerExpanded,Is.False);
            var renamed=await store.WriteAsync(reopened.Library.Rename("preset-one","Renamed"),reopened.Revision);
            Assert.That(renamed.Library.Find("preset-one").Name,Is.EqualTo("Renamed"));
            var deleted=await store.WriteAsync(renamed.Library.Delete("preset-one"),renamed.Revision);
            Assert.That(deleted.Library.Presets,Is.Empty);Assert.That(deleted.Library.LastSelectedId,Is.Null);
            var other=await new JsonLayoutPresetStore(Path.Combine(directory,"other-profile")).ReadAsync();Assert.That(other.Library.Presets,Is.Empty);
        }
        [Test] public async Task UnknownComponentsAndExtensionFieldsSurviveWithoutPrecisionLoss()
        {
            var json=LayoutPresetLibrary.Empty.Save(Preset()).ToJson();json["futureLibrarySetting"]=17;
            var preset=(JObject)json["presets"][0];preset["futurePresetSetting"]="keep";
            var component=(JObject)preset["components"]["fixture.panel"].DeepClone();component["futureSetting"]=new JObject{["a"]=true};
            component["rect"]["x"]=.123456789123;((JObject)preset["components"])["unknown.future"]=component;
            File.WriteAllText(FilePath,json.ToString());var store=new JsonLayoutPresetStore(directory);var read=await store.ReadAsync();
            var saved=await store.WriteAsync(read.Library.Rename("preset-one","Still here"),read.Revision);
            var roundtrip=saved.Library.ToJson();Assert.That(JToken.DeepEquals(roundtrip["presets"][0]["components"]["unknown.future"],component),Is.True);
            Assert.That((int)roundtrip["futureLibrarySetting"],Is.EqualTo(17));Assert.That((string)roundtrip["presets"][0]["futurePresetSetting"],Is.EqualTo("keep"));
        }
        [TestCase(PresetWriteStage.TemporaryFlushed)] [TestCase(PresetWriteStage.BeforeReplace)]
        public async Task InterruptedWriteRetainsLastGoodAndCleansTemporaryFiles(PresetWriteStage stage)
        {
            var normal=new JsonLayoutPresetStore(directory);var first=await normal.ReadAsync();first=await normal.WriteAsync(first.Library.Save(Preset()),first.Revision);
            var interrupted=new JsonLayoutPresetStore(directory,s=>{if(s==stage)throw new IOException("injected");});
            var failed=await interrupted.WriteAsync(first.Library.Rename("preset-one","Lost write"),first.Revision);
            Assert.That(failed.Status,Is.EqualTo(PresetStoreStatus.IoError));
            var read=await normal.ReadAsync();Assert.That(read.Library.Find("preset-one").Name,Is.EqualTo("Compact"));Assert.That(read.Revision,Is.EqualTo(first.Revision));
            Assert.That(Directory.GetFiles(directory,"*.tmp"),Is.Empty);
        }
        [Test] public async Task CancellationAfterFlushDoesNotReplaceTheDestination()
        {
            var normal=new JsonLayoutPresetStore(directory);var first=await normal.ReadAsync();first=await normal.WriteAsync(first.Library.Save(Preset()),first.Revision);
            using var cancel=new CancellationTokenSource();var interrupted=new JsonLayoutPresetStore(directory,_=>cancel.Cancel());
            Assert.ThrowsAsync<OperationCanceledException>(async()=>await interrupted.WriteAsync(first.Library.Rename("preset-one","Cancelled"),first.Revision,cancel.Token));
            Assert.That((await normal.ReadAsync()).Revision,Is.EqualTo(first.Revision));Assert.That(Directory.GetFiles(directory,"*.tmp"),Is.Empty);
        }
        [Test] public async Task CorruptPrimaryRecoversBackupAndNeverRotatesCorruptionOverIt()
        {
            var store=new JsonLayoutPresetStore(directory);var first=await store.ReadAsync();first=await store.WriteAsync(first.Library.Save(Preset()),first.Revision);
            await store.WriteAsync(first.Library.Rename("preset-one","Second"),first.Revision);
            byte[] backup=File.ReadAllBytes(FilePath+".bak");File.WriteAllText(FilePath,"broken json");
            var recovered=await store.ReadAsync();Assert.That(recovered.Status,Is.EqualTo(PresetStoreStatus.RecoveredBackup));
            Assert.That(recovered.Library.Find("preset-one").Name,Is.EqualTo("Compact"));
            var saved=await store.WriteAsync(recovered.Library.Rename("preset-one","Recovered"),recovered.Revision);
            Assert.That(saved.Success,Is.True);Assert.That(File.ReadAllBytes(FilePath+".bak"),Is.EqualTo(backup));
            Assert.That(Directory.GetFiles(directory,"*.recovery-*.json").Length,Is.EqualTo(1));
        }
        [Test] public async Task UnsupportedVersionsStayReadOnlyAndCorruptionWithoutBackupIsPreserved()
        {
            var store=new JsonLayoutPresetStore(directory);
            foreach(int version in new[]{0,2}){
                string text=new JObject{["version"]=version,["future"]="untouched"}.ToString();File.WriteAllText(FilePath,text);
                var read=await store.ReadAsync();Assert.That(read.Status,Is.EqualTo(PresetStoreStatus.UnsupportedVersion));Assert.That(read.CanWrite,Is.False);
                var save=await store.WriteAsync(LayoutPresetLibrary.Empty.Save(Preset()),read.Revision);Assert.That(save.Status,Is.EqualTo(PresetStoreStatus.UnsupportedVersion));
                Assert.That(File.ReadAllText(FilePath),Is.EqualTo(text));
            }
            File.WriteAllText(FilePath,"broken");var corrupt=await store.ReadAsync();Assert.That(corrupt.Status,Is.EqualTo(PresetStoreStatus.Corrupt));
            var written=await store.WriteAsync(corrupt.Library.Save(Preset()),corrupt.Revision);Assert.That(written.Success,Is.True);
            Assert.That(File.ReadAllText(Directory.GetFiles(directory,"*.recovery-*.json").Single()),Is.EqualTo("broken"));
        }
        [Test] public async Task StaleAndConcurrentWritesCannotOverwriteAnotherInstance()
        {
            var a=new JsonLayoutPresetStore(directory);var b=new JsonLayoutPresetStore(directory);var initial=await a.ReadAsync();
            var results=await Task.WhenAll(a.WriteAsync(initial.Library.Save(Preset("A","a")),initial.Revision),b.WriteAsync(initial.Library.Save(Preset("B","b")),initial.Revision));
            Assert.That(results.Count(r=>r.Success),Is.EqualTo(1));Assert.That(results.Count(r=>r.Status==PresetStoreStatus.Conflict),Is.EqualTo(1));
            var read=await a.ReadAsync();Assert.That(read.Library.Presets.Count,Is.EqualTo(1));
        }
        [Test] public async Task LockedFileAndPayloadLimitReportStructuredErrors()
        {
            var store=new JsonLayoutPresetStore(directory);
            using(var locked=new FileStream(FilePath+".lock",FileMode.Create,FileAccess.ReadWrite,FileShare.None))
                Assert.That((await store.ReadAsync()).Status,Is.EqualTo(PresetStoreStatus.Busy));
            var empty=await store.ReadAsync();var json=LayoutPresetLibrary.Empty.Save(Preset()).ToJson();json["large"]=new string('x',1048576);
            var huge=LayoutPresetLibrary.Parse(json);var result=await store.WriteAsync(huge,empty.Revision);
            Assert.That(result.Status,Is.EqualTo(PresetStoreStatus.ValidationError));Assert.That(File.Exists(FilePath),Is.False);
        }
        [Test] public async Task NewerBackupIsProtectedAndDeepExtensionsCannotCreateUnreadableFiles()
        {
            var store=new JsonLayoutPresetStore(directory);var initial=await store.ReadAsync();var saved=await store.WriteAsync(initial.Library.Save(Preset()),initial.Revision);
            string future=new JObject{["version"]=2,["future"]=true}.ToString();File.WriteAllText(FilePath+".bak",future);
            var read=await store.ReadAsync();Assert.That(read.CanWrite,Is.False);
            Assert.That((await store.WriteAsync(saved.Library,read.Revision)).Status,Is.EqualTo(PresetStoreStatus.UnsupportedVersion));
            Assert.That(File.ReadAllText(FilePath+".bak"),Is.EqualTo(future));
            File.Delete(FilePath+".bak");read=await store.ReadAsync();
            var root=saved.Library.ToJson();var nested=new JObject();root["extension"]=nested;
            for(int i=0;i<40;i++){var next=new JObject();nested["child"]=next;nested=next;}
            var rejected=await store.WriteAsync(LayoutPresetLibrary.Parse(root),read.Revision);
            Assert.That(rejected.Status,Is.EqualTo(PresetStoreStatus.ValidationError));Assert.That((await store.ReadAsync()).Revision,Is.EqualTo(read.Revision));
        }
        [Test] public async Task DamagedBackupIsArchivedBeforeAValidPrimaryRotatesOverIt()
        {
            var store=new JsonLayoutPresetStore(directory);var first=await store.ReadAsync();first=await store.WriteAsync(first.Library.Save(Preset()),first.Revision);
            File.WriteAllText(FilePath+".bak","damaged backup");var read=await store.ReadAsync();
            Assert.That(read.Success,Is.True);Assert.That((await store.WriteAsync(read.Library.Rename("preset-one","Updated"),read.Revision)).Success,Is.True);
            string archive=Directory.GetFiles(directory,"*.recovery-*.json").Single();Assert.That(File.ReadAllText(archive),Is.EqualTo("damaged backup"));
        }
        [Test] public async Task DuplicatePropertiesAndInvalidGeometryFallBackWithoutGuessing()
        {
            var store=new JsonLayoutPresetStore(directory);
            File.WriteAllText(FilePath,"{\"version\":1,\"version\":1,\"lastSelectedId\":null,\"presets\":[]}");
            Assert.That((await store.ReadAsync()).Status,Is.EqualTo(PresetStoreStatus.Corrupt));
            var json=LayoutPresetLibrary.Empty.Save(Preset()).ToJson();json["presets"][0]["components"]["fixture.panel"]["rect"]["width"]=-1;
            File.WriteAllText(FilePath,json.ToString());Assert.That((await store.ReadAsync()).Status,Is.EqualTo(PresetStoreStatus.Corrupt));
            File.WriteAllText(FilePath,"\uFEFF"+LayoutPresetLibrary.Empty.Save(Preset()).ToJson());
            Assert.That((await store.ReadAsync()).Success,Is.True);
        }
        [Test] public void NamesLimitsAndMalformedDockGraphsAreRejected()
        {
            Assert.Throws<ArgumentException>(()=>Preset(new string('x',65)));
            Assert.Throws<ArgumentException>(()=>new LayoutPresetLibrary(Enumerable.Range(0,65).Select(i=>Preset("Layout "+i,"id-"+i))));
            Assert.Throws<ArgumentException>(()=>new HudLayoutPreset("too-many","Too many",Enumerable.Range(0,257).Select(i=>
                new System.Collections.Generic.KeyValuePair<string,HudComponentSnapshot>("component."+i,Preset().Components["fixture.panel"]))));
            Assert.Throws<ArgumentException>(()=>Preset("Default"));Assert.Throws<ArgumentException>(()=>Preset("bad\nname"));
            Assert.Throws<ArgumentException>(()=>LayoutPresetLibrary.Empty.Save(Preset()).Save(Preset("compact","different")));
            var states=new[]{new System.Collections.Generic.KeyValuePair<string,HudComponentSnapshot>("a",new HudComponentSnapshot(new Rect(0,0,.2f,.3f),ContainerMode.Panel,"b",ContainerDockEdge.Left,0,true)),
                new System.Collections.Generic.KeyValuePair<string,HudComponentSnapshot>("b",new HudComponentSnapshot(new Rect(0,0,.2f,.3f),ContainerMode.Panel,"a",ContainerDockEdge.Left,0,true))};
            Assert.Throws<ArgumentException>(()=>new HudLayoutPreset("cycle","Cycle",states));
            Assert.Throws<ArgumentException>(()=>new HudComponentSnapshot(new Rect(float.NaN,0,1,1),ContainerMode.Panel,null,ContainerDockEdge.None,0,true));
        }
    }
}

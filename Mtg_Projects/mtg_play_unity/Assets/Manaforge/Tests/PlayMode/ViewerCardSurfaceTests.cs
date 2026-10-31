using System;
using System.Collections;
using System.IO;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerCardSurfaceTests
    {
        private GameObject host;
        private PanelSettings settings;
        private ViewerCardSurface surface;
        private sealed class Scope : IDisposable
        {
            private readonly Action dispose;
            public Scope(Action dispose){this.dispose=dispose;}
            public void Dispose(){dispose();}
        }
        private static ProjectedCardFrame Frame(string viewer="one",long revision=1,bool hidden=false,string name="Viewer text",bool empty=false,string session="fixture-0001")
        {
            var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
            var message=(JObject)corpus["positive"][0]["envelope"];var snapshot=message["body"]["snapshot"];
            snapshot["session_id"]=session;snapshot["viewer_id"]=viewer;snapshot["revision"]=revision;
            snapshot["decision"]=JValue.CreateNull();snapshot["actions"]=new JArray();
            var card=snapshot["objects"][0];card["hidden"]=hidden;
            if(hidden){card["characteristics"]=JValue.CreateNull();card["card_identity"]=JValue.CreateNull();}
            else {card["characteristics"]["name"]=name;card["characteristics"]["power"]="4";card["characteristics"]["toughness"]="5";card["characteristics"]["engine_view_text"]=new JArray("Not complete Oracle text");}
            if(empty)snapshot["objects"]=new JArray();
            return ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true);
        }
        [UnitySetUp] public IEnumerator Setup()
        {
            host=new GameObject("Viewer surface test");settings=ScriptableObject.CreateInstance<PanelSettings>();
            settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=host.AddComponent<UIDocument>();document.panelSettings=settings;
            document.rootVisualElement.style.width=1000;document.rootVisualElement.style.height=800;
            surface=new ViewerCardSurface(document.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup()
        {
            surface?.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);yield return null;
        }
        [UnityTest] public IEnumerator ViewerSwitchClearsBeforePrivateTextureDisposalAndKeepsAnEmptyFrame()
        {
            var privateTexture=new Texture2D(4,4);var sharedTexture=new Texture2D(4,4);CardView previous=null;bool released=false;
            var first=surface.BeginViewer("fixture-0001","one",new Scope(()=>{
                Assert.That(surface.CardsRoot.childCount,Is.Zero);
                foreach(var label in previous.Query<Label>().ToList())Assert.That(label.text,Is.Empty);
                foreach(var image in surface.InspectionView.Query<Image>().ToList())Assert.That(image.image,Is.Null);
                Assert.That(surface.InspectionView.tooltip,Is.Null.Or.Empty);
                released=true;UnityEngine.Object.Destroy(privateTexture);
            }));
            yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(first,Frame(name:"First viewer")),Is.True);
            previous=surface.CardsRoot.Q<CardView>();previous.tooltip="Private tooltip";
            Assert.That(surface.Inspect(first,"fixture-0002"),Is.True);
            var identity=VisualPrintingPolicy.Resolve(false,new VisualPrintingCandidate("oracle","private-printing","front",true,true),Array.Empty<VisualPrintingCandidate>());
            surface.InspectionView.Bind(identity,privateTexture,new Rect(0,0,1,1));surface.InspectionView.UpdateValues(new CardDisplayValues("Private inspection",null,null,null,null,null));
            surface.InspectionView.tooltip="Private inspection tooltip";
            using(var flip=new CardInspectionFlip(surface.InspectionView)) {
                int swaps=0;flip.Begin(()=>swaps++);
                var next=surface.BeginViewer("fixture-0001","two");Assert.That(released,Is.True);
                Assert.That(surface.TryPresent(first,Frame()),Is.False);Assert.That(surface.TryPresent(next,Frame("two")),Is.False);
                yield return null;
                Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.That(surface.TryPresent(next,Frame("two")),Is.False);
                yield return null;
                Assert.That(privateTexture==null,Is.True);Assert.That(sharedTexture==null,Is.False);
                Assert.That(surface.TryPresent(next,Frame("two",name:"Second viewer")),Is.True);
                flip.Advance(1);Assert.That(swaps,Is.Zero);
                Assert.That(surface.CardsRoot.Q<Label>("name").text,Is.EqualTo("Second viewer"));
                Assert.That(surface.Inspect(next,"fixture-0002"),Is.True);
                Assert.That(surface.Inspect(first,"fixture-0002"),Is.False);
                Assert.That(surface.InspectionView.Q<Label>("name").text,Is.EqualTo("Second viewer"));
            }
            UnityEngine.Object.Destroy(sharedTexture);
        }
        [UnityTest] public IEnumerator StaleFramesWrongScopeAndRetiredTicketsCannotPublish()
        {
            var ticket=surface.BeginViewer("fixture-0001","one");yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(ticket,Frame(revision:3)),Is.True);
            Assert.That(surface.SetMinimumRevision(ticket,5),Is.True);
            Assert.That(surface.TryPresent(ticket,Frame(revision:4)),Is.False);
            Assert.That(surface.TryPresent(ticket,Frame(revision:5)),Is.True);
            Assert.That(surface.TryPresent(ticket,Frame(revision:5)),Is.False);
            Assert.That(surface.TryPresent(ticket,Frame("two",6)),Is.False);
            Assert.That(surface.TryPresent(ticket,Frame(revision:6,session:"other-session")),Is.False);
            var next=surface.BeginViewer("fixture-0001","one",minimumRevision:5);yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(ticket,Frame(revision:6)),Is.False);
            Assert.That(surface.SetMinimumRevision(ticket,99),Is.False);
            Assert.That(surface.ClearViewer(ticket),Is.False);
            Assert.That(surface.TryPresent(next,Frame(revision:6)),Is.True);
            Assert.That(surface.ClearViewer(next),Is.True);Assert.That(surface.TryPresent(next,Frame(revision:7)),Is.False);Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.False);
        }
        [UnityTest] public IEnumerator UpdatesReuseViewsAndConcealmentRemovalAndInspectionClearOldData()
        {
            var ticket=surface.BeginViewer("fixture-0001","one");yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(ticket,Frame(name:"First")),Is.True);var view=surface.CardsRoot.Q<CardView>();
            Assert.That(view.Q<Label>("stats").text,Is.EqualTo("4/5"));Assert.That(view.Identity,Is.Null);Assert.That(view.Artwork,Is.Null);
            Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.True);Assert.That(surface.InspectionView.Q<Label>("rules").text,Is.Empty);
            Assert.That(surface.TryPresent(ticket,Frame(revision:2,name:"Changed")),Is.True);
            Assert.That(surface.CardsRoot.Q<CardView>(),Is.SameAs(view));Assert.That(view.Q<Label>("name").text,Is.EqualTo("Changed"));
            Assert.That(surface.InspectionView.Q<Label>("name").text,Is.Empty);
            Assert.That(surface.TryPresent(ticket,Frame(revision:3,hidden:true)),Is.True);
            foreach(var label in view.Query<Label>().ToList())Assert.That(label.text,Is.Empty);
            Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.False);
            Assert.That(surface.TryPresent(ticket,Frame(revision:4,empty:true)),Is.True);
            Assert.That(view.parent,Is.Null);Assert.That(surface.CardsRoot.childCount,Is.Zero);
        }
        [UnityTest] public IEnumerator RemovalCallbacksCannotSwitchViewersDuringPresentation()
        {
            var ticket=surface.BeginViewer("fixture-0001","one");yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(ticket,Frame()),Is.True);int attempts=0;
            surface.CardsRoot.Q<CardView>().RegisterCallback<DetachFromPanelEvent>(_=>{
                attempts++;var error=Assert.Throws<InvalidOperationException>(()=>surface.BeginViewer("fixture-0001","two"));
                Assert.That(error.Message,Is.EqualTo("VIEWER_SURFACE_UNAVAILABLE"));
                Assert.Throws<InvalidOperationException>(()=>surface.Dispose());
            });
            Assert.That(surface.TryPresent(ticket,Frame(revision:2,empty:true)),Is.True);Assert.That(attempts,Is.GreaterThan(0));
            Assert.That(surface.TryPresent(ticket,Frame(revision:3)),Is.True);
        }
        [UnityTest] public IEnumerator CleanupFailureClosesTheSurfaceWithoutLeakingItsMessage()
        {
            int attempts=0;var ticket=surface.BeginViewer("fixture-0001","one",new Scope(()=>{if(++attempts==1)throw new Exception("Private diagnostic");}));
            yield return null;yield return null;yield return null;Assert.That(surface.TryPresent(ticket,Frame()),Is.True);
            var error=Assert.Throws<InvalidOperationException>(()=>surface.BeginViewer("fixture-0001","two"));
            Assert.That(error.Message,Is.EqualTo("VIEWER_SURFACE_CLEANUP_FAILED"));Assert.That(error.InnerException,Is.Null);
            Assert.That(surface.CardsRoot.childCount,Is.Zero);
            Assert.Throws<InvalidOperationException>(()=>surface.TryPresent(ticket,Frame(revision:2)));
            Assert.Throws<InvalidOperationException>(()=>surface.BeginViewer("fixture-0001","two"));
            surface.Dispose();Assert.That(attempts,Is.EqualTo(2),"Failed private cleanup retains ownership for disposal retry");
        }
        [UnityTest] public IEnumerator WorkerCannotMutateSurfaceOrTransferAssetOwnership()
        {
            bool disposed=false;var assets=new Scope(()=>disposed=true);
            var error=Task.Run(()=>Assert.Throws<InvalidOperationException>(()=>surface.BeginViewer("fixture-0001","one",assets))).GetAwaiter().GetResult();
            Assert.That(error.Message,Is.EqualTo("VIEWER_SURFACE_THREAD"));Assert.That(disposed,Is.False);
            Assert.That(surface.CardsRoot.childCount,Is.Zero);yield return null;
        }
    }
}

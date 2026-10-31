using System;
using System.Collections;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerArtworkTests
    {
        private GameObject host;private PanelSettings settings;private ViewerCardSurface surface;
        private static CatalogArtworkFace Catalog(string printing="exact-printing",string layout="normal",int faces=1,bool standard=true,string type="Artifact Creature")
            =>new CatalogArtworkFace("oracle",printing,"Original printing name",layout,faces,standard,type);
        private static PreparedCardArtwork Prepare(ViewerArtworkRequest request,byte first=200)
        {var bytes=new byte[16];bytes[0]=first;return PreparedCardArtwork.Prepare(request,Catalog(),2,2,bytes);}
        private static Color32 ReadPixel(Texture2D texture)
        {
            var prior=RenderTexture.active;var target=RenderTexture.GetTemporary(2,2,0,RenderTextureFormat.ARGB32,RenderTextureReadWrite.Linear);
            var copy=new Texture2D(2,2,TextureFormat.RGBA32,false);
            try{Graphics.Blit(texture,target);RenderTexture.active=target;copy.ReadPixels(new Rect(0,0,2,2),0,0);copy.Apply();return copy.GetPixels32()[0];}
            finally{RenderTexture.active=prior;RenderTexture.ReleaseTemporary(target);UnityEngine.Object.Destroy(copy);}
        }
        [UnitySetUp] public IEnumerator Setup()
        {
            host=new GameObject("Viewer artwork tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=host.AddComponent<UIDocument>();document.panelSettings=settings;
            document.rootVisualElement.style.width=1200;document.rootVisualElement.style.height=800;
            surface=new ViewerCardSurface(document.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator ExactPrintingArtworkIsSharedWithInspectionAndSurvivesCurrentNameChanges()
        {
            var scope=new ViewerArtworkScope();var ticket=surface.BeginViewer("fixture-0001","one",scope);yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true)),Is.True);surface.Inspect(ticket,"fixture-0002");
            var request=surface.RequestArtwork(ticket,"fixture-0002");Assert.That(request,Is.Not.Null);
            Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.SameAs(request));
            var prepared=Task.Run(()=>Prepare(request)).GetAwaiter().GetResult();
            Assert.That(surface.TryApplyArtwork(ticket,prepared),Is.True);Assert.That(prepared.IsDisposed,Is.True);
            var view=surface.CardsRoot.Q<CardView>();var texture=(Texture2D)view.Artwork;
            Assert.That(texture,Is.Not.Null);Assert.That(texture.isReadable,Is.False);Assert.That(scope.Bytes,Is.EqualTo(16));
            Assert.That(surface.InspectionView.Artwork,Is.SameAs(texture));Assert.That(view.Identity.SelectedPrintingId,Is.EqualTo("exact-printing"));
            Assert.That(view.Q<Label>("name").text,Is.EqualTo("Viewer text"));Assert.That(surface.InspectionView.Q<Label>("rules").text,Is.Empty);
            Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:2,name:"Copied current name",artwork:true)),Is.True);
            Assert.That(view.Artwork,Is.SameAs(texture));Assert.That(view.Q<Label>("name").text,Is.EqualTo("Copied current name"));
            Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.Null);
            Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:3,hidden:true)),Is.True);
            Assert.That(view.Artwork,Is.Null);Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.Null);
            surface.BeginViewer("fixture-0001","two",new ViewerArtworkScope());yield return null;yield return null;
            Assert.That(texture==null,Is.True);Assert.That(scope.Count,Is.Zero);
        }
        [UnityTest] public IEnumerator GraphicsUploadUsesTheCopiedWorkerPixels()
        {
            if(SystemInfo.graphicsDeviceType==UnityEngine.Rendering.GraphicsDeviceType.Null)
                Assert.Ignore("Real GPU pixel readback requires tools/unity-play.ps1 -Mode PlayMode -Graphics");
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));var request=surface.RequestArtwork(ticket,"fixture-0002");
            var pixels=new byte[16];for(int i=0;i<16;i+=4){pixels[i]=255;pixels[i+3]=255;}
            var prepared=Task.Run(()=>PreparedCardArtwork.Prepare(request,Catalog(),2,2,pixels)).GetAwaiter().GetResult();
            for(int i=0;i<16;i+=4){pixels[i]=0;pixels[i+2]=255;}
            Assert.That(surface.TryApplyArtwork(ticket,prepared),Is.True);
            var color=ReadPixel((Texture2D)surface.CardsRoot.Q<CardView>().Artwork);
            Assert.That(color.r,Is.GreaterThan(250));Assert.That(color.b,Is.LessThan(5),"Producer buffer reuse must not alter the private upload");
        }
        [UnityTest] public IEnumerator WatermarksRetiredEpochsAndWorkerCallsCannotAttachOrRetainCompletedPixels()
        {
            var scope=new ViewerArtworkScope();var ticket=surface.BeginViewer("fixture-0001","one",scope);yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));var first=Prepare(surface.RequestArtwork(ticket,"fixture-0002"));
            var error=Task.Run(()=>Assert.Throws<InvalidOperationException>(()=>surface.TryApplyArtwork(ticket,first))).GetAwaiter().GetResult();
            Assert.That(error.Message,Is.EqualTo("VIEWER_SURFACE_THREAD"));Assert.That(first.IsDisposed,Is.False);
            surface.SetMinimumRevision(ticket,2);Assert.That(surface.TryApplyArtwork(ticket,first),Is.False);Assert.That(first.IsDisposed,Is.True);Assert.That(scope.Count,Is.Zero);
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:2,artwork:true));var late=Prepare(surface.RequestArtwork(ticket,"fixture-0002"));
            var nextScope=new ViewerArtworkScope();var next=surface.BeginViewer("fixture-0001","two",nextScope);yield return null;yield return null;yield return null;
            surface.TryPresent(next,ViewerCardSurfaceTests.Frame("two",artwork:true));
            Assert.That(surface.TryApplyArtwork(next,late),Is.False);Assert.That(late.IsDisposed,Is.True);Assert.That(nextScope.Count,Is.Zero);
        }
        [UnityTest] public IEnumerator BudgetFailureKeepsTheViewUsableAndIdenticalPixelsReuseAnOwnedTexture()
        {
            var scope=new ViewerArtworkScope(16);var ticket=surface.BeginViewer("fixture-0001","one",scope);yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true,objectCount:2));
            var first=Prepare(surface.RequestArtwork(ticket,"fixture-0002"));Assert.That(surface.TryApplyArtwork(ticket,first),Is.True);
            var views=surface.CardsRoot.Query<CardView>().ToList();var different=Prepare(surface.RequestArtwork(ticket,"fixture-extra-1"),100);
            Assert.That(surface.TryApplyArtwork(ticket,different),Is.False);Assert.That(different.IsDisposed,Is.True);Assert.That(views[1].Artwork,Is.Null);
            var same=Prepare(surface.RequestArtwork(ticket,"fixture-extra-1"));Assert.That(surface.TryApplyArtwork(ticket,same),Is.True);
            Assert.That(views[1].Artwork,Is.SameAs(views[0].Artwork));Assert.That(scope.Count,Is.EqualTo(1));Assert.That(scope.Bytes,Is.EqualTo(16));
            Assert.That(surface.Inspect(ticket,"fixture-extra-1"),Is.True);
        }
        [UnityTest] public IEnumerator UnsupportedMetadataConcealedFacesAndMissingIdentitiesCannotRequestOrPrepareArt()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame());Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.Null);
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:2,artwork:true,faceDownState:null));Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.Null);
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:3,artwork:true,faceDownState:true));Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.Null);
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:4,artwork:true));var request=surface.RequestArtwork(ticket,"fixture-0002");
            foreach(var catalog in new[]{Catalog("other"),Catalog(layout:"transform",faces:2),Catalog(faces:2),Catalog(standard:false),Catalog(type:"Planeswalker")}) {
                var error=Assert.Throws<ArgumentException>(()=>PreparedCardArtwork.Prepare(request,catalog,2,2,new byte[16]));
                Assert.That(error.Message,Does.StartWith("ARTWORK_"));Assert.That(error.InnerException,Is.Null);
            }
            Assert.Throws<ArgumentException>(()=>PreparedCardArtwork.Prepare(request,Catalog(),1025,1,new byte[4100]));
            Assert.Throws<ArgumentException>(()=>PreparedCardArtwork.Prepare(request,Catalog(),2,2,new byte[15]));
            var instant=PreparedCardArtwork.Prepare(request,Catalog(type:"Instant"),2,2,new byte[16]);
            Assert.That(surface.TryApplyArtwork(ticket,instant),Is.True);Assert.That(surface.CardsRoot.Q<CardView>().Mode,Is.EqualTo(CardPresentationMode.Full));
        }
        [UnityTest] public IEnumerator OwnedScopeCannotBeReusedByAnotherSurfaceOrTheSameViewerEpoch()
        {
            var scope=new ViewerArtworkScope();var ticket=surface.BeginViewer("fixture-0001","one",scope);yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));Assert.That(surface.TryApplyArtwork(ticket,Prepare(surface.RequestArtwork(ticket,"fixture-0002"))),Is.True);
            Assert.Throws<InvalidOperationException>(()=>surface.BeginViewer("fixture-0001","one",scope));
            using(var other=new ViewerCardSurface(new VisualElement()))Assert.Throws<InvalidOperationException>(()=>other.BeginViewer("fixture-0001","two",scope));
            Assert.That(scope.Count,Is.EqualTo(1));Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:2,artwork:true)),Is.True);
        }
    }
}

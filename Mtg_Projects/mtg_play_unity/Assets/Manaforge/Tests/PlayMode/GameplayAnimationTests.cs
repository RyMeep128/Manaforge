using System;
using System.Collections;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayAnimationTests
    {
        private GameObject node;private PanelSettings settings;private VisualElement root;
        private ViewerCardSurface surface;private ViewerSurfaceTicket ticket;private GameplayAnimationCoordinator animation;
        private float now;private bool reduced;private string id;
        private static ProjectedDecisionFrame Decision(long revision=1,string result=null)
        {
            var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
            wire["body"]["snapshot"]["revision"]=revision;
            if(result!=null){wire["body"]["snapshot"]["result"]=result;wire["body"]["snapshot"]["status"]="finished";}
            return ViewerDecisionProjection.ParseSnapshot(wire.ToString(),"fixture-0001","one",0,true);
        }
        private void Enqueue(params GameplayMotionCue[] cues)
        {var frame=Decision();animation.Observe(frame,new[]{new GameplayMotionBatch(frame.Context,cues)});animation.Advance();}
        [UnitySetUp] public IEnumerator Setup()
        {
            node=new GameObject("Gameplay animation tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var doc=node.AddComponent<UIDocument>();doc.panelSettings=settings;root=doc.rootVisualElement;root.style.width=1280;root.style.height=720;
            surface=new ViewerCardSurface(root);ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());
            now=0;reduced=false;yield return null;yield return null;yield return null;
            Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true)),Is.True);id=surface.PresentedObjectIds()[0];
            var request=surface.RequestArtwork(ticket,id);var catalog=new CatalogArtworkFace("oracle","exact-printing","front","normal",1,true,"Creature");
            Assert.That(surface.TryApplyArtwork(ticket,PreparedCardArtwork.Prepare(request,catalog,2,2,new byte[16])),Is.True);
            animation=new GameplayAnimationCoordinator(root,surface,(owner,zone)=>zone=="library"?new Vector2(40,100):new Vector2(600,500),player=>null,()=>reduced,()=>now);
            yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup()
        {animation.Dispose();surface.Dispose();UnityEngine.Object.Destroy(node);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator EffectsSurviveSnapshotsAndKeepInspectionAndInputAvailable()
        {
            Assert.That(surface.Inspect(ticket,id),Is.True);var texture=surface.InspectionView.Artwork;
            var button=new Button(){text="Manual choice"};root.Add(button);
            Enqueue(new GameplayMotionCue(GameplayMotionKind.Cast,id,owner:"one",from:"hand",to:"stack"));
            Assert.That(animation.ActiveCount,Is.EqualTo(1));Assert.That(animation.HoldAutomaticPassing,Is.True);
            now=.4f;Assert.That(surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:2,artwork:true,name:"Updated stats")),Is.True);
            animation.Observe(Decision(2),Array.Empty<GameplayMotionBatch>());animation.Advance();
            Assert.That(animation.ActiveCount,Is.EqualTo(1));Assert.That(surface.HasInspection,Is.True);Assert.That(surface.InspectionView.Artwork,Is.SameAs(texture));
            Assert.That(button.enabledInHierarchy,Is.True);Assert.That(root.Q("gameplay-animation-layer").pickingMode,Is.EqualTo(PickingMode.Ignore));
            now=1.01f;animation.Advance();Assert.That(animation.ActiveCount,Is.Zero);Assert.That(animation.HoldAutomaticPassing,Is.False);yield return null;
        }
        [UnityTest] public IEnumerator SameCardEffectsSerializeAndAutomationHoldIsCapped()
        {
            Enqueue(new GameplayMotionCue(GameplayMotionKind.Cast,id),new GameplayMotionCue(GameplayMotionKind.Damage,id,text:"-2"),new GameplayMotionCue(GameplayMotionKind.Arrive,id));
            Assert.That(animation.ActiveCount,Is.EqualTo(1));Assert.That(animation.PendingCount,Is.EqualTo(1));
            now=1.1f;animation.Advance();Assert.That(animation.ActiveCount,Is.EqualTo(1));Assert.That(animation.HoldAutomaticPassing,Is.True);
            now=2.1f;animation.Advance();Assert.That(animation.ActiveCount,Is.EqualTo(1));Assert.That(animation.HoldAutomaticPassing,Is.False);yield return null;
        }
        [UnityTest] public IEnumerator HiddenPendingSnapshotRevokesBorrowedArtworkBeforeItIsApplied()
        {
            Enqueue(new GameplayMotionCue(GameplayMotionKind.Cast,id));Assert.That(animation.ActiveCount,Is.EqualTo(1));
            Assert.That(ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(revision:2,hidden:true)),Is.True);
            animation.Advance();Assert.That(animation.ActiveCount,Is.Zero);Assert.That(root.Query<Image>("motion-card").ToList(),Is.Empty);yield return null;
        }
        [UnityTest] public IEnumerator ReducedMotionImmediatelyStopsTravelAndParticles()
        {
            Enqueue(new GameplayMotionCue(GameplayMotionKind.Draw,owner:"one",from:"library",to:"hand"));
            Assert.That(animation.ParticleCount,Is.GreaterThan(0));
            reduced=true;now=.1f;animation.Advance();Assert.That(animation.ParticleCount,Is.Zero);
            Assert.That(root.Q<Image>("motion-card").style.display.value,Is.EqualTo(DisplayStyle.None));
            now=.251f;animation.Advance();Assert.That(animation.ActiveCount,Is.Zero);yield return null;
        }
        [UnityTest] public IEnumerator MassEffectsStayBoundedAndDisposeClearsEverything()
        {
            Enqueue(Enumerable.Range(0,64).Select(i=>new GameplayMotionCue(GameplayMotionKind.Draw,owner:"one",from:"library",to:"hand")).ToArray());
            Assert.That(animation.ActiveCount,Is.LessThanOrEqualTo(GameplayAnimationCoordinator.MaximumActive));
            Assert.That(animation.ParticleCount,Is.LessThanOrEqualTo(GameplayAnimationCoordinator.MaximumParticles));
            animation.Dispose();Assert.That(animation.ActiveCount,Is.Zero);Assert.That(animation.PendingCount,Is.Zero);
            Assert.That(root.Q("gameplay-animation-layer"),Is.Null);yield return null;
        }
        [UnityTest] public IEnumerator ResultFanfareCanFinishAfterViewerResourcesAreCleared()
        {
            surface.ClearViewer(ticket);animation.Clear();var frame=Decision(2,"win");animation.Observe(frame,Array.Empty<GameplayMotionBatch>());animation.Advance();
            Assert.That(animation.ActiveCount,Is.EqualTo(1));Assert.That(root.Q<Label>("motion-caption").text,Is.EqualTo("Victory"));
            Assert.That(root.Query<Image>("motion-card").ToList(),Is.Empty);
            now=2.01f;animation.Advance();Assert.That(animation.ActiveCount,Is.Zero);yield return null;
        }
    }
}

using System;
using System.Collections;
using System.Collections.Concurrent;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerPresentationPumpTests
    {
        private GameObject host;private PanelSettings settings;private ViewerCardSurface surface;
        private static PreparedCardArtwork Prepare(ViewerArtworkRequest request)=>PreparedCardArtwork.Prepare(request,
            new CatalogArtworkFace("oracle","exact-printing","front","normal",1,true,"Creature"),2,2,new byte[16]);
        private static TaskCompletionSource<bool> Signal()=>new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        private static IEnumerator Until(Func<bool> done)
        {double end=Time.realtimeSinceStartupAsDouble+10;while(!done() && Time.realtimeSinceStartupAsDouble<end)yield return null;Assert.That(done(),Is.True,"Presentation pump timed out");}
        [UnitySetUp] public IEnumerator Setup()
        {
            host=new GameObject("Presentation pump tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=host.AddComponent<UIDocument>();document.panelSettings=settings;surface=new ViewerCardSurface(document.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator FrameBarrierAndPerUpdateAdmissionAndUploadBudgetsArePreserved()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());int calls=0;
            var jobs=surface.CreateArtworkJobs(ticket,(r,c)=>{Interlocked.Increment(ref calls);return Task.FromResult(Prepare(r));});
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true,objectCount:3));
            Assert.That(surface.Pump(ticket),Is.Zero);Assert.That(calls,Is.Zero);Assert.That(surface.CardsRoot.childCount,Is.Zero);
            yield return null;Assert.That(surface.Pump(ticket),Is.Zero);yield return null;
            Assert.That(surface.Pump(ticket,0,1),Is.EqualTo(2)); // one snapshot and one admission
            yield return Until(()=>ticket.Mailbox.ArtworkCount==1 && jobs.RunningCount==0);
            Assert.That(calls,Is.EqualTo(1));Assert.That(surface.Pump(ticket,0,0),Is.Zero);Assert.That(ticket.Mailbox.ArtworkCount,Is.EqualTo(1));
            Assert.That(surface.Pump(ticket,1,0),Is.EqualTo(1));Assert.That(ticket.Mailbox.ArtworkCount,Is.Zero);
            Assert.That(surface.Pump(ticket,0,2),Is.EqualTo(2));yield return Until(()=>ticket.Mailbox.ArtworkCount==2 && jobs.RunningCount==0);
            Assert.That(calls,Is.EqualTo(3));Assert.That(surface.Pump(ticket,1,0),Is.EqualTo(1));Assert.That(ticket.Mailbox.ArtworkCount,Is.EqualTo(1));
            surface.Pump(ticket);Assert.That(surface.Inspect(ticket,"fixture-extra-2"),Is.True);Assert.That(surface.InspectionView.Q<Image>("artwork").image,Is.Not.Null);
            jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator BackpressureRetainsUnadmittedWorkWithoutReplayingAcceptedFailures()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;
            var release=Signal();int calls=0;var ids=new ConcurrentQueue<string>();
            var jobs=surface.CreateArtworkJobs(ticket,async(r,c)=>{ids.Enqueue(r.ObjectId);Interlocked.Increment(ref calls);await release.Task.ConfigureAwait(false);return null;},1,1);
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true,objectCount:4));surface.Pump(ticket,0,1);yield return Until(()=>Volatile.Read(ref calls)==1);
            Assert.That(surface.Pump(ticket,0,16),Is.EqualTo(1));Assert.That(jobs.QueuedCount,Is.EqualTo(1));Assert.That(surface.Pump(ticket,0,16),Is.Zero);
            release.SetResult(true);yield return Until(()=>Volatile.Read(ref calls)==2 && jobs.RunningCount==0 && jobs.QueuedCount==0);
            for(int i=0;i<20 && Volatile.Read(ref calls)<4;i++){surface.Pump(ticket);yield return null;}
            yield return Until(()=>Volatile.Read(ref calls)==4 && jobs.RunningCount==0 && jobs.QueuedCount==0);
            for(int i=0;i<5;i++){surface.Pump(ticket);yield return null;}
            Assert.That(calls,Is.EqualTo(4));Assert.That(ids.Distinct().Count(),Is.EqualTo(4));Assert.That(ticket.Mailbox.ArtworkCount,Is.Zero);
            jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator NewSnapshotReplacesTheAdmissionCursorAndRetiredTicksCannotDriveTheNextViewer()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;
            var revisions=new ConcurrentQueue<long>();var jobs=surface.CreateArtworkJobs(ticket,(r,c)=>{revisions.Enqueue(r.Revision);return Task.FromResult(Prepare(r));});
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true,objectCount:4));surface.Pump(ticket,0,1);yield return Until(()=>ticket.Mailbox.ArtworkCount==1);
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(revision:2,artwork:true,objectCount:1));surface.Pump(ticket);
            yield return Until(()=>ticket.Mailbox.ArtworkCount==1 && jobs.RunningCount==0);surface.Pump(ticket);
            Assert.That(revisions.ToArray(),Is.EqualTo(new long[]{1,2}));Assert.That(surface.CardsRoot.childCount,Is.EqualTo(1));
            var next=surface.BeginViewer("fixture-0001","two",new ViewerArtworkScope());int nextCalls=0;
            var nextJobs=surface.CreateArtworkJobs(next,(r,c)=>{Interlocked.Increment(ref nextCalls);return Task.FromResult(Prepare(r));});
            next.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame("two",artwork:true));yield return null;yield return null;
            Assert.That(surface.Pump(ticket),Is.Zero);Assert.That(nextCalls,Is.Zero);surface.Pump(next);yield return Until(()=>next.Mailbox.ArtworkCount==1);
            next.Mailbox.Dispose();surface.Pump(next);Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.That(nextJobs.IsStopped,Is.True);
            yield return Until(()=>jobs.Completion.IsCompleted && nextJobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator WatermarksConcealmentAndInvalidBudgetsNeverScheduleWork()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;
            int calls=0;var jobs=surface.CreateArtworkJobs(ticket,(r,c)=>{Interlocked.Increment(ref calls);return Task.FromResult(Prepare(r));});
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true));
            Assert.Throws<ArgumentOutOfRangeException>(()=>surface.Pump(ticket,0,17));Assert.That(ticket.Mailbox.HasPendingFrame,Is.True);
            Assert.Throws<ArgumentOutOfRangeException>(()=>surface.Pump(ticket,-1,0));
            surface.Pump(ticket,0,0);ticket.Mailbox.AdvanceMinimumRevision(2);surface.Pump(ticket);Assert.That(calls,Is.Zero);
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(revision:2,hidden:true,artwork:true));surface.Pump(ticket);yield return null;Assert.That(calls,Is.Zero);
            surface.ClearViewer(ticket);Assert.That(surface.Pump(ticket),Is.Zero);yield return Until(()=>jobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator WatermarkBehindAppliedStatePreservesItsRequestsAndAdmissionCursor()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(revision:3,artwork:true,objectCount:2));surface.Pump(ticket,0,0);
            var request=surface.RequestArtwork(ticket,"fixture-0002");ticket.Mailbox.AdvanceMinimumRevision(2);surface.Pump(ticket,0,0);
            Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.SameAs(request));
            int calls=0;var jobs=surface.CreateArtworkJobs(ticket,(r,c)=>{Interlocked.Increment(ref calls);return Task.FromResult(Prepare(r));});
            Assert.That(surface.Pump(ticket,0,2),Is.EqualTo(2));yield return Until(()=>ticket.Mailbox.ArtworkCount==2 && jobs.RunningCount==0);
            surface.Pump(ticket);Assert.That(calls,Is.EqualTo(2));Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.True);
            Assert.That(surface.InspectionView.Q<Image>("artwork").image,Is.Not.Null);jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);
        }
    }
}

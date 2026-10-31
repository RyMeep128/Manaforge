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
    public sealed class ViewerArtworkJobTests
    {
        private GameObject host;private PanelSettings settings;private ViewerCardSurface surface;
        private static TaskCompletionSource<T> Signal<T>()=>new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        private static PreparedCardArtwork Prepare(ViewerArtworkRequest request)=>PreparedCardArtwork.Prepare(request,
            new CatalogArtworkFace("oracle","exact-printing","Printed face","normal",1,true,"Artifact Creature"),2,2,new byte[16]);
        private static IEnumerator Until(Func<bool> done)
        {double deadline=Time.realtimeSinceStartupAsDouble+5;while(!done() && Time.realtimeSinceStartupAsDouble<deadline)yield return null;Assert.That(done(),Is.True,"Bounded asynchronous job wait timed out");}
        [UnitySetUp] public IEnumerator Setup()
        {
            host=new GameObject("Artwork job tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=host.AddComponent<UIDocument>();document.panelSettings=settings;surface=new ViewerCardSurface(document.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator ConcurrencyQueueDeduplicationAndWorkerThreadLimitsAreEnforced()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true,objectCount:4));
            int ui=Thread.CurrentThread.ManagedThreadId,started=0,onUi=0;var release=Signal<bool>();
            var jobs=surface.CreateArtworkJobs(ticket,async(request,token)=>{
                if(Thread.CurrentThread.ManagedThreadId==ui)Interlocked.Increment(ref onUi);
                Interlocked.Increment(ref started);await release.Task.ConfigureAwait(false);return Prepare(request);
            },2,1);
            var first=surface.RequestArtwork(ticket,"fixture-0002");Assert.That(jobs.TryQueue(first),Is.True);yield return Until(()=>Volatile.Read(ref started)==1);
            Assert.That(jobs.TryQueue(first),Is.False);
            Assert.That(jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-extra-1")),Is.True);yield return Until(()=>Volatile.Read(ref started)==2);
            var third=surface.RequestArtwork(ticket,"fixture-extra-2");Assert.That(jobs.TryQueue(third),Is.True);Assert.That(jobs.TryQueue(third),Is.False);
            Assert.That(jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-extra-3")),Is.False);
            Assert.That(jobs.RunningCount,Is.EqualTo(2));Assert.That(jobs.QueuedCount,Is.EqualTo(1));
            release.SetResult(true);yield return Until(()=>ticket.Mailbox.ArtworkCount==3 && jobs.RunningCount==0 && jobs.QueuedCount==0);
            Assert.That(onUi,Is.Zero);Assert.That(started,Is.EqualTo(3));jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator NewRevisionPrunesQueuedJobsAndDiscardsTheOldActiveResult()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true,objectCount:3));
            var started=Signal<bool>();var release=Signal<bool>();var revisions=new ConcurrentQueue<long>();PreparedCardArtwork old=null;
            var jobs=surface.CreateArtworkJobs(ticket,async(request,token)=>{
                revisions.Enqueue(request.Revision);if(request.Revision==1){started.TrySetResult(true);await release.Task.ConfigureAwait(false);old=Prepare(request);return old;}return Prepare(request);
            },1,2);
            jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-0002"));yield return Until(()=>started.Task.IsCompleted);
            jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-extra-1"));jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-extra-2"));
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(revision:2,name:"New state",artwork:true));
            Assert.That(jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-0002")),Is.True);Assert.That(jobs.QueuedCount,Is.EqualTo(1));
            release.SetResult(true);yield return Until(()=>ticket.Mailbox.ArtworkCount==1 && jobs.RunningCount==0);
            Assert.That(old.IsDisposed,Is.True);Assert.That(revisions.ToArray(),Is.EqualTo(new long[]{1,2}));surface.DrainMailbox(ticket);
            Assert.That(surface.CardsRoot.Q<Label>("name").text,Is.EqualTo("New state"));
            jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator ViewerSwitchNeverWaitsForAnIgnoringProviderAndDisposesItsLateResult()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));var started=Signal<bool>();var release=Signal<bool>();PreparedCardArtwork late=null;
            var jobs=surface.CreateArtworkJobs(ticket,async(request,token)=>{started.TrySetResult(true);await release.Task.ConfigureAwait(false);late=Prepare(request);return late;},1);
            jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-0002"));yield return Until(()=>started.Task.IsCompleted);
            var next=surface.BeginViewer("fixture-0001","two",new ViewerArtworkScope());Assert.That(jobs.IsStopped,Is.True);Assert.That(jobs.Completion.IsCompleted,Is.False);
            yield return null;yield return null;surface.TryPresent(next,ViewerCardSurfaceTests.Frame("two",name:"New viewer",artwork:true));
            release.SetResult(true);yield return Until(()=>jobs.Completion.IsCompleted);
            Assert.That(late.IsDisposed,Is.True);Assert.That(ticket.Mailbox.ArtworkCount,Is.Zero);Assert.That(next.Mailbox.ArtworkCount,Is.Zero);
            Assert.That(surface.CardsRoot.Q<Label>("name").text,Is.EqualTo("New viewer"));
        }
        [UnityTest] public IEnumerator ProviderErrorsNullAndMismatchedResultsDoNotEscapePrivateDiagnostics()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true,objectCount:3));
            var first=surface.RequestArtwork(ticket,"fixture-0002");var second=surface.RequestArtwork(ticket,"fixture-extra-1");var third=surface.RequestArtwork(ticket,"fixture-extra-2");
            PreparedCardArtwork mismatched=null;int calls=0;
            var jobs=surface.CreateArtworkJobs(ticket,(request,token)=>{
                Interlocked.Increment(ref calls);
                if(ReferenceEquals(request,first))throw new Exception("Private cache path/card name");
                if(ReferenceEquals(request,second)){mismatched=Prepare(third);return Task.FromResult(mismatched);}
                return Task.FromResult<PreparedCardArtwork>(null);
            },1);
            jobs.TryQueue(first);jobs.TryQueue(second);jobs.TryQueue(third);yield return Until(()=>Volatile.Read(ref calls)==3 && jobs.RunningCount==0 && jobs.QueuedCount==0);
            Assert.That(mismatched.IsDisposed,Is.True);Assert.That(ticket.Mailbox.ArtworkCount,Is.Zero);Assert.That(jobs.LastCode,Is.EqualTo("ARTWORK_JOB_UNAVAILABLE"));
            Assert.Throws<InvalidOperationException>(()=>surface.CreateArtworkJobs(ticket,(r,t)=>Task.FromResult<PreparedCardArtwork>(null)));
            jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);
        }
        [UnityTest] public IEnumerator CancellationCallbacksRunOffTheUIThreadAndCannotBreakCleanup()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true));int ui=Thread.CurrentThread.ManagedThreadId,callbackThread=0;
            var started=Signal<bool>();var cancelled=Signal<PreparedCardArtwork>();
            var jobs=surface.CreateArtworkJobs(ticket,async(request,token)=>{
                using(token.Register(()=>{callbackThread=Thread.CurrentThread.ManagedThreadId;cancelled.TrySetCanceled();throw new Exception("Private callback failure");})) {
                    started.TrySetResult(true);return await cancelled.Task.ConfigureAwait(false);
                }
            });
            jobs.TryQueue(surface.RequestArtwork(ticket,"fixture-0002"));yield return Until(()=>started.Task.IsCompleted);
            surface.ClearViewer(ticket);Assert.That(surface.CardsRoot.childCount,Is.Zero);yield return Until(()=>jobs.Completion.IsCompleted);
            Assert.That(callbackThread,Is.Not.EqualTo(ui));Assert.That(callbackThread,Is.Not.Zero);Assert.That(jobs.LastCode,Does.StartWith("ARTWORK_JOB_"));
            Assert.That(jobs.LastCode,Does.Not.Contain("Private"));Assert.That(jobs.QueuedCount,Is.Zero);Assert.That(jobs.RunningCount,Is.Zero);
        }
        [UnityTest] public IEnumerator FastProvidersAndConcurrentAdmissionsDoNotStrandAcceptedWork()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            surface.TryPresent(ticket,ViewerCardSurfaceTests.Frame(artwork:true,objectCount:64));int calls=0,accepted=0;
            var jobs=surface.CreateArtworkJobs(ticket,(request,token)=>{Interlocked.Increment(ref calls);return Task.FromResult(Prepare(request));},2,128);
            var requests=Enumerable.Range(0,64).Select(i=>surface.RequestArtwork(ticket,i==0?"fixture-0002":"fixture-extra-"+i)).ToArray();
            Task.Run(()=>Parallel.ForEach(requests,request=>{if(jobs.TryQueue(request))Interlocked.Increment(ref accepted);})).GetAwaiter().GetResult();
            Assert.That(accepted,Is.EqualTo(64));yield return Until(()=>Volatile.Read(ref calls)==64 && jobs.RunningCount==0 && jobs.QueuedCount==0);
            jobs.Dispose();yield return Until(()=>jobs.Completion.IsCompleted);Assert.That(jobs.RunningCount,Is.Zero);
        }
    }
}

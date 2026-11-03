using System;
using System.Collections;
using System.Linq;
using System.Threading.Tasks;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerMailboxPumpTests
    {
        private GameObject host;private PanelSettings settings;private ViewerCardSurface surface;
        private static PreparedCardArtwork Prepare(ViewerArtworkRequest request)=>PreparedCardArtwork.Prepare(request,
            new CatalogArtworkFace("oracle","exact-printing","Printed face","normal",1,true,"Artifact Creature"),2,2,new byte[16]);
        [UnitySetUp] public IEnumerator Setup()
        {
            host=new GameObject("Mailbox pump tests");settings=ScriptableObject.CreateInstance<PanelSettings>();settings.themeStyleSheet=Resources.Load<ThemeStyleSheet>("CardTheme");
            var document=host.AddComponent<UIDocument>();document.panelSettings=settings;surface=new ViewerCardSurface(document.rootVisualElement);yield return null;
        }
        [UnityTearDown] public IEnumerator Cleanup(){surface.Dispose();UnityEngine.Object.Destroy(host);UnityEngine.Object.Destroy(settings);yield return null;}
        [UnityTest] public IEnumerator PumpPreservesTheEmptyFrameAndLimitsArtworkWork()
        {
            var scope=new ViewerArtworkScope();var ticket=surface.BeginViewer("fixture-0001","one",scope,maximumArtworkCompletions:1,maximumArtworkBytes:16);
            Task.Run(()=>ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true,objectCount:2))).GetAwaiter().GetResult();
            Assert.That(surface.DrainMailbox(ticket),Is.Zero);Assert.That(ticket.Mailbox.HasPendingFrame,Is.True);
            yield return null;Assert.That(surface.DrainMailbox(ticket),Is.Zero);Assert.That(surface.CardsRoot.childCount,Is.Zero);
            yield return null;Assert.That(surface.DrainMailbox(ticket),Is.EqualTo(1));Assert.That(ticket.Mailbox.HasPendingFrame,Is.False);
            var request=surface.RequestArtwork(ticket,"fixture-0002");var first=Prepare(request);
            Assert.That(ticket.Mailbox.TryPostArtwork(first),Is.True);Assert.That(ticket.Mailbox.TryPostArtwork(first),Is.False);Assert.That(first.IsDisposed,Is.False);
            var duplicate=Prepare(request);Assert.That(ticket.Mailbox.TryPostArtwork(duplicate),Is.False);Assert.That(duplicate.IsDisposed,Is.True);
            var secondRequest=surface.RequestArtwork(ticket,"fixture-extra-1");var overflow=Prepare(secondRequest);
            Assert.That(ticket.Mailbox.TryPostArtwork(overflow),Is.False);Assert.That(overflow.IsDisposed,Is.True);
            Assert.That(ticket.Mailbox.ArtworkBytes,Is.EqualTo(16));Assert.That(surface.DrainMailbox(ticket,0),Is.Zero);Assert.That(scope.Count,Is.Zero);
            Assert.That(surface.DrainMailbox(ticket,1),Is.EqualTo(1));Assert.That(first.IsDisposed,Is.True);
            Assert.That(ticket.Mailbox.TryPostArtwork(Prepare(secondRequest)),Is.True);Assert.That(surface.DrainMailbox(ticket,1),Is.EqualTo(1));
            var views=surface.CardsRoot.Query<CardView>().ToList();Assert.That(views[0].Artwork,Is.SameAs(views[1].Artwork));
            Assert.That(scope.Count,Is.EqualTo(1));Assert.That(ticket.Mailbox.ArtworkBytes,Is.Zero);
        }
        [UnityTest] public IEnumerator NewSnapshotsWatermarksAndShutdownClearQueuedAndLatePixels()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope());yield return null;yield return null;yield return null;
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true));surface.DrainMailbox(ticket);
            var oldRequest=surface.RequestArtwork(ticket,"fixture-0002");var old=Prepare(oldRequest);ticket.Mailbox.TryPostArtwork(old);
            Task.Run(()=>ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(revision:2,name:"Newest",artwork:true))).GetAwaiter().GetResult();
            Assert.That(old.IsDisposed,Is.True);Assert.That(surface.RequestArtwork(ticket,"fixture-0002"),Is.Null);
            var late=Prepare(oldRequest);Assert.That(ticket.Mailbox.TryPostArtwork(late),Is.False);Assert.That(late.IsDisposed,Is.True);
            surface.DrainMailbox(ticket);Assert.That(surface.CardsRoot.Q<Label>("name").text,Is.EqualTo("Newest"));
            var second=Prepare(surface.RequestArtwork(ticket,"fixture-0002"));ticket.Mailbox.TryPostArtwork(second);
            Task.Run(()=>ticket.Mailbox.AdvanceMinimumRevision(3)).GetAwaiter().GetResult();Assert.That(second.IsDisposed,Is.True);
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(revision:3,artwork:true));surface.DrainMailbox(ticket);
            var final=Prepare(surface.RequestArtwork(ticket,"fixture-0002"));ticket.Mailbox.TryPostArtwork(final);
            Task.Run(()=>ticket.Mailbox.Dispose()).GetAwaiter().GetResult();Assert.That(final.IsDisposed,Is.True);
            Assert.That(surface.Inspect(ticket,"fixture-0002"),Is.False);Assert.That(surface.DrainMailbox(ticket),Is.Zero);Assert.That(surface.CardsRoot.childCount,Is.Zero);
            Assert.That(ticket.Mailbox.HasPendingFrame,Is.False);Assert.That(ticket.Mailbox.ArtworkCount,Is.Zero);
        }
        [UnityTest] public IEnumerator ConcurrentCompletionsStayBoundedAndDisposalReleasesEveryOwnedBuffer()
        {
            var ticket=surface.BeginViewer("fixture-0001","one",new ViewerArtworkScope(),maximumArtworkCompletions:2,maximumArtworkBytes:32);
            yield return null;yield return null;yield return null;
            ticket.Mailbox.TryPostFrame(ViewerCardSurfaceTests.Frame(artwork:true,objectCount:4));surface.DrainMailbox(ticket);
            var ids=new[]{"fixture-0002","fixture-extra-1","fixture-extra-2","fixture-extra-3"};
            var requests=ids.Select(id=>surface.RequestArtwork(ticket,id)).ToArray();
            var completions=Enumerable.Range(0,16).Select(i=>Prepare(requests[i%4])).ToArray();
            Task.Run(()=>Parallel.ForEach(completions,item=>ticket.Mailbox.TryPostArtwork(item))).GetAwaiter().GetResult();
            Assert.That(ticket.Mailbox.ArtworkCount,Is.EqualTo(2));Assert.That(ticket.Mailbox.ArtworkBytes,Is.EqualTo(32));
            ticket.Mailbox.Dispose();Assert.That(completions.All(item=>item.IsDisposed),Is.True);surface.DrainMailbox(ticket);
            Assert.That(surface.CardsRoot.childCount,Is.Zero);Assert.That(ticket.Mailbox.ArtworkBytes,Is.Zero);
        }
    }
}

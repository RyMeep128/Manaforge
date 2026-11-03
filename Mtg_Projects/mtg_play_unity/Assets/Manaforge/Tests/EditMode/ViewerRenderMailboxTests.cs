using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerRenderMailboxTests
    {
        private ViewerCardSurface surface;private ViewerSurfaceTicket ticket;
        private static ProjectedCardFrame Frame(long revision,string viewer="one",string session="fixture-0001")
        {
            var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
            var message=corpus["positive"][0]["envelope"];var snapshot=message["body"]["snapshot"];
            snapshot["session_id"]=session;snapshot["viewer_id"]=viewer;snapshot["revision"]=revision;snapshot["decision"]=JValue.CreateNull();
            return ViewerCardProjection.ParseSnapshot(message.ToString(),session,viewer,0,true);
        }
        [SetUp] public void Setup(){surface=new ViewerCardSurface(new VisualElement());ticket=surface.BeginViewer("fixture-0001","one");}
        [TearDown] public void Cleanup(){surface.Dispose();}
        [Test] public void NewestCompleteFrameReplacesOlderFramesWithoutExposingPartialData()
        {
            var first=Frame(1);var latest=Frame(3);
            Assert.That(ticket.Mailbox.TryPostFrame(first),Is.True);Assert.That(ticket.Mailbox.TryPostFrame(latest),Is.True);
            Assert.That(ticket.Mailbox.TryPostFrame(Frame(2)),Is.False);Assert.That(ticket.Mailbox.TryPeekFrame(out var frame),Is.True);
            Assert.That(frame,Is.SameAs(latest));Assert.That(frame.Cards[0].Context,Is.SameAs(frame.Context));
            Assert.That(ticket.Mailbox.TryPeekFrame(out var again),Is.True);Assert.That(again,Is.SameAs(latest),"Peek does not lose a frame while the UI barrier is closed");
        }
        [Test] public void OtherScopesAndDuplicateRevisionsCannotReplaceTheLatestFrame()
        {
            var frame=Frame(5);ticket.Mailbox.TryPostFrame(frame);
            Assert.That(ticket.Mailbox.TryPostFrame(Frame(6,"two")),Is.False);
            Assert.That(ticket.Mailbox.TryPostFrame(Frame(6,session:"other")),Is.False);
            Assert.That(ticket.Mailbox.TryPostFrame(Frame(5)),Is.False);
            ticket.Mailbox.TryPeekFrame(out var current);Assert.That(current,Is.SameAs(frame));
        }
        [Test] public void WatermarksDropObsoleteFramesAndCannotMoveBackward()
        {
            ticket.Mailbox.TryPostFrame(Frame(1));Assert.That(ticket.Mailbox.AdvanceMinimumRevision(3),Is.True);
            Assert.That(ticket.Mailbox.HasPendingFrame,Is.False);Assert.That(ticket.Mailbox.TryPostFrame(Frame(2)),Is.False);
            Assert.That(ticket.Mailbox.AdvanceMinimumRevision(2),Is.False);Assert.That(ticket.Mailbox.MinimumRevision,Is.EqualTo(3));
            Assert.That(ticket.Mailbox.TryPostFrame(Frame(3)),Is.True);
        }
        [Test] public void ConcurrentWorkersLeaveOnlyTheHighestRevision()
        {
            var frames=Enumerable.Range(1,64).Select(i=>Frame(i)).ToArray();
            Task.Run(()=>Parallel.ForEach(frames,frame=>ticket.Mailbox.TryPostFrame(frame))).GetAwaiter().GetResult();
            Assert.That(ticket.Mailbox.TryPeekFrame(out var latest),Is.True);Assert.That(latest.Context.Revision,Is.EqualTo(64));
            Assert.That(ticket.Mailbox.ArtworkCount,Is.Zero);Assert.That(ticket.Mailbox.ArtworkBytes,Is.Zero);
        }
        [Test] public void SwitchingEvenToTheSameViewerRetiresTheOldMailbox()
        {
            var old=ticket.Mailbox;old.TryPostFrame(Frame(1));var next=surface.BeginViewer("fixture-0001","one");
            Assert.That(old.IsStopped,Is.True);Assert.That(old.HasPendingFrame,Is.False);Assert.That(old.TryPostFrame(Frame(2)),Is.False);
            Assert.That(next.Mailbox,Is.Not.SameAs(old));Assert.That(next.Mailbox.TryPostFrame(Frame(2)),Is.True);
        }
        [Test] public void InvalidLimitsFailBeforeRetiringTheActiveViewer()
        {
            Assert.Throws<ArgumentException>(()=>surface.BeginViewer("fixture-0001","two",maximumArtworkCompletions:0));
            Assert.Throws<ArgumentException>(()=>surface.BeginViewer("fixture-0001","two",maximumArtworkBytes:0));
            Assert.That(ticket.Mailbox.IsStopped,Is.False);Assert.That(ticket.Mailbox.TryPostFrame(Frame(1)),Is.True);
        }
    }
}

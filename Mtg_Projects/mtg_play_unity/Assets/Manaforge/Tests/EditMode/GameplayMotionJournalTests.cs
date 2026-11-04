using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class GameplayMotionJournalTests
    {
        private static JObject Source(long revision=1)
        {
            var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
            var snapshot=wire["body"]["snapshot"];snapshot["revision"]=revision;snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";
            snapshot["turn"]=1;snapshot["active_player_id"]="one";
            var card=snapshot["objects"][0];card["zone"]="battlefield";card["face_down"]=false;card["tapped"]=false;card["damage"]=0;
            snapshot["players"][0]["life"]=20;snapshot["players"][0]["library_count"]=50;snapshot["players"][0]["hand_count"]=5;
            return wire;
        }
        private static ProjectedCardFrame Cards(JObject wire)=>ViewerCardProjection.ParseSnapshot(wire.ToString(),"fixture-0001","one",0,true);
        private static ProjectedDecisionFrame Decision(JObject wire)=>ViewerDecisionProjection.ParseSnapshot(wire.ToString(),"fixture-0001","one",0,true);
        private static void Observe(ViewerAnimationJournal journal,JObject wire)=>journal.Observe(Cards(wire),Decision(wire));
        [Test] public void CoalescingKeepsIntermediateCastsAndDamageWithoutReplayingInitialState()
        {
            var wire=Source();wire["body"]["snapshot"]["objects"][0]["zone"]="hand";
            var surface=new ViewerCardSurface(new UnityEngine.UIElements.VisualElement());var ticket=surface.BeginViewer("fixture-0001","one");
            try{
                Assert.That(ticket.Mailbox.TryPostFrame(Cards(wire),Decision(wire)),Is.True);
                wire["body"]["snapshot"]["revision"]=2;wire["body"]["snapshot"]["objects"][0]["zone"]="stack";
                Assert.That(ticket.Mailbox.TryPostFrame(Cards(wire),Decision(wire)),Is.True);
                wire["body"]["snapshot"]["revision"]=3;wire["body"]["snapshot"]["objects"][0]["zone"]="battlefield";
                Assert.That(ticket.Mailbox.TryPostFrame(Cards(wire),Decision(wire)),Is.True);
                var cues=ticket.Mailbox.TakeAnimations(3).SelectMany(batch=>batch.Cues).ToArray();
                Assert.That(cues.Select(cue=>cue.Kind),Is.EqualTo(new[]{GameplayMotionKind.Cast,GameplayMotionKind.Arrive}));
                Assert.That(ticket.Mailbox.TryPeekFrame(out var latest),Is.True);Assert.That(latest.Context.Revision,Is.EqualTo(3));
                Assert.That(ticket.Mailbox.TryPostFrame(Cards(wire),Decision(wire)),Is.False);
                Assert.That(ticket.Mailbox.TakeAnimations(3),Is.Empty);
            }finally{surface.Dispose();}
        }
        [Test] public void StatDamageTapAndLifeCuesAreIndependentAndDuplicatesAreIgnored()
        {
            var wire=Source();var journal=new ViewerAnimationJournal();Observe(journal,wire);Assert.That(journal.Count,Is.Zero);
            var snapshot=wire["body"]["snapshot"];snapshot["revision"]=2;
            var card=snapshot["objects"][0];card["damage"]=1;card["tapped"]=true;card["characteristics"]["power"]="3";snapshot["players"][0]["life"]=18;
            Observe(journal,wire);Observe(journal,wire);
            var cues=journal.TakeThrough(2).SelectMany(batch=>batch.Cues).ToArray();
            Assert.That(cues.Count(cue=>cue.Kind==GameplayMotionKind.Damage),Is.EqualTo(2));
            Assert.That(cues.Count(cue=>cue.Kind==GameplayMotionKind.Tap),Is.EqualTo(1));Assert.That(cues.Count(cue=>cue.Kind==GameplayMotionKind.Boost),Is.EqualTo(1));
            snapshot["revision"]=3;card["damage"]=0;Observe(journal,wire);Assert.That(journal.TakeThrough(3),Is.Empty,"Damage cleanup does not invent healing or a second impact");
        }
        [Test] public void DrawsUseCountsAndConcealedCardsNeverGenerateIdentityEffects()
        {
            var wire=Source();var journal=new ViewerAnimationJournal();Observe(journal,wire);
            var snapshot=wire["body"]["snapshot"];snapshot["revision"]=2;var card=snapshot["objects"][0];
            card["hidden"]=true;card["characteristics"]=null;card["card_identity"]=null;
            snapshot["players"][1]["library_count"]=51;snapshot["players"][1]["hand_count"]=9;Observe(journal,wire);
            var cues=journal.TakeThrough(2).SelectMany(batch=>batch.Cues).ToArray();
            Assert.That(cues.Length,Is.EqualTo(2));Assert.That(cues.All(cue=>cue.Kind==GameplayMotionKind.Draw && cue.ObjectId==null && cue.OwnerId=="two"),Is.True);
        }
        [Test] public void CombatEffectsUseOnlyNewConfirmedAssignments()
        {
            var wire=Source();var snapshot=wire["body"]["snapshot"];var blocker=snapshot["objects"][0].DeepClone();blocker["object_id"]="fixture-blocker";((JArray)snapshot["objects"]).Add(blocker);
            var journal=new ViewerAnimationJournal();Observe(journal,wire);snapshot["revision"]=2;
            snapshot["combat"]=new JArray(new JObject{["attackers"]=new JArray("fixture-0002"),["blockers"]=new JArray("fixture-blocker"),["defender_id"]="two",["blocked"]=true});
            Observe(journal,wire);var cues=journal.TakeThrough(2).Single().Cues;
            Assert.That(cues.Single(cue=>cue.Kind==GameplayMotionKind.Attack).RelatedId,Is.EqualTo("two"));
            Assert.That(cues.Single(cue=>cue.Kind==GameplayMotionKind.Block).RelatedId,Is.EqualTo("fixture-0002"));
            snapshot["revision"]=3;Observe(journal,wire);Assert.That(journal.TakeThrough(3),Is.Empty);
        }
        [Test] public void UnknownStackDepartureDoesNotInventAResolutionOrTarget()
        {
            var wire=Source();var snapshot=wire["body"]["snapshot"];snapshot["objects"][0]["zone"]="stack";
            var journal=new ViewerAnimationJournal();Observe(journal,wire);snapshot["revision"]=2;snapshot["objects"]=new JArray();Observe(journal,wire);
            var cue=journal.TakeThrough(2).Single().Cues.Single();Assert.That(cue.Kind,Is.EqualTo(GameplayMotionKind.StackChange));
            Assert.That(cue.ObjectId,Is.Null);Assert.That(cue.RelatedId,Is.Null);Assert.That(cue.ToZone,Is.Null);
        }
        [Test] public void OverflowStaysBoundedAndCompletionReplacesPendingEffects()
        {
            var wire=Source();var journal=new ViewerAnimationJournal();Observe(journal,wire);
            for(int i=2;i<=70;i++){
                wire["body"]["snapshot"]["revision"]=i;wire["body"]["snapshot"]["objects"][0]["tapped"]=i%2==0;Observe(journal,wire);
                Assert.That(journal.Count,Is.LessThanOrEqualTo(ViewerAnimationJournal.MaximumBatches));
            }
            wire["body"]["snapshot"]["revision"]=71;wire["body"]["snapshot"]["status"]="finished";wire["body"]["snapshot"]["result"]="win";Observe(journal,wire);
            Assert.That(journal.TakeThrough(71).Single().Cues.Single().Kind,Is.EqualTo(GameplayMotionKind.Result));
            journal.Clear();Assert.That(journal.Count,Is.Zero);
        }
        [Test] public void ExtraTurnGetsANewTurnBannerAndReplayDoesNot()
        {
            var wire=Source();var journal=new ViewerAnimationJournal();Observe(journal,wire);
            wire["body"]["snapshot"]["revision"]=2;wire["body"]["snapshot"]["turn"]=2;Observe(journal,wire);
            Assert.That(journal.TakeThrough(2).Single().Cues.Single().Text,Is.EqualTo("Your turn"));
            wire["body"]["snapshot"]["revision"]=1;Observe(journal,wire);Assert.That(journal.Count,Is.Zero);
        }
    }
}

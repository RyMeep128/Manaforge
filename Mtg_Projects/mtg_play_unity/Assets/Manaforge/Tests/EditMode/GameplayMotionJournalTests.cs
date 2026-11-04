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
        [Test] public void RevealGroupsSurviveSnapshotsAndRequireOrderedAcknowledgement()
        {
            var wire=Source();var snapshot=wire["body"]["snapshot"];
            Func<string,string,JObject> observation=(id,group)=>new JObject{
                ["observation_id"]=id,["group_id"]=group,["group_label"]="Revealed cards",["source"]="revealed",
                ["hidden"]=false,["name"]="Forest",["oracle_id"]=null,["printing_id"]=null,
                ["set_code"]=null,["collector_number"]=null};
            snapshot["observations"]=new JArray(observation("a","first"),observation("b","first"));
            var queue=new ViewerRevealQueue();queue.Observe(Cards(wire));
            Assert.That(queue.Current.Cards.Count,Is.EqualTo(2));var authorized=queue.Current.Cards[0];
            queue.Observe(Cards(wire));Assert.That(queue.Authorizes(authorized),Is.True);
            ((JArray)snapshot["observations"]).Add(observation("c","second"));queue.Observe(Cards(wire));
            Assert.That(queue.Acknowledge("second"),Is.False);Assert.That(queue.Acknowledge("first"),Is.True);
            Assert.That(queue.Authorizes(authorized),Is.False);Assert.That(queue.Current.Id,Is.EqualTo("second"));
            Assert.That(queue.Acknowledge("second"),Is.True);queue.Observe(Cards(wire));Assert.That(queue.Pending,Is.False);
            ((JArray)snapshot["observations"]).Add(observation("d","third"));queue.Observe(Cards(wire));
            Assert.That(queue.Current.Cards.Single().Id,Is.EqualTo("d"));snapshot["session_id"]="another-session";queue.Observe(new ProjectedCardFrame(snapshot));
            Assert.That(queue.Current.Id,Is.EqualTo("first"));Assert.That(queue.Current.Cards.Count,Is.EqualTo(2));snapshot["status"]="complete";queue.Observe(new ProjectedCardFrame(snapshot));Assert.That(queue.Pending,Is.False);
            queue.Clear();Assert.That(queue.Pending,Is.False);
        }
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
        [Test] public void RotatingCommandReferencesDoNotReplayArrivalsTappingOrCombat()
        {
            var wire=Source();var snapshot=wire["body"]["snapshot"];var card=snapshot["objects"][0];card["presentation_id"]="visual-one";
            var journal=new ViewerAnimationJournal();Observe(journal,wire);
            for(int i=2;i<=4;i++){snapshot["revision"]=i;card["object_id"]="route-"+i;Observe(journal,wire);Assert.That(journal.TakeThrough(i),Is.Empty);}
            snapshot["revision"]=5;var arrival=card.DeepClone();arrival["object_id"]="route-new";arrival["presentation_id"]="visual-two";((JArray)snapshot["objects"]).Add(arrival);Observe(journal,wire);
            var cue=journal.TakeThrough(5).Single().Cues.Single();Assert.That(cue.Kind,Is.EqualTo(GameplayMotionKind.Arrive));Assert.That(cue.SubjectId,Is.EqualTo("visual-two"));
            snapshot["revision"]=6;card["object_id"]="route-6";arrival["object_id"]="route-next";card["tapped"]=true;
            snapshot["combat"]=new JArray(new JObject{["attackers"]=new JArray("route-6"),["blockers"]=new JArray("route-next"),["defender_id"]="two",["blocked"]=true});
            Observe(journal,wire);var effects=journal.TakeThrough(6).Single().Cues;Assert.That(effects.Count,Is.EqualTo(3));
            Assert.That(effects.Single(c=>c.Kind==GameplayMotionKind.Attack).SubjectId,Is.EqualTo("visual-one"));
            Assert.That(effects.Single(c=>c.Kind==GameplayMotionKind.Block).RelatedId,Is.EqualTo("visual-one"));
            snapshot["revision"]=7;card["object_id"]="route-7";arrival["object_id"]="route-last";
            snapshot["combat"][0]["attackers"]=new JArray("route-7");snapshot["combat"][0]["blockers"]=new JArray("route-last");
            Observe(journal,wire);Assert.That(journal.TakeThrough(7),Is.Empty);
        }
        [Test] public void PresentationIdentityAliasesAndConcealedTokensAreRejected()
        {
            var wire=Source();var card=wire["body"]["snapshot"]["objects"][0];card["presentation_id"]="same";
            var copy=card.DeepClone();copy["object_id"]="other-route";((JArray)wire["body"]["snapshot"]["objects"]).Add(copy);
            Assert.Throws<Manaforge.Play.Protocol.WireEnvelope.EnvelopeException>(()=>Cards(wire));
            wire["body"]["snapshot"]["objects"]=new JArray(card.DeepClone());card=wire["body"]["snapshot"]["objects"][0];
            card["hidden"]=true;card["characteristics"]=null;card["card_identity"]=null;
            Assert.Throws<Manaforge.Play.Protocol.WireEnvelope.EnvelopeException>(()=>Cards(wire));
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
            Assert.That(cues.Length,Is.EqualTo(2));Assert.That(cues.All(cue=>cue.Kind==GameplayMotionKind.Draw && cue.SubjectId==null && cue.OwnerId=="two"),Is.True);
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
            Assert.That(cue.SubjectId,Is.Null);Assert.That(cue.RelatedId,Is.Null);Assert.That(cue.ToZone,Is.Null);
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

using System;
using System.IO;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class UnityPriorityPolicyTests
    {
        private static string Fixtures=>Environment.GetEnvironmentVariable("MANAFORGE_TEST_FIXTURES")
            ??Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures");
        private static JObject Source(string viewer="one",long revision=1,string decision="fixture-priority")
        {
            var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Fixtures,"receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();
            var snapshot=wire["body"]["snapshot"];
            snapshot["viewer_id"]=viewer;snapshot["revision"]=revision;snapshot["turn"]=1;
            snapshot["active_player_id"]="one";snapshot["priority_player_id"]=viewer;
            snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";snapshot["actions_complete"]=true;
            snapshot["objects"]=new JArray();snapshot["unsupported_fields"]=new JArray();
            snapshot["decision"]["decision_id"]=decision;snapshot["decision"]["player_id"]=viewer;
            snapshot["decision"]["family"]="selection";snapshot["decision"]["is_priority"]=true;
            snapshot["actions"]=new JArray(new JObject{["action_id"]="fixture-pass",["kind"]="pass",["object_id"]=null,["label"]="Pass priority",["priority_class"]="unknown"});
            return wire;
        }
        private static ProjectedDecisionFrame Frame(JObject wire)=>ViewerDecisionProjection.ParseSnapshot(wire.ToString(),
            (string)wire["body"]["snapshot"]["session_id"],(string)wire["body"]["snapshot"]["viewer_id"],0,true);
        private static void Response(JObject wire)
        {
            ((JArray)wire["body"]["snapshot"]["actions"]).Add(new JObject{["action_id"]="fixture-response",["kind"]="fixture-only",["object_id"]=null,["label"]="Response",["priority_class"]="meaningful"});
        }
        private static void Stack(JObject wire,params string[] ids)
        {
            var sample=JObject.Parse(File.ReadAllText(Path.Combine(Fixtures,"wire-receive-v1.json")))["positive"][0]["envelope"]["body"]["snapshot"]["objects"][0];
            var objects=new JArray();foreach(string id in ids){var card=sample.DeepClone();card["object_id"]=id;card["zone"]="stack";objects.Add(card);}
            wire["body"]["snapshot"]["objects"]=objects;
        }
        [Test] public void YieldPresentationRemainsCompactAcrossOffersAndPendingClaims()
        {
            var policy=new UnityPriorityPolicy();var frame=Frame(Source());policy.BeginYield("end-turn",frame);
            Assert.That(YieldPresentation.Resolve(policy.Current,frame).Compact,Is.True);policy.Claim(frame);
            Assert.That(YieldPresentation.Resolve(policy.Current,frame).Text,Is.EqualTo("Ending your turn..."));
            Assert.That(YieldPresentation.Resolve(policy.Current,null).Compact,Is.True);
            var next=Frame(Source(revision:2,decision:"next"));policy.Observe(next);
            Assert.That(YieldPresentation.Resolve(policy.Current,next).Compact,Is.True);
            policy.SetStop("step","PRECOMBAT_MAIN",true);Assert.That(YieldPresentation.Resolve(policy.Current,next).Mode,Is.EqualTo(YieldPresentationMode.Stopped));
            policy.SetStop("step","PRECOMBAT_MAIN",false);
            var wire=Source();wire["body"]["snapshot"]["decision"]["is_priority"]=false;
            Assert.That(YieldPresentation.Resolve(policy.Current,Frame(wire)).Mode,Is.EqualTo(YieldPresentationMode.RequiredInput));
            Assert.That(policy.Current.Yield,Is.EqualTo("end-turn"));
            policy.Failed();Assert.That(YieldPresentation.Resolve(policy.Current,next).Mode,Is.EqualTo(YieldPresentationMode.Failed));
            Assert.That(YieldPresentation.Resolve(policy.Current,next,completed:true).Compact,Is.False);
        }
        [Test] public void PassiveYieldViewRetainsItsChildrenAndUsesSuppliedCancelAction()
        {
            var policy=new UnityPriorityPolicy();var frame=Frame(Source());policy.BeginYield("turn",frame);
            var parent=new UnityEngine.UIElements.VisualElement();using(var view=new YieldStatusView(parent,policy.CancelYield)){
                var label=view.Root[0];var button=view.Root[1];
                for(int i=0;i<20;i++)view.Bind(YieldPresentation.Resolve(policy.Current,frame));
                Assert.That(view.Root[0],Is.SameAs(label));Assert.That(view.Root[1],Is.SameAs(button));
                Assert.That(((UnityEngine.UIElements.Label)label).text,Is.EqualTo("Passing to your turn..."));
                policy.CancelYield();view.Bind(YieldPresentation.Resolve(policy.Current,frame));
                Assert.That(view.Root.style.display.value,Is.EqualTo(UnityEngine.UIElements.DisplayStyle.None));
            }
        }
        [Test] public void DefaultIsAutomaticWithNoStopsOrYield()
        {
            var policy=new UnityPriorityPolicy();Assert.That(policy.Evaluate(Frame(Source())),Is.Not.Null);
            Assert.That(policy.Current.Automatic,Is.True);Assert.That(policy.Current.Manual,Is.False);
            Assert.That(policy.Current.Stops,Is.Empty);Assert.That(policy.Current.Yield,Is.Null);
        }
        [Test] public void EmptyRenderedListDoesNotProveNoResponses()
        {
            var wire=Source();wire["body"]["snapshot"]["actions_complete"]=false;
            var frame=Frame(wire);Assert.That(UnityPriorityPolicy.Responses(frame),Is.EqualTo(PriorityResponse.Unknown));
            Assert.That(new UnityPriorityPolicy().Evaluate(frame),Is.Null);
        }
        [TestCase("UNTAP")][TestCase("UPKEEP")][TestCase("DRAW")]
        public void BeginningSkipsResponsesButStopsAtMainAndHonorsManualControl(string step)
        {
            var wire=Source();Response(wire);var snapshot=wire["body"]["snapshot"];snapshot["phase"]="BEGINNING";snapshot["step"]=step;
            var policy=new UnityPriorityPolicy();Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            policy.Current.Manual=true;Assert.That(policy.Evaluate(Frame(wire)),Is.Null);policy.Current.Manual=false;
            policy.SetStop("phase","BEGINNING",true);Assert.That(policy.Evaluate(Frame(wire)),Is.Null);policy.SetStop("phase","BEGINNING",false);
            snapshot["decision"]["is_priority"]=false;Assert.That(policy.Evaluate(Frame(wire)),Is.Null);snapshot["decision"]["is_priority"]=true;
            snapshot["phase"]="PRECOMBAT_MAIN";snapshot["step"]="PRECOMBAT_MAIN";Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void AfterCastingManaOnlyPriorityPassesOnceAndFreshOffersRemainAutomatic()
        {
            var wire=Source();Stack(wire,"cast-spell");
            ((JArray)wire["body"]["snapshot"]["actions"]).Add(new JObject{["action_id"]="unused-land",["kind"]="activate",["object_id"]=null,["label"]="Activate",["priority_class"]="basic_mana"});
            var policy=new UnityPriorityPolicy();var frame=Frame(wire);
            Assert.That(UnityPriorityPolicy.Responses(frame),Is.EqualTo(PriorityResponse.No));
            Assert.That(policy.Claim(frame),Is.True);Assert.That(policy.Claim(frame),Is.False);
            wire["body"]["snapshot"]["revision"]=2;wire["body"]["snapshot"]["decision"]["decision_id"]="fresh-priority";
            Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            policy.Current.Manual=true;Assert.That(policy.Evaluate(Frame(wire)),Is.Null);policy.Current.Manual=false;
            policy.SetStop("step","PRECOMBAT_MAIN",true);Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
        }
        [TestCase("activate","unknown")][TestCase("activate","meaningful")][TestCase("cast_spell","basic_mana")]
        public void OnlyExplicitEngineManaActivationsCanBeIgnored(string kind,string classification)
        {
            var wire=Source();Stack(wire,"cast-spell");
            ((JArray)wire["body"]["snapshot"]["actions"]).Add(new JObject{["action_id"]="response",["kind"]=kind,["object_id"]=null,["label"]="Response",["priority_class"]=classification});
            Assert.That(new UnityPriorityPolicy().Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void ManaOnlyActionsStillRequireCompleteInformationAndNoChoices()
        {
            var wire=Source();((JArray)wire["body"]["snapshot"]["actions"]).Add(new JObject{["action_id"]="mana",["kind"]="activate",["object_id"]=null,["label"]="Mana",["priority_class"]="basic_mana"});
            wire["body"]["snapshot"]["actions_complete"]=false;Assert.That(new UnityPriorityPolicy().Evaluate(Frame(wire)),Is.Null);
            wire["body"]["snapshot"]["actions_complete"]=true;
            wire["body"]["snapshot"]["decision"]["options"]=new JArray(new JObject{["option_id"]="choice",["label"]="Response",["object_id"]=null,["player_id"]=null,["selected"]=false});
            Assert.That(new UnityPriorityPolicy().Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void AvailableResponsesHoldPriority()
        {
            var wire=Source();Response(wire);var frame=Frame(wire);
            Assert.That(UnityPriorityPolicy.Responses(frame),Is.EqualTo(PriorityResponse.Yes));
            Assert.That(new UnityPriorityPolicy().Evaluate(frame),Is.Null);
        }
        [TestCase("mana")][TestCase("target")][TestCase("boolean")][TestCase("ability")][TestCase("number")][TestCase("amounts")]
        public void ExplicitYieldNeverAnswersOtherDecisionFamilies(string family)
        {
            var policy=new UnityPriorityPolicy();policy.BeginYield("turn",Frame(Source()));
            var wire=Source();wire["body"]["snapshot"]["decision"]["family"]=family;
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void CombatFinishWithPassActionIsNotPriority()
        {
            var wire=Source();wire["body"]["snapshot"]["decision"]["is_priority"]=false;
            var policy=new UnityPriorityPolicy();policy.BeginYield("stack",Frame(Source()));
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void ExplicitYieldCanSkipResponsesAndCancelRestoresPrompt()
        {
            var wire=Source();Response(wire);var frame=Frame(wire);var policy=new UnityPriorityPolicy();
            policy.BeginYield("turn",frame);Assert.That(policy.Evaluate(frame),Is.Not.Null);
            policy.CancelYield();Assert.That(policy.Evaluate(frame),Is.Null);
        }
        [Test] public void ManualControlOverridesBothAutomaticModes()
        {
            var frame=Frame(Source());var policy=new UnityPriorityPolicy();policy.BeginYield("turn",frame);
            policy.Current.Manual=true;Assert.That(policy.Evaluate(frame),Is.Null);
            policy.CancelYield();policy.Current.Manual=false;Assert.That(policy.Evaluate(frame),Is.Not.Null);
        }
        [TestCase("phase","BEGINNING")][TestCase("step","UPKEEP")]
        public void StopsOverrideAutomaticAndExplicitYield(string kind,string value)
        {
            var wire=Source();wire["body"]["snapshot"]["phase"]="BEGINNING";wire["body"]["snapshot"]["step"]="UPKEEP";
            var frame=Frame(wire);var policy=new UnityPriorityPolicy();policy.Observe(frame);
            Assert.That(policy.SetStop(kind,value,true),Is.True);Assert.That(policy.Evaluate(frame),Is.Null);
            policy.BeginYield("turn",frame);Assert.That(policy.Evaluate(frame),Is.Null);
            policy.SetStop(kind,value,false);Assert.That(policy.Evaluate(frame),Is.Not.Null);
        }
        [TestCase("two")][TestCase("one")]
        public void EndTurnYieldExpiresOnNextTurnIncludingExtraTurns(string nextPlayer)
        {
            var wire=Source();Response(wire);var policy=new UnityPriorityPolicy();
            policy.BeginYield("end-turn",Frame(wire));Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            wire["body"]["snapshot"]["turn"]=2;wire["body"]["snapshot"]["active_player_id"]=nextPlayer;
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.Null);
        }
        [Test] public void EndTurnYieldSurvivesRequiredChoicesAndRespectsStops()
        {
            var wire=Source();Response(wire);var policy=new UnityPriorityPolicy();policy.BeginYield("end-turn",Frame(wire));
            wire["body"]["snapshot"]["decision"]["is_priority"]=false;
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.EqualTo("end-turn"));
            wire["body"]["snapshot"]["decision"]["is_priority"]=true;
            policy.SetStop("step","PRECOMBAT_MAIN",true);Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
            policy.SetStop("step","PRECOMBAT_MAIN",false);Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            policy.Failed();Assert.That(policy.Current.Yield,Is.Null);Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void NextTurnYieldExpiresAtTheViewersNextTurn()
        {
            var wire=Source();Response(wire);var policy=new UnityPriorityPolicy();policy.BeginYield("turn",Frame(wire));
            wire["body"]["snapshot"]["turn"]=2;wire["body"]["snapshot"]["active_player_id"]="two";
            Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            wire["body"]["snapshot"]["turn"]=3;wire["body"]["snapshot"]["active_player_id"]="one";
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.Null);
        }
        [TestCase("add")][TestCase("remove")][TestCase("reorder")]
        public void StackYieldExpiresOnMembershipOrOrderChange(string change)
        {
            var wire=Source();Response(wire);Stack(wire,"fixture-stack-a","fixture-stack-b");
            var policy=new UnityPriorityPolicy();policy.BeginYield("stack",Frame(wire));
            Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            Stack(wire,change=="add"?new[]{"fixture-stack-a","fixture-stack-b","fixture-stack-c"}
                :change=="remove"?new[]{"fixture-stack-a"}:new[]{"fixture-stack-b","fixture-stack-a"});
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.Null);
        }
        [Test] public void ClaimPreventsDuplicateOrRetriedAutomaticSubmission()
        {
            var frame=Frame(Source());var policy=new UnityPriorityPolicy();
            Assert.That(policy.Claim(frame),Is.True);Assert.That(policy.Claim(frame),Is.False);Assert.That(policy.Evaluate(frame),Is.Null);
            policy.Failed();policy.Resume();Assert.That(policy.Claim(frame),Is.False);
        }
        [Test] public void StaleSnapshotCannotSubmit()
        {
            var policy=new UnityPriorityPolicy();policy.Observe(Frame(Source(revision:2)));
            Assert.That(policy.Claim(Frame(Source(revision:1))),Is.False);
        }
        [Test] public void SeatSwitchCancelsYieldAndKeepsSettingsIsolated()
        {
            var policy=new UnityPriorityPolicy();var one=Frame(Source());policy.BeginYield("turn",one);policy.Current.Automatic=false;
            Assert.That(policy.Evaluate(Frame(Source("two"))),Is.Not.Null);Assert.That(policy.Current.Automatic,Is.True);
            policy.Observe(one);Assert.That(policy.Current.Automatic,Is.False);Assert.That(policy.Current.Yield,Is.Null);
        }
        [Test] public void FailureCancelsYieldAndPausesAutomaticPassing()
        {
            var frame=Frame(Source());var policy=new UnityPriorityPolicy();policy.BeginYield("turn",frame);policy.Failed();
            Assert.That(policy.Current.Yield,Is.Null);Assert.That(policy.Evaluate(frame),Is.Null);
            policy.Resume();Assert.That(policy.Evaluate(frame),Is.Not.Null);
        }
        [Test] public void GameEndAndNewSessionResetTemporaryState()
        {
            var policy=new UnityPriorityPolicy();var wire=Source();policy.BeginYield("turn",Frame(wire));
            wire["message_type"]="result";wire["body"]["snapshot"]["result"]="win";wire["body"]["snapshot"]["status"]="finished";
            wire["body"]["snapshot"]["decision"]=null;wire["body"]["snapshot"]["actions"]=new JArray();
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.Null);
            wire=Source();wire["body"]["snapshot"]["session_id"]="fixture-new-session";
            Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);Assert.That(policy.Current.Stops,Is.Empty);
        }
        [Test] public void DisconnectSuspensionCancelsYieldAndRejectsOldFrame()
        {
            var policy=new UnityPriorityPolicy();var frame=Frame(Source());policy.BeginYield("turn",frame);policy.Suspend();
            Assert.That(policy.Current.Yield,Is.Null);Assert.That(policy.Claim(frame),Is.False);
        }
        [Test] public void MissingTurnContextAndWrongPrioritySeatHold()
        {
            var wire=Source();wire["body"]["snapshot"]["turn"]=null;
            Assert.That(new UnityPriorityPolicy().Evaluate(Frame(wire)),Is.Null);
            wire=Source();wire["body"]["snapshot"]["priority_player_id"]="two";
            Assert.That(new UnityPriorityPolicy().Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void ResolveAllContinuesThroughRemovalsAndStopsAtEmptyStack()
        {
            var wire=Source();Stack(wire,"a","b");Response(wire);var policy=new UnityPriorityPolicy();policy.BeginYield("resolve-stack",Frame(wire));
            Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            wire["body"]["snapshot"]["revision"]=2;wire["body"]["snapshot"]["decision"]["decision_id"]="after-one";Stack(wire,"a");
            Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            wire["body"]["snapshot"]["revision"]=3;wire["body"]["snapshot"]["decision"]["decision_id"]="after-all";Stack(wire);
            Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.Null);Assert.That(policy.Current.Reason,Is.EqualTo("Stack resolved"));
        }
        [Test] public void ResolveAllPausesForChoicesAndStopsForNewStackObjectsOrFailure()
        {
            var wire=Source();Stack(wire,"a");Response(wire);var policy=new UnityPriorityPolicy();policy.BeginYield("resolve-stack",Frame(wire));
            wire["body"]["snapshot"]["decision"]["is_priority"]=false;Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.EqualTo("resolve-stack"));
            wire["body"]["snapshot"]["decision"]["is_priority"]=true;Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            Stack(wire,"a","new-response");Assert.That(policy.Evaluate(Frame(wire)),Is.Null);Assert.That(policy.Current.Yield,Is.Null);
            policy.BeginYield("resolve-stack",Frame(wire));policy.Failed();Assert.That(policy.Claim(Frame(wire)),Is.False);
        }
        [Test] public void ResolveAllHonorsStopsAndRestoresManualControl()
        {
            var wire=Source();Stack(wire,"a");var policy=new UnityPriorityPolicy();policy.Observe(Frame(wire));policy.Current.Manual=true;policy.BeginYield("resolve-stack",Frame(wire));
            policy.SetStop("step","PRECOMBAT_MAIN",true);Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
            policy.SetStop("step","PRECOMBAT_MAIN",false);Assert.That(policy.Evaluate(Frame(wire)),Is.Not.Null);
            policy.CancelYield();Assert.That(policy.Current.Manual,Is.True);Assert.That(policy.Evaluate(Frame(wire)),Is.Null);
        }
        [Test] public void ProjectedPriorityContextIncludesStepAndImmutableStackOrder()
        {
            var wire=Source();Stack(wire,"fixture-stack-a","fixture-stack-b");var frame=Frame(wire);
            Assert.That(frame.Step,Is.EqualTo("PRECOMBAT_MAIN"));Assert.That(frame.PriorityPlayerId,Is.EqualTo("one"));
            CollectionAssert.AreEqual(new[]{"fixture-stack-a","fixture-stack-b"},frame.StackIds);
            Assert.That(((System.Collections.Generic.IList<string>)frame.StackIds).IsReadOnly,Is.True);
        }
    }
}

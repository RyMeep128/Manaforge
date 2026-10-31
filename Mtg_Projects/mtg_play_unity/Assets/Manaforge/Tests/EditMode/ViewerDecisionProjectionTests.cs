using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerDecisionProjectionTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")));
        private static JObject Choice()=>(JObject)Corpus()["positive"][2]["envelope"].DeepClone();
        private static JObject Priority()=>(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"].DeepClone();
        private static ProjectedDecisionFrame Project(JObject source)=>ViewerDecisionProjection.ParseSnapshot(source.ToString(Formatting.None),(string)source["body"]["snapshot"]["session_id"],(string)source["body"]["snapshot"]["viewer_id"],0,true);
        [Test] public void ManaReferencesCarryOnlyViewerRoutingAndDoNotInferEligibility()
        {
            var frame=Priority();var snapshot=frame["body"]["snapshot"];snapshot["decision"]["family"]="mana";var obj=snapshot["objects"][0];obj["hidden"]=true;obj["tapped"]=true;obj["controller_id"]="two";
            var projected=Project(frame);Assert.That(projected.ManaSourceReferences.Count,Is.EqualTo(((JArray)snapshot["objects"]).Count));var reference=projected.ManaSourceReferences[0];Assert.That(reference.ObjectId,Is.EqualTo((string)obj["object_id"]));Assert.That(reference.Context.ViewerId,Is.EqualTo("one"));Assert.That(reference.DecisionId,Is.EqualTo(projected.Decision.DecisionId));
            CollectionAssert.AreEquivalent(new[]{"Context","DecisionId","ObjectId"},typeof(ProjectedManaSource).GetProperties().Select(property=>property.Name));Assert.That(((System.Collections.Generic.IList<ProjectedManaSource>)projected.ManaSourceReferences).IsReadOnly,Is.True);
        }
        [Test] public void ManaReferencesAreEmptyOutsideManaAndIndependentAcrossSnapshots()
        {
            var source=Priority();Assert.That(Project(source).ManaSourceReferences,Is.Empty);source["body"]["snapshot"]["decision"]["family"]="mana";var first=Project(source);var second=Project(source);Assert.That(ReferenceEquals(first.ManaSourceReferences[0],second.ManaSourceReferences[0]),Is.False);source["body"]["snapshot"]["objects"]=new JArray();Assert.That(Project(source).ManaSourceReferences,Is.Empty);Assert.That(first.ManaSourceReferences,Is.Not.Empty);
        }
        [Test] public void SharedPositiveSnapshotsPreserveExactDecisionAndCompletenessFields()
        {
            foreach(var test in Corpus()["positive"]) {
                if((string)test["envelope"]["message_type"]=="event")continue;var value=test["envelope"];var snapshot=value["body"]["snapshot"];
                var frame=ViewerDecisionProjection.ParseSnapshot(value.ToString(),(string)test["session"],(string)test["viewer"],(long)test["minimum_revision"],(bool)test["fixture_mode"]);
                Assert.That(frame.Context.Revision,Is.EqualTo((long)snapshot["revision"]));Assert.That(frame.Status,Is.EqualTo((string)snapshot["status"]));Assert.That(frame.ActionsComplete,Is.EqualTo((bool)snapshot["actions_complete"]));Assert.That(frame.Actions.Count,Is.EqualTo(((JArray)snapshot["actions"]).Count));
                if(snapshot["decision"].Type==JTokenType.Null)Assert.That(frame.Decision,Is.Null);else{Assert.That(frame.Decision.DecisionId,Is.EqualTo((string)snapshot["decision"]["decision_id"]));Assert.That(frame.Decision.Family,Is.EqualTo((string)snapshot["decision"]["family"]));Assert.That(frame.Decision.Prompt,Is.EqualTo((string)snapshot["decision"]["prompt"]));}
            }
        }
        [Test] public void SharedInvalidPrivateStaleAndMisroutedMessagesRemainRejected()
        {
            foreach(var test in Corpus()["negative"]) {
                var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>ViewerDecisionProjection.ParseSnapshot(test["envelope"].ToString(),(string)test["session"],(string)test["viewer"],(long)test["minimum_revision"],(bool)test["fixture_mode"]));Assert.That(error.Code,Is.EqualTo((string)test["code"]));Assert.That(error.Message,Is.EqualTo(error.Code));
            }
        }
        [Test] public void NestedDecisionViewsAreReadOnlyAndEarlierSnapshotsDoNotRebind()
        {
            var source=Choice();var first=Project(source);string label=first.Decision.Options[0].Label;
            source["body"]["snapshot"]["decision"]["options"][0]["label"]="Later label";var later=Project(source);Assert.That(first.Decision.Options[0].Label,Is.EqualTo(label));Assert.That(later.Decision.Options[0].Label,Is.EqualTo("Later label"));
            Assert.Throws<NotSupportedException>(()=>((IList<ProjectedChoiceOption>)first.Decision.Options)[0]=null);
            foreach(var type in new[]{typeof(ProjectedDecisionFrame),typeof(ProjectedDecision),typeof(ProjectedAction),typeof(ProjectedChoiceOption),typeof(ProjectedAmountConstraint)}) {
                Assert.That(type.GetFields().Length,Is.Zero);foreach(var property in type.GetProperties()){Assert.That(property.CanWrite,Is.False);Assert.That(property.PropertyType.IsArray,Is.False);Assert.That(typeof(JToken).IsAssignableFrom(property.PropertyType),Is.False);}
            }
        }
        [Test] public void UnknownZeroFalseDefaultsAndAmountOrderRemainDistinctWithoutNormalization()
        {
            var source=Choice();var request=source["body"]["snapshot"]["decision"];var unknown=Project(source).Decision;Assert.That(unknown.Minimum,Is.Null);Assert.That(unknown.Maximum,Is.Null);Assert.That(unknown.Options[0].Selected,Is.False);
            request["family"]="future-family";request["minimum"]=0;request["maximum"]=0;request["cancellable"]=true;request["can_finish"]=true;request["is_priority"]=true;request["options"][0]["selected"]=true;
            request["amounts"]=new JArray(new JObject{["label"]="First",["minimum"]=long.MinValue,["maximum"]=long.MaxValue,["default"]=JValue.CreateNull()},new JObject{["label"]="Second",["minimum"]=0,["maximum"]=0,["default"]=0});
            var projected=Project(source).Decision;Assert.That(projected.Family,Is.EqualTo("future-family"));Assert.That(projected.Minimum,Is.Zero);Assert.That(projected.Maximum,Is.Zero);Assert.That(projected.Cancellable && projected.CanFinish && projected.IsPriority,Is.True);Assert.That(projected.Options[0].Selected,Is.True);
            Assert.That(projected.Amounts.Select(value=>value.Label),Is.EqualTo(new[]{"First","Second"}));Assert.That(projected.Amounts[0].Minimum,Is.EqualTo(long.MinValue));Assert.That(projected.Amounts[0].Maximum,Is.EqualTo(long.MaxValue));Assert.That(projected.Amounts[0].Default,Is.Null);Assert.That(projected.Amounts[1].Default,Is.Zero);
            Assert.Throws<NotSupportedException>(()=>((IList<ProjectedAmountConstraint>)projected.Amounts).Clear());
        }
        [Test] public void EngineTokensShareExactContextWithoutAssumingTwoSeats()
        {
            var source=Priority();var snapshot=source["body"]["snapshot"];snapshot["viewer_id"]="five";snapshot["priority_player_id"]="five";snapshot["decision"]["player_id"]="five";
            var player=snapshot["players"][0].DeepClone();player["player_id"]="five";player["name"]="Five";((JArray)snapshot["players"]).Add(player);
            var frame=Project(source);Assert.That(frame.Context.ViewerId,Is.EqualTo("five"));Assert.That(frame.Decision.Context,Is.SameAs(frame.Context));Assert.That(frame.Actions[0].Context,Is.SameAs(frame.Context));Assert.That(frame.Actions[0].DecisionId,Is.EqualTo(frame.Decision.DecisionId));Assert.That(frame.Actions[0].ActionId,Is.EqualTo("fixture-action"));
            var choice=Project(Choice());foreach(var option in choice.Decision.Options){Assert.That(option.Context,Is.SameAs(choice.Context));Assert.That(option.DecisionId,Is.EqualTo(choice.Decision.DecisionId));}
        }
        [Test] public void MissingDecisionDoesNotInventAnActionBinding()
        {var source=Priority();source["body"]["snapshot"]["decision"]=JValue.CreateNull();var frame=Project(source);Assert.That(frame.Actions.Count,Is.EqualTo(1));Assert.That(frame.Decision,Is.Null);Assert.That(frame.Actions[0].DecisionId,Is.Null);}
        [Test] public void EventsCannotMasqueradeAsDecisionSnapshots()
        {var source=Corpus()["positive"][6];Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>ViewerDecisionProjection.ParseSnapshot(source["envelope"].ToString(),(string)source["session"],(string)source["viewer"],0,true)).Code,Is.EqualTo("PROJECTION_SNAPSHOT_REQUIRED"));}
        [TestCase("actions")] [TestCase("options")] [TestCase("amounts")]
        public void OversizedUiCollectionsFailWithFixedTransportIndependentCode(string family)
        {
            var source=Priority();var snapshot=source["body"]["snapshot"];var values=new JArray();
            for(int i=0;i<=ViewerDecisionProjection.MaximumItems;i++) {
                if(family=="actions")values.Add(new JObject{["action_id"]="fixture-a"+i,["kind"]="fixture",["object_id"]=JValue.CreateNull(),["label"]="Action",["priority_class"]="manual"});
                else if(family=="options")values.Add(new JObject{["option_id"]="fixture-o"+i,["label"]="Option",["object_id"]=JValue.CreateNull(),["player_id"]=JValue.CreateNull(),["selected"]=false});
                else values.Add(new JObject{["label"]="Amount",["minimum"]=0,["maximum"]=1,["default"]=JValue.CreateNull()});
            }
            if(family=="actions")snapshot["actions"]=values;else snapshot["decision"][family]=values;
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>Project(source)).Code,Is.EqualTo("DECISION_PROJECTION_LIMIT"));
        }
        [Test] public void DecisionProjectionExcludesCardIdentityAndPrivateRevealPayloads()
        {
            var source=Choice();source["body"]["snapshot"]["observations"]=new JArray(new JObject{["observation_id"]="fixture-reveal",["source"]="fixture",["hidden"]=false,["name"]="Private reveal value",["set_code"]="ABC",["collector_number"]="123"});
            string encoded=JsonConvert.SerializeObject(Project(source));Assert.That(encoded,Does.Not.Contain("Private reveal value"));Assert.That(encoded,Does.Not.Contain("printing_id"));Assert.That(encoded,Does.Not.Contain("deck_entry_id"));Assert.That(encoded,Does.Not.Contain("observations"));
        }
    }
}

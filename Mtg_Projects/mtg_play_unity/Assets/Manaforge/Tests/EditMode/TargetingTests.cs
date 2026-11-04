using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using Manaforge.Play.Protocol;
namespace Manaforge.Play.Tests
{
    public sealed class TargetingTests
    {
        private JObject Source()
        {
            var wire=(JObject)JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/wire-receive-v1.json")))["positive"][0]["envelope"].DeepClone();
            var snapshot=wire["body"]["snapshot"];snapshot["decision"]=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")))["cases"][0]["steps"][0]["envelope"]["body"]["snapshot"]["decision"].DeepClone();snapshot["decision"]["is_priority"]=false;snapshot["decision"]["family"]="selection";
            snapshot["decision"]["options"]=new JArray(new JObject{["option_id"]="target-one",["label"]="You",["object_id"]=null,["player_id"]="one",["selected"]=false});
            snapshot["decision"]["targeting"]=new JObject{["source_id"]=snapshot["objects"][0]["object_id"].DeepClone(),["minimum"]=1,["maximum"]=2,["complete"]=true,["selected"]=new JArray(new JObject{["object_id"]=null,["player_id"]="one",["ordinal"]=1,["amount"]=3})};return wire;
        }
        private ProjectedDecisionFrame Frame(JObject wire)=>ViewerDecisionProjection.ParseSnapshot(wire.ToString(),(string)wire["body"]["snapshot"]["session_id"],"one",0,true);
        [Test] public void TargetingUsesOnlyExplicitNativeContextAndConfirmedSelections()
        {
            var wire=Source();var state=new TargetingState(Frame(wire));Assert.That(state.Active,Is.True);Assert.That(state.Legal.Count,Is.EqualTo(1));Assert.That(state.Selected[0].Amount,Is.EqualTo(3));Assert.That(state.Prompt,Does.Contain("Selected 1 (1-2)"));
            wire["body"]["snapshot"]["decision"]["targeting"]=null;Assert.That(new TargetingState(Frame(wire)).Active,Is.False);
        }
        [Test] public void UnknownSourceAndUnknownCountsRemainAvailableAsFallbacks()
        {
            var wire=Source();var target=wire["body"]["snapshot"]["decision"]["targeting"];target["source_id"]=null;target["minimum"]=null;target["maximum"]=null;target["complete"]=false;
            var state=new TargetingState(Frame(wire));Assert.That(state.SourceId,Is.Null);Assert.That(state.Prompt,Does.Not.Contain("(1-2)"));Assert.That(state.Prompt,Does.Contain("unavailable"));
        }
        [Test] public void InvalidTargetReferencesAndRangesAreRejected()
        {
            var wire=Source();wire["body"]["snapshot"]["decision"]["targeting"]["source_id"]="missing";Assert.Throws<WireEnvelope.EnvelopeException>(()=>Frame(wire));
            wire=Source();wire["body"]["snapshot"]["decision"]["targeting"]["selected"][0]["player_id"]="missing";Assert.Throws<WireEnvelope.EnvelopeException>(()=>Frame(wire));
            wire=Source();wire["body"]["snapshot"]["decision"]["targeting"]["maximum"]=0;Assert.Throws<WireEnvelope.EnvelopeException>(()=>Frame(wire));
        }
        [Test] public void StackTargetsPreserveRepeatedTargetsAndCompleteness()
        {
            var wire=Source();var snapshot=wire["body"]["snapshot"];snapshot["objects"][0]["zone"]="stack";
            var target=new JObject{["object_id"]=null,["player_id"]="one",["ordinal"]=1,["amount"]=null};var second=(JObject)target.DeepClone();second["ordinal"]=2;
            snapshot["stack_targets"]=new JArray(new JObject{["source_id"]=snapshot["objects"][0]["object_id"].DeepClone(),["targets"]=new JArray(target,second),["complete"]=false});
            var frame=Frame(wire);Assert.That(frame.StackTargets[0].Targets.Count,Is.EqualTo(2));Assert.That(frame.StackTargets[0].Complete,Is.False);
        }
    }
}

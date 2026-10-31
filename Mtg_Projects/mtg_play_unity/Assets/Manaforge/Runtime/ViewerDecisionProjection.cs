using System;
using System.Collections.Generic;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Immutable UI slices of engine-supplied tokens, never a command authority or rules engine.
    public sealed class ProjectedAction
    {
        public CardProjectionContext Context {get;} public string DecisionId {get;}
        public string ActionId {get;} public string Kind {get;} public string ObjectId {get;}
        public string Label {get;} public string PriorityClass {get;}
        internal ProjectedAction(CardProjectionContext context,string decision,JToken source)
        {Context=context;DecisionId=decision;ActionId=(string)source["action_id"];Kind=(string)source["kind"];ObjectId=(string)source["object_id"];Label=(string)source["label"];PriorityClass=(string)source["priority_class"];}
    }
    public sealed class ProjectedChoiceOption
    {
        public CardProjectionContext Context {get;} public string DecisionId {get;}
        public string OptionId {get;} public string Label {get;} public string ObjectId {get;}
        public string PlayerId {get;} public bool Selected {get;}
        internal ProjectedChoiceOption(CardProjectionContext context,string decision,JToken source)
        {Context=context;DecisionId=decision;OptionId=(string)source["option_id"];Label=(string)source["label"];ObjectId=(string)source["object_id"];PlayerId=(string)source["player_id"];Selected=(bool)source["selected"];}
    }
    // Addressable viewer object only; membership never means the engine permits mana production.
    public sealed class ProjectedManaSource
    {
        public CardProjectionContext Context {get;} public string DecisionId {get;} public string ObjectId {get;}
        internal ProjectedManaSource(CardProjectionContext context,string decision,string objectId){Context=context;DecisionId=decision;ObjectId=objectId;}
    }
    public sealed class ProjectedAmountConstraint
    {
        public string Label {get;} public long Minimum {get;} public long Maximum {get;} public long? Default {get;}
        internal ProjectedAmountConstraint(JToken source){Label=(string)source["label"];Minimum=(long)source["minimum"];Maximum=(long)source["maximum"];Default=(long?)source["default"];}
    }
    public sealed class ProjectedDecision
    {
        public CardProjectionContext Context {get;} public string DecisionId {get;} public string PlayerId {get;}
        public string Family {get;} public string Prompt {get;}
        public IReadOnlyList<ProjectedChoiceOption> Options {get;} public IReadOnlyList<ProjectedAmountConstraint> Amounts {get;}
        public long? Minimum {get;} public long? Maximum {get;} public bool Cancellable {get;} public bool CanFinish {get;} public bool IsPriority {get;}
        internal ProjectedDecision(CardProjectionContext context,JToken source)
        {
            Context=context;DecisionId=(string)source["decision_id"];PlayerId=(string)source["player_id"];Family=(string)source["family"];Prompt=(string)source["prompt"];
            Minimum=(long?)source["minimum"];Maximum=(long?)source["maximum"];Cancellable=(bool)source["cancellable"];CanFinish=(bool)source["can_finish"];IsPriority=(bool)source["is_priority"];
            Options=Array.AsReadOnly(source["options"].Select(value=>new ProjectedChoiceOption(context,DecisionId,value)).ToArray());
            Amounts=Array.AsReadOnly(source["amounts"].Select(value=>new ProjectedAmountConstraint(value)).ToArray());
        }
    }
    public sealed class ProjectedDecisionFrame
    {
        public CardProjectionContext Context {get;} public string Status {get;} public bool ActionsComplete {get;}
        public IReadOnlyList<ProjectedAction> Actions {get;} public ProjectedDecision Decision {get;}
        public IReadOnlyList<ProjectedManaSource> ManaSourceReferences {get;}
        public IReadOnlyList<string> UnsupportedFields {get;}
        internal ProjectedDecisionFrame(JObject source)
        {
            Context=new CardProjectionContext((string)source["session_id"],(string)source["viewer_id"],(long)source["revision"]);Status=(string)source["status"];ActionsComplete=(bool)source["actions_complete"];
            if(source["decision"].Type!=JTokenType.Null)Decision=new ProjectedDecision(Context,source["decision"]);
            ManaSourceReferences=Array.AsReadOnly(Decision?.Family=="mana"
                ?source["objects"].Select(value=>new ProjectedManaSource(Context,Decision.DecisionId,(string)value["object_id"])).ToArray()
                :Array.Empty<ProjectedManaSource>());
            Actions=Array.AsReadOnly(source["actions"].Select(value=>new ProjectedAction(Context,Decision?.DecisionId,value)).ToArray());UnsupportedFields=ViewerCardProjection.Strings(source["unsupported_fields"]);
        }
    }
    public static class ViewerDecisionProjection
    {
        public const int MaximumItems=4096;
        public static ProjectedDecisionFrame ParseSnapshot(string text,string session,string viewer,long minimumRevision,bool fixtureMode=false)
            =>Project(ViewerCardProjection.ValidateSnapshot(text,session,viewer,minimumRevision,fixtureMode));
        internal static ProjectedDecisionFrame Project(JObject snapshot)
        {
            var decision=snapshot["decision"];
            if(((JArray)snapshot["actions"]).Count>MaximumItems || (decision.Type!=JTokenType.Null && (((JArray)decision["options"]).Count>MaximumItems || ((JArray)decision["amounts"]).Count>MaximumItems)))
                throw new WireEnvelope.EnvelopeException("DECISION_PROJECTION_LIMIT");
            return new ProjectedDecisionFrame(snapshot);
        }
    }
}

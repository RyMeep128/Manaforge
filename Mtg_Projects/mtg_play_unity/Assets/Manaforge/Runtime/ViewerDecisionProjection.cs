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
    public sealed class ProjectedChoicePreview
    {
        public bool Hidden {get;} public string Name {get;} public string TypeLine {get;} public string Rules {get;}
        internal ProjectedChoicePreview(JToken card){Hidden=(bool)card["hidden"];if(Hidden)return;Name=(string)card["name"];TypeLine=(string)card["type_line"];Rules=card["rules"] is JArray rules?string.Join("\n",rules.Select(line=>(string)line)):null;}
    }
    public sealed class ProjectedChoiceGroup
    {
        public string GroupId {get;} public string Label {get;} public string OptionId {get;} public IReadOnlyList<ProjectedChoicePreview> Cards {get;}
        internal ProjectedChoiceGroup(JToken value){GroupId=(string)value["group_id"];Label=(string)value["label"];OptionId=(string)value["option_id"];Cards=Array.AsReadOnly(value["cards"].Select(card=>new ProjectedChoicePreview(card)).ToArray());}
    }
    public sealed class ProjectedDecision
    {
        public CardProjectionContext Context {get;} public string DecisionId {get;} public string PlayerId {get;}
        public string Family {get;} public string Prompt {get;}
        public IReadOnlyList<ProjectedChoiceOption> Options {get;} public IReadOnlyList<ProjectedAmountConstraint> Amounts {get;}
        public long? Minimum {get;} public long? Maximum {get;} public bool Cancellable {get;} public bool CanFinish {get;} public bool IsPriority {get;}
        public ProjectedTargetingContext Targeting {get;}
        public IReadOnlyList<ProjectedChoiceGroup> Groups {get;}
        public string RequestId {get;} public string RequestKind {get;}
        internal ProjectedDecision(CardProjectionContext context,JToken source)
        {
            if(source["request"] is JObject request){RequestId=(string)request["request_id"];RequestKind=(string)request["kind"];}
            Groups=Array.AsReadOnly((source["groups"] as JArray ?? new JArray()).Select(group=>new ProjectedChoiceGroup(group)).ToArray());
            Context=context;DecisionId=(string)source["decision_id"];PlayerId=(string)source["player_id"];Family=(string)source["family"];Prompt=(string)source["prompt"];
            Minimum=(long?)source["minimum"];Maximum=(long?)source["maximum"];Cancellable=(bool)source["cancellable"];CanFinish=(bool)source["can_finish"];IsPriority=(bool)source["is_priority"];
            if(source["targeting"] is JObject target)Targeting=new ProjectedTargetingContext(target);
            Options=Array.AsReadOnly(source["options"].Select(value=>new ProjectedChoiceOption(context,DecisionId,value)).ToArray());
            Amounts=Array.AsReadOnly(source["amounts"].Select(value=>new ProjectedAmountConstraint(value)).ToArray());
        }
    }
    public sealed class ProjectedCombatAssignment
    {
        public IReadOnlyList<string> AttackerIds {get;} public IReadOnlyList<string> BlockerIds {get;} public IReadOnlyList<string> AttackerNames {get;} public IReadOnlyList<string> BlockerNames {get;} public IReadOnlyList<long?> BlockerDamage {get;} public string DefenderName {get;} public string DefenderId {get;} public string DefenderLoyalty {get;} public string DefenderDefense {get;} public long? DefenderLife {get;} public int BlockerCount {get;}
        private static string ObjectName(JObject snapshot,string id,string fallback)
        {
            var card=snapshot["objects"].FirstOrDefault(value=>(string)value["object_id"]==id);
            return (string)(card?["characteristics"] as JObject)?["name"]??fallback;
        }
        internal ProjectedCombatAssignment(JToken assignment,JObject snapshot)
        {
            AttackerIds=Array.AsReadOnly(assignment["attackers"].Select(id=>(string)id).ToArray());
            BlockerIds=Array.AsReadOnly(assignment["blockers"].Select(id=>(string)id).ToArray());
            AttackerNames=Array.AsReadOnly(assignment["attackers"].Select(id=>ObjectName(snapshot,(string)id,"Unknown attacker")).ToArray());
            DefenderId=(string)assignment["defender_id"];var defender=snapshot["players"].FirstOrDefault(player=>(string)player["player_id"]==(string)assignment["defender_id"]);DefenderName=(string)defender?["name"]??ObjectName(snapshot,DefenderId,"Unknown defender");DefenderLife=(long?)defender?["life"];var defended=snapshot["objects"].FirstOrDefault(card=>(string)card["object_id"]==DefenderId);DefenderLoyalty=(string)(defended?["characteristics"] as JObject)?["loyalty"];DefenderDefense=(string)(defended?["characteristics"] as JObject)?["defense"];
            BlockerDamage=Array.AsReadOnly(assignment["blockers"].Select(id=>(long?)snapshot["objects"].FirstOrDefault(card=>(string)card["object_id"]==(string)id)?["damage"]).ToArray());
            BlockerNames=Array.AsReadOnly(assignment["blockers"].Select(id=>ObjectName(snapshot,(string)id,"Unknown blocker")).ToArray());BlockerCount=BlockerNames.Count;
        }
    }
    public sealed class ProjectedCommander
    {
        public string CommanderId {get;} public string Zone {get;} public string ObjectId {get;} public string OwnerId {get;} public string Name {get;} public long? CommandZonePlays {get;} public string AdditionalCastCost {get;}
        public IReadOnlyDictionary<string,long> DamageDealt {get;}
        internal ProjectedCommander(JToken source,JObject snapshot){CommanderId=(string)source["commander_id"];var visible=snapshot["objects"].FirstOrDefault(card=>(string)card["commander_id"]==CommanderId);Zone=(string)visible?["zone"];ObjectId=(string)visible?["object_id"];OwnerId=(string)source["owner_id"];Name=(string)source["name"];CommandZonePlays=(long?)source["command_zone_plays"];AdditionalCastCost=(string)source["additional_cast_cost"];if(source["damage_dealt"] is JArray damage)DamageDealt=new System.Collections.ObjectModel.ReadOnlyDictionary<string,long>(damage.ToDictionary(pair=>(string)pair[0],pair=>(long)pair[1]));}
    }
    public sealed class ProjectedDecisionFrame
    {
        public CardProjectionContext Context {get;} public string Status {get;} public string Result {get;} public long? Turn {get;} public string Phase {get;} public string ActivePlayerId {get;} public bool ActionsComplete {get;}
        public string PaymentReason {get;} public string DecisionError {get;} public string SessionNotice {get;}
        public string Step {get;} public string PriorityPlayerId {get;}
        public IReadOnlyList<string> StackIds {get;}
        public IReadOnlyDictionary<string,long?> PlayerLifeTotals {get;}
        public IReadOnlyDictionary<string,long?> PlayerLibraryCounts {get;} public IReadOnlyDictionary<string,long?> PlayerHandCounts {get;}
        public IReadOnlyList<ProjectedCommander> Commanders {get;}
        public IReadOnlyDictionary<string,long> ViewerMana {get;}
        public IReadOnlyList<ProjectedCombatAssignment> Combat {get;}
        public IReadOnlyList<ProjectedAction> Actions {get;} public ProjectedDecision Decision {get;}
        public IReadOnlyList<ProjectedManaSource> ManaSourceReferences {get;}
        public IReadOnlyList<string> UnsupportedFields {get;}
        public System.Collections.Generic.IReadOnlyList<ProjectedStackTargets> StackTargets {get;}
        internal ProjectedDecisionFrame(JObject source)
        {
            if(source["commanders"] is JArray commanders)Commanders=Array.AsReadOnly(commanders.Select(value=>new ProjectedCommander(value,source)).ToArray());
            PaymentReason=(string)source["payment_reason"];DecisionError=(string)source["decision_error"];SessionNotice=(string)source["session_notice"];
            StackTargets=Array.AsReadOnly((source["stack_targets"] as JArray ?? new JArray()).Select(value=>new ProjectedStackTargets(value)).ToArray());
            Step=(string)source["step"];PriorityPlayerId=(string)source["priority_player_id"];
            StackIds=Array.AsReadOnly(source["objects"].Where(card=>(string)card["zone"]=="stack").Select(card=>(string)card["object_id"]).ToArray());
            Result=(string)source["result"];Turn=(long?)source["turn"];Phase=(string)source["phase"];ActivePlayerId=(string)source["active_player_id"];
            PlayerLifeTotals=new System.Collections.ObjectModel.ReadOnlyDictionary<string,long?>(source["players"].ToDictionary(player=>(string)player["player_id"],player=>(long?)player["life"]));
            PlayerLibraryCounts=new System.Collections.ObjectModel.ReadOnlyDictionary<string,long?>(source["players"].ToDictionary(player=>(string)player["player_id"],player=>(long?)player["library_count"]));
            PlayerHandCounts=new System.Collections.ObjectModel.ReadOnlyDictionary<string,long?>(source["players"].ToDictionary(player=>(string)player["player_id"],player=>(long?)player["hand_count"]));
            Combat=Array.AsReadOnly(source["combat"].Select(group=>new ProjectedCombatAssignment(group,source)).ToArray());
            Context=new CardProjectionContext((string)source["session_id"],(string)source["viewer_id"],(long)source["revision"]);Status=(string)source["status"];var pool=source["players"].FirstOrDefault(player=>(string)player["player_id"]==Context.ViewerId)?["mana"];if(pool is JArray amounts)ViewerMana=new System.Collections.ObjectModel.ReadOnlyDictionary<string,long>(amounts.ToDictionary(pair=>(string)pair[0],pair=>(long)pair[1]));ActionsComplete=(bool)source["actions_complete"];
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
            var objects=snapshot["objects"].Select(value=>(string)value["object_id"]).ToHashSet();
            var players=snapshot["players"].Select(value=>(string)value["player_id"]).ToHashSet();
            void CheckTarget(JToken target){if((string)target["object_id"] is string objectId && !objects.Contains(objectId) || (string)target["player_id"] is string playerId && !players.Contains(playerId))throw new WireEnvelope.EnvelopeException("TARGET_REFERENCE_UNAVAILABLE");}
            if(decision is JObject decisionObject && decisionObject["targeting"] is JObject targeting){
                if((string)targeting["source_id"] is string source && !objects.Contains(source) || (long?)targeting["minimum"]>(long?)targeting["maximum"])throw new WireEnvelope.EnvelopeException("TARGET_CONTEXT_INVALID");
                foreach(var target in targeting["selected"])CheckTarget(target);
            }
            if(snapshot["stack_targets"] is JArray relationships)foreach(var relation in relationships){
                if(!snapshot["objects"].Any(value=>(string)value["object_id"]==(string)relation["source_id"] && (string)value["zone"]=="stack"))throw new WireEnvelope.EnvelopeException("TARGET_SOURCE_UNAVAILABLE");
                foreach(var target in relation["targets"])CheckTarget(target);
            }
            return new ProjectedDecisionFrame(snapshot);
        }
    }
}

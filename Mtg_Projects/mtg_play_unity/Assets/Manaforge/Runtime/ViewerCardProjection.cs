using System;
using System.Collections.Generic;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    public sealed class CardProjectionContext
    {
        public string SessionId {get;} public string ViewerId {get;} public long Revision {get;}
        internal CardProjectionContext(string session,string viewer,long revision){SessionId=session;ViewerId=viewer;Revision=revision;}
    }
    public sealed class ProjectedPrinting
    {
        public string OracleId {get;} public string PrintingId {get;}
        internal ProjectedPrinting(JToken value){OracleId=(string)value["oracle_id"];PrintingId=(string)value["printing_id"];}
    }
    public sealed class ProjectedCounter
    {
        public string Name {get;} public long Amount {get;}
        internal ProjectedCounter(JToken value){Name=(string)value[0];Amount=(long)value[1];}
    }
    public sealed class ProjectedCharacteristics
    {
        public string Name {get;} public string Power {get;} public string Toughness {get;}
        public string TypeLine {get;} public string Color {get;} public string Loyalty {get;} public string Defense {get;}
        public bool? Transformed {get;} public bool? Flipped {get;} public bool? IsCopy {get;}
        public IReadOnlyList<string> EngineViewText {get;}
        public IReadOnlyList<string> CurrentAbilities {get;}
        public IReadOnlyList<string> UnsupportedFields {get;}
        public IReadOnlyList<ProjectedCounter> Counters {get;}
        internal ProjectedCharacteristics(JToken value)
        {
            Name=(string)value["name"];Power=(string)value["power"];Toughness=(string)value["toughness"];
            TypeLine=(string)value["type_line"];Color=(string)value["color"];Loyalty=(string)value["loyalty"];Defense=(string)value["defense"];
            Transformed=(bool?)value["transformed"];Flipped=(bool?)value["flipped"];IsCopy=(bool?)value["is_copy"];
            EngineViewText=ViewerCardProjection.Strings(value["engine_view_text"]);
            CurrentAbilities=ViewerCardProjection.Strings(value["current_abilities"]);
            UnsupportedFields=ViewerCardProjection.Strings(value["unsupported_fields"]);
            Counters=value["counters"].Type==JTokenType.Null?null:Array.AsReadOnly(value["counters"].Select(c=>new ProjectedCounter(c)).ToArray());
        }
    }
    public sealed class ProjectedCard
    {
        public CardProjectionContext Context {get;}
        public string ObjectId {get;} public string Zone {get;} public string OwnerId {get;} public string ControllerId {get;}
        public bool Hidden {get;}
        public ProjectedPrinting Printing {get;}
        public ProjectedCharacteristics Characteristics {get;}
        public bool? Tapped {get;} public bool? FaceDown {get;} public long? Damage {get;}
        public IReadOnlyList<string> Attachments {get;}
        public string AttachedTo {get;} public string CommanderId {get;} public string CopySourceId {get;}
        internal ProjectedCard(CardProjectionContext context,JToken value)
        {
            Context=context;ObjectId=(string)value["object_id"];Zone=(string)value["zone"];
            OwnerId=(string)value["owner_id"];ControllerId=(string)value["controller_id"];Hidden=(bool)value["hidden"];
            // Concealed objects retain opaque routing only; no artwork, characteristics or relationship hints.
            if(Hidden)return;
            Printing=value["card_identity"].Type==JTokenType.Null?null:new ProjectedPrinting(value["card_identity"]);
            Characteristics=value["characteristics"].Type==JTokenType.Null?null:new ProjectedCharacteristics(value["characteristics"]);
            Tapped=(bool?)value["tapped"];FaceDown=(bool?)value["face_down"];Damage=(long?)value["damage"];
            Attachments=ViewerCardProjection.Strings(value["attachments"]);AttachedTo=(string)value["attached_to"];
            CommanderId=(string)value["commander_id"];CopySourceId=(string)value["copy_source_id"];
        }
    }
    // Immutable card slice, not another game model: excludes decisions, legal actions and private observations.
    public sealed class ProjectedCardFrame
    {
        public CardProjectionContext Context {get;}
        public string Status {get;} public string Result {get;}
        public IReadOnlyList<ProjectedCard> Cards {get;}
        public IReadOnlyList<string> UnsupportedFields {get;}
        internal ProjectedCardFrame(JToken snapshot)
        {
            Context=new CardProjectionContext((string)snapshot["session_id"],(string)snapshot["viewer_id"],(long)snapshot["revision"]);
            Status=(string)snapshot["status"];Result=(string)snapshot["result"];
            Cards=Array.AsReadOnly(snapshot["objects"].Select(obj=>new ProjectedCard(Context,obj)).ToArray());
            UnsupportedFields=ViewerCardProjection.Strings(snapshot["unsupported_fields"]);
        }
    }
    public static class ViewerCardProjection
    {
        public const int MaximumObjects=4096;
        internal static IReadOnlyList<string> Strings(JToken token)=>token.Type==JTokenType.Null?null:Array.AsReadOnly(token.Select(v=>(string)v).ToArray());
        // Worker-side boundary. No file IO, Unity APIs, artwork lookup, logging or mutable JSON escapes.
        // Caller supplies authenticated context and monotonic minimum revision; history remains owned by the channel.
        public static ProjectedCardFrame ParseSnapshot(string text,string session,string viewer,long minimumRevision,bool fixtureMode=false)
            =>new ProjectedCardFrame(ValidateSnapshot(text,session,viewer,minimumRevision,fixtureMode));
        // Worker-only shared validation; mutable intermediate never leaves projection/receive internals.
        internal static JObject ValidateSnapshot(string text,string session,string viewer,long minimumRevision,bool fixtureMode)
        {
            if(string.IsNullOrWhiteSpace(session) || string.IsNullOrWhiteSpace(viewer) || minimumRevision<0)
                throw new WireEnvelope.EnvelopeException("PROJECTION_CONTEXT");
            var envelope=ReceiveMessages.Parse(text,session,viewer,minimumRevision,fixtureMode);
            if((string)envelope["message_type"]=="event")throw new WireEnvelope.EnvelopeException("PROJECTION_SNAPSHOT_REQUIRED");
            var snapshot=(JObject)envelope["body"]["snapshot"];
            if(((JArray)snapshot["objects"]).Count>MaximumObjects)throw new WireEnvelope.EnvelopeException("PROJECTION_OBJECT_LIMIT");
            return snapshot;
        }
    }
}

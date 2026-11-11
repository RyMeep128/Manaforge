using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Standalone contract. No registration in gameplay receive/command routing.
    public static class OrganizationMessages
    {
        public const int MaxBytes=262144;
        private static readonly JObject Schema=JObject.Parse(OrganizationContractSchema.Json);
        private const string White=@"[ \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]";
        private static bool Id(string value)=>value!=null && Regex.IsMatch(value,@"\A[A-Za-z0-9_.:-]{1,128}\z");
        public sealed class Context
        {
            public string MatchEpoch {get;} public string ViewerId {get;} public long BasisRevision {get;}
            public IReadOnlyDictionary<string,string> Objects {get;} public IReadOnlyDictionary<string,string> Seats {get;}
            public IReadOnlyCollection<string> VisibleSeats {get;}
            public Context(string epoch,string viewer,long basis,IDictionary<string,string> objects,IDictionary<string,string> seats,IEnumerable<string> admitted,IEnumerable<string> visibleSeats)
            {
                var allowed=new HashSet<string>(admitted,StringComparer.Ordinal);var roster=new HashSet<string>(visibleSeats,StringComparer.Ordinal);
                if(!Id(epoch) || !Id(viewer) || basis<0 || objects.Count>1024 || roster.Count==0 || roster.Count>8 || !new HashSet<string>(objects.Keys,StringComparer.Ordinal).SetEquals(seats.Keys) || objects.Values.Distinct(StringComparer.Ordinal).Count()!=objects.Count)throw new ArgumentException("ORGANIZATION_CONTEXT");
                foreach(string seat in roster)if(!Id(seat))throw new ArgumentException("ORGANIZATION_CONTEXT");
                foreach(string handle in objects.Keys)if(!Id(handle) || !Id(objects[handle]) || !allowed.Contains(objects[handle]) || !roster.Contains(seats[handle]))throw new ArgumentException("ORGANIZATION_CONTEXT");
                MatchEpoch=epoch;ViewerId=viewer;BasisRevision=basis;Objects=new ReadOnlyDictionary<string,string>(new Dictionary<string,string>(objects,StringComparer.Ordinal));Seats=new ReadOnlyDictionary<string,string>(new Dictionary<string,string>(seats,StringComparer.Ordinal));VisibleSeats=new List<string>(roster).AsReadOnly();
            }
        }
        public static int Negotiate(IEnumerable<int> local,IEnumerable<int> peer,bool authenticated)=>authenticated && local!=null && peer!=null && local.Contains(1) && peer.Contains(1)?1:0;
        private static bool Valid(JToken value,JToken element)
        {
            if(element.Type==JTokenType.Boolean)return (bool)element;var rule=(JObject)element;
            if(rule["$ref"]!=null){string reference=(string)rule["$ref"];return Valid(value,Schema["$defs"][reference.Substring(reference.LastIndexOf('/')+1)]);}
            if(rule["anyOf"] is JArray any && !any.Any(part=>Valid(value,part)))return false;
            if(rule["allOf"] is JArray all && !all.All(part=>Valid(value,part)))return false;
            if(rule["if"]!=null && Valid(value,rule["if"]) && rule["then"]!=null && !Valid(value,rule["then"]))return false;
            if(rule["const"]!=null && !JToken.DeepEquals(value,rule["const"]))return false;
            if(rule["enum"] is JArray options && !options.Any(option=>JToken.DeepEquals(value,option)))return false;
            if(rule["type"]!=null){bool matches;switch((string)rule["type"]){case "null":matches=value.Type==JTokenType.Null;break;case "object":matches=value is JObject;break;case "array":matches=value is JArray;break;case "string":matches=value.Type==JTokenType.String;break;case "integer":matches=value.Type==JTokenType.Integer;break;default:return false;}if(!matches)return false;}
            if(value is JObject obj){var properties=rule["properties"] as JObject??new JObject();
                if(rule["required"] is JArray required && required.Any(key=>obj[(string)key]==null))return false;
                foreach(var field in obj.Properties()){if(properties[field.Name]!=null){if(!Valid(field.Value,properties[field.Name]))return false;}else if(rule["additionalProperties"]?.Type==JTokenType.Boolean && !(bool)rule["additionalProperties"])return false;}
            }
            if(value is JArray array){
                if(rule["minItems"]!=null && array.Count<(int)rule["minItems"] || rule["maxItems"]!=null && array.Count>(int)rule["maxItems"])return false;
                for(int i=0;i<array.Count;i++){if(rule["items"]!=null && !Valid(array[i],rule["items"]))return false;if((bool?)rule["uniqueItems"]==true)for(int j=0;j<i;j++)if(JToken.DeepEquals(array[i],array[j]))return false;}
            }
            if(value.Type==JTokenType.String){string text=(string)value;int length=0;for(int i=0;i<text.Length;i++,length++)if(char.IsHighSurrogate(text[i]))i++;
                if(rule["minLength"]!=null && length<(int)rule["minLength"] || rule["maxLength"]!=null && length>(int)rule["maxLength"])return false;
                if(rule["pattern"]!=null && !Regex.IsMatch(text,(string)rule["pattern"],RegexOptions.CultureInvariant))return false;
            }
            if(value.Type==JTokenType.Integer){long number=(long)value;if(rule["minimum"]!=null && number<(long)rule["minimum"] || rule["maximum"]!=null && number>(long)rule["maximum"])return false;}
            return true;
        }
        private static void Require(bool value,string code){if(!value)throw new WireEnvelope.EnvelopeException(code);}
        private static void Name(JToken value){if(value.Type!=JTokenType.Null)Require(Regex.Replace((string)value,White,"").Length>0,"ORGANIZATION_INVALID");}
        public static JObject Parse(string raw,Context context)
        {
            Require(raw!=null && raw.Length<=MaxBytes,"ORGANIZATION_SIZE");
            try{Require(new UTF8Encoding(false,true).GetByteCount(raw)<=MaxBytes,"ORGANIZATION_SIZE");}catch(EncoderFallbackException){throw new WireEnvelope.EnvelopeException("JSON_INVALID");}
            var message=WireEnvelope.ParseObject(raw);Require(message!=null && Valid(message,Schema),"ORGANIZATION_INVALID");string type=(string)message["message_type"];var body=(JObject)message["body"];
            if(type=="organization_capabilities")return message;
            Require(context!=null && (string)body["match_epoch"]==context.MatchEpoch && (long)body["basis_revision"]==context.BasisRevision,"ORGANIZATION_CONTEXT");
            if(type=="organization_command"){
                var operation=(JObject)body["operation"];Name(operation["name"]);var selected=new HashSet<string>(StringComparer.Ordinal);
                foreach(string handle in (JArray)operation["members"])Require(selected.Add(handle) && context.Objects.ContainsKey(handle),"ORGANIZATION_CONTEXT");
            }
            if(type=="organization_snapshot"){
                Require((string)body["viewer_id"]==context.ViewerId,"ORGANIZATION_CONTEXT");var seats=new HashSet<string>(StringComparer.Ordinal);var groups=new HashSet<string>(StringComparer.Ordinal);var objects=new HashSet<string>(StringComparer.Ordinal);var membership=new Dictionary<string,string>(StringComparer.Ordinal);
                foreach(JObject seat in (JArray)body["seats"]){string seatId=(string)seat["seat_id"];Require(seats.Add(seatId) && context.VisibleSeats.Contains(seatId),"ORGANIZATION_CONTEXT");
                    foreach(string handle in (JArray)seat["root"]){Require(!membership.ContainsKey(handle),"ORGANIZATION_INVALID");membership.Add(handle,seatId);}
                    foreach(JObject group in (JArray)seat["groups"]){Require(groups.Add((string)group["group_id"]),"ORGANIZATION_INVALID");Name(group["name"]);foreach(string handle in (JArray)group["members"]){Require(!membership.ContainsKey(handle),"ORGANIZATION_INVALID");membership.Add(handle,seatId);}}
                }
                Require(membership.Count<=1024,"ORGANIZATION_INVALID");var mapped=new HashSet<string>(StringComparer.Ordinal);
                foreach(JObject mapping in (JArray)body["mappings"]){string handle=(string)mapping["handle"],reference=(string)mapping["object_reference"],seat=(string)mapping["seat_id"];
                    Require(mapped.Add(handle) && objects.Add(reference) && context.Objects.TryGetValue(handle,out var expectedReference) && expectedReference==reference && context.Seats.TryGetValue(handle,out var expectedSeat) && expectedSeat==seat && membership.TryGetValue(handle,out var memberSeat) && memberSeat==seat,"ORGANIZATION_CONTEXT");
                }
                Require(mapped.SetEquals(membership.Keys),"ORGANIZATION_INVALID");
            }
            return message;
        }
        public static string Serialize(JObject message,Context context){string raw=message.ToString(Formatting.None);Parse(raw,context);return raw;}
        public static string EncodeOperation(string messageId,string commandId,long expectedOrganizationRevision,OrganizationOperation operation,Context context)
        {
            var message=new JObject{["wire_version"]=1,["organization_version"]=1,["message_type"]="organization_command",["message_id"]=messageId,["body"]=new JObject{["match_epoch"]=context.MatchEpoch,["command_id"]=commandId,["expected_organization_revision"]=expectedOrganizationRevision,["basis_revision"]=context.BasisRevision,["operation"]=JObject.FromObject(operation)}};
            return Serialize(message,context);
        }
    }
}

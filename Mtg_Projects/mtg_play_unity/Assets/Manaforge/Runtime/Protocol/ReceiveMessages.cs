using System;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Reviewed fixed DTO-schema subset, never a peer-supplied schema or general JSON Schema engine.
    // WireEnvelope must validate syntax, integer range, depth and size first.
    public static class ReceiveMessages
    {
        private static readonly JObject Schema = JObject.Parse(ReceiveContractSchema.Json);
        private static bool Valid(JToken value, JToken rule)
        {
            if (rule.Type == JTokenType.Boolean) return (bool)rule;
            if (rule["$ref"] != null)
                return Valid(value, Schema["$defs"][(string)rule["$ref"].ToString().Split('/').Last()]);
            if (rule["anyOf"] is JArray alternatives && !alternatives.Any(part => Valid(value, part))) return false;
            if (rule["enum"] is JArray options && !options.Any(part => JToken.DeepEquals(value, part))) return false;
            if (rule["const"] != null && !JToken.DeepEquals(value, rule["const"])) return false;
            if (rule["type"] != null)
            {
                bool matches = (string)rule["type"] switch
                {
                    "null" => value.Type == JTokenType.Null,
                    "string" => value.Type == JTokenType.String,
                    "integer" => value.Type == JTokenType.Integer,
                    "boolean" => value.Type == JTokenType.Boolean,
                    "object" => value is JObject,
                    "array" => value is JArray,
                    _ => throw new InvalidOperationException("Unsupported fixture schema type")
                };
                if (!matches) return false;
            }
            if (rule["minimum"] != null && (long)value < (long)rule["minimum"]) return false;
            if (value is JObject obj)
            {
                if (rule["required"] is JArray required && required.Any(key => obj.Property((string)key) == null)) return false;
                if (rule["properties"] is JObject properties)
                {
                    foreach (var property in obj.Properties())
                    {
                        if (properties[property.Name] != null)
                        {
                            if (!Valid(property.Value, properties[property.Name])) return false;
                        }
                        else if (rule["additionalProperties"]?.Type == JTokenType.Boolean && !(bool)rule["additionalProperties"]) return false;
                    }
                }
            }
            if (value is JArray array)
            {
                if (rule["minItems"] != null && array.Count < (int)rule["minItems"]) return false;
                if (rule["maxItems"] != null && array.Count > (int)rule["maxItems"]) return false;
                var prefix = rule["prefixItems"] as JArray;
                for (int i = 0; i < array.Count; i++)
                {
                    var itemRule = prefix != null && i < prefix.Count ? prefix[i] : rule["items"];
                    if (itemRule != null && !Valid(array[i], itemRule)) return false;
                }
            }
            if (rule["allOf"] is JArray all && !all.All(part => Valid(value, part))) return false;
            if (rule["if"] != null && Valid(value, rule["if"]) && rule["then"] != null && !Valid(value, rule["then"])) return false;
            return true;
        }


        private static void Fail(string code) => throw new WireEnvelope.EnvelopeException(code);
        private static bool Unique(JArray items,string key) => items.All(item => !string.IsNullOrEmpty((string)item[key]))
            && items.Select(item=>(string)item[key]).Distinct(StringComparer.Ordinal).Count()==items.Count;
        public static JObject Parse(string text,string session,string viewer,long minimumRevision,bool fixtureMode=false)
        {
            var envelope=WireEnvelope.Parse(text);var body=(JObject)envelope["body"];
            string type=(string)envelope["message_type"];
            if(type!="snapshot" && type!="event" && type!="result")Fail("RECEIVE_UNSUPPORTED");
            if(body["fixture_only"]?.Type!=JTokenType.Boolean)Fail("RECEIVE_SHAPE");
            if((bool)body["fixture_only"]!=fixtureMode)Fail("RECEIVE_MODE");
            string receivedSession,receivedViewer;long revision;
            if(type=="event")
            {
                if(body.Count!=4 || body["session_id"]?.Type!=JTokenType.String || body["viewer_id"]?.Type!=JTokenType.String
                    || body["event"]==null || !Valid(body["event"],Schema["$defs"]["GameEvent"]))Fail("RECEIVE_SHAPE");
                receivedSession=(string)body["session_id"];receivedViewer=(string)body["viewer_id"];revision=(long)body["event"]["revision"];
            }
            else
            {
                if(body.Count!=2 || body["snapshot"]==null || !Valid(body["snapshot"],Schema["$defs"]["GameSnapshot"]))Fail("RECEIVE_SHAPE");
                var snapshot=(JObject)body["snapshot"];
                receivedSession=(string)snapshot["session_id"];receivedViewer=(string)snapshot["viewer_id"];revision=(long)snapshot["revision"];
                if(type=="result" && ((string)snapshot["status"]!="finished" || snapshot["result"].Type!=JTokenType.String
                    || string.IsNullOrEmpty((string)snapshot["result"])))Fail("RECEIVE_SHAPE");
                if(!Unique((JArray)snapshot["players"],"player_id") || !Unique((JArray)snapshot["objects"],"object_id")
                    || !Unique((JArray)snapshot["actions"],"action_id"))Fail("RECEIVE_CONTEXT");
                if(snapshot["decision"].Type!=JTokenType.Null && (string)snapshot["decision"]["player_id"]!=viewer)Fail("RECEIVE_VIEWER");
            }
            if(receivedSession!=session)Fail("RECEIVE_SESSION");
            if(receivedViewer!=viewer)Fail("RECEIVE_VIEWER");
            if(revision<minimumRevision)Fail("RECEIVE_REVISION");
            return envelope; // validated intermediate tree; immutable scene projection is a separate boundary
        }
    }
}

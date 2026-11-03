using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    // Fixture-only schema subset validator. Never accepts live messages or owns rules.
    public sealed class ProtocolFixtureTests
    {
        private static readonly string DirectoryPath = Path.GetFullPath(Path.Combine(Application.dataPath, "../../mtg_play/protocol"));
        private static readonly JObject Schema = JObject.Parse(File.ReadAllText(Path.Combine(DirectoryPath, "python-contracts-v1.schema.json")));

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

        [Test]
        public void SharedPositiveFixturesValidateAndRoundTripThroughGeneratedModels()
        {
            var document = JObject.Parse(File.ReadAllText(Path.Combine(DirectoryPath, "fixtures/python-baseline-v1.json")));
            var serializer = JsonSerializer.Create(new JsonSerializerSettings { MissingMemberHandling = MissingMemberHandling.Error, TypeNameHandling = TypeNameHandling.None });
            int count = 0;
            foreach (var entry in document["cases"])
            {
                string record = (string)entry["record"];
                var payload = entry["payload"];
                Assert.That(Valid(payload, Schema["$defs"][record]), Is.True, (string)entry["name"]);
                var type = typeof(Protocol.GameSnapshot).Assembly.GetType("Manaforge.Play.Protocol." + record, true);
                var model = payload.ToObject(type, serializer);
                Assert.That(JToken.DeepEquals(payload, JToken.FromObject(model, serializer)), Is.True, (string)entry["name"]);
                count++;
            }
            Assert.That(count, Is.GreaterThanOrEqualTo(9));
        }

        [Test]
        public void SharedNegativeFixturesAreRejectedBeforeDeserialization()
        {
            var document = JObject.Parse(File.ReadAllText(Path.Combine(DirectoryPath, "fixtures/python-negative-v1.json")));
            int count = 0;
            foreach (var entry in document["cases"])
            {
                Assert.That(Valid(entry["payload"], Schema["$defs"][(string)entry["record"]]), Is.False, (string)entry["name"]);
                count++;
            }
            Assert.That(count, Is.GreaterThanOrEqualTo(12));
        }
    }
}

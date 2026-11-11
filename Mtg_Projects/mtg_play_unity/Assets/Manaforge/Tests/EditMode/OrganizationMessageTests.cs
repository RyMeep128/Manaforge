using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class OrganizationMessageTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/organization-v1.json")));
        private static OrganizationMessages.Context Context(JObject fixture)
        {
            var seatRefs=fixture["seats"].ToObject<Dictionary<string,string>>();var objects=new Dictionary<string,string>();var seats=new Dictionary<string,string>();
            foreach(JObject binding in (JArray)fixture["bindings"]){string handle=(string)binding["handle"];objects.Add(handle,(string)binding["object_reference"]);seats.Add(handle,seatRefs[(string)binding["host_seat"]]);}
            var result=new OrganizationMessages.Context((string)fixture["match_epoch"],(string)fixture["viewer_id"],(long)fixture["basis_revision"],objects,seats,fixture["admitted"].ToObject<string[]>(),seatRefs.Values);
            objects.Clear();seats.Clear();seatRefs.Clear();return result;
        }
        [Test] public void SharedCorpusMatchesSchemaLexicalAndViewerRules()
        {
            var corpus=Corpus();var context=Context((JObject)corpus["context"]);
            foreach(JObject test in (JArray)corpus["cases"]){string name=(string)test["name"],raw=(string)test["text"];JObject parsed=null;
                try{parsed=OrganizationMessages.Parse(raw,context);}catch(IOException error){if((bool)test["valid"])Assert.Fail(name+": "+error.Message);}
                Assert.That(parsed!=null,Is.EqualTo((bool)test["valid"]),name);
                if(parsed!=null){Assert.That(JToken.DeepEquals(parsed,OrganizationMessages.Parse(OrganizationMessages.Serialize(parsed,context),context)),Is.True,name);Assert.Throws<WireEnvelope.EnvelopeException>(()=>WireEnvelope.Parse(raw),"Legacy accepted "+name);}
            }
        }
        [Test] public void GeneratedOperationCodecAndCapabilitySelectionStayExplicit()
        {
            var corpus=Corpus();var context=Context((JObject)corpus["context"]);
            string raw=(string)((JArray)corpus["cases"]).OfType<JObject>().Single(test=>(string)test["name"]=="command-create")["text"];
            var command=OrganizationMessages.Parse(raw,context)["body"].ToObject<OrganizationCommand>();
            Assert.That(command.operation.x,Is.EqualTo(250000));Assert.That(command.operation.y,Is.EqualTo(750000));
            string encoded=OrganizationMessages.EncodeOperation("encoded","new-command",3,command.operation,context);var body=OrganizationMessages.Parse(encoded,context)["body"];
            Assert.That((long)body["expected_organization_revision"],Is.EqualTo(3));Assert.That((long)body["basis_revision"],Is.EqualTo(7));Assert.That(encoded.Contains("SECRET"),Is.False);
            Assert.That(OrganizationMessages.Negotiate(new[]{1},new[]{1},true),Is.EqualTo(1));
            Assert.That(OrganizationMessages.Negotiate(new[]{1},new[]{1},false),Is.Zero);Assert.That(OrganizationMessages.Negotiate(new[]{1},new[]{2},true),Is.Zero);Assert.That(OrganizationMessages.Negotiate(null,new[]{1},true),Is.Zero);
            Assert.Throws<ArgumentException>(()=>new OrganizationMessages.Context("match","viewer-a",7,new Dictionary<string,string>{{"h1","private"}},new Dictionary<string,string>{{"h1","seat-a"}},new[]{"object-1"},new[]{"seat-a"}));
        }
        [Test] public void OversizedSnapshotSerializationRejectsInsteadOfTruncating()
        {
            var root=new JArray();var mappings=new JArray();var objects=new Dictionary<string,string>();var seats=new Dictionary<string,string>();string padding=new string('x',115);
            for(int i=0;i<1024;i++){string handle="h"+padding+i,reference="o"+padding+i;objects.Add(handle,reference);seats.Add(handle,"seat-a");root.Add(handle);mappings.Add(new JObject{["handle"]=handle,["object_reference"]=reference,["seat_id"]="seat-a"});}
            var context=new OrganizationMessages.Context("match","viewer-a",7,objects,seats,objects.Values,new[]{"seat-a"});
            var message=new JObject{["wire_version"]=1,["organization_version"]=1,["message_type"]="organization_snapshot",["message_id"]="large",["body"]=new JObject{["match_epoch"]="match",["viewer_id"]="viewer-a",["organization_revision"]=0,["basis_revision"]=7,["seats"]=new JArray(new JObject{["seat_id"]="seat-a",["root"]=root,["groups"]=new JArray()}),["mappings"]=mappings}};
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>OrganizationMessages.Serialize(message,context)).Code,Is.EqualTo("ORGANIZATION_SIZE"));
        }
    }
}

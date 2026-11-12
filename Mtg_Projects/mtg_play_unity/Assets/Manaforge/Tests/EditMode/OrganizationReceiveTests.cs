using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class OrganizationReceiveTests
    {
        private static JObject Envelope(string type,JObject body)=>new JObject{["wire_version"]=1,["organization_version"]=2,["message_type"]="organization_"+type,["message_id"]="packet",["body"]=body};
        private static string Caps()=>Envelope("capabilities",new JObject{["versions"]=new JArray(2)}).ToString();
        private static JObject Game(long revision,string reference="object-one")=>new JObject{["revision"]=revision,["status"]="active",["players"]=new JArray(new JObject{["player_id"]="viewer-a"},new JObject{["player_id"]="seat-b"}),["objects"]=new JArray(new JObject{["object_id"]=reference,["zone"]="battlefield",["hidden"]=false,["face_down"]=false,["controller_id"]="viewer-a"})};
        private static JObject Snapshot(long gameplay,long organization=1,string reference="object-one")=>Envelope("snapshot",new JObject{["match_epoch"]="match",["viewer_id"]="viewer-a",["gameplay_revision"]=gameplay,["organization_revision"]=organization,["basis_revision"]=gameplay,["seats"]=new JArray(new JObject{["seat_id"]="viewer-a",["root"]=new JArray(),["groups"]=new JArray(new JObject{["group_id"]="g",["name"]="Engine",["x"]=0,["y"]=0,["members"]=new JArray("h1")})},new JObject{["seat_id"]="seat-b",["root"]=new JArray(),["groups"]=new JArray()}),["mappings"]=new JArray(new JObject{["handle"]="h1",["object_reference"]=reference,["seat_id"]="viewer-a"})});
        [TestCase(2),TestCase(3)] public void SharedCorpusRetainsStrictV1SemanticRules(int version)
        {
            var corpus=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,$"../../mtg_play/protocol/fixtures/organization-v{version}.json")));var fixture=(JObject)corpus["context"];var refs=fixture["seats"].ToObject<Dictionary<string,string>>();var objects=new Dictionary<string,string>();var seats=new Dictionary<string,string>();
            foreach(var binding in fixture["bindings"]){objects.Add((string)binding["handle"],(string)binding["object_reference"]);seats.Add((string)binding["handle"],refs[(string)binding["host_seat"]]);}
            var context=new OrganizationMessages.Context("match","viewer-a",7,objects,seats,objects.Values,refs.Values);
            foreach(var test in corpus["cases"]){bool accepted=true;try{if(version==3)OrganizationV3Messages.Parse((string)test["text"],context);else OrganizationV2Messages.Parse((string)test["text"],context);}catch(IOException){accepted=false;}Assert.That(accepted,Is.EqualTo((bool)test["valid"]),(string)test["name"]);}
            Assert.Throws<WireEnvelope.EnvelopeException>(()=>OrganizationMessages.ParseContract(Snapshot(7).ToString()));var missing=Snapshot(7);((JObject)missing["body"]).Remove("gameplay_revision");Assert.Throws<WireEnvelope.EnvelopeException>(()=>OrganizationV2Messages.ParseContract(missing.ToString()));
        }
        [Test] public void FutureFramesWaitAndNewGameplayImmediatelyRevokesOldGeometry()
        {
            using var session=new ClientOrganizationSession("viewer-a",_=>{});Assert.That(session.Receive(Caps()),Is.Not.Null);session.Receive(Snapshot(7).ToString());Assert.That(session.ForRevision(7),Is.Null);
            session.ObserveGameplay(Game(7));var first=session.ForRevision(7);Assert.That(first.Groups.Single().Objects.Single(),Is.EqualTo("object-one"));
            session.ObserveGameplay(Game(8,"rotated"));Assert.That(session.ForRevision(7),Is.Null);Assert.That(session.ForRevision(8),Is.Null);session.Receive(Snapshot(7).ToString());Assert.That(session.ForRevision(8),Is.Null);
            session.Receive(Snapshot(8,1,"rotated").ToString());Assert.That(session.ForRevision(8).Handles["rotated"],Is.EqualTo("h1"));
            session.Receive(Snapshot(8,2,"rotated").ToString());session.Receive(Snapshot(8,1,"rotated").ToString());Assert.That(session.ForRevision(8).Revision,Is.EqualTo(2));
            var conflict=Snapshot(8,2,"rotated");conflict["body"]["seats"][0]["groups"][0]["name"]="Conflict";Assert.Throws<WireEnvelope.EnvelopeException>(()=>session.Receive(conflict.ToString()));
        }
        [Test] public void MappingsCannotAdmitHiddenForeignOrReplacedObjects()
        {
            using var session=new ClientOrganizationSession("viewer-a",_=>{});session.Receive(Caps());session.ObserveGameplay(Game(7));Assert.Throws<WireEnvelope.EnvelopeException>(()=>session.Receive(Snapshot(7,1,"unknown").ToString()));
            var hidden=Game(7);hidden["objects"][0]["hidden"]=true;session.ObserveGameplay(hidden);Assert.Throws<WireEnvelope.EnvelopeException>(()=>session.Receive(Snapshot(7).ToString()));
            var foreign=Game(7);foreign["objects"][0]["controller_id"]="seat-b";session.ObserveGameplay(foreign);Assert.Throws<WireEnvelope.EnvelopeException>(()=>session.Receive(Snapshot(7).ToString()));
        }
        [Test] public async Task ReceiptsCompleteOnlyKnownPendingCommandsWithoutApplyingHistoricalState()
        {
            var written=new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);using var session=new ClientOrganizationSession("viewer-a",raw=>written.TrySetResult(raw));session.Receive(Caps());session.ObserveGameplay(Game(7));session.Receive(Snapshot(7).ToString());var frame=session.ForRevision(7);
            var operation=new JObject{["kind"]="rename",["group_id"]="g",["name"]="Changed",["x"]=JValue.CreateNull(),["y"]=JValue.CreateNull(),["index"]=JValue.CreateNull(),["members"]=new JArray()};var pending=session.Submit(frame,operation);Assert.That(await session.Submit(frame,operation),Is.False);
            Assert.That(await Task.WhenAny(written.Task,Task.Delay(3000)),Is.SameAs(written.Task));var command=JObject.Parse(await written.Task);session.ObserveGameplay(Game(8,"rotated"));session.Receive(Snapshot(8,1,"rotated").ToString());
            var receipt=Envelope("receipt",new JObject{["match_epoch"]="match",["command_id"]=command["body"]["command_id"],["outcome"]="applied",["organization_revision"]=1,["basis_revision"]=7,["reason_code"]=JValue.CreateNull()});session.Receive(receipt.ToString());Assert.That(await pending,Is.True);Assert.That(session.ForRevision(8).Groups.Single().Objects.Single(),Is.EqualTo("rotated"));Assert.That(session.ForRevision(7),Is.Null);
            Assert.Throws<WireEnvelope.EnvelopeException>(()=>session.Receive(receipt.ToString()));Assert.That(await session.Submit(frame,operation),Is.False);session.Dispose();Assert.That(session.ForRevision(8),Is.Null);
        }
        [Test] public void NewestFutureSnapshotWinsAndDisposalCannotResurrectIt()
        {
            using var session=new ClientOrganizationSession("viewer-a",_=>{});session.Receive(Caps());session.Receive(Snapshot(8,2,"eight").ToString());session.Receive(Snapshot(7,3,"seven").ToString());session.ObserveGameplay(Game(8,"eight"));Assert.That(session.ForRevision(8).Revision,Is.EqualTo(2));session.Dispose();session.ObserveGameplay(Game(9));Assert.That(session.ForRevision(9),Is.Null);
        }
    }
}

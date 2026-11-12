using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
namespace Manaforge.Play.Protocol
{
    // CPU-only, session-scoped correlation mailbox and independent single-command tracker.
    public sealed class ClientOrganizationSession : IDisposable
    {
        private readonly object gate=new object();private readonly string viewer;private readonly Action<string> write;
        private JObject game,currentBody,future;private ProjectedOrganizationFrame current;private string epoch,pending;
        private TaskCompletionSource<bool> receipt;private bool negotiated,stopped;private int version=2;
        public void ConfigureVersion(int value){lock(gate){if(negotiated || value!=2 && value!=3)throw new System.InvalidOperationException("ORGANIZATION_VERSION");version=value;}}
        public int Version=>version;
        private JObject ParseContract(string raw)=>version==3?OrganizationV3Messages.ParseContract(raw):OrganizationV2Messages.ParseContract(raw);
        public ClientOrganizationSession(string viewer,Action<string> write){this.viewer=viewer;this.write=write;}
        public bool Pending {get{lock(gate)return pending!=null;}}
        public string LastError {get;private set;}
        public ProjectedOrganizationFrame ForRevision(long revision){lock(gate)return !stopped && current?.GameplayRevision==revision?current:null;}
        internal void AdvanceMinimum(long minimum){lock(gate){if(current!=null && current.GameplayRevision<minimum){current=null;currentBody=null;}if(game!=null && (long)game["revision"]<minimum)game=null;if(future!=null && (long)future["gameplay_revision"]<minimum)future=null;}}
        public void ObserveGameplay(JObject snapshot)
        {
            lock(gate){if(stopped)return;game=(JObject)snapshot.DeepClone();if(current?.GameplayRevision!=(long)game["revision"]){current=null;currentBody=null;}
                if((string)game["status"]!="active"){current=null;future=null;return;}
                if(future!=null && (long)future["gameplay_revision"]<=(long)game["revision"]){var body=future;future=null;Admit(body);}}
        }
        public string Receive(string raw)
        {
            var message=ParseContract(raw);string type=(string)message["message_type"];var body=(JObject)message["body"];
            lock(gate){if(stopped)throw new WireEnvelope.EnvelopeException("ORGANIZATION_STOPPED");
                if(type=="organization_capabilities"){
                    if(!body["versions"].Values<int>().Contains(version))return null;if(negotiated)return null;negotiated=true;
                    return new JObject{["wire_version"]=1,["organization_version"]=version,["message_type"]="organization_capabilities",["message_id"]="organization-capabilities",["body"]=new JObject{["versions"]=new JArray(version)}}.ToString(Formatting.None);
                }
                if(!negotiated)throw new WireEnvelope.EnvelopeException("ORGANIZATION_NOT_NEGOTIATED");
                if(type=="organization_receipt"){
                    if(version==3)OrganizationV3Messages.ParseReceipt(raw,epoch,pending==null?Array.Empty<string>():new[]{pending});else OrganizationV2Messages.ParseReceipt(raw,epoch,pending==null?Array.Empty<string>():new[]{pending});LastError=(string)body["reason_code"];pending=null;receipt?.TrySetResult((string)body["outcome"]=="applied");receipt=null;return null;
                }
                if(type!="organization_snapshot" || (string)body["viewer_id"]!=viewer)throw new WireEnvelope.EnvelopeException("ORGANIZATION_CONTEXT");
                string match=(string)body["match_epoch"];if(epoch!=null && epoch!=match)throw new WireEnvelope.EnvelopeException("ORGANIZATION_EPOCH");epoch=match;
                long revision=(long)body["gameplay_revision"];
                if(game==null || revision>(long)game["revision"]){if(future!=null && revision==(long)future["gameplay_revision"] && (long)body["organization_revision"]==(long)future["organization_revision"] && !JToken.DeepEquals(body,future))throw new WireEnvelope.EnvelopeException("ORGANIZATION_CONFLICT");if(future==null || revision>(long)future["gameplay_revision"] || revision==(long)future["gameplay_revision"] && (long)body["organization_revision"]>(long)future["organization_revision"])future=(JObject)body.DeepClone();return null;}
                Admit(body);return null;
            }
        }
        private void Admit(JObject body)
        {
            if(game==null || (long)body["gameplay_revision"]!=(long)game["revision"] || (string)game["status"]!="active")return;
            if(current!=null && (long)body["organization_revision"]<current.Revision)return;
            if(currentBody!=null && (long)body["organization_revision"]==current.Revision){if(!JToken.DeepEquals(body,currentBody))throw new WireEnvelope.EnvelopeException("ORGANIZATION_CONFLICT");return;}
            var admitted=game["objects"].Where(o=>(string)o["zone"]=="battlefield" && (bool?)o["hidden"]==false && (bool?)o["face_down"]==false).ToDictionary(o=>(string)o["object_id"],o=>(string)o["controller_id"],StringComparer.Ordinal);
            var objects=new Dictionary<string,string>();var seats=new Dictionary<string,string>();foreach(var mapping in body["mappings"]){string handle=(string)mapping["handle"],reference=(string)mapping["object_reference"],seat=(string)mapping["seat_id"];if(!admitted.TryGetValue(reference,out var owner) || owner!=seat)throw new WireEnvelope.EnvelopeException("ORGANIZATION_CONTEXT");objects.Add(handle,reference);seats.Add(handle,seat);}
            var context=new OrganizationMessages.Context(epoch,viewer,(long)body["basis_revision"],objects,seats,admitted.Keys,game["players"].Select(p=>(string)p["player_id"]));
            var envelope=new JObject{["wire_version"]=1,["organization_version"]=version,["message_type"]="organization_snapshot",["message_id"]="validate",["body"]=body};if(version==3)OrganizationV3Messages.Parse(envelope.ToString(Formatting.None),context);else OrganizationV2Messages.Parse(envelope.ToString(Formatting.None),context);
            currentBody=(JObject)body.DeepClone();current=new ProjectedOrganizationFrame(currentBody);
        }
        public Task<bool> Submit(ProjectedOrganizationFrame frame,JObject operation)
        {
            string wire;Task<bool> result;
            lock(gate){if(stopped || !negotiated || !ReferenceEquals(frame,current) || pending!=null)return Task.FromResult(false);
                if(version==3 && operation["presentation_mode"]==null){operation=(JObject)operation.DeepClone();operation["presentation_mode"]=JValue.CreateNull();}
                pending=Guid.NewGuid().ToString("N");receipt=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);result=receipt.Task;LastError=null;
                wire=new JObject{["wire_version"]=1,["organization_version"]=version,["message_type"]="organization_command",["message_id"]=Guid.NewGuid().ToString("N"),["body"]=new JObject{["match_epoch"]=frame.Epoch,["command_id"]=pending,["expected_organization_revision"]=frame.Revision,["basis_revision"]=frame.Basis,["operation"]=operation.DeepClone()}}.ToString(Formatting.None);
                try{OrganizationV2Messages.ParseContract(wire);}catch{pending=null;receipt=null;throw;}
            }
            Task.Run(()=>{try{write(wire);}catch{Dispose();}});return result;
        }
        public void Dispose(){lock(gate){if(stopped)return;stopped=true;game=currentBody=future=null;current=null;pending=null;LastError="ORGANIZATION_DISCONNECTED";receipt?.TrySetResult(false);receipt=null;}}
    }
}

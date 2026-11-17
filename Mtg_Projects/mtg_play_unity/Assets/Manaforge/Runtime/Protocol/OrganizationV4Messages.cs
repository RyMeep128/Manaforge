using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
namespace Manaforge.Play.Protocol
{
    // V4 stores free positions only for admitted, ungrouped battlefield identities.
    public static class OrganizationV4Messages
    {
        public static JObject ParseContract(string raw)=>OrganizationMessages.ParseV4Contract(raw);
        private static string Legacy(JObject message){
            var copy=(JObject)message.DeepClone();copy["organization_version"]=3;var body=(JObject)copy["body"];
            if(body["versions"]!=null)body["versions"]=new JArray(3);
            if(body["seats"] is JArray seats)foreach(JObject seat in seats)seat.Remove("placements");
            if(body["operation"] is JObject op && (string)op["kind"]=="place"){op["kind"]="move";op["x"]=op["y"]=JValue.CreateNull();op["index"]=0;}
            return copy.ToString(Formatting.None);
        }
        public static JObject Parse(string raw,OrganizationMessages.Context context){
            var message=ParseContract(raw);OrganizationV3Messages.Parse(Legacy(message),context);
            if(message["body"]["seats"] is JArray seats)foreach(JObject seat in seats){
                var roots=new HashSet<string>(seat["root"].Values<string>());var seen=new HashSet<string>();
                foreach(var placement in seat["placements"]){string handle=(string)placement["handle"];if(!roots.Contains(handle) || !seen.Add(handle))throw new WireEnvelope.EnvelopeException("ORGANIZATION_CONTEXT");}
            }
            return message;
        }
        public static JObject ParseReceipt(string raw,string epoch,IEnumerable<string> pending){var message=ParseContract(raw);OrganizationV3Messages.ParseReceipt(Legacy(message),epoch,pending);return message;}
    }
}

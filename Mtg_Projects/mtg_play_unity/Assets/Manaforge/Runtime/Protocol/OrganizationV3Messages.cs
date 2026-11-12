using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
namespace Manaforge.Play.Protocol
{
    public static class OrganizationV3Messages
    {
        public static JObject ParseContract(string raw)=>OrganizationMessages.ParseV3Contract(raw);
        private static string Legacy(JObject message){
            var copy=(JObject)message.DeepClone();copy["organization_version"]=1;var body=(JObject)copy["body"];body.Remove("gameplay_revision");
            if(body["seats"] is JArray seats)foreach(var seat in seats)foreach(JObject group in seat["groups"])group.Remove("presentation_mode");
            if(body["operation"] is JObject op){op.Remove("presentation_mode");if((string)op["kind"]=="set_mode"){op["kind"]="rename";op["name"]="Mode";}}
            return copy.ToString(Formatting.None);
        }
        public static JObject Parse(string raw,OrganizationMessages.Context context){var message=ParseContract(raw);OrganizationMessages.Parse(Legacy(message),context);return message;}
        public static JObject ParseReceipt(string raw,string epoch,IEnumerable<string> pending){var message=ParseContract(raw);OrganizationMessages.ParseReceipt(Legacy(message),epoch,pending);return message;}
    }
}

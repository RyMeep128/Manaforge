using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
namespace Manaforge.Play.Protocol
{
    public static class OrganizationV2Messages
    {
        public static JObject ParseContract(string raw)=>OrganizationMessages.ParseV2Contract(raw);
        private static string Legacy(JObject message){var copy=(JObject)message.DeepClone();copy["organization_version"]=1;((JObject)copy["body"]).Remove("gameplay_revision");return copy.ToString(Formatting.None);}
        public static JObject Parse(string raw,OrganizationMessages.Context context){var message=ParseContract(raw);OrganizationMessages.Parse(Legacy(message),context);return message;}
        public static JObject ParseReceipt(string raw,string epoch,IEnumerable<string> pending){var message=ParseContract(raw);OrganizationMessages.ParseReceipt(Legacy(message),epoch,pending);return message;}
    }
}

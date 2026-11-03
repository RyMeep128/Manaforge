using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Authenticated gateway-to-viewer terminal channel errors only; never command outcomes.
    public static class SessionErrors
    {
        private static bool Id(string value) => value != null && Regex.IsMatch(value, @"\A[A-Za-z0-9_.:-]{1,128}\z");
        private static bool Id(JToken value) => value?.Type == JTokenType.String && Id((string)value);
        private static void Fail(string code) => throw new WireEnvelope.EnvelopeException(code);
        public static string Parse(string text, string session, string viewer)
        {
            if (!Id(session) || !Id(viewer)) Fail("ERROR_CONTEXT");
            var envelope = WireEnvelope.Parse(text);
            if ((string)envelope["message_type"] != "error") Fail("ERROR_UNSUPPORTED");
            var body = (JObject)envelope["body"];
            if (body.Count != 4 || !Id(body["session_id"]) || !Id(body["viewer_id"])
                || body["terminal"]?.Type != JTokenType.Boolean || !(bool)body["terminal"]
                || body["code"]?.Type != JTokenType.String) Fail("ERROR_SHAPE");
            string code = (string)body["code"];
            switch (code)
            {
                case "PROTOCOL_INCOMPATIBLE": case "SESSION_CLOSED": case "SESSION_FAILED":
                case "ENGINE_UNAVAILABLE": case "RECEIVE_OVERFLOW": case "INTERNAL_ERROR": break;
                default: Fail("ERROR_SHAPE"); break;
            }
            if ((string)body["session_id"] != session) Fail("ERROR_SESSION");
            if ((string)body["viewer_id"] != viewer) Fail("ERROR_VIEWER");
            return code; // fixed safe display category; no mutable peer content retained
        }
    }
}

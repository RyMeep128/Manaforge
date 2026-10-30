using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // First vertical slice only: perform, acknowledgements, viewer shutdown.
    public static class WireMessages
    {
        private static readonly string[] Rejections = { "SESSION_MISMATCH", "VIEWER_MISMATCH", "STALE_REVISION",
            "STALE_DECISION", "ACTION_UNAVAILABLE", "COMMAND_PENDING", "ENGINE_REJECTED" };
        private static bool Id(JToken token) => token?.Type == JTokenType.String
            && Regex.IsMatch((string)token, @"\A[A-Za-z0-9_.:-]{1,128}\z");
        private static bool Revision(JToken token) => token?.Type == JTokenType.Integer && (long)token >= 0;
        private static bool Keys(JObject body, params string[] names) => body.Count == names.Length && names.All(n => body.Property(n) != null);
        private static void Fail() => throw new WireEnvelope.EnvelopeException("MESSAGE_INVALID");

        public static JObject Parse(string text)
        {
            var envelope = WireEnvelope.Parse(text);
            var body = (JObject)envelope["body"];
            string type = (string)envelope["message_type"];
            if (type == "command")
            {
                if (!Keys(body, "session_id", "viewer_id", "revision", "operation", "decision_id", "action_id")
                    || !Id(body["session_id"]) || !Id(body["viewer_id"]) || !Revision(body["revision"])
                    || body["operation"]?.Type != JTokenType.String || (string)body["operation"] != "perform"
                    || !Id(body["decision_id"]) || !Id(body["action_id"])) Fail();
            }
            else if (type == "ack")
            {
                if (!Keys(body, "session_id", "viewer_id", "command_id", "request_revision", "outcome", "code")
                    || !Id(body["session_id"]) || !Id(body["viewer_id"]) || !(Id(body["command_id"]) && Regex.IsMatch((string)body["command_id"], @"\A[A-Za-z0-9_-]{1,128}\z"))
                    || !Revision(body["request_revision"]) || body["outcome"]?.Type != JTokenType.String) Fail();
                string outcome = (string)body["outcome"];
                bool noCode = body["code"]?.Type == JTokenType.Null;
                string code = body["code"]?.Type == JTokenType.String ? (string)body["code"] : null;
                if (!((outcome == "submitted" || outcome == "confirmed") && noCode)
                    && !(outcome == "rejected" && Array.IndexOf(Rejections, code) >= 0)
                    && !(outcome == "uncertain" && code == "COMMAND_UNCERTAIN")) Fail();
            }
            else if (type == "shutdown")
            {
                if (!Keys(body, "session_id", "viewer_id", "reason") || !Id(body["session_id"]) || !Id(body["viewer_id"])
                    || body["reason"]?.Type != JTokenType.String
                    || Array.IndexOf(new[] { "client_close", "cancel", "startup_failed" }, (string)body["reason"]) < 0) Fail();
            }
            else throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
            return envelope;
        }

        // Compare only against an authenticated, viewer-scoped current engine decision.
        // Caller must serialize this with execution; null means no mismatch, never confirmation.
        public static string CheckCurrent(string commandText, string session, string authenticatedViewer,
            long revision, string decision, IEnumerable<string> allowedActions)
        {
            var envelope = Parse(commandText);
            if ((string)envelope["message_type"] != "command") throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
            var body = (JObject)envelope["body"];
            if ((string)body["session_id"] != session) return "SESSION_MISMATCH";
            if ((string)body["viewer_id"] != authenticatedViewer) return "VIEWER_MISMATCH";
            if ((long)body["revision"] != revision) return "STALE_REVISION";
            if ((string)body["decision_id"] != decision) return "STALE_DECISION";
            if (!allowedActions.Contains((string)body["action_id"])) return "ACTION_UNAVAILABLE";
            return null;
        }
    }
}

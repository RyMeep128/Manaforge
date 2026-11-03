using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Shared existing decision-family shapes, acknowledgements and viewer shutdown; no rules dispatch.
    public static class WireMessages
    {
        public const int MaxAmountValues = 1024;
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
                if (!Id(body["session_id"]) || !Id(body["viewer_id"]) || !Revision(body["revision"])
                    || !Id(body["decision_id"]) || body["operation"]?.Type != JTokenType.String) Fail();
                string argument = null;
                switch ((string)body["operation"])
                {
                    case "perform": argument = "action_id"; if (!Id(body[argument])) Fail(); break;
                    case "choose": argument = "option_id"; if (!Id(body[argument])) Fail(); break;
                    case "select_mana_source": argument = "object_id"; if (!Id(body[argument])) Fail(); break;
                    case "choose_number": argument = "value"; if (body[argument]?.Type != JTokenType.Integer) Fail(); break;
                    case "choose_amounts":
                        argument = "values";
                        if (!(body[argument] is JArray amounts) || amounts.Count > MaxAmountValues || amounts.Any(v => v.Type != JTokenType.Integer)) Fail();
                        break;
                    case "finish_selection": case "cancel": break;
                    default: Fail(); break;
                }
                var required = new[] { "session_id", "viewer_id", "revision", "operation", "decision_id" };
                if (!Keys(body, argument == null ? required : required.Concat(new[] { argument }).ToArray())) Fail();
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

        private static string Binding(JObject body, string session, string viewer, long revision, string decision)
        {
            if ((string)body["session_id"] != session) return "SESSION_MISMATCH";
            if ((string)body["viewer_id"] != viewer) return "VIEWER_MISMATCH";
            if ((long)body["revision"] != revision) return "STALE_REVISION";
            if ((string)body["decision_id"] != decision) return "STALE_DECISION";
            return null;
        }
        // Context only. A match does NOT authorize a choice, numeric value, source or cancellation.
        public static string CheckBinding(string text, string session, string viewer, long revision, string decision)
        {
            var envelope = Parse(text);
            if ((string)envelope["message_type"] != "command") throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
            return Binding((JObject)envelope["body"], session, viewer, revision, decision);
        }
        // Preserve the existing perform-only action comparison; never silently admit another family.
        public static string CheckCurrent(string commandText, string session, string authenticatedViewer,
            long revision, string decision, IEnumerable<string> allowedActions)
        {
            var envelope = Parse(commandText);
            if ((string)envelope["message_type"] != "command" || (string)envelope["body"]["operation"] != "perform")
                throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
            var body = (JObject)envelope["body"];
            string mismatch = Binding(body, session, authenticatedViewer, revision, decision);
            if (mismatch != null) return mismatch;
            return allowedActions.Contains((string)body["action_id"]) ? null : "ACTION_UNAVAILABLE";
        }
    }
}

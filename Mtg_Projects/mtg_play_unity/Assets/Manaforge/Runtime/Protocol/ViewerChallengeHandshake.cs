using System;
using System.Diagnostics;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    // Pre-auth hello subprotocol. Peer nonce fields never replace trusted session/viewer/pin context.
    public static class ViewerChallengeHandshake
    {
        private static void Fail()=>throw new WireEnvelope.EnvelopeException("AUTH_FAILED");
        private static string Nonce(JToken token)
        {if(token?.Type!=JTokenType.String || !Regex.IsMatch((string)token,@"\A[0-9a-f]{64}\z"))Fail();return (string)token;}
        private static JObject Body(string text,bool response)
        {
            if(text==null || new UTF8Encoding(false,true).GetByteCount(text)>4096)Fail();
            var value=WireEnvelope.Parse(text);var body=(JObject)value["body"];
            var fields=response?new[]{"auth_exchange_version","stage","server_nonce","client_nonce"}:new[]{"auth_exchange_version","stage","server_nonce"};
            if((string)value["message_type"]!="hello" || (string)value["message_id"]!=(response?"auth-nonce":"auth-challenge")
                || body.Count!=fields.Length || fields.Any(f=>body.Property(f)==null)
                || body["auth_exchange_version"]?.Type!=JTokenType.Integer || (long)body["auth_exchange_version"]!=1
                || body["stage"]?.Type!=JTokenType.String || (string)body["stage"]!=(response?"client_nonce":"gateway_challenge"))Fail();
            Nonce(body["server_nonce"]);if(response)Nonce(body["client_nonce"]);return body;
        }
        private static string Message(string server,string client=null)
        {
            Nonce(new JValue(server));if(client!=null)Nonce(new JValue(client));
            var body=new JObject{["auth_exchange_version"]=1,["stage"]=client==null?"gateway_challenge":"client_nonce",["server_nonce"]=server};
            if(client!=null)body["client_nonce"]=client;
            return new JObject{["wire_version"]=1,["message_type"]="hello",["message_id"]=client==null?"auth-challenge":"auth-nonce",["body"]=body}.ToString(Formatting.None);
        }
        public static string Challenge(string server)=>Message(server);
        public static string Response(string server,string client)=>Message(server,client??throw new ArgumentNullException(nameof(client)));
        public static string ReadChallenge(string text)=>Nonce(Body(text,false)["server_nonce"]);
        public static string ReadResponse(string text,string expectedServer)
        {var body=Body(text,true);if(Nonce(body["server_nonce"])!=expectedServer)Fail();return Nonce(body["client_nonce"]);}
        private static string Fresh()
        {var bytes=new byte[32];try{using(var random=RandomNumberGenerator.Create())random.GetBytes(bytes);return BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant();}finally{Array.Clear(bytes,0,bytes.Length);}}
        private static string Hello(ViewerBootstrap expected,string role,string server,string client)=>new JObject{
            ["wire_version"]=1,["message_type"]="hello",["message_id"]="auth-"+role,
            ["body"]=new JObject{["protocol_version"]=1,["engine_version"]=expected.EngineVersion,["artifact_manifest_sha256"]=expected.ArtifactManifestSha256,
                ["session_id"]=expected.SessionId,["viewer_id"]=expected.ViewerId,["server_nonce"]=server,["client_nonce"]=client,["role"]=role,["proof"]=new string('0',64)}}.ToString(Formatting.None);
        private static int Remaining(Stopwatch timer,int budget,CancellationToken cancellation)
        {if(cancellation.IsCancellationRequested)throw new WireEnvelope.EnvelopeException("AUTH_CANCELLED");double left=budget-timer.Elapsed.TotalMilliseconds;if(left<=0)throw new WireEnvelope.EnvelopeException("AUTH_TIMEOUT");return Math.Max(1,(int)Math.Ceiling(left));}
        // Worker-only. Valid budget transfers transport ownership and consumes the bootstrap key once.
        public static ClientSessionChannel Open(LoopbackFrameReader owned,ViewerBootstrap expected,int milliseconds=5000,CancellationToken cancellation=default,bool fixtureMode=false)
        {
            if(owned==null)throw new ArgumentNullException(nameof(owned));
            if(milliseconds<1 || milliseconds>60000)throw new ArgumentOutOfRangeException(nameof(milliseconds));
            var timer=Stopwatch.StartNew();byte[] key=null;ClientSessionChannel channel=null;
            try {
                if(!owned.BeginViewerChallenge() || expected==null)Fail();
                Remaining(timer,milliseconds,cancellation);key=expected.TakeViewerKey();
                string server=ReadChallenge(owned.Read(Remaining(timer,milliseconds,cancellation),cancellation)),client=Fresh();
                owned.Write(Response(server,client),Remaining(timer,milliseconds,cancellation),cancellation);
                channel=ClientHandshake.Open(owned,Hello(expected,"client",server,client),Hello(expected,"gateway",server,client),key,Remaining(timer,milliseconds,cancellation),cancellation,fixtureMode);
                Remaining(timer,milliseconds,cancellation);return channel;
            }
            catch(Exception error) {
                channel?.Dispose();owned.Dispose();string code="AUTH_FAILED";
                if(cancellation.IsCancellationRequested)code="AUTH_CANCELLED";
                else if(error is TextFrame.FrameException frame && frame.Code.Contains("TIMEOUT"))code="AUTH_TIMEOUT";
                else if(error is WireEnvelope.EnvelopeException envelope && (envelope.Code=="AUTH_TIMEOUT" || envelope.Code=="AUTH_CANCELLED"))code=envelope.Code;
                throw new WireEnvelope.EnvelopeException(code);
            }
            finally{if(key!=null)Array.Clear(key,0,key.Length);}
        }
    }
}

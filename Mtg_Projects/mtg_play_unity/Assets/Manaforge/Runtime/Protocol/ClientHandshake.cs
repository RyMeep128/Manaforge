using System;
using System.Diagnostics;
using System.Threading;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play.Protocol
{
    public static class ClientHandshake
    {
        // Caller supplies trusted launch expectations and fresh per-connection nonces, never peer-derived pins.
        // Budget validation precedes transfer; thereafter this method owns the transport on success AND failure.
        public static ClientSessionChannel Open(LoopbackFrameReader ownedTransport,string clientTemplate,string expectedGateway,
            byte[] viewerKey,int milliseconds=5000,CancellationToken cancellation=default,bool fixtureMode=false)
        {
            if(ownedTransport==null)throw new ArgumentNullException(nameof(ownedTransport));
            if(milliseconds<1 || milliseconds>60000)throw new ArgumentOutOfRangeException(nameof(milliseconds));
            var timer=Stopwatch.StartNew();byte[] key=null;
            try
            {
                if(!ownedTransport.BeginViewerHandshake())throw new WireEnvelope.EnvelopeException("AUTH_FAILED");
                cancellation.ThrowIfCancellationRequested();
                if(viewerKey==null || viewerKey.Length!=32)throw new WireEnvelope.EnvelopeException("AUTH_FAILED");
                key=(byte[])viewerKey.Clone();
                var client=ViewerAuthentication.Parse(clientTemplate);var gateway=ViewerAuthentication.Parse(expectedGateway);
                if((string)client["body"]["role"]!="client" || (string)gateway["body"]["role"]!="gateway")throw new WireEnvelope.EnvelopeException("AUTH_FAILED");
                foreach(string field in new[]{"protocol_version","engine_version","artifact_manifest_sha256","session_id","viewer_id","server_nonce","client_nonce"})
                    if(!JToken.DeepEquals(client["body"][field],gateway["body"][field]))throw new WireEnvelope.EnvelopeException("AUTH_FAILED");
                using var verifier=new ViewerAuthentication.Verifier(expectedGateway,key);
                client["body"]["proof"]=ViewerAuthentication.ComputeProof(clientTemplate,key);
                ownedTransport.Write(client.ToString(Formatting.None),Remaining(timer,milliseconds,cancellation),cancellation);
                string reply=ownedTransport.Read(Remaining(timer,milliseconds,cancellation),cancellation);
                if(!verifier.Verify(reply))throw new WireEnvelope.EnvelopeException("AUTH_FAILED");
                Remaining(timer,milliseconds,cancellation);
                return new ClientSessionChannel(ownedTransport,(string)client["body"]["session_id"],(string)client["body"]["viewer_id"],fixtureMode);
            }
            catch(OperationCanceledException){ownedTransport.Dispose();throw new WireEnvelope.EnvelopeException("AUTH_CANCELLED");}
            catch(TextFrame.FrameException error)
            {
                ownedTransport.Dispose();
                string code=cancellation.IsCancellationRequested?"AUTH_CANCELLED":
                    error.Code=="FRAME_TIMEOUT" || error.Code=="FRAME_WRITE_TIMEOUT"?"AUTH_TIMEOUT":"AUTH_FAILED";
                throw new WireEnvelope.EnvelopeException(code);
            }
            catch(WireEnvelope.EnvelopeException error)
            {
                ownedTransport.Dispose();
                string code=cancellation.IsCancellationRequested?"AUTH_CANCELLED":error.Code=="AUTH_TIMEOUT"?"AUTH_TIMEOUT":"AUTH_FAILED";
                throw new WireEnvelope.EnvelopeException(code);
            }
            catch{ownedTransport.Dispose();throw new WireEnvelope.EnvelopeException("AUTH_FAILED");}
            finally{if(key!=null)Array.Clear(key,0,key.Length);}
        }
        private static int Remaining(Stopwatch timer,int budget,CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();double remaining=budget-timer.Elapsed.TotalMilliseconds;
            if(remaining<=0)throw new WireEnvelope.EnvelopeException("AUTH_TIMEOUT");
            return Math.Max(1,(int)Math.Ceiling(remaining));
        }
    }
}

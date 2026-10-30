using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class ClientHandshakeTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/viewer-auth-v1.json")));
        private static JObject Client()=>(JObject)Corpus()["positive"][0]["envelope"].DeepClone();
        private static JObject Gateway()=>(JObject)Corpus()["positive"][1]["envelope"].DeepClone();
        private static byte[] Key()=>Enumerable.Range(0,32).Select(i=>(byte)i).ToArray();
        private sealed class Pair : IDisposable
        {
            public readonly TcpClient Peer;public readonly LoopbackFrameReader Transport;
            public Pair(){var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();try{
                Peer=new TcpClient(AddressFamily.InterNetwork);Peer.ReceiveTimeout=2000;
                Assert.That(Peer.ConnectAsync(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port).Wait(2000),Is.True);
                Transport=new LoopbackFrameReader(listener.AcceptSocket());
            }catch{Peer?.Dispose();throw;}finally{listener.Stop();}}
            public void Dispose(){Transport.Dispose();Peer.Dispose();}
        }
        private static Task Reply(Pair p,JObject response,byte[] key,bool verify=true)=>Task.Run(()=>{
            string hello=TextFrame.Read(p.Peer.GetStream());
            if(verify)using(var verifier=new ViewerAuthentication.Verifier(Client().ToString(),key))Assert.That(verifier.Verify(hello),Is.True);
            TextFrame.Write(p.Peer.GetStream(),response.ToString());
        });
        private static string Failure(Action open){var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>open());Assert.That(error.Message,Is.EqualTo(error.Code));return error.Code;}
        [Test] public void ValidGatewayProofReturnsAnOwnerAndLeavesCallerKeyOwnershipIntact()
        {
            using var p=new Pair();var key=Key();var peer=Reply(p,Gateway(),key);
            using var owner=ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),key);
            Assert.That(peer.Wait(2000),Is.True);Assert.That(owner.State,Is.EqualTo(ClientChannelState.Active));Assert.That(owner.CanSubmit,Is.False);
            Assert.That(key,Is.EqualTo(Key()));Assert.That(p.Transport.IsClosed,Is.False);
        }
        [TestCase("proof")] [TestCase("pin")] [TestCase("viewer")] [TestCase("reflection")] [TestCase("data")]
        public void UnverifiedPeerContentCannotReplaceTrustedExpectedContext(string defect)
        {
            using var p=new Pair();var key=Key();var response=Gateway();
            if(defect=="proof")response["body"]["proof"]=new string('0',64);
            if(defect=="pin" || defect=="viewer"){
                response["body"][defect=="pin"?"artifact_manifest_sha256":"viewer_id"]=defect=="pin"?new string('b',64):"other";
                response["body"]["proof"]=ViewerAuthentication.ComputeProof(response.ToString(),key);
            }
            if(defect=="reflection")response=Client();if(defect=="data")response["message_type"]="snapshot";
            var peer=Reply(p,response,key);
            Assert.That(Failure(()=>ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),key)),Is.EqualTo("AUTH_FAILED"));
            Assert.That(p.Transport.IsClosed,Is.True);Assert.That(peer.Wait(2000),Is.True);
        }
        private static void HeldProof(Pair p,string expectedCode,int budget,CancellationToken token)
        {
            using var release=new ManualResetEventSlim();var peer=Task.Run(()=>{TextFrame.Read(p.Peer.GetStream());release.Wait(2000);});
            try{Assert.That(Failure(()=>ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),Key(),budget,token)),Is.EqualTo(expectedCode));Assert.That(p.Transport.IsClosed,Is.True);}
            finally{release.Set();Assert.That(peer.Wait(2000),Is.True);}
        }
        [Test] public void GatewayProofWaitUsesTheHandshakeDeadline(){using var p=new Pair();HeldProof(p,"AUTH_TIMEOUT",120,CancellationToken.None);}
        [Test] public void CancellationClosesAnAttemptWaitingForProof(){using var p=new Pair();using var stop=new CancellationTokenSource();stop.CancelAfter(60);HeldProof(p,"AUTH_CANCELLED",5000,stop.Token);}
        [Test] public void InconsistentTrustedTemplatesFailBeforeWriting()
        {
            using var p=new Pair();var expected=Gateway();expected["body"]["session_id"]="different";
            Assert.That(Failure(()=>ClientHandshake.Open(p.Transport,Client().ToString(),expected.ToString(),Key())),Is.EqualTo("AUTH_FAILED"));Assert.That(TextFrame.Read(p.Peer.GetStream()),Is.Null);
        }
        [Test] public void PreCancelledAttemptClosesWithoutSendingAHello()
        {
            using var p=new Pair();using var stop=new CancellationTokenSource();stop.Cancel();
            Assert.That(Failure(()=>ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),Key(),1000,stop.Token)),Is.EqualTo("AUTH_CANCELLED"));Assert.That(TextFrame.Read(p.Peer.GetStream()),Is.Null);
        }
        [TestCase(0)] [TestCase(31)] public void InvalidViewerKeyClosesWithoutRawDiagnostics(int length)
        {
            using var p=new Pair();Assert.That(Failure(()=>ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),length==0?null:new byte[length])),Is.EqualTo("AUTH_FAILED"));Assert.That(p.Transport.IsClosed,Is.True);
        }
        [Test] public void SameConnectionCannotAuthenticateAgain()
        {
            using var p=new Pair();var peer=Reply(p,Gateway(),Key());using var owner=ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),Key());Assert.That(peer.Wait(2000),Is.True);
            Assert.That(Failure(()=>ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),Key())),Is.EqualTo("AUTH_FAILED"));Assert.That(p.Transport.IsClosed,Is.True);
        }
        [TestCase(0)] [TestCase(60001)] public void InvalidBudgetPrecedesOwnershipTransfer(int budget)
        {
            using var p=new Pair();Assert.Throws<ArgumentOutOfRangeException>(()=>ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),Key(),budget));Assert.That(p.Transport.IsClosed,Is.False);
        }
        [Test] public void ValidProofDoesNotEnableFixtureModeFromPeerData()
        {
            using var p=new Pair();var peer=Task.Run(()=>{
                TextFrame.Read(p.Peer.GetStream());TextFrame.Write(p.Peer.GetStream(),Gateway().ToString());
                var fixture=JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")));
                TextFrame.Write(p.Peer.GetStream(),fixture["cases"][0]["steps"][0]["envelope"].ToString());
            });
            using var owner=ClientHandshake.Open(p.Transport,Client().ToString(),Gateway().ToString(),Key());
            Assert.That(Failure(()=>owner.ReceiveNext(1000)),Is.EqualTo("RECEIVE_MODE"));Assert.That(owner.QueuedCount,Is.Zero);Assert.That(peer.Wait(2000),Is.True);
        }
    }
}

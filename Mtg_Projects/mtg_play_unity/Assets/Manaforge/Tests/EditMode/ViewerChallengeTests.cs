using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerChallengeTests
    {
        private static JObject Corpus(string name)=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/"+name+"-v1.json")));
        private static ViewerBootstrap Bootstrap()=>ViewerBootstrap.Parse(Encoding.UTF8.GetBytes(Corpus("viewer-bootstrap")["positive"][0].ToString()));
        private sealed class Pair:IDisposable
        {
            public TcpClient Peer;public LoopbackFrameReader Reader;
            public Pair(){var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();try{Peer=new TcpClient();Peer.Connect(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port);Peer.ReceiveTimeout=2000;Reader=new LoopbackFrameReader(listener.AcceptSocket());}finally{listener.Stop();}}
            public void Dispose(){Reader.Dispose();Peer.Dispose();}
        }
        [Test] public void SharedChallengeCorpusRejectsUnknownAndMalformedFields()
        {
            var corpus=Corpus("viewer-challenge");foreach(var item in corpus["positive"]){string value=(bool)item["response"]?ViewerChallengeHandshake.ReadResponse(item["envelope"].ToString(),new string('1',64)):ViewerChallengeHandshake.ReadChallenge(item["envelope"].ToString());Assert.That(value.Length,Is.EqualTo(64));}
            foreach(var item in corpus["negative"])Assert.Throws<WireEnvelope.EnvelopeException>(()=>{if((bool)item["response"])ViewerChallengeHandshake.ReadResponse(item["envelope"].ToString(),new string('1',64));else ViewerChallengeHandshake.ReadChallenge(item["envelope"].ToString());});
            Assert.Throws<WireEnvelope.EnvelopeException>(()=>ViewerChallengeHandshake.ReadResponse(ViewerChallengeHandshake.Response(new string('2',64),new string('3',64)),new string('1',64)));
        }
        private static string Failure(Action action)=>Assert.Throws<WireEnvelope.EnvelopeException>(()=>action()).Code;
        [Test] public void TimeoutCancellationAndInvalidBudgetPreserveOwnershipRules()
        {
            using(var pair=new Pair())using(var settings=Bootstrap()) {
                Assert.Throws<ArgumentOutOfRangeException>(()=>ViewerChallengeHandshake.Open(pair.Reader,settings,0));Assert.That(pair.Reader.IsClosed,Is.False);
                Assert.That(Failure(()=>ViewerChallengeHandshake.Open(pair.Reader,settings,70)),Is.EqualTo("AUTH_TIMEOUT"));Assert.That(pair.Reader.IsClosed,Is.True);
                Assert.Throws<IOException>(()=>settings.TakeViewerKey());
            }
            using(var pair=new Pair())using(var settings=Bootstrap())using(var cancel=new CancellationTokenSource()){cancel.Cancel();Assert.That(Failure(()=>ViewerChallengeHandshake.Open(pair.Reader,settings,1000,cancel.Token)),Is.EqualTo("AUTH_CANCELLED"));Assert.That(pair.Reader.IsClosed,Is.True);}
        }
        [TestCase(false)] [TestCase(true)] public void FreshClientNonceIsBoundToTrustedPinsAndReplayProofsAreRejected(bool wrongPin)
        {
            string previous=null;
            for(int attempt=0;attempt<2;attempt++)using(var pair=new Pair())using(var settings=Bootstrap()) {
                string observed=null;var gatewayTemplate=(JObject)Corpus("viewer-auth")["positive"][1]["envelope"].DeepClone();var peer=Task.Run(()=>{
                    var stream=pair.Peer.GetStream();TextFrame.Write(stream,ViewerChallengeHandshake.Challenge(new string('1',64)));stream.Flush();
                    observed=ViewerChallengeHandshake.ReadResponse(TextFrame.Read(stream),new string('1',64));
                    var actual=ViewerAuthentication.Parse(TextFrame.Read(stream));Assert.That((string)actual["body"]["artifact_manifest_sha256"],Is.EqualTo(new string('a',64)));
                    var gateway=(JObject)gatewayTemplate.DeepClone();
                    if(wrongPin){gateway["body"]["client_nonce"]=observed;gateway["body"]["artifact_manifest_sha256"]=new string('b',64);var key=new byte[32];for(int i=0;i<32;i++)key[i]=(byte)i;gateway["body"]["proof"]=ViewerAuthentication.ComputeProof(gateway.ToString(),key);Array.Clear(key,0,key.Length);}
                    // Otherwise deliberately replay the original proof with its old client nonce.
                    TextFrame.Write(stream,gateway.ToString());stream.Flush();
                });
                Assert.That(Failure(()=>ViewerChallengeHandshake.Open(pair.Reader,settings,2000)),Is.EqualTo("AUTH_FAILED"));Assert.That(peer.Wait(3000),Is.True);
                Assert.That(observed,Is.Not.EqualTo(new string('2',64)));if(previous!=null)Assert.That(observed,Is.Not.EqualTo(previous));previous=observed;
            }
        }
    }
}

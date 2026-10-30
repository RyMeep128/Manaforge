using System;
using System.Collections;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace Manaforge.Play.Tests
{
    // Test-only owned process. No runtime launcher, real deck, rule or engine integration.
    public sealed class DummyExchangeTests
    {
        private sealed class Peer : IDisposable
        {
            public readonly Process Process;
            public TcpClient Client;
            private bool disposed;
            public Peer(string directory)
            {
                Assert.That(File.Exists(Path.Combine(directory,"manaforge/protocol/DummyGateway.class")),Is.True,"Run the Java dummy fixture preparation first");
                string jar=Path.Combine(directory,"gson.jar"),fixture=Path.Combine(directory,"dummy-session-v1.json");
                var start=new ProcessStartInfo("java", "-cp \""+directory+Path.PathSeparator+jar+"\" manaforge.protocol.DummyGateway \""+fixture+"\"")
                { UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,
                  RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true };
                Process=new Process { StartInfo=start };
                Assert.That(Process.Start(),Is.True);
                Process.ErrorDataReceived+=(sender,args)=>{}; // fixture emits fixed safe code only; never collect raw diagnostics
                Process.BeginErrorReadLine();
            }
            public void Dispose()
            {
                if(disposed)return;
                disposed=true;
                Client?.Close();
                if(!Process.HasExited)
                {
                    Process.StandardInput.Close();
                    if(!Process.WaitForExit(2000)) { Process.Kill(); Assert.That(Process.WaitForExit(2000),Is.True,"Owned dummy did not stop"); }
                }
                Process.Dispose();
            }
        }
        private static string Hex(byte[] bytes)=>string.Concat(bytes.Select(b=>b.ToString("x2")));
        private static byte[] RandomBytes()
        { var bytes=new byte[32];using(var rng=RandomNumberGenerator.Create())rng.GetBytes(bytes);return bytes; }
        private static JObject Message(string type,string id,JObject body)=>new JObject
        { ["wire_version"]=1,["message_type"]=type,["message_id"]=id,["body"]=body };
        private static JObject Hello(JObject boot,JObject ready,string role)=>Message("hello","auth-"+role,new JObject
        {
            ["protocol_version"]=1,["engine_version"]=boot["engine_version"],
            ["artifact_manifest_sha256"]=boot["artifact_manifest_sha256"],["session_id"]=boot["session_id"],
            ["viewer_id"]=boot["viewer_id"],["client_nonce"]=boot["client_nonce"],
            ["server_nonce"]=ready["server_nonce"],["role"]=role,["proof"]=new string('0',64)
        });
        private static void Send(Stream stream,JObject message) { TextFrame.Write(stream,message.ToString(Formatting.None));stream.Flush(); }
        private static JObject Read(Stream stream,long minimumRevision=0)=>ReceiveMessages.Parse(TextFrame.Read(stream),"fixture-session","one",minimumRevision,true);
        private static JObject Command(string id,long revision,string decision,string action)=>Message("command",id,new JObject
        { ["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=revision,["operation"]="perform",["decision_id"]=decision,["action_id"]=action });
        private static void SendTracked(Stream stream,JObject command,CommandTracker tracker)
        {
            string text=command.ToString(Formatting.None);tracker.Begin(text);
            try { TextFrame.Write(stream,text);stream.Flush(); }
            catch { tracker.Disconnect();throw; }
        }
        private static void Ack(Stream stream,string id,long revision,string outcome,string code,CommandTracker tracker=null)
        {
            var reply=WireMessages.Parse(TextFrame.Read(stream)); var body=(JObject)reply["body"];
            Assert.That((string)reply["message_type"],Is.EqualTo("ack"));
            Assert.That((string)body["session_id"],Is.EqualTo("fixture-session"));Assert.That((string)body["viewer_id"],Is.EqualTo("one"));
            Assert.That((string)body["command_id"],Is.EqualTo(id));Assert.That((long)body["request_revision"],Is.EqualTo(revision));
            Assert.That((string)body["outcome"],Is.EqualTo(outcome));Assert.That((string)body["code"],Is.EqualTo(code));
            tracker?.Accept(reply.ToString(Formatting.None));
        }
        private static void Exchange(Peer peer,bool wrongKey,bool ownerEof)
        {
            byte[] key=RandomBytes();
            try
            {
                var boot=new JObject { ["fixture_only"]=true,["viewer_key_hex"]=Hex(key),["engine_version"]="fixture-engine",
                    ["artifact_manifest_sha256"]=new string('a',64),["session_id"]="fixture-session",["viewer_id"]="one",["client_nonce"]=Hex(RandomBytes()) };
                Send(peer.Process.StandardInput.BaseStream,boot);
                // The owned child's stdout is a private readiness pipe, not gameplay relay.
                string readyText=TextFrame.Read(peer.Process.StandardOutput.BaseStream);
                var ready=(JObject)WireEnvelope.Parse("{\"wire_version\":1,\"message_type\":\"hello\",\"message_id\":\"ready\",\"body\":"+readyText+"}")["body"];
                Assert.That(ready["port"]?.Type,Is.EqualTo(JTokenType.Integer));
                Assert.That(ready.Count,Is.EqualTo(3));Assert.That((string)ready["host"],Is.EqualTo("127.0.0.1"));
                int port=(int)ready["port"];Assert.That(port,Is.InRange(1,65535));
                if(ownerEof)
                {
                    peer.Process.StandardInput.Close();
                    Assert.That(peer.Process.WaitForExit(5000),Is.True,"Owner EOF must stop the owned listener");
                    Assert.That(peer.Process.ExitCode,Is.Zero);return;
                }
                peer.Client=new TcpClient(AddressFamily.InterNetwork);peer.Client.Connect(IPAddress.Loopback,port);
                peer.Client.ReceiveTimeout=5000;peer.Client.SendTimeout=5000;
                using(var stream=peer.Client.GetStream())
                {
                    var clientHello=Hello(boot,ready,"client");
                    var signingKey=wrongKey?new byte[32]:key;
                    clientHello["body"]["proof"]=ViewerAuthentication.ComputeProof(clientHello.ToString(),signingKey);
                    Send(stream,clientHello);
                    if(wrongKey)
                    {
                        Assert.That(TextFrame.Read(stream),Is.Null,"Unauthenticated peer must receive no snapshot");
                        Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.EqualTo(2));return;
                    }
                    using(var verifier=new ViewerAuthentication.Verifier(Hello(boot,ready,"gateway").ToString(),key))
                        Assert.That(verifier.Verify(TextFrame.Read(stream)),Is.True,"Gateway proof failed");
                    var incoming=Read(stream);Assert.That((string)incoming["message_type"],Is.EqualTo("snapshot"));
                    var body=(JObject)incoming["body"];Assert.That(body.Count,Is.EqualTo(2));Assert.That((bool)body["fixture_only"],Is.True);
                    var snapshot=JsonConvert.DeserializeObject<GameSnapshot>(body["snapshot"].ToString(),new JsonSerializerSettings
                    { TypeNameHandling=TypeNameHandling.None,MissingMemberHandling=MissingMemberHandling.Error,DateParseHandling=DateParseHandling.None });
                    Assert.That(snapshot.session_id,Is.EqualTo("fixture-session"));Assert.That(snapshot.viewer_id,Is.EqualTo("one"));
                    foreach(var obj in snapshot.objects.Where(o=>o.hidden || o.face_down == true))
                    { Assert.That(obj.card_identity,Is.Null);Assert.That(obj.characteristics,Is.Null); }
                    Assert.That(snapshot.objects.Any(o=>o.hidden),Is.True,"Fixture must exercise concealment");
                    var eventMessage=Read(stream,snapshot.revision);Assert.That((string)eventMessage["message_type"],Is.EqualTo("event"));
                    Assert.That((string)eventMessage["body"]["event"]["player_id"],Is.EqualTo("two"),"Actor is not the authenticated recipient");
                    string decision=snapshot.decision.decision_id,action=snapshot.actions.Single().action_id;
                    using var tracker=new CommandTracker(snapshot.session_id,snapshot.viewer_id);
                    SendTracked(stream,Command("stale",snapshot.revision-1,decision,action),tracker);Ack(stream,"stale",snapshot.revision-1,"rejected","STALE_REVISION",tracker);
                    Assert.That(tracker.CanSubmit,Is.True,"A matched rejection releases the command slot");
                    SendTracked(stream,Command("current",snapshot.revision,decision,action),tracker);Ack(stream,"current",snapshot.revision,"submitted",null,tracker);
                    var result=Read(stream,snapshot.revision);Assert.That((string)result["message_type"],Is.EqualTo("result"));
                    Assert.That((bool)result["body"]["fixture_only"],Is.True);Assert.That((string)result["body"]["snapshot"]["result"],Is.EqualTo("fixture_complete"));
                    Assert.That((string)result["body"]["snapshot"]["status"],Is.EqualTo("finished"));
                    Assert.That((string)result["body"]["snapshot"]["session_id"],Is.EqualTo(snapshot.session_id));Assert.That((string)result["body"]["snapshot"]["viewer_id"],Is.EqualTo(snapshot.viewer_id));
                    Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Submitted),"A terminal fixture snapshot is not command confirmation");
                    Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command("blocked",snapshot.revision,decision,action).ToString())).Code,Is.EqualTo("COMMAND_PENDING"));
                    // Deliberate raw protocol probe of the SERVER guard, bypassing normal client submission.
                    Send(stream,Command("pending",snapshot.revision,decision,action));Ack(stream,"pending",snapshot.revision,"rejected","COMMAND_PENDING");
                    var shutdown=Message("shutdown","close",new JObject{["session_id"]=snapshot.session_id,["viewer_id"]=snapshot.viewer_id,["reason"]="client_close"});
                    Send(stream,shutdown);var closed=WireMessages.Parse(TextFrame.Read(stream));
                    Assert.That((string)closed["message_type"],Is.EqualTo("shutdown"));Assert.That(JToken.DeepEquals(closed["body"],shutdown["body"]),Is.True);
                    Assert.That(TextFrame.Read(stream),Is.Null);Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);
                    tracker.Disconnect();Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));
                }
            }
            finally { Array.Clear(key,0,key.Length); }
        }
        private static IEnumerator Run(bool wrongKey,bool ownerEof)
        {
            string directory=Path.GetFullPath(Path.Combine(Application.dataPath,"../Artifacts/JavaDummy"));
            using(var peer=new Peer(directory))
            {
                var task=Task.Run(()=>Exchange(peer,wrongKey,ownerEof));var timer=Stopwatch.StartNew();
                try
                {
                    while(!task.IsCompleted && timer.Elapsed.TotalSeconds<25)yield return null;
                    Assert.That(task.IsCompleted,Is.True,"Owned dummy exchange timed out");
                    task.GetAwaiter().GetResult();
                }
                finally
                {
                    // Dispose the owned handles to unblock any worker on failure/timeout.
                    if(!task.IsCompleted) { peer.Dispose();Assert.That(task.Wait(3000),Is.True,"Dummy worker did not finish"); }
                }
            }
        }
        [UnityTest] public IEnumerator JavaPeerExchangesAuthenticatedFixtureAndRejectsStaleAndPendingActions()=>Run(false,false);
        [UnityTest] public IEnumerator WrongViewerKeyReceivesNoSessionData()=>Run(true,false);
        [UnityTest] public IEnumerator OwnerPipeEofStopsTheOwnedListener()=>Run(false,true);
    }
}

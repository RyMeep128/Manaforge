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
            public LoopbackFrameReader Reader;
            private bool disposed;
            public Peer(string directory,bool sessionError=false,bool partialFrame=false,bool clientPartialFrame=false,bool blockedClient=false,string choiceOperation=null,string authMode=null)
            {
                Assert.That(File.Exists(Path.Combine(directory,"manaforge/protocol/DummyGateway.class")),Is.True,"Run the Java dummy fixture preparation first");
                string jar=Path.Combine(directory,"gson.jar"),fixture=Path.Combine(directory,"dummy-session-v1.json");
                var start=new ProcessStartInfo("java", "-cp \""+directory+Path.PathSeparator+jar+"\" manaforge.protocol.DummyGateway \""+fixture+"\""+(authMode=="gateway-timeout"?" server-auth-timeout":authMode=="timeout"?" delayed-proof":choiceOperation=="select_mana_source"?" mana":choiceOperation=="choose_number"?" number":choiceOperation=="choose_amounts"?" amounts":choiceOperation!=null?" choice":blockedClient?" blocked-client":clientPartialFrame?" client-partial-frame":partialFrame?" partial-frame":sessionError?" session-error":""))
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
                Reader?.Dispose();Client?.Close();
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
        private static void Send(LoopbackFrameReader owner,JObject message) => owner.Write(message.ToString(Formatting.None));
        private static JObject Read(LoopbackFrameReader input,long minimumRevision=0,ReceiveInbox inbox=null)
        {
            string text=input.Read();
            if(inbox==null)return ReceiveMessages.Parse(text,"fixture-session","one",minimumRevision,true);
            if(!inbox.Enqueue(text))return null;
            Assert.That(inbox.TryTake(out var packet),Is.True);
            using(packet)return ReceiveMessages.Parse(packet.ReadJson(),"fixture-session","one",minimumRevision,true);
        }
        private static JObject Command(string id,long revision,string decision,string action)=>Message("command",id,new JObject
        { ["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=revision,["operation"]="perform",["decision_id"]=decision,["action_id"]=action });
        private static void SendTracked(LoopbackFrameReader owner,JObject command,CommandTracker tracker)
        {
            string text=command.ToString(Formatting.None);tracker.Begin(text);
            try { owner.Write(text); }
            catch { tracker.Disconnect();throw; }
        }
        private static void Ack(LoopbackFrameReader input,string id,long revision,string outcome,string code,CommandTracker tracker=null)
        {
            var reply=WireMessages.Parse(input.Read()); var body=(JObject)reply["body"];
            Assert.That((string)reply["message_type"],Is.EqualTo("ack"));
            Assert.That((string)body["session_id"],Is.EqualTo("fixture-session"));Assert.That((string)body["viewer_id"],Is.EqualTo("one"));
            Assert.That((string)body["command_id"],Is.EqualTo(id));Assert.That((long)body["request_revision"],Is.EqualTo(revision));
            Assert.That((string)body["outcome"],Is.EqualTo(outcome));Assert.That((string)body["code"],Is.EqualTo(code));
            tracker?.Accept(reply.ToString(Formatting.None));
        }
        private static void Coordinated(Peer peer,bool sessionError,ClientSessionChannel authenticated=null)
        {
            using var channel=authenticated??new ClientSessionChannel(peer.Reader,"fixture-session","one",true);
            Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("snapshot"));
            Assert.That(channel.ReceiveNext(5000).Applied,Is.False);
            Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("event"));
            Assert.That(channel.TryTake(out var first),Is.True);
            JObject snapshot;using(first)snapshot=(JObject)ReceiveMessages.Parse(first.ReadJson(),"fixture-session","one",0,true)["body"]["snapshot"];
            Assert.That(channel.TryTake(out var eventPacket),Is.True);eventPacket.Dispose();
            long revision=(long)snapshot["revision"];string decision=(string)snapshot["decision"]["decision_id"],action=(string)snapshot["actions"][0]["action_id"];
            Assert.That(channel.CanSubmit,Is.True);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>channel.Submit(Command("stale",revision-1,decision,action).ToString())).Code,Is.EqualTo("STALE_REVISION"));
            channel.Submit(Command("current",revision,decision,action).ToString());
            Assert.That(channel.ReceiveNext(5000).Receipt.State,Is.EqualTo(CommandState.Submitted));
            if(sessionError) {
                Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("error"));
                Assert.That(channel.State,Is.EqualTo(ClientChannelState.Stopped));Assert.That(channel.Completion.Result.Code,Is.EqualTo("SESSION_FAILED"));
                Assert.That(channel.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(channel.QueuedCount,Is.Zero);
            } else {
                Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("result"));Assert.That(channel.CanSubmit,Is.False);
                Assert.That(channel.Pending.State,Is.EqualTo(CommandState.Submitted),"A result does not confirm a command");
                channel.RequestShutdown("client_close");Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("shutdown"));
                Assert.That(channel.State,Is.EqualTo(ClientChannelState.Completed));Assert.That(channel.Completion.Result.Graceful,Is.True);
                Assert.That(channel.TryTake(out var resultPacket),Is.True);using(resultPacket)Assert.That((string)WireEnvelope.Parse(resultPacket.ReadJson())["message_type"],Is.EqualTo("result"));
                Assert.That(channel.Pending.State,Is.EqualTo(CommandState.Uncertain));
            }
            Assert.That(channel.CanSubmit,Is.False);Assert.That(peer.Reader.IsClosed,Is.True);
            Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);
        }
        private static void CoordinatedChoice(Peer peer,string operation)
        {
            using var channel=new ClientSessionChannel(peer.Reader,"fixture-session","one",true);
            Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("snapshot"));Assert.That(channel.ReceiveNext(5000).Applied,Is.False);
            channel.ReceiveNext(5000);Assert.That(channel.TryTake(out var first),Is.True);
            JObject snapshot;using(first)snapshot=(JObject)WireEnvelope.Parse(first.ReadJson())["body"]["snapshot"];
            Assert.That(channel.TryTake(out var e),Is.True);e.Dispose();Assert.That(channel.CanSubmit,Is.True);
            var body=new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=snapshot["revision"],
                ["decision_id"]=snapshot["decision"]["decision_id"],["operation"]=operation};
            if(operation=="choose")body["option_id"]=snapshot["decision"]["options"][0]["option_id"];
            if(operation=="choose_number")body["value"]=-2;
            if(operation=="choose_amounts")body["values"]=new JArray(-2,3);
            if(operation=="select_mana_source")body["object_id"]=snapshot["objects"].Last()["object_id"];
            channel.Submit(Message("command","choice-submit",body).ToString());
            Assert.That(channel.ReceiveNext(5000).Receipt.State,Is.EqualTo(CommandState.Submitted));
            Assert.That(channel.ReceiveNext(5000).Receipt.State,Is.EqualTo(CommandState.Confirmed),"Explicit fixture confirmation only");
            Assert.That(channel.ReceiveNext(5000).Type,Is.EqualTo("result"));Assert.That(channel.CanSubmit,Is.False);
            channel.RequestShutdown("client_close");channel.ReceiveNext(5000);
            Assert.That(channel.TryTake(out var result),Is.True);using(result)Assert.That((bool)WireEnvelope.Parse(result.ReadJson())["body"]["fixture_only"],Is.True);
            Assert.That(channel.Pending,Is.Null);Assert.That(channel.Completion.Result.Graceful,Is.True);
            Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);
        }
        private static void Exchange(Peer peer,bool wrongKey,bool ownerEof,bool conflictingDuplicate,bool sessionError,bool partialFrame,bool clientPartialFrame,bool blockedClient,bool coordinated,string choiceOperation,string authMode)
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
                peer.Client=new TcpClient(AddressFamily.InterNetwork);
                if(blockedClient)peer.Client.ReceiveBufferSize=1024;
                peer.Client.Connect(IPAddress.Loopback,port);
                peer.Client.ReceiveTimeout=5000;peer.Client.SendTimeout=5000;
                peer.Reader=new LoopbackFrameReader(peer.Client.Client);
                using(var stream=peer.Client.GetStream())
                {
                    if(authMode!=null) {
                        if(authMode=="gateway-timeout") {
                            Assert.That(peer.Reader.Read(2000),Is.Null,"Unauthenticated stalled client must receive no gateway proof/session data");
                            Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);return;
                        }
                        if(authMode=="timeout") {
                            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>ClientHandshake.Open(peer.Reader,Hello(boot,ready,"client").ToString(),Hello(boot,ready,"gateway").ToString(),key,150,fixtureMode:true)).Code,Is.EqualTo("AUTH_TIMEOUT"));
                            Assert.That(peer.Reader.IsClosed,Is.True);peer.Process.StandardInput.Close();
                            Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);return;
                        }
                        using var authenticated=ClientHandshake.Open(peer.Reader,Hello(boot,ready,"client").ToString(),Hello(boot,ready,"gateway").ToString(),key,5000,fixtureMode:true);
                        Coordinated(peer,false,authenticated);return;
                    }
                    var clientHello=Hello(boot,ready,"client");
                    var signingKey=wrongKey?new byte[32]:key;
                    clientHello["body"]["proof"]=ViewerAuthentication.ComputeProof(clientHello.ToString(),signingKey);
                    Send(peer.Reader,clientHello);
                    if(wrongKey)
                    {
                        Assert.That(peer.Reader.Read(),Is.Null,"Unauthenticated peer must receive no snapshot");
                        Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.EqualTo(2));return;
                    }
                    using(var verifier=new ViewerAuthentication.Verifier(Hello(boot,ready,"gateway").ToString(),key))
                        Assert.That(verifier.Verify(peer.Reader.Read()),Is.True,"Gateway proof failed");
                    if(blockedClient)
                    {
                        Assert.That(peer.Process.WaitForExit(3000),Is.True,"Java write must stop when authenticated client does not read");
                        Assert.That(peer.Process.ExitCode,Is.Zero,"Dummy must verify FRAME_WRITE_TIMEOUT");peer.Reader.Dispose();return;
                    }
                    if(partialFrame)
                    {
                        Assert.That(Assert.Throws<TextFrame.FrameException>(()=>peer.Reader.Read(150)).Code,Is.EqualTo("FRAME_TIMEOUT"));
                        Assert.That(peer.Reader.IsClosed,Is.True);
                        peer.Process.StandardInput.Close();
                        Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);return;
                    }
                    if(choiceOperation!=null){CoordinatedChoice(peer,choiceOperation);return;}
                    if(coordinated){Coordinated(peer,sessionError);return;}
                    using var inbox=new ReceiveInbox("fixture-session","one",true);
                    var incoming=Read(peer.Reader,inbox:inbox);Assert.That((string)incoming["message_type"],Is.EqualTo("snapshot"));
                    var body=(JObject)incoming["body"];Assert.That(body.Count,Is.EqualTo(2));Assert.That((bool)body["fixture_only"],Is.True);
                    var snapshot=JsonConvert.DeserializeObject<GameSnapshot>(body["snapshot"].ToString(),new JsonSerializerSettings
                    { TypeNameHandling=TypeNameHandling.None,MissingMemberHandling=MissingMemberHandling.Error,DateParseHandling=DateParseHandling.None });
                    Assert.That(snapshot.session_id,Is.EqualTo("fixture-session"));Assert.That(snapshot.viewer_id,Is.EqualTo("one"));
                    foreach(var obj in snapshot.objects.Where(o=>o.hidden || o.face_down == true))
                    { Assert.That(obj.card_identity,Is.Null);Assert.That(obj.characteristics,Is.Null); }
                    Assert.That(snapshot.objects.Any(o=>o.hidden),Is.True,"Fixture must exercise concealment");
                    Assert.That(Read(peer.Reader,inbox:inbox),Is.Null,"Repeated snapshot must not be applied twice");
                    var eventMessage=Read(peer.Reader,snapshot.revision,inbox);Assert.That((string)eventMessage["message_type"],Is.EqualTo("event"));
                    Assert.That((string)eventMessage["body"]["event"]["player_id"],Is.EqualTo("two"),"Actor is not the authenticated recipient");
                    if(clientPartialFrame)
                    {
                        stream.Write(new byte[]{0,0},0,2);stream.Flush();
                        Assert.That(peer.Reader.Read(2000),Is.Null,"Java must close a stalled client frame");
                        Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.EqualTo(2));return;
                    }
                    string decision=snapshot.decision.decision_id,action=snapshot.actions.Single().action_id;
                    using var tracker=new CommandTracker(snapshot.session_id,snapshot.viewer_id);
                    SendTracked(peer.Reader,Command("stale",snapshot.revision-1,decision,action),tracker);Ack(peer.Reader,"stale",snapshot.revision-1,"rejected","STALE_REVISION",tracker);
                    Assert.That(tracker.CanSubmit,Is.True,"A matched rejection releases the command slot");
                    SendTracked(peer.Reader,Command("current",snapshot.revision,decision,action),tracker);Ack(peer.Reader,"current",snapshot.revision,"submitted",null,tracker);
                    if(sessionError)
                    {
                        Assert.That(tracker.AcceptSessionError(peer.Reader.Read()),Is.EqualTo("SESSION_FAILED"));
                        Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));
                        Assert.That(tracker.Current.CommandId,Is.EqualTo("current"));Assert.That(tracker.CanSubmit,Is.False);
                        Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.AuthenticatedReconnect());
                        Assert.That(peer.Reader.Read(),Is.Null,"Terminal session failure must close the channel");
                        Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);return;
                    }
                    var result=Read(peer.Reader,snapshot.revision,inbox);Assert.That((string)result["message_type"],Is.EqualTo("result"));
                    Assert.That((bool)result["body"]["fixture_only"],Is.True);Assert.That((string)result["body"]["snapshot"]["result"],Is.EqualTo("fixture_complete"));
                    Assert.That((string)result["body"]["snapshot"]["status"],Is.EqualTo("finished"));
                    Assert.That((string)result["body"]["snapshot"]["session_id"],Is.EqualTo(snapshot.session_id));Assert.That((string)result["body"]["snapshot"]["viewer_id"],Is.EqualTo(snapshot.viewer_id));
                    if(conflictingDuplicate)
                    {
                        // Same ID with different contents must not create another submission reservation.
                        Send(peer.Reader,Command("current",snapshot.revision+1,decision,action));
                        Assert.That(peer.Reader.Read(),Is.Null,"Conflicting ID reuse closes the connection");
                        Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.EqualTo(2));
                        tracker.Disconnect();Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));return;
                    }
                    // Deliberate raw retry probe, bypassing the normal client's ID-reuse prevention.
                    Send(peer.Reader,Command("current",snapshot.revision,decision,action));Ack(peer.Reader,"current",snapshot.revision,"submitted",null,tracker);
                    Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Submitted),"A terminal fixture snapshot is not command confirmation");
                    Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>tracker.Begin(Command("blocked",snapshot.revision,decision,action).ToString())).Code,Is.EqualTo("COMMAND_PENDING"));
                    // Deliberate raw protocol probe of the SERVER guard, bypassing normal client submission.
                    Send(peer.Reader,Command("pending",snapshot.revision,decision,action));Ack(peer.Reader,"pending",snapshot.revision,"rejected","COMMAND_PENDING");
                    var shutdown=Message("shutdown","close",new JObject{["session_id"]=snapshot.session_id,["viewer_id"]=snapshot.viewer_id,["reason"]="client_close"});
                    Send(peer.Reader,shutdown);var closed=WireMessages.Parse(peer.Reader.Read());
                    Assert.That((string)closed["message_type"],Is.EqualTo("shutdown"));Assert.That(JToken.DeepEquals(closed["body"],shutdown["body"]),Is.True);
                    Assert.That(peer.Reader.Read(),Is.Null);Assert.That(peer.Process.WaitForExit(5000),Is.True);Assert.That(peer.Process.ExitCode,Is.Zero);
                    tracker.Disconnect();Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));
                }
            }
            finally { Array.Clear(key,0,key.Length); }
        }
        private static IEnumerator Run(bool wrongKey,bool ownerEof,bool conflictingDuplicate=false,bool sessionError=false,bool partialFrame=false,bool clientPartialFrame=false,bool blockedClient=false,bool coordinated=false,string choiceOperation=null,string authMode=null)
        {
            string directory=Path.GetFullPath(Path.Combine(Application.dataPath,"../Artifacts/JavaDummy"));
            using(var peer=new Peer(directory,sessionError,partialFrame,clientPartialFrame,blockedClient,choiceOperation,authMode))
            {
                var task=Task.Run(()=>Exchange(peer,wrongKey,ownerEof,conflictingDuplicate,sessionError,partialFrame,clientPartialFrame,blockedClient,coordinated,choiceOperation,authMode));var timer=Stopwatch.StartNew();
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
        [UnityTest] public IEnumerator GatewayHandshakeDeadlineClosesAnIdleUnauthenticatedClient()=>Run(false,false,authMode:"gateway-timeout");
        [UnityTest] public IEnumerator BoundedHandshakeReturnsAnOwnedAuthenticatedSession()=>Run(false,false,authMode:"success");
        [UnityTest] public IEnumerator BoundedHandshakeStopsDelayedProofAndOwnedPeer()=>Run(false,false,authMode:"timeout");
        [UnityTest] public IEnumerator CoordinatedManaSourcePreservesViewerObjectIdentity()=>Run(false,false,choiceOperation:"select_mana_source");
        [UnityTest] public IEnumerator CoordinatedNumberPreservesExplicitSignedFixtureValue()=>Run(false,false,choiceOperation:"choose_number");
        [UnityTest] public IEnumerator CoordinatedAmountsPreserveExplicitFixtureVector()=>Run(false,false,choiceOperation:"choose_amounts");
        [UnityTest] public IEnumerator CoordinatedOpaqueOptionUsesFixtureReceipts()=>Run(false,false,choiceOperation:"choose");
        [UnityTest] public IEnumerator CoordinatedFinishUsesExplicitFixtureFlag()=>Run(false,false,choiceOperation:"finish_selection");
        [UnityTest] public IEnumerator CoordinatedCancelUsesExplicitFixtureFlag()=>Run(false,false,choiceOperation:"cancel");
        [UnityTest] public IEnumerator CoordinatedSessionOwnsAdmissionShutdownAndFinalPacketDrain()=>Run(false,false,coordinated:true);
        [UnityTest] public IEnumerator CoordinatedSessionErrorRevokesQueuedDataAndPreservesUncertainty()=>Run(false,false,sessionError:true,coordinated:true);
        [UnityTest] public IEnumerator JavaWriteDeadlineStopsAnAuthenticatedNonReadingClient()=>Run(false,false,false,false,false,false,true);
        [UnityTest] public IEnumerator JavaRejectsAnAuthenticatedClientPartialFrame()=>Run(false,false,false,false,false,true);
        [UnityTest] public IEnumerator PartialJavaFrameTimesOutAndOwnedPeerStops()=>Run(false,false,false,false,true);
        [UnityTest] public IEnumerator TerminalJavaSessionErrorPreservesPendingCommandUncertainty()=>Run(false,false,false,true);
        [UnityTest] public IEnumerator ConflictingDuplicateCannotReplaceTheRecordedCommand()=>Run(false,false,true);
    }
}

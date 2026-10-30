using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;
namespace Manaforge.Play.Tests
{
    public sealed class ClientSessionChannelTests
    {
        private static JObject Corpus()=>JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/receive-history-v1.json")));
        private static JObject Snapshot(string id="s1",long revision=7){var value=(JObject)Corpus()["cases"][0]["steps"][0]["envelope"].DeepClone();value["message_id"]=id;value["body"]["snapshot"]["revision"]=revision;return value;}
        private static JObject Message(string type,JObject body)=>new JObject{["wire_version"]=1,["message_type"]=type,["message_id"]="reply",["body"]=body};
        private static JObject Command(string id="c1",long revision=7)=>Message("command",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["revision"]=revision,["decision_id"]="fixture-decision",["operation"]="perform",["action_id"]="fixture-action"}).WithId(id);
        private static JObject Ack(string outcome="submitted",string viewer="one")=>Message("ack",new JObject{["session_id"]="fixture-session",["viewer_id"]=viewer,["command_id"]="c1",["request_revision"]=7,["outcome"]=outcome,["code"]=JValue.CreateNull()});
        private sealed class Pair : IDisposable
        {
            public readonly TcpClient Peer;
            public readonly LoopbackFrameReader Transport;
            public readonly ClientSessionChannel Channel;
            public Pair(int maximumMessages=128)
            {
                var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
                try{Peer=new TcpClient(AddressFamily.InterNetwork);Peer.ReceiveTimeout=2000;
                    Assert.That(Peer.ConnectAsync(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port).Wait(2000),Is.True);
                    Transport=new LoopbackFrameReader(listener.AcceptSocket());Channel=new ClientSessionChannel(Transport,"fixture-session","one",true,maximumMessages);
                }catch{Transport?.Dispose();Peer?.Dispose();throw;}finally{listener.Stop();}
            }
            public void Send(JObject value)=>TextFrame.Write(Peer.GetStream(),value.ToString(Formatting.None));
            public void Prime(bool pending=false){Send(Snapshot());Channel.ReceiveNext(1000);if(pending){Channel.Submit(Command().ToString());WireMessages.Parse(TextFrame.Read(Peer.GetStream()));}}
            public void Dispose(){Channel.Dispose();Peer.Dispose();}
        }
        private static void Stopped(Pair p,string code,bool pending=true)
        {
            Assert.That(p.Channel.State,Is.EqualTo(ClientChannelState.Stopped));Assert.That(p.Channel.CanSubmit,Is.False);
            Assert.That(p.Transport.IsClosed,Is.True);Assert.That(p.Channel.QueuedCount,Is.Zero);Assert.That(p.Channel.TryTake(out _),Is.False);
            Assert.That(p.Channel.Completion.Result.Code,Is.EqualTo(code));
            if(pending)Assert.That(p.Channel.Pending.State,Is.EqualTo(CommandState.Uncertain));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Command("later").ToString())).Code,Is.EqualTo("SESSION_STOPPED"));
        }
        [Test] public void RoutesDataDuplicatesAndCorrelatedReceipts()
        {
            using var p=new Pair();Assert.That(p.Channel.CanSubmit,Is.False);p.Prime();Assert.That(p.Channel.CanSubmit,Is.True);
            p.Send(Snapshot());Assert.That(p.Channel.ReceiveNext(1000).Applied,Is.False);Assert.That(p.Channel.QueuedCount,Is.EqualTo(1));
            p.Channel.Submit(Command().ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["action_id"],Is.EqualTo("fixture-action"));
            p.Send(Ack());Assert.That(p.Channel.ReceiveNext(1000).Receipt.State,Is.EqualTo(CommandState.Submitted));
            p.Send(Ack("confirmed"));Assert.That(p.Channel.ReceiveNext(1000).Receipt.State,Is.EqualTo(CommandState.Confirmed));Assert.That(p.Channel.CanSubmit,Is.True);
        }
        [TestCase("malformed","JSON_INVALID")] [TestCase("viewer","ACK_CONTEXT")]
        public void InvalidReceiveStopsPendingCommandsAndRevokesQueuedData(string defect,string code)
        {
            using var p=new Pair();p.Prime(true);
            if(defect=="malformed")TextFrame.Write(p.Peer.GetStream(),"private looked-at card");else p.Send(Ack(viewer:"two"));
            var error=Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.ReceiveNext(1000));Assert.That(error.Code,Is.EqualTo(code));Assert.That(error.Message,Is.EqualTo(code));Stopped(p,code);
        }
        [Test] public void OverflowStopsSocketInboxAndCommandAdmissionTogether()
        {
            using var p=new Pair(1);p.Prime(true);p.Send(Snapshot("s2"));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.ReceiveNext(1000)).Code,Is.EqualTo("INBOX_OVERFLOW"));Stopped(p,"INBOX_OVERFLOW");
        }
        [Test] public void CancelReleasesAnOutstandingReaderAndPreservesTheFirstCause()
        {
            using var p=new Pair();p.Prime(true);
            var read=Task.Run(()=>Assert.Throws<TextFrame.FrameException>(()=>p.Channel.ReceiveNext(5000)).Code);
            Assert.That(SpinWait.SpinUntil(()=>p.Transport.ReadInProgress,1000),Is.True);p.Channel.Cancel();
            Assert.That(read.Wait(2000),Is.True);Assert.That(read.Result,Is.EqualTo("FRAME_CLOSED"));Stopped(p,"SESSION_CANCELLED");
        }
        [Test] public void UnexpectedEofIsNotARejectedActionOrGracefulOutcome()
        {
            using var p=new Pair();p.Prime(true);p.Peer.Client.Shutdown(SocketShutdown.Send);
            Assert.That(p.Channel.ReceiveNext(1000).Type,Is.EqualTo("eof"));Assert.That(p.Channel.Completion.Result.Graceful,Is.False);Stopped(p,"SESSION_EOF");
        }
        [Test] public void TerminalErrorCoordinatesTheSameFailurePath()
        {
            using var p=new Pair();p.Prime(true);p.Send(Message("error",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["terminal"]=true,["code"]="SESSION_FAILED"}));
            Assert.That(p.Channel.ReceiveNext(1000).Type,Is.EqualTo("error"));Stopped(p,"SESSION_FAILED");
        }
        [Test] public void UnrequestedShutdownCannotPretendToBeGraceful()
        {
            using var p=new Pair();p.Prime(true);p.Send(Message("shutdown",new JObject{["session_id"]="fixture-session",["viewer_id"]="one",["reason"]="client_close"}));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.ReceiveNext(1000)).Code,Is.EqualTo("SESSION_SHUTDOWN_INVALID"));Stopped(p,"SESSION_SHUTDOWN_INVALID");
        }
        [Test] public void MatchedShutdownAllowsFinalPacketsToDrainWithoutConfirmingPendingActions()
        {
            using var p=new Pair();p.Prime(true);p.Channel.RequestShutdown("client_close");
            var request=WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()));p.Send(Message("shutdown",(JObject)request["body"].DeepClone()));
            p.Channel.ReceiveNext(1000);Assert.That(p.Channel.State,Is.EqualTo(ClientChannelState.Completed));Assert.That(p.Channel.Completion.Result.Graceful,Is.True);
            Assert.That(p.Channel.Pending.State,Is.EqualTo(CommandState.Uncertain));Assert.That(p.Channel.TryTake(out var packet),Is.True);packet.Dispose();Assert.That(p.Channel.TryTake(out _),Is.False);
        }
        [Test] public void ResultStopsFurtherSubmissionButStillAcceptsTheExactPendingReceipt()
        {
            using var p=new Pair();p.Prime(true);
            var result=(JObject)Corpus()["cases"].Single(c=>(string)c["name"]=="result-terminal")["steps"][1]["envelope"].DeepClone();p.Send(result);p.Channel.ReceiveNext(1000);
            Assert.That(p.Channel.Pending.State,Is.EqualTo(CommandState.AwaitingAck));Assert.That(p.Channel.CanSubmit,Is.False);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Command("c2").ToString())).Code,Is.EqualTo("SESSION_RESULT"));
            p.Send(Ack("confirmed"));Assert.That(p.Channel.ReceiveNext(1000).Receipt.State,Is.EqualTo(CommandState.Confirmed));Assert.That(p.Channel.CanSubmit,Is.False);
        }
        [Test] public void UnofferedLocalActionIsRejectedBeforeWritingAndKeepsTheSessionUsable()
        {
            using var p=new Pair();p.Prime();var bad=Command();bad["body"]["action_id"]="not-offered";
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(bad.ToString())).Code,Is.EqualTo("ACTION_UNAVAILABLE"));
            Assert.That(p.Channel.CanSubmit,Is.True);p.Channel.Submit(Command().ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["message_id"],Is.EqualTo("c1"));
        }
        [Test] public void DisposalClearsOwnedStateAndPreservesFirstTerminationMetadata()
        {
            using var p=new Pair();p.Prime(true);p.Channel.Cancel();p.Channel.Dispose();p.Channel.Dispose();
            Assert.That(p.Channel.State,Is.EqualTo(ClientChannelState.Disposed));Assert.That(p.Channel.QueuedCount,Is.Zero);Assert.That(p.Channel.Pending,Is.Null);
            Assert.That(p.Channel.Completion.Result.Code,Is.EqualTo("SESSION_CANCELLED"));Assert.That(p.Transport.IsClosed,Is.True);
        }
        [Test] public void WriteCancellationRevokesQueuedDataAndKeepsTheRegisteredCommandUncertain()
        {
            using var p=new Pair();p.Prime();using var stop=new CancellationTokenSource();stop.Cancel();
            Assert.That(Assert.Throws<TextFrame.FrameException>(()=>p.Channel.Submit(Command().ToString(),1000,stop.Token)).Code,Is.EqualTo("FRAME_WRITE_CANCELLED"));Stopped(p,"FRAME_WRITE_CANCELLED");
        }
        [Test] public void HigherRevisionEventRevokesTokensUntilANewSnapshotArrives()
        {
            using var p=new Pair();p.Prime();var e=(JObject)Corpus()["cases"][0]["steps"][2]["envelope"].DeepClone();e["body"]["event"]["revision"]=8;
            p.Send(e);p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.False);
            p.Send(Snapshot("s2",8));p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.True);
            p.Channel.Submit(Command(revision:8).ToString());Assert.That((long)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["revision"],Is.EqualTo(8));
        }
        [Test] public void ChoiceFamiliesRemainExplicitlyUnsupportedByThisCoordinatorSlice()
        {
            using var p=new Pair();p.Prime();var choice=Command();choice["body"]["operation"]="choose";((JObject)choice["body"]).Remove("action_id");choice["body"]["option_id"]="option";
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(choice.ToString())).Code,Is.EqualTo("SESSION_COMMAND_UNSUPPORTED"));Assert.That(p.Channel.CanSubmit,Is.True);
        }
        [TestCase("finished")] [TestCase("unknown")] [TestCase("empty-decision")]
        public void SnapshotsWithoutActiveDecisionsDoNotEnableProvidedActionTokens(string status)
        {
            using var p=new Pair();var snapshot=Snapshot();if(status=="empty-decision")snapshot["body"]["snapshot"]["decision"]["decision_id"]="";
            else snapshot["body"]["snapshot"]["status"]=status;p.Send(snapshot);p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.False);
        }
    }
    internal static class SessionFixtureObjectExtensions
    {
        internal static JObject WithId(this JObject value,string id){value["message_id"]=id;return value;}
    }
}

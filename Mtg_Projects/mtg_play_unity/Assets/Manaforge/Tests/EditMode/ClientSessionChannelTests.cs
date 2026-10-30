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
        [Test] public void ControlReceiptsCannotBeSubmittedAsGameplayCommands()
        {
            using var p=new Pair();p.Prime();
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Ack().ToString())).Code,Is.EqualTo("SESSION_COMMAND_UNSUPPORTED"));Assert.That(p.Channel.CanSubmit,Is.True);
        }
        private static JObject ChoiceSnapshot(string id="s1",long revision=7,string option="offered",bool controls=true)
        {
            var snapshot=Snapshot(id,revision);snapshot["body"]["snapshot"]["actions"]=new JArray();
            var request=snapshot["body"]["snapshot"]["decision"];request["family"]="selection";request["is_priority"]=false;
            request["can_finish"]=controls;request["cancellable"]=controls;
            request["options"]=option==null?new JArray():new JArray(new JObject{["option_id"]=option,["label"]="Public fixture",["object_id"]=JValue.CreateNull(),["player_id"]=JValue.CreateNull(),["selected"]=false});
            return snapshot;
        }
        private static JObject Choice(string operation,string option="offered",long revision=7)
        {
            var command=Command(revision:revision);var body=(JObject)command["body"];body.Remove("action_id");body["operation"]=operation;
            if(operation=="choose")body["option_id"]=option;return command;
        }
        [TestCase("choose")] [TestCase("finish_selection")] [TestCase("cancel")]
        public void OfferedChoicesAndFlagsUseTheSameReceiptAndUncertaintyPath(string operation)
        {
            using var p=new Pair();p.Send(ChoiceSnapshot());p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.True);
            p.Channel.Submit(Choice(operation).ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["operation"],Is.EqualTo(operation));
            p.Send(Ack());Assert.That(p.Channel.ReceiveNext(1000).Receipt.State,Is.EqualTo(CommandState.Submitted));
            p.Peer.Client.Shutdown(SocketShutdown.Send);p.Channel.ReceiveNext(1000);Stopped(p,"SESSION_EOF");
        }
        [TestCase("choose","OPTION_UNAVAILABLE")] [TestCase("finish_selection","SELECTION_NOT_FINISHABLE")] [TestCase("cancel","CANCELLATION_UNSUPPORTED")]
        public void UnofferedOptionOrControlNeverWritesOrPoisonsAHealthySession(string operation,string code)
        {
            using var p=new Pair();p.Send(ChoiceSnapshot(controls:false));p.Channel.ReceiveNext(1000);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Choice(operation,"not-offered").ToString())).Code,Is.EqualTo(code));
            Assert.That(p.Channel.Pending,Is.Null);Assert.That(p.Channel.CanSubmit,Is.True);
            p.Channel.Submit(Choice("choose").ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["option_id"],Is.EqualTo("offered"));
        }
        [TestCase("finish_selection")] [TestCase("cancel")]
        public void ExplicitControlsDoNotRequireAnActionOrOptionList(string operation)
        {
            using var p=new Pair();p.Send(ChoiceSnapshot(option:null));p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.True);
            p.Channel.Submit(Choice(operation).ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["operation"],Is.EqualTo(operation));
        }
        [Test] public void NewSnapshotReplacesOptionIdsAndFlagsWithoutKeepingOldPermissions()
        {
            using var p=new Pair();p.Send(ChoiceSnapshot());p.Channel.ReceiveNext(1000);
            p.Send(ChoiceSnapshot("s2",8,"new-option",false));p.Channel.ReceiveNext(1000);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Choice("choose",revision:8).ToString())).Code,Is.EqualTo("OPTION_UNAVAILABLE"));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Choice("finish_selection",revision:8).ToString())).Code,Is.EqualTo("SELECTION_NOT_FINISHABLE"));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Choice("cancel",revision:8).ToString())).Code,Is.EqualTo("CANCELLATION_UNSUPPORTED"));
        }
        [Test] public void HigherRevisionEventRevokesChoiceAndControlPermissions()
        {
            using var p=new Pair();p.Send(ChoiceSnapshot());p.Channel.ReceiveNext(1000);
            var e=(JObject)Corpus()["cases"][0]["steps"][2]["envelope"].DeepClone();e["body"]["event"]["revision"]=8;p.Send(e);p.Channel.ReceiveNext(1000);
            Assert.That(p.Channel.CanSubmit,Is.False);Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Choice("cancel").ToString())).Code,Is.EqualTo("SESSION_NO_DECISION"));
        }
        private static JObject NumericSnapshot(string family,long? minimum,long? maximum,params long[] ranges)
        {
            var snapshot=ChoiceSnapshot(option:null,controls:false);var request=snapshot["body"]["snapshot"]["decision"];
            request["family"]=family;request["minimum"]=minimum.HasValue?new JValue(minimum.Value):JValue.CreateNull();
            request["maximum"]=maximum.HasValue?new JValue(maximum.Value):JValue.CreateNull();
            var amounts=new JArray();for(int i=0;i<ranges.Length;i+=2)amounts.Add(new JObject{["label"]="Public constraint",["minimum"]=ranges[i],["maximum"]=ranges[i+1],["default"]=JValue.CreateNull()});
            request["amounts"]=amounts;return snapshot;
        }
        private static JObject Numeric(string operation,params long[] values)
        {
            var command=Choice(operation);command["body"][operation=="choose_number"?"value":"values"]=operation=="choose_number"
                ?(JToken)new JValue(values[0]):new JArray(values.Select(value=>new JValue(value)));return command;
        }
        private static void PresentNumeric(Pair p,JObject snapshot)
        {
            var send=Task.Run(()=>p.Send(snapshot));p.Channel.ReceiveNext(2000);Assert.That(send.Wait(2000),Is.True);
        }
        [TestCase(long.MinValue)] [TestCase(long.MaxValue)] [TestCase(0L)]
        public void NumberRangePreservesSignedIntegerExtremes(long value)
        {
            using var p=new Pair();PresentNumeric(p,NumericSnapshot("number",long.MinValue,long.MaxValue));Assert.That(p.Channel.CanSubmit,Is.True);
            p.Channel.Submit(Numeric("choose_number",value).ToString());Assert.That((long)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["value"],Is.EqualTo(value));
        }
        [TestCase(-4L)] [TestCase(4L)] public void NumberOutsideTheSuppliedRangeIsNotWritten(long value)
        {
            using var p=new Pair();PresentNumeric(p,NumericSnapshot("number",-3,3));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Numeric("choose_number",value).ToString())).Code,Is.EqualTo("AMOUNT_OUT_OF_RANGE"));
            Assert.That(p.Channel.Pending,Is.Null);p.Channel.Submit(Numeric("choose_number",0).ToString());Assert.That((long)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["value"],Is.Zero);
        }
        [TestCase("signed")] [TestCase("empty")] [TestCase("overflow-cancellation")]
        public void AmountsPreserveValuesAndUseExactMathematicalTotals(string kind)
        {
            using var p=new Pair();long[] values;JObject snapshot;
            if(kind=="signed"){values=new[]{-2L,3L};snapshot=NumericSnapshot("amounts",1,1,-3,0,0,5);}
            else if(kind=="empty"){values=Array.Empty<long>();snapshot=NumericSnapshot("amounts",0,0);}
            else{values=new[]{long.MaxValue,long.MaxValue,long.MinValue};snapshot=NumericSnapshot("amounts",long.MinValue,long.MaxValue,long.MinValue,long.MaxValue,long.MinValue,long.MaxValue,long.MinValue,long.MaxValue);}
            PresentNumeric(p,snapshot);Assert.That(p.Channel.CanSubmit,Is.True);p.Channel.Submit(Numeric("choose_amounts",values).ToString());
            Assert.That(WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["values"].Select(v=>(long)v),Is.EqualTo(values));
        }
        [Test] public void AmountTotalCannotWrapIntoAnApparentlyValidRange()
        {
            using var p=new Pair();PresentNumeric(p,NumericSnapshot("amounts",-3,3,long.MinValue,long.MaxValue,long.MinValue,long.MaxValue));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Numeric("choose_amounts",long.MaxValue,long.MaxValue).ToString())).Code,Is.EqualTo("AMOUNT_OUT_OF_RANGE"));Assert.That(p.Channel.Pending,Is.Null);
        }
        [TestCase("count")] [TestCase("entry")] [TestCase("total")]
        public void AmountConstraintsAreCheckedWithoutPaddingClampingOrRedistributing(string defect)
        {
            using var p=new Pair();PresentNumeric(p,NumericSnapshot("amounts",3,5,0,3,0,3));
            long[] values=defect=="count"?new[]{3L}:defect=="entry"?new[]{4L,0L}:new[]{1L,1L};
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Numeric("choose_amounts",values).ToString())).Code,Is.EqualTo("AMOUNT_OUT_OF_RANGE"));Assert.That(p.Channel.Pending,Is.Null);
        }
        [TestCase("missing")] [TestCase("inverted")] [TestCase("amount-range")] [TestCase("amount-total")] [TestCase("oversized")]
        public void UnsupportedNumericConstraintsStayUnavailable(string defect)
        {
            using var p=new Pair();bool number=defect=="missing" || defect=="inverted";
            var snapshot=number?NumericSnapshot("number",defect=="missing"?(long?)null:5,1):NumericSnapshot("amounts",0,0,0,0);
            var request=snapshot["body"]["snapshot"]["decision"];
            if(defect=="amount-range")request["amounts"][0]["minimum"]=1;
            if(defect=="amount-total")request["minimum"]=JValue.CreateNull();
            if(defect=="oversized")request["amounts"]=new JArray(Enumerable.Range(0,WireMessages.MaxAmountValues+1).Select(_=>request["amounts"][0].DeepClone()));
            PresentNumeric(p,snapshot);Assert.That(p.Channel.CanSubmit,Is.False);
            var command=Numeric(number?"choose_number":"choose_amounts",0);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(command.ToString())).Code,Is.EqualTo("SESSION_NUMERIC_UNAVAILABLE"));Assert.That(p.Channel.State,Is.EqualTo(ClientChannelState.Active));
        }
        [Test] public void AmountVectorAtTheTransportLimitIsPreserved()
        {
            using var p=new Pair();var snapshot=NumericSnapshot("amounts",0,0,0,0);var request=snapshot["body"]["snapshot"]["decision"];
            request["amounts"]=new JArray(Enumerable.Range(0,WireMessages.MaxAmountValues).Select(_=>request["amounts"][0].DeepClone()));
            PresentNumeric(p,snapshot);p.Channel.Submit(Numeric("choose_amounts",new long[WireMessages.MaxAmountValues]).ToString());
            Assert.That(WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["values"].Count(),Is.EqualTo(WireMessages.MaxAmountValues));
        }
        [Test] public void NumericConstraintsAreReplacedAndRevokedWithTheDecision()
        {
            using var p=new Pair();PresentNumeric(p,NumericSnapshot("number",0,10));var next=NumericSnapshot("number",20,30);next["message_id"]="s2";next["body"]["snapshot"]["revision"]=8;PresentNumeric(p,next);
            var command=Numeric("choose_number",5);command["body"]["revision"]=8;
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(command.ToString())).Code,Is.EqualTo("AMOUNT_OUT_OF_RANGE"));
            var e=(JObject)Corpus()["cases"][0]["steps"][2]["envelope"].DeepClone();e["body"]["event"]["revision"]=9;p.Send(e);p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.False);
        }
        [Test] public void NumericOperationCannotUseADifferentDecisionFamily()
        {
            using var p=new Pair();PresentNumeric(p,NumericSnapshot("number",0,10));
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(Numeric("choose_amounts",1).ToString())).Code,Is.EqualTo("DECISION_FAMILY_MISMATCH"));Assert.That(p.Channel.Pending,Is.Null);
        }
        private static JObject ManaSnapshot(string id="s1",long revision=7)
        {var snapshot=ChoiceSnapshot(id,revision,option:null,controls:false);snapshot["body"]["snapshot"]["decision"]["family"]="mana";return snapshot;}
        private static string ManaObject(JObject snapshot)=>(string)snapshot["body"]["snapshot"]["objects"][0]["object_id"];
        private static JObject ManaCommand(string objectId,long revision=7)
        {var command=Choice("select_mana_source",revision:revision);command["body"]["object_id"]=objectId;return command;}
        [Test] public void CurrentManaObjectUsesTheSameReceiptsAndUncertaintyPath()
        {
            using var p=new Pair();var snapshot=ManaSnapshot();p.Send(snapshot);p.Channel.ReceiveNext(1000);Assert.That(p.Channel.CanSubmit,Is.True);
            p.Channel.Submit(ManaCommand(ManaObject(snapshot)).ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["object_id"],Is.EqualTo(ManaObject(snapshot)));
            p.Send(Ack());Assert.That(p.Channel.ReceiveNext(1000).Receipt.State,Is.EqualTo(CommandState.Submitted));p.Peer.Client.Shutdown(SocketShutdown.Send);p.Channel.ReceiveNext(1000);Stopped(p,"SESSION_EOF");
        }
        [TestCase("tapped")] [TestCase("face-down")] [TestCase("unknown-characteristics")] [TestCase("other-controller")]
        [TestCase("hand")] [TestCase("unknown-zone")] [TestCase("hidden")]
        public void ObjectAddressabilityDoesNotInventManaEligibility(string kind)
        {
            using var p=new Pair();var snapshot=ManaSnapshot();var obj=snapshot["body"]["snapshot"]["objects"][0];obj["hidden"]=false;obj["zone"]="battlefield";
            if(kind=="tapped")obj["tapped"]=true;if(kind=="face-down")obj["face_down"]=true;
            if(kind=="other-controller")obj["controller_id"]="two";if(kind=="hand")obj["zone"]="hand";
            if(kind=="unknown-zone")obj["zone"]="future-zone";if(kind=="hidden")obj["hidden"]=true;
            p.Send(snapshot);p.Channel.ReceiveNext(1000);p.Channel.Submit(ManaCommand(ManaObject(snapshot)).ToString());
            Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["object_id"],Is.EqualTo(ManaObject(snapshot)));
        }
        [TestCase("other-viewer-object")] [TestCase("old-incarnation")]
        public void UnaddressableManaObjectIsRejectedBeforeWriting(string objectId)
        {
            using var p=new Pair();var snapshot=ManaSnapshot();p.Send(snapshot);p.Channel.ReceiveNext(1000);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(ManaCommand(objectId).ToString())).Code,Is.EqualTo("STALE_OR_INVALID_OBJECT"));
            Assert.That(p.Channel.Pending,Is.Null);Assert.That(p.Channel.CanSubmit,Is.True);p.Channel.Submit(ManaCommand(ManaObject(snapshot)).ToString());
            Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["object_id"],Is.EqualTo(ManaObject(snapshot)));
        }
        [Test] public void NewSnapshotReplacesManaObjectIncarnations()
        {
            using var p=new Pair();var first=ManaSnapshot();p.Send(first);p.Channel.ReceiveNext(1000);var next=ManaSnapshot("s2",8);next["body"]["snapshot"]["objects"][0]["object_id"]="new-incarnation";
            p.Send(next);p.Channel.ReceiveNext(1000);Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(ManaCommand(ManaObject(first),8).ToString())).Code,Is.EqualTo("STALE_OR_INVALID_OBJECT"));
            p.Channel.Submit(ManaCommand("new-incarnation",8).ToString());Assert.That((string)WireMessages.Parse(TextFrame.Read(p.Peer.GetStream()))["body"]["object_id"],Is.EqualTo("new-incarnation"));
        }
        [Test] public void HigherRevisionEventRevokesManaAddressability()
        {
            using var p=new Pair();var snapshot=ManaSnapshot();p.Send(snapshot);p.Channel.ReceiveNext(1000);
            var e=(JObject)Corpus()["cases"][0]["steps"][2]["envelope"].DeepClone();e["body"]["event"]["revision"]=8;p.Send(e);p.Channel.ReceiveNext(1000);
            Assert.That(p.Channel.CanSubmit,Is.False);Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(ManaCommand(ManaObject(snapshot)).ToString())).Code,Is.EqualTo("SESSION_NO_DECISION"));
        }
        [Test] public void ManaOperationRequiresAManaDecisionFamily()
        {
            using var p=new Pair();var snapshot=Snapshot();p.Send(snapshot);p.Channel.ReceiveNext(1000);
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(ManaCommand(ManaObject(snapshot)).ToString())).Code,Is.EqualTo("DECISION_FAMILY_MISMATCH"));Assert.That(p.Channel.Pending,Is.Null);
        }
        [Test] public void EmptyObjectSetDoesNotInventAManaSource()
        {
            using var p=new Pair();var snapshot=ManaSnapshot();snapshot["body"]["snapshot"]["objects"]=new JArray();p.Send(snapshot);p.Channel.ReceiveNext(1000);
            Assert.That(p.Channel.CanSubmit,Is.False);Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(ManaCommand("invented").ToString())).Code,Is.EqualTo("STALE_OR_INVALID_OBJECT"));
        }
        [Test] public void ManaObjectCannotBypassAStaleDecisionToken()
        {
            using var p=new Pair();var snapshot=ManaSnapshot();p.Send(snapshot);p.Channel.ReceiveNext(1000);var command=ManaCommand(ManaObject(snapshot));command["body"]["decision_id"]="stale";
            Assert.That(Assert.Throws<WireEnvelope.EnvelopeException>(()=>p.Channel.Submit(command.ToString())).Code,Is.EqualTo("STALE_DECISION"));Assert.That(p.Channel.Pending,Is.Null);
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

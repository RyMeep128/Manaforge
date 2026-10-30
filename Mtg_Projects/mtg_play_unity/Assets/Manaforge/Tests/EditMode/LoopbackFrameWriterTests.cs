using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
namespace Manaforge.Play.Tests
{
    public sealed class LoopbackFrameWriterTests
    {
        private sealed class Pair : IDisposable
        {
            public readonly TcpClient Peer;
            public readonly LoopbackFrameReader Channel;
            public Pair()
            {
                var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
                try {
                    Peer=new TcpClient(AddressFamily.InterNetwork);Peer.ReceiveBufferSize=1024;Peer.ReceiveTimeout=2000;
                    Assert.That(Peer.ConnectAsync(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port).Wait(2000),Is.True);
                    var accepted=listener.AcceptSocket();accepted.SendBufferSize=1024;
                    Channel=new LoopbackFrameReader(accepted);
                } catch{Peer?.Dispose();throw;}finally{listener.Stop();}
            }
            public void Dispose(){Channel.Dispose();Peer.Dispose();}
        }
        private static string Large()=>new string('x',TextFrame.MaxBytes);
        private static string Failure(Action write)
        {var error=Assert.Throws<TextFrame.FrameException>(()=>write());Assert.That(error.Message,Is.EqualTo(error.Code));return error.Code;}
        [Test] public void WritesCompleteFramesAndPermitsAReaderAlongsideTheWriter()
        {
            using var pair=new Pair();var write=Task.Run(()=>{pair.Channel.Write("one",1000);pair.Channel.Write("two",1000);});
            Assert.That(TextFrame.Read(pair.Peer.GetStream()),Is.EqualTo("one"));Assert.That(TextFrame.Read(pair.Peer.GetStream()),Is.EqualTo("two"));
            TextFrame.Write(pair.Peer.GetStream(),"reply");Assert.That(pair.Channel.Read(1000),Is.EqualTo("reply"));Assert.That(write.Wait(2000),Is.True);
        }
        [Test] public void NonReadingPeerCannotHoldAFrameWriteIndefinitely()
        {
            using var pair=new Pair();var write=Task.Run(()=>Failure(()=>pair.Channel.Write(Large(),150)));
            Assert.That(write.Wait(2000),Is.True);Assert.That(write.Result,Is.EqualTo("FRAME_WRITE_TIMEOUT"));Assert.That(pair.Channel.IsClosed,Is.True);
            Assert.That(Failure(()=>pair.Channel.Write("retry")),Is.EqualTo("FRAME_CLOSED"));
        }
        [Test] public void CancellationStopsAWriteAndClosesTheChannel()
        {
            using var pair=new Pair();using var stop=new CancellationTokenSource();
            var write=Task.Run(()=>Failure(()=>pair.Channel.Write(Large(),5000,stop.Token)));
            Assert.That(SpinWait.SpinUntil(()=>pair.Channel.WriteInProgress,1000),Is.True);stop.Cancel();
            Assert.That(write.Wait(2000),Is.True);Assert.That(write.Result,Is.EqualTo("FRAME_WRITE_CANCELLED"));Assert.That(pair.Channel.IsClosed,Is.True);
        }
        [Test] public void OwnerDisposalStopsAnOutstandingWrite()
        {
            using var pair=new Pair();var write=Task.Run(()=>Failure(()=>pair.Channel.Write(Large(),5000)));
            Assert.That(SpinWait.SpinUntil(()=>pair.Channel.WriteInProgress,1000),Is.True);pair.Channel.Dispose();
            Assert.That(write.Wait(2000),Is.True);Assert.That(write.Result,Is.EqualTo("FRAME_CLOSED"));
        }
        [Test] public void ConcurrentWritersCannotInterleaveTheirFrameBytes()
        {
            using var pair=new Pair();var first=Task.Run(()=>Failure(()=>pair.Channel.Write(Large(),5000)));
            Assert.That(SpinWait.SpinUntil(()=>pair.Channel.WriteInProgress,1000),Is.True);
            Assert.That(Failure(()=>pair.Channel.Write("other",1000)),Is.EqualTo("FRAME_CONCURRENT_WRITE"));
            Assert.That(first.Wait(2000),Is.True);Assert.That(first.Result,Is.EqualTo("FRAME_CLOSED"));
        }
        [TestCase("null","FRAME_SIZE")] [TestCase("empty","FRAME_SIZE")]
        [TestCase("bom","FRAME_BOM")] [TestCase("utf8","FRAME_UTF8")]
        public void InvalidFramesWriteNoHeaderAndLeaveAnUnusedChannelAvailable(string defect,string code)
        {
            string text=defect=="null"?null:defect=="empty"?"":defect=="bom"?"\ufeffbad":new string((char)0xd800,1);
            using var pair=new Pair();Assert.That(Failure(()=>pair.Channel.Write(text,1000)),Is.EqualTo(code));
            Assert.That(pair.Channel.IsClosed,Is.False);pair.Channel.Write("valid",1000);
            Assert.That(TextFrame.Read(pair.Peer.GetStream()),Is.EqualTo("valid"));
        }
        [TestCase(0)] [TestCase(60001)] public void InvalidBudgetsDoNotWriteAnything(int budget)
        {
            using var pair=new Pair();Assert.Throws<ArgumentOutOfRangeException>(()=>pair.Channel.Write("bad",budget));
            pair.Channel.Write("valid",1000);Assert.That(TextFrame.Read(pair.Peer.GetStream()),Is.EqualTo("valid"));
        }
        [Test] public void PreCancelledWriteDoesNotTurnAPendingCommandIntoARejection()
        {
            using var pair=new Pair();using var stop=new CancellationTokenSource();using var tracker=new CommandTracker("session","one");
            string command=new JObject{["wire_version"]=1,["message_type"]="command",["message_id"]="c1",["body"]=new JObject{
                ["session_id"]="session",["viewer_id"]="one",["revision"]=7,["decision_id"]="decision",["operation"]="perform",["action_id"]="action"}}.ToString();
            tracker.Begin(command);stop.Cancel();Assert.That(Failure(()=>pair.Channel.Write(command,1000,stop.Token)),Is.EqualTo("FRAME_WRITE_CANCELLED"));
            tracker.Disconnect();Assert.That(tracker.Current.State,Is.EqualTo(CommandState.Uncertain));Assert.That(tracker.CanSubmit,Is.False);
        }
    }
}

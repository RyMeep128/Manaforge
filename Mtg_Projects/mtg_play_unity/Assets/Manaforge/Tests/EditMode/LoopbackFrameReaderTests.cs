using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using NUnit.Framework;
namespace Manaforge.Play.Tests
{
    public sealed class LoopbackFrameReaderTests
    {
        private sealed class Pair : IDisposable
        {
            public readonly TcpClient Sender;
            public readonly LoopbackFrameReader Reader;
            public Pair()
            {
                var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
                try {
                    Sender=new TcpClient(AddressFamily.InterNetwork);
                    Assert.That(Sender.ConnectAsync(IPAddress.Loopback,((IPEndPoint)listener.LocalEndpoint).Port).Wait(2000),Is.True);
                    var accepted=listener.AcceptSocket();accepted.LingerState=new LingerOption(true,5);
                    Reader=new LoopbackFrameReader(accepted);
                    Assert.That(accepted.LingerState.Enabled,Is.False,"Owned close must not wait for configured linger");
                } catch { Sender?.Dispose();throw; }
                finally { listener.Stop(); }
            }
            public void Send(byte[] bytes) => Sender.GetStream().Write(bytes,0,bytes.Length);
            public void Dispose(){Reader.Dispose();Sender.Dispose();}
        }
        private static string Failure(Action read)
        {
            var error=Assert.Throws<TextFrame.FrameException>(()=>read());
            Assert.That(error.Message,Is.EqualTo(error.Code));return error.Code;
        }
        [Test] public void CompleteFramesAndBetweenFrameEofRemainDistinct()
        {
            using var pair=new Pair();TextFrame.Write(pair.Sender.GetStream(),"one");TextFrame.Write(pair.Sender.GetStream(),"two");
            pair.Sender.Client.Shutdown(SocketShutdown.Send);
            Assert.That(pair.Reader.Read(1000),Is.EqualTo("one"));Assert.That(pair.Reader.Read(1000),Is.EqualTo("two"));
            Assert.That(pair.Reader.Read(1000),Is.Null);Assert.That(pair.Reader.IsClosed,Is.False,"Owner decides whether EOF is expected");
        }
        [TestCase(0)] [TestCase(2)] [TestCase(5)]
        public void IdlePartialHeaderAndPartialPayloadHaveOneAbsoluteDeadline(int bytes)
        {
            using var pair=new Pair();var partial=new byte[]{0,0,0,4,(byte)'a'};
            if(bytes>0){var data=new byte[bytes];Array.Copy(partial,data,bytes);pair.Send(data);}
            var timer=Stopwatch.StartNew();Assert.That(Failure(()=>pair.Reader.Read(120)),Is.EqualTo("FRAME_TIMEOUT"));
            Assert.That(timer.ElapsedMilliseconds,Is.GreaterThanOrEqualTo(80).And.LessThan(2000));
            Assert.That(pair.Reader.IsClosed,Is.True);Assert.That(Failure(()=>pair.Reader.Read()),Is.EqualTo("FRAME_CLOSED"));
        }
        [Test] public void TricklingBytesCannotResetTheFrameBudget()
        {
            using var pair=new Pair();using var stop=new CancellationTokenSource();
            var sender=Task.Run(()=>{
                try {
                    var frame=new byte[36];frame[3]=32;
                    foreach(byte value in frame){if(stop.Token.WaitHandle.WaitOne(30))break;pair.Send(new[]{value});}
                } catch(Exception error) when(error is IOException || error is SocketException || error is ObjectDisposedException){}
            });
            try {
                var timer=Stopwatch.StartNew();Assert.That(Failure(()=>pair.Reader.Read(180)),Is.EqualTo("FRAME_TIMEOUT"));
                Assert.That(timer.ElapsedMilliseconds,Is.LessThan(1500));Assert.That(pair.Reader.IsClosed,Is.True);
            } finally{stop.Cancel();Assert.That(sender.Wait(2000),Is.True,"Owned trickle writer did not stop");}
        }
        [TestCase(2)] [TestCase(5)] public void CancellationClosesAReadWaitingForTheRestOfAFrame(int bytes)
        {
            using var pair=new Pair();var partial=new byte[]{0,0,0,4,(byte)'a'};var data=new byte[bytes];Array.Copy(partial,data,bytes);pair.Send(data);
            using var stop=new CancellationTokenSource();stop.CancelAfter(60);
            var read=Task.Run(()=>Failure(()=>pair.Reader.Read(5000,stop.Token)));
            Assert.That(read.Wait(2000),Is.True);Assert.That(read.Result,Is.EqualTo("FRAME_CANCELLED"));Assert.That(pair.Reader.IsClosed,Is.True);
        }
        [Test] public void ExplicitOwnerDisposalUnblocksTheWorker()
        {
            using var pair=new Pair();var read=Task.Run(()=>Failure(()=>pair.Reader.Read(5000)));
            Assert.That(SpinWait.SpinUntil(()=>pair.Reader.ReadInProgress,1000),Is.True);
            pair.Reader.Dispose();Assert.That(read.Wait(2000),Is.True);Assert.That(read.Result,Is.EqualTo("FRAME_CLOSED"));
        }
        [TestCase("size","FRAME_SIZE")] [TestCase("truncated","FRAME_TRUNCATED")] [TestCase("utf8","FRAME_UTF8")]
        public void FramingFailuresCloseRatherThanResumeTheSocket(string defect,string code)
        {
            using var pair=new Pair();
            pair.Send(defect=="size"?new byte[4]:defect=="truncated"?new byte[]{0,0,0,4,1}:new byte[]{0,0,0,1,255});
            pair.Sender.Client.Shutdown(SocketShutdown.Send);
            Assert.That(Failure(()=>pair.Reader.Read(1000)),Is.EqualTo(code));Assert.That(pair.Reader.IsClosed,Is.True);
        }
        [TestCase(0)] [TestCase(60001)] public void InvalidBudgetsDoNotConsumeInput(int milliseconds)
        {
            using var pair=new Pair();TextFrame.Write(pair.Sender.GetStream(),"still-owned");
            Assert.Throws<ArgumentOutOfRangeException>(()=>pair.Reader.Read(milliseconds));
            Assert.That(pair.Reader.Read(1000),Is.EqualTo("still-owned"));
        }
        [Test] public void ConcurrentReadersFailClosedInsteadOfDividingAFrame()
        {
            using var pair=new Pair();var first=Task.Run(()=>Failure(()=>pair.Reader.Read(5000)));
            Assert.That(SpinWait.SpinUntil(()=>pair.Reader.ReadInProgress,1000),Is.True);
            Assert.That(Failure(()=>pair.Reader.Read(1000)),Is.EqualTo("FRAME_CONCURRENT"));
            Assert.That(first.Wait(2000),Is.True);Assert.That(first.Result,Is.EqualTo("FRAME_CLOSED"));
        }
        [Test] public void PreCancelledReadClosesTheOwnedChannel()
        {
            using var pair=new Pair();using var stop=new CancellationTokenSource();stop.Cancel();
            Assert.That(Failure(()=>pair.Reader.Read(1000,stop.Token)),Is.EqualTo("FRAME_CANCELLED"));Assert.That(pair.Reader.IsClosed,Is.True);
        }
    }
}

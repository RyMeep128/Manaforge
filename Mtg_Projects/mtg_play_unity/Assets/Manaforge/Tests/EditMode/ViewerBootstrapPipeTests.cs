using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEngine;

namespace Manaforge.Play.Tests
{
    public sealed class ViewerBootstrapPipeTests
    {
        private sealed class Pair : IDisposable
        {
            public readonly AnonymousPipeServerStream Writer=new AnonymousPipeServerStream(PipeDirection.Out,HandleInheritability.Inheritable);
            public readonly ViewerBootstrapPipe Reader;
            public Pair(){Reader=ViewerBootstrapPipe.FromInheritedHandle(Writer.ClientSafePipeHandle);}
            public void Dispose(){Reader.Dispose();Writer.Dispose();}
        }
        private static byte[] Payload()=>Encoding.UTF8.GetBytes(JObject.Parse(File.ReadAllText(Path.Combine(Application.dataPath,"../../mtg_play/protocol/fixtures/viewer-bootstrap-v1.json")))["positive"][0].ToString());
        private static byte[] Frame(byte[] payload){int n=payload.Length;var frame=new byte[n+4];frame[0]=(byte)(n>>24);frame[1]=(byte)(n>>16);frame[2]=(byte)(n>>8);frame[3]=(byte)n;Array.Copy(payload,0,frame,4,n);return frame;}
        private static string Failure(Task task){Assert.That(SpinWait.SpinUntil(()=>task.IsCompleted,3000),Is.True,"Pipe worker did not retire");Assert.That(task.IsFaulted,Is.True);var error=task.Exception.GetBaseException() as ViewerBootstrapPipe.PipeException;Assert.That(error,Is.Not.Null);Assert.That(error.Message,Is.EqualTo(error.Code));return error.Code;}
        [Test] public void FragmentedPrivateFrameThenOwnerEofCompletesWithoutClosingCallerHandle()
        {
            using var pair=new Pair();var read=pair.Reader.ReadBootstrapAsync();var frame=Frame(Payload());
            var write=Task.Run(()=>{foreach(byte value in frame)pair.Writer.WriteByte(value);pair.Writer.Flush();});
            Assert.That(read.Wait(3000),Is.True);using var bootstrap=read.GetAwaiter().GetResult();Assert.That(write.Wait(3000),Is.True);
            Assert.That(bootstrap.ViewerId,Is.EqualTo("seat-one"));Assert.That(pair.Writer.ClientSafePipeHandle.IsClosed,Is.False);
            var lifeline=pair.Reader.WaitForOwnerCloseAsync();Assert.That(lifeline.Wait(30),Is.False);pair.Writer.Dispose();Assert.That(lifeline.Wait(3000),Is.True);
        }
        [TestCase(0,"BOOTSTRAP_PIPE_EOF")] [TestCase(2,"BOOTSTRAP_PIPE_TRUNCATED")] [TestCase(6,"BOOTSTRAP_PIPE_TRUNCATED")]
        public void EofBeforeOrInsideFrameRejectsPartialPayload(int count,string code)
        {
            using var pair=new Pair();var read=pair.Reader.ReadBootstrapAsync();var frame=Frame(Payload());pair.Writer.Write(frame,0,count);pair.Writer.Dispose();Assert.That(Failure(read),Is.EqualTo(code));
        }
        [Test] public void OversizeAndInvalidPayloadFailBeforeAnyBootstrapEscapes()
        {
            using(var pair=new Pair()){var read=pair.Reader.ReadBootstrapAsync();pair.Writer.Write(new byte[]{0,0,64,1},0,4);pair.Writer.Flush();Assert.That(Failure(read),Is.EqualTo("BOOTSTRAP_PIPE_SIZE"));}
            using(var pair=new Pair()){var read=pair.Reader.ReadBootstrapAsync();var frame=Frame(Encoding.UTF8.GetBytes("private malformed data"));pair.Writer.Write(frame,0,frame.Length);pair.Writer.Flush();Assert.That(Failure(read),Is.EqualTo("BOOTSTRAP_PIPE_PAYLOAD"));}
        }
        [Test] public void StalledHeaderAndPayloadShareOneBoundedStartupDeadline()
        {
            using(var pair=new Pair()){var time=Stopwatch.StartNew();Assert.That(Failure(pair.Reader.ReadBootstrapAsync(60)),Is.EqualTo("BOOTSTRAP_PIPE_TIMEOUT"));Assert.That(time.ElapsedMilliseconds,Is.LessThan(2000));}
            using(var pair=new Pair()){var read=pair.Reader.ReadBootstrapAsync(60);pair.Writer.Write(new byte[]{0,0,1,0},0,4);pair.Writer.Flush();Assert.That(Failure(read),Is.EqualTo("BOOTSTRAP_PIPE_TIMEOUT"));}
        }
        [Test] public void CancellationAndDisposeReleaseWaitingWorkersAndSingleConsumerIsEnforced()
        {
            using(var pair=new Pair())using(var cancel=new CancellationTokenSource()) {
                var read=pair.Reader.ReadBootstrapAsync(5000,cancel.Token);Assert.Throws<ViewerBootstrapPipe.PipeException>(()=>pair.Reader.ReadBootstrapAsync());
                Assert.Throws<ViewerBootstrapPipe.PipeException>(()=>pair.Reader.WaitForOwnerCloseAsync());cancel.Cancel();Assert.That(Failure(read),Is.EqualTo("BOOTSTRAP_PIPE_CANCELLED"));
            }
            using(var pair=new Pair()){var read=pair.Reader.ReadBootstrapAsync();pair.Reader.Dispose();Assert.That(Failure(read),Is.EqualTo("BOOTSTRAP_PIPE_CLOSED"));}
        }
        [Test] public void ExtraLifelineDataIsRejectedAndLifelineCancellationRetires()
        {
            using(var pair=new Pair()){var read=pair.Reader.ReadBootstrapAsync();var frame=Frame(Payload());pair.Writer.Write(frame,0,frame.Length);pair.Writer.Flush();Assert.That(read.Wait(3000),Is.True);using var value=read.Result;
                var lifeline=pair.Reader.WaitForOwnerCloseAsync();pair.Writer.WriteByte(1);pair.Writer.Flush();Assert.That(Failure(lifeline),Is.EqualTo("BOOTSTRAP_PIPE_UNEXPECTED_DATA"));}
            using(var pair=new Pair())using(var cancel=new CancellationTokenSource()){var read=pair.Reader.ReadBootstrapAsync();var frame=Frame(Payload());pair.Writer.Write(frame,0,frame.Length);pair.Writer.Flush();Assert.That(read.Wait(3000),Is.True);using var value=read.Result;
                var lifeline=pair.Reader.WaitForOwnerCloseAsync(cancel.Token);cancel.Cancel();Assert.That(Failure(lifeline),Is.EqualTo("BOOTSTRAP_PIPE_CANCELLED"));}
        }
    }
}

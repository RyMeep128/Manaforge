using System;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;

namespace Manaforge.Play.Protocol
{
    public static class ViewerSessionConnection
    {
        // Worker-only connect + fresh authentication under one budget. No DNS or credential arguments.
        public static Task<ClientSessionChannel> OpenAsync(ViewerBootstrap expected,int milliseconds=5000,CancellationToken cancellation=default,bool fixtureMode=false)
        {
            if(expected==null)throw new ArgumentNullException(nameof(expected));
            if(milliseconds<1 || milliseconds>60000)throw new ArgumentOutOfRangeException(nameof(milliseconds));
            var timer=Stopwatch.StartNew();
            return Task.Run(()=>{
                Socket socket=null;Task connecting=null;ClientSessionChannel channel=null;
                try {
                    Remaining(timer,milliseconds,cancellation);socket=new Socket(AddressFamily.InterNetwork,SocketType.Stream,ProtocolType.Tcp);
                    connecting=socket.ConnectAsync(IPAddress.Loopback,expected.Port);
                    while(!connecting.IsCompleted){Remaining(timer,milliseconds,cancellation);Thread.Sleep(10);}
                    connecting.GetAwaiter().GetResult();
                    var transport=new LoopbackFrameReader(socket);
                    channel=ViewerChallengeHandshake.Open(transport,expected,Remaining(timer,milliseconds,cancellation),cancellation,fixtureMode);
                    Remaining(timer,milliseconds,cancellation);socket=null;return channel;
                }
                catch(Exception error) {
                    channel?.Dispose();socket?.Dispose();
                    string code=cancellation.IsCancellationRequested?"AUTH_CANCELLED":error is WireEnvelope.EnvelopeException envelope && envelope.Code=="AUTH_TIMEOUT"?"AUTH_TIMEOUT":"AUTH_FAILED";
                    throw new WireEnvelope.EnvelopeException(code);
                }
                finally{if(connecting!=null)connecting.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);}
            });
        }
        private static int Remaining(Stopwatch timer,int budget,CancellationToken cancellation)
        {if(cancellation.IsCancellationRequested)throw new WireEnvelope.EnvelopeException("AUTH_CANCELLED");double left=budget-timer.Elapsed.TotalMilliseconds;if(left<=0)throw new WireEnvelope.EnvelopeException("AUTH_TIMEOUT");return Math.Max(1,(int)Math.Ceiling(left));}
    }
}

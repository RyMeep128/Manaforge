using System;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;

namespace Manaforge.Play
{
    public sealed class ViewerHostStop
    {
        public string Code {get;} public ViewerSessionStop Session {get;} public bool CleanupConfirmed {get;}
        internal ViewerHostStop(string code,ViewerSessionStop session,bool cleanup){Code=code;Session=session;CleanupConfirmed=cleanup;}
    }
    // Create/tick/dispose on the surface's UI thread. No network reads, parsing or waits occur there.
    public sealed class ViewerSessionHost : IDisposable
    {
        private readonly object gate=new object();private readonly int thread=Thread.CurrentThread.ManagedThreadId;
        private readonly ViewerCardSurface surface;private readonly ViewerSurfaceTicket ticket;private readonly ViewerBootstrap bootstrap;
        private readonly Task ownerEnded;private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private readonly CancellationToken token;private readonly TaskCompletionSource<ViewerHostStop> completion=new TaskCompletionSource<ViewerHostStop>(TaskCreationOptions.RunContinuationsAsynchronously);
        private ViewerSessionReceiver receiver;private ClientSessionChannel channel;private bool stopped,disposed;private string stopCode;
        public Task<ViewerHostStop> Completion=>completion.Task;
        public bool Authenticated {get{lock(gate)return !stopped && channel!=null;}}
        // Bootstrap ownership transfers only after BeginViewer succeeds. Parent owns its pipe/lifeline task.
        public ViewerSessionHost(ViewerCardSurface surface,ViewerBootstrap ownedBootstrap,Task ownerEnded,bool fixtureMode=false,int connectionMilliseconds=5000,int readMilliseconds=60000)
        {
            if(surface==null || ownedBootstrap==null || ownerEnded==null || connectionMilliseconds<1 || connectionMilliseconds>60000 || readMilliseconds<1 || readMilliseconds>60000)throw new ArgumentException("VIEWER_HOST_CONTEXT");
            var assets=new ViewerArtworkScope();
            try{ticket=surface.BeginViewer(ownedBootstrap.SessionId,ownedBootstrap.ViewerId,assets);}catch{assets.Dispose();throw;}
            this.surface=surface;bootstrap=ownedBootstrap;this.ownerEnded=ownerEnded;token=cancellation.Token;
            ownerEnded.ContinueWith(task=>{_=task.Exception;Stop("VIEWER_OWNER_ENDED");},TaskScheduler.Default);
            if(ownerEnded.IsCompleted)Stop("VIEWER_OWNER_ENDED");
            Task.Run(()=>Run(fixtureMode,connectionMilliseconds,readMilliseconds));
        }
        private async Task Run(bool fixtureMode,int connectionMilliseconds,int readMilliseconds)
        {
            ClientSessionChannel opened=null;ViewerSessionStop summary=null;bool cleanup=true;
            try {
                opened=await ViewerSessionConnection.OpenAsync(bootstrap,connectionMilliseconds,token,fixtureMode).ConfigureAwait(false);
                lock(gate){if(stopped)return;channel=opened;receiver=new ViewerSessionReceiver(channel,ticket,fixtureMode);}
                while(receiver.ReceiveOnce(readMilliseconds,token)){}
                Stop("VIEWER_RECEIVE_ENDED");
            }
            catch{Stop("VIEWER_CONNECT_FAILED");}
            finally {
                Stop("VIEWER_HOST_ENDED");
                if(receiver!=null)summary=await receiver.Completion.ConfigureAwait(false);
                try{opened?.Dispose();}catch{cleanup=false;}
                try{bootstrap.Dispose();cancellation.Dispose();}catch{cleanup=false;}
                completion.TrySetResult(new ViewerHostStop(stopCode,summary,cleanup));
            }
        }
        private void Stop(string code)
        {
            ViewerSessionReceiver active;ClientSessionChannel connected;
            lock(gate){if(stopped)return;stopped=true;stopCode=code;ticket.Mailbox.Dispose();active=receiver;connected=channel;}
            active?.Cancel();connected?.Cancel();try{cancellation.Cancel();}catch(ObjectDisposedException){}
        }
        public bool TryTake(out ViewerSessionUpdate update)
        {lock(gate){update=null;return !stopped && receiver!=null && receiver.TryTake(out update);}}
        private void ThreadOnly(){if(Thread.CurrentThread.ManagedThreadId!=thread)throw new InvalidOperationException("VIEWER_HOST_THREAD");}
        public int Tick(int maximumArtworkUploads=2,int maximumArtworkRequests=4)
        {
            ThreadOnly();if(disposed)return 0;
            if(ownerEnded.IsCompleted)Stop("VIEWER_OWNER_ENDED");return surface.Pump(ticket,maximumArtworkUploads,maximumArtworkRequests);
        }
        // Inspection is presentation-only; no action/decision token is fabricated or submitted.
        public bool Inspect(string objectId)
        {
            ThreadOnly();if(disposed)return false;
            if(ownerEnded.IsCompleted)Stop("VIEWER_OWNER_ENDED");
            bool revoked;lock(gate)revoked=stopped;
            if(revoked){surface.Pump(ticket);return false;}return surface.Inspect(ticket,objectId);
        }
        public void Cancel(){Stop("VIEWER_HOST_CANCELLED");}
        public void Dispose(){ThreadOnly();if(disposed)return;disposed=true;Stop("VIEWER_HOST_DISPOSED");surface.ClearViewer(ticket);}
    }
}

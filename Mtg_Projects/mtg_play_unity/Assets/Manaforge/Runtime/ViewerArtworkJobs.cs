using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Manaforge.Play
{
    // Provider runs on a worker: existing Core cache mapping/decoder in, prepared pixels out.
    // No provider callback or cancellation callback executes under gate or on the calling UI thread.
    public sealed class ViewerArtworkJobs : IDisposable
    {
        private readonly object gate=new object();
        private readonly ViewerSurfaceTicket ticket;
        private readonly Func<ViewerArtworkRequest,CancellationToken,Task<PreparedCardArtwork>> provider;
        private readonly Queue<ViewerArtworkRequest> queue=new Queue<ViewerArtworkRequest>();
        private readonly HashSet<ViewerArtworkRequest> pending=new HashSet<ViewerArtworkRequest>();
        private readonly CancellationTokenSource cancellation=new CancellationTokenSource();
        private readonly CancellationToken token;
        private readonly TaskCompletionSource<bool> completion=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly int concurrency,maximumQueued;
        private int workers,running;
        private bool stopped,cancellationFinished,finished;
        private string lastCode;
        internal ViewerArtworkJobs(ViewerSurfaceTicket ticket,Func<ViewerArtworkRequest,CancellationToken,Task<PreparedCardArtwork>> provider,int concurrency,int maximumQueued)
        {
            if(provider==null)throw new ArgumentNullException(nameof(provider));
            if(concurrency<1 || concurrency>8 || maximumQueued<1 || maximumQueued>128)throw new ArgumentException("ARTWORK_JOB_LIMITS");
            this.ticket=ticket;this.provider=provider;this.concurrency=concurrency;this.maximumQueued=maximumQueued;token=cancellation.Token;
        }
        public int RunningCount {get{lock(gate)return running;}}
        public int QueuedCount {get{lock(gate)return queue.Count;}}
        public string LastCode {get{lock(gate)return lastCode;}}
        public bool IsStopped {get{lock(gate)return stopped;}}
        public Task Completion=>completion.Task;
        public bool TryQueue(ViewerArtworkRequest request)
        {
            if(request==null)return false;
            lock(gate) {
                if(stopped || !ReferenceEquals(request.Ticket,ticket) || !ticket.Mailbox.AllowsArtwork(request.Revision))return false;
                int count=queue.Count;
                for(int i=0;i<count;i++){var queued=queue.Dequeue();if(ticket.Mailbox.AllowsArtwork(queued.Revision))queue.Enqueue(queued);else pending.Remove(queued);}
                if(pending.Contains(request) || queue.Count>=maximumQueued)return false;
                pending.Add(request);queue.Enqueue(request);
                StartWorkers();
                return true;
            }
        }
        private void Code(string value){lock(gate)lastCode=value;}
        private void StartWorkers()
        {while(!stopped && !ticket.Mailbox.IsStopped && workers<concurrency && workers<queue.Count+running){workers++;Task.Run(RunWorker);}}
        private void FinishIfStopped()
        {
            if(!stopped || workers!=0 || !cancellationFinished || finished)return;
            finished=true;cancellation.Dispose();completion.TrySetResult(true);
        }
        private async Task RunWorker()
        {
            try {
                while(true) {
                    ViewerArtworkRequest request;
                    lock(gate) {
                        if(stopped || ticket.Mailbox.IsStopped || queue.Count==0)return;
                        request=queue.Dequeue();
                        if(!ticket.Mailbox.AllowsArtwork(request.Revision)){pending.Remove(request);continue;}
                        running++;
                    }
                    PreparedCardArtwork prepared=null;
                    try {
                        token.ThrowIfCancellationRequested();
                        prepared=await provider(request,token).ConfigureAwait(false);
                        if(prepared==null)Code("ARTWORK_JOB_UNAVAILABLE");
                        else if(!ReferenceEquals(prepared.Request,request))Code("ARTWORK_JOB_RESULT");
                        else {
                            lock(gate) {
                                if(stopped || token.IsCancellationRequested || ticket.Mailbox.IsStopped)lastCode="ARTWORK_JOB_CANCELLED";
                                else {bool posted=ticket.Mailbox.TryPostArtwork(prepared);prepared=null;if(!posted)lastCode="ARTWORK_JOB_DROPPED";}
                            }
                        }
                    }
                    catch(OperationCanceledException){Code("ARTWORK_JOB_CANCELLED");}
                    catch{Code("ARTWORK_JOB_FAILED");}
                    finally{prepared?.Dispose();lock(gate){running--;pending.Remove(request);}}
                }
            }
            catch{Code("ARTWORK_JOB_FAILED");}
            finally{lock(gate){workers--;StartWorkers();FinishIfStopped();}}
        }
        // Nonblocking: cancels providers on a worker, never waits on the Unity thread.
        public void Dispose()
        {
            lock(gate) {
                if(stopped)return;stopped=true;
                while(queue.Count>0)pending.Remove(queue.Dequeue());
            }
            Task.Run(()=>{
                try{cancellation.Cancel();}catch{Code("ARTWORK_JOB_CANCELLATION_CALLBACK_FAILED");}
                finally{lock(gate){cancellationFinished=true;FinishIfStopped();}}
            });
        }
    }
}

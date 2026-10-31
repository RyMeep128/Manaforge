using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Manaforge.Play
{
    // Explicit input only. No JSON/network writes on UI, defaults, retries or inferred game choices.
    public sealed class ViewerCommandDispatcher : IDisposable
    {
        private enum Operation { Perform,Choose,Finish,Cancel,Number,Amounts }
        private readonly object gate=new object();private readonly ClientSessionChannel channel;private readonly ViewerDecisionBinding binding;private readonly int milliseconds;
        private bool stopped;private int running;private readonly TaskCompletionSource<bool> completion=new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task Completion=>completion.Task;
        internal ViewerCommandDispatcher(ClientSessionChannel channel,ViewerDecisionBinding binding,int milliseconds)
        {this.channel=channel;this.binding=binding;this.milliseconds=milliseconds;}
        public Task<TrackedCommand> PerformAsync(ViewerDecisionOffer offer,ProjectedAction action,CancellationToken cancellation=default)=>Queue(offer,Operation.Perform,action,null,cancellation);
        public Task<TrackedCommand> ChooseAsync(ViewerDecisionOffer offer,ProjectedChoiceOption option,CancellationToken cancellation=default)=>Queue(offer,Operation.Choose,null,option,cancellation);
        public Task<TrackedCommand> FinishSelectionAsync(ViewerDecisionOffer offer,CancellationToken cancellation=default)=>Queue(offer,Operation.Finish,null,null,cancellation);
        public Task<TrackedCommand> CancelChoiceAsync(ViewerDecisionOffer offer,CancellationToken cancellation=default)=>Queue(offer,Operation.Cancel,null,null,cancellation);
        public Task<TrackedCommand> ChooseNumberAsync(ViewerDecisionOffer offer,long value,CancellationToken cancellation=default)
            =>Queue(offer,Operation.Number,null,null,cancellation,value);
        public Task<TrackedCommand> ChooseAmountsAsync(ViewerDecisionOffer offer,long[] values,CancellationToken cancellation=default)
        {
            if(cancellation.IsCancellationRequested)return Task.FromCanceled<TrackedCommand>(cancellation);
            if(values==null || values.Length>WireMessages.MaxAmountValues)return Task.FromException<TrackedCommand>(new WireEnvelope.EnvelopeException("AMOUNT_OUT_OF_RANGE"));
            return Queue(offer,Operation.Amounts,null,null,cancellation,0,(long[])values.Clone());
        }
        private static void Fail(string code)=>throw new WireEnvelope.EnvelopeException(code);
        private Task<TrackedCommand> Queue(ViewerDecisionOffer offer,Operation operation,ProjectedAction action,ProjectedChoiceOption option,CancellationToken cancellation,long number=0,long[] amounts=null)
        {
            if(cancellation.IsCancellationRequested)return Task.FromCanceled<TrackedCommand>(cancellation);
            ViewerDecisionBinding.Reservation reservation=null;
            lock(gate) {
                try {
                    if(stopped)Fail("SESSION_STOPPED");if(running!=0)Fail("COMMAND_PENDING");
                    reservation=binding.Reserve(offer);var frame=reservation.Frame;
                    if(operation==Operation.Perform && (action==null || !frame.Actions.Any(value=>ReferenceEquals(value,action))))Fail("ACTION_UNAVAILABLE");
                    if(operation==Operation.Choose && (option==null || !frame.Decision.Options.Any(value=>ReferenceEquals(value,option))))Fail("OPTION_UNAVAILABLE");
                    if(operation==Operation.Finish && !frame.Decision.CanFinish)Fail("SELECTION_NOT_FINISHABLE");
                    if(operation==Operation.Cancel && !frame.Decision.Cancellable)Fail("CANCELLATION_UNSUPPORTED");
                    running++;var owned=reservation;return Task.Run(()=>Send(owned,operation,action,option,cancellation,number,amounts));
                }
                catch(Exception error){if(reservation!=null)binding.Release(reservation);return Task.FromException<TrackedCommand>(error is WireEnvelope.EnvelopeException?error:new WireEnvelope.EnvelopeException("COMMAND_UNAVAILABLE"));}
            }
        }
        private TrackedCommand Send(ViewerDecisionBinding.Reservation reservation,Operation operation,ProjectedAction action,ProjectedChoiceOption option,CancellationToken cancellation,long number,long[] amounts)
        {
            ClientSessionChannel.PreparedSubmission prepared=null;
            try {
                cancellation.ThrowIfCancellationRequested();lock(gate){if(stopped)Fail("SESSION_STOPPED");}
                var frame=reservation.Frame;var body=new JObject{["session_id"]=frame.Context.SessionId,["viewer_id"]=frame.Context.ViewerId,["revision"]=frame.Context.Revision,["decision_id"]=frame.Decision.DecisionId,
                    ["operation"]=operation==Operation.Perform?"perform":operation==Operation.Choose?"choose":operation==Operation.Finish?"finish_selection":operation==Operation.Number?"choose_number":operation==Operation.Amounts?"choose_amounts":"cancel"};
                if(operation==Operation.Number)body["value"]=number;if(operation==Operation.Amounts)body["values"]=new JArray(amounts.Select(value=>new JValue(value)));
                if(action!=null)body["action_id"]=action.ActionId;if(option!=null)body["option_id"]=option.OptionId;
                string text=new JObject{["wire_version"]=1,["message_type"]="command",["message_id"]="ui_"+Guid.NewGuid().ToString("N"),["body"]=body}.ToString(Formatting.None);
                prepared=binding.Prepare(reservation,text);return channel.WriteSubmission(prepared,milliseconds,cancellation);
            }
            finally{prepared?.Dispose();binding.Release(reservation);lock(gate){running--;if(stopped && running==0)completion.TrySetResult(true);}}
        }
        public void Dispose()
        {lock(gate){if(stopped)return;stopped=true;if(running==0)completion.TrySetResult(true);}channel.Cancel();}
    }
}

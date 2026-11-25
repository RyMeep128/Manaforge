using System;
using System.Collections.Generic;
using System.Linq;

namespace Manaforge.Play
{
    public enum PriorityResponse { Unknown, Yes, No }
    public sealed class UnityPrioritySettings
    {
        public bool Automatic=true,Manual,Paused;
        public readonly HashSet<string> Stops=new HashSet<string>(StringComparer.Ordinal);
        public bool RepeatStops;
        internal readonly HashSet<string> OneShotStops=new HashSet<string>(StringComparer.Ordinal);
        internal readonly Dictionary<string,string> StopVisits=new Dictionary<string,string>(StringComparer.Ordinal);
        internal HashSet<string> PreviousBattlefield=new HashSet<string>(StringComparer.Ordinal);
        internal string ObservedStep;
        internal long? ObservedTurn;
        internal bool EndStepOwnArrival,EndStepOpponentArrival;
        internal readonly HashSet<string> EndStepArrivedSources=new HashSet<string>(StringComparer.Ordinal);
        internal readonly HashSet<string> SmartSeen=new HashSet<string>(StringComparer.Ordinal);
        public string Yield {get;internal set;}
        public string Reason {get;internal set;}="Waiting for priority";
        internal long? YieldTurn;
        internal string YieldStack;
        internal string ResolveBoundary;
        internal bool OptionalResponseBoundary;
        internal bool? YieldManual;
        internal string FullControlPhase;
        internal long? FullControlTurn;
        public bool TemporaryFullControl=>FullControlPhase!=null;
        internal long Revision=-1;
        internal readonly HashSet<string> Attempted=new HashSet<string>(StringComparer.Ordinal);
    }
    // Only engine-supplied priority, actions and completeness are considered here.
    // This policy never calculates legality or answers another decision family.
    public sealed class UnityPriorityPolicy
    {
        public static readonly string[] Steps={"UNTAP","UPKEEP","DRAW","PRECOMBAT_MAIN","BEGIN_COMBAT","DECLARE_ATTACKERS","DECLARE_BLOCKERS","FIRST_COMBAT_DAMAGE","COMBAT_DAMAGE","END_COMBAT","POSTCOMBAT_MAIN","END_TURN","CLEANUP"};
        public static readonly string[] Phases={"BEGINNING","PRECOMBAT_MAIN","COMBAT","POSTCOMBAT_MAIN","END"};
        private readonly Dictionary<Tuple<string,string>,UnityPrioritySettings> seats=new Dictionary<Tuple<string,string>,UnityPrioritySettings>();
        private Tuple<string,string> context;
        public UnityPrioritySettings Current {get;private set;}=new UnityPrioritySettings();
        public static string StackKey(ProjectedDecisionFrame frame)=>string.Join("|",frame.StackIds);
        public static PriorityResponse Responses(ProjectedDecisionFrame frame)
        {
            if(frame==null || !frame.ActionsComplete || frame.Decision?.IsPriority!=true)return PriorityResponse.Unknown;
            return frame.Actions.Any(action=>action.Kind!="pass" && !(action.Kind=="activate" && action.PriorityClass=="basic_mana")) || frame.Decision?.Options.Count>0
                ?PriorityResponse.Yes:PriorityResponse.No;
        }
        public void CancelYield(){if(Current.YieldManual.HasValue && !Current.Manual)Current.Manual=Current.YieldManual.Value;Current.YieldManual=null;Current.Yield=null;Current.YieldTurn=null;Current.YieldStack=null;Current.ResolveBoundary=null;Current.OptionalResponseBoundary=false;}
        public void Suspend(){CancelYield();Current.Paused=true;Current.Reason="Automatic passing suspended";}
        public void Failed(){CancelYield();Current.Paused=true;Current.Reason="Automatic passing paused after a command failure";}
        public void Resume(){Current.Paused=false;}
        private void HoldBoundary(ProjectedDecisionFrame frame){Current.ResolveBoundary=frame?.Decision?.IsPriority==true && frame.Decision.PlayerId==frame.Context.ViewerId?frame.Decision.DecisionId:"pending";Current.OptionalResponseBoundary=false;Current.EndStepOwnArrival=Current.EndStepOpponentArrival=false;Current.EndStepArrivedSources.Clear();}
        public void CancelPassing(ProjectedDecisionFrame frame){CancelYield();HoldBoundary(frame);}
        public void SetTemporaryFullControl(bool enabled,ProjectedDecisionFrame frame)
        {
            Observe(frame);CancelYield();
            Current.FullControlPhase=enabled?(frame?.Phase??"pending"):null;
            Current.FullControlTurn=enabled?frame?.Turn:null;
        }
        public static bool HasStop(UnityPrioritySettings settings,ProjectedDecisionFrame frame)
        {
            if(frame==null)return false;
            string scope=frame.ActivePlayerId==frame.Context.ViewerId?"own:":"opponent:";
            return settings.Stops.Contains("step:"+frame.Step) || settings.Stops.Contains("phase:"+frame.Phase)
                || settings.Stops.Contains(scope+"step:"+frame.Step) || settings.Stops.Contains(scope+"phase:"+frame.Phase);
        }
        public void BeginYield(string mode,ProjectedDecisionFrame frame)
        {
            Observe(frame);if(frame==null || (mode!="response" && mode!="turn" && mode!="stack" && mode!="end-turn" && mode!="resolve-stack") || frame.Status!="active" || frame.Result!=null)return;
            if(mode=="resolve-stack" && frame.StackIds.Count==0)return;
            CancelYield();Current.YieldManual=mode=="resolve-stack"?(bool?)Current.Manual:null;
            Current.Yield=mode;Current.YieldTurn=frame.Turn;Current.YieldStack=StackKey(frame);Current.Manual=false;
            Current.FullControlPhase=null;Current.FullControlTurn=null;
        }
        public bool SetStop(string kind,string value,bool enabled)
        {
            if(!(kind=="step" && Steps.Contains(value) || kind=="phase" && Phases.Contains(value)))return false;
            string key=kind+":"+value;if(enabled)Current.Stops.Add(key);else Current.Stops.Remove(key);return true;
        }
        public bool SetStop(string scope,string kind,string value,bool enabled,bool persistent=true)
        {
            if(scope!="own" && scope!="opponent")return false;
            if(!(kind=="step" && Steps.Contains(value) || kind=="phase" && Phases.Contains(value)))return false;
            string key=scope+":"+kind+":"+value;
            Current.StopVisits.Remove(key);Current.OneShotStops.Remove(key);
            if(enabled){Current.Stops.Add(key);if(!persistent)Current.OneShotStops.Add(key);}else Current.Stops.Remove(key);return true;
        }
        public void Observe(ProjectedDecisionFrame frame)
        {
            if(frame==null)return;
            var key=Tuple.Create(frame.Context.SessionId,frame.Context.ViewerId);
            if(!Equals(key,context)){
                CancelYield();Current.FullControlPhase=null;Current.FullControlTurn=null;context=key;
                if(!seats.TryGetValue(key,out var state)){state=new UnityPrioritySettings();seats.Add(key,state);}
                Current=state;CancelYield();Current.FullControlPhase=null;Current.FullControlTurn=null;
            }
            if(frame.Context.Revision<Current.Revision)return;
            Current.Revision=frame.Context.Revision;
            if(Current.ResolveBoundary=="pending" && frame.Decision?.IsPriority==true && frame.Decision.PlayerId==frame.Context.ViewerId)Current.ResolveBoundary=frame.Decision.DecisionId;
            if(frame.Status!="active" || frame.Result!=null){Suspend();return;}
            string scope=frame.ActivePlayerId==frame.Context.ViewerId?"own":"opponent";
            foreach(string stop in Current.OneShotStops.ToArray()){
                string[] parts=stop.Split(':');bool matches=parts[0]==scope && (parts[1]=="phase"?frame.Phase:frame.Step)==parts[2];
                string visit=frame.Turn+":"+(parts[1]=="phase"?frame.Phase:frame.Step);
                if(Current.StopVisits.TryGetValue(stop,out var entered) && (!matches || visit!=entered)){Current.Stops.Remove(stop);Current.OneShotStops.Remove(stop);Current.StopVisits.Remove(stop);}
                else if(matches)Current.StopVisits[stop]=visit;
            }
            bool ownEnd=scope=="own" && frame.Step=="END_TURN";
            var arrivals=frame.BattlefieldControllers.Where(card=>!Current.PreviousBattlefield.Contains(card.Key)).ToArray();
            if(ownEnd && Current.ObservedStep=="END_TURN" && Current.ObservedTurn==frame.Turn){
                Current.EndStepOwnArrival|=arrivals.Any(card=>card.Value==frame.Context.ViewerId);
                foreach(var card in arrivals.Where(card=>card.Value==frame.Context.ViewerId))Current.EndStepArrivedSources.Add(card.Key);
                Current.EndStepOpponentArrival|=arrivals.Any(card=>card.Value!=frame.Context.ViewerId);
            }
            else if(!ownEnd){Current.EndStepOwnArrival=Current.EndStepOpponentArrival=false;Current.EndStepArrivedSources.Clear();}
            Current.PreviousBattlefield=new HashSet<string>(frame.BattlefieldControllers.Keys,StringComparer.Ordinal);Current.ObservedStep=frame.Step;Current.ObservedTurn=frame.Turn;
            if(Current.FullControlPhase=="pending" && frame.Phase!=null){Current.FullControlPhase=frame.Phase;Current.FullControlTurn=frame.Turn;}
            else if(Current.FullControlPhase!=null && (Current.FullControlPhase!=frame.Phase || Current.FullControlTurn!=frame.Turn)){Current.FullControlPhase=null;Current.FullControlTurn=null;HoldBoundary(frame);}
            // A response boundary is retained on the exact offer: ordinary auto-pass
            // must not consume the opportunity that ended an explicit yield.
            if(Current.Yield=="response"){
                bool response=frame.StackIds.Any(id=>!(Current.YieldStack??"").Split('|').Contains(id) && (!frame.StackControllers.TryGetValue(id,out var controller) || controller!=frame.Context.ViewerId));
                if(response || arrivals.Any(card=>card.Value!=frame.Context.ViewerId) || frame.Turn!=Current.YieldTurn){CancelYield();HoldBoundary(frame);Current.OptionalResponseBoundary=true;}
                else Current.YieldStack=StackKey(frame);
            }
            if(Current.Yield=="turn" && (!frame.Turn.HasValue || !Current.YieldTurn.HasValue
                || frame.Turn<Current.YieldTurn || frame.ActivePlayerId==frame.Context.ViewerId && frame.Turn!=Current.YieldTurn))CancelYield();
            if(Current.Yield=="end-turn" && (!frame.Turn.HasValue || frame.Turn!=Current.YieldTurn))CancelYield();
            if(Current.Yield=="stack" && StackKey(frame)!=Current.YieldStack)CancelYield();
            if(Current.Yield=="resolve-stack"){
                if(frame.StackIds.Count==0){CancelYield();HoldBoundary(frame);}
                else if(frame.StackIds.Any(id=>!(Current.YieldStack??"").Split('|').Contains(id))){CancelYield();HoldBoundary(frame);}
            }
        }
        public ProjectedAction Evaluate(ProjectedDecisionFrame frame)
        {
            Observe(frame);
            string reason=null;
            if(frame==null || frame.Status!="active" || frame.Result!=null)reason="Waiting for priority";
            else if(frame.Context.Revision<Current.Revision)reason="Waiting for current state";
            else if(Current.Paused)reason="Automatic passing paused after a command failure";
            else if(Current.ResolveBoundary!=null && Current.ResolveBoundary==frame.Decision?.DecisionId && (!Current.OptionalResponseBoundary || Responses(frame)!=PriorityResponse.No))reason="Stack resolved";
            else if(Current.Manual || Current.TemporaryFullControl)reason="Full Control";
            else if(frame.Decision==null || !frame.Decision.IsPriority || frame.Decision.Family!="selection"
                || frame.Decision.PlayerId!=frame.Context.ViewerId || frame.PriorityPlayerId!=frame.Context.ViewerId)reason="Decision requires input";
            else if(frame.Step==null || !Steps.Contains(frame.Step) || !frame.Turn.HasValue || frame.ActivePlayerId==null)reason="Priority context unavailable";
            else if(HasStop(Current,frame))reason="Phase / step stop";
            else if(Current.Attempted.Contains(frame.Decision.DecisionId))reason="Waiting for engine confirmation";
            else if(Current.Yield==null && !Current.Automatic)reason="Automatic passing off";
            else if(Current.Yield==null)reason=AutomaticHold(frame);
            if(reason!=null){Current.Reason=reason;return null;}
            var passes=frame.Actions.Where(action=>action.Kind=="pass" && action.ObjectId==null).ToArray();
            if(passes.Length!=1){Current.Reason="Pass action unavailable";return null;}
            Current.Reason=Current.Yield=="resolve-stack"?"Resolving stack":Current.Yield=="end-turn"?"Yielding until this turn ends":Current.Yield=="turn"?"Yielding until my next turn":Current.Yield=="stack"?"Yielding until stack changes":"Automatic priority";
            return passes[0];
        }
        private string AutomaticHold(ProjectedDecisionFrame frame)
        {
            var response=Responses(frame);bool own=frame.ActivePlayerId==frame.Context.ViewerId;
            if(response==PriorityResponse.Unknown)return "Response information unavailable";
            if(own && frame.StackIds.Count==0 && (frame.Step=="PRECOMBAT_MAIN" || frame.Step=="POSTCOMBAT_MAIN")){
                if(frame.ViewerMana?.Any(amount=>amount.Value>0)==true)return "Floating mana: continue when ready";
                return response==PriorityResponse.Yes?"Main phase":null;
            }
            bool action=frame.Actions.Any(item=>item.Kind!="pass") || frame.Decision.Options.Count>0;
            bool ownArrival=Current.EndStepOwnArrival && frame.Actions.Any(item=>item.Kind=="activate" && item.ObjectId!=null && Current.EndStepArrivedSources.Contains(item.ObjectId)),opponentArrival=Current.EndStepOpponentArrival;
            Current.EndStepOwnArrival=Current.EndStepOpponentArrival=false;Current.EndStepArrivedSources.Clear();
            if(own && frame.Step=="END_TURN" && (frame.ViewerMana?.Any(amount=>amount.Value>0)==true || ownArrival && action || opponentArrival && response==PriorityResponse.Yes)){
                HoldBoundary(frame);return "Smart Priority: end-step opportunity";
            }
            if(frame.PriorityHints==null)return response==PriorityResponse.Yes?"Smart Priority information unavailable":null;
            bool knownTop=frame.PriorityObjectId!=null && frame.StackIds.Contains(frame.PriorityObjectId);
            if(action)foreach(string hint in frame.PriorityHints){
                bool smart=hint=="final_saga" || hint=="untap_resources" && own && frame.Step=="END_TURN" || response==PriorityResponse.Yes && (hint=="self_leaves" || hint=="copy_spell" || hint=="draw_hazard" && own && frame.Step=="UPKEEP");
                if(!smart)continue;
                if(hint!="draw_hazard" && !knownTop)return "Smart Priority context unavailable";
                string key=(hint=="draw_hazard"?frame.Turn+":"+frame.Step:frame.PriorityObjectId)+":"+hint;
                if(Current.SmartSeen.Add(key)){HoldBoundary(frame);return "Smart Priority: response opportunity";}
            }
            if(knownTop && frame.PriorityHints.Contains("own_stack"))return null;
            if(frame.StackIds.Count>0)return response==PriorityResponse.Yes?"Responses available":null;
            if(own && (frame.Step=="UPKEEP" || frame.Step=="DRAW" || frame.Step=="END_TURN" || frame.Step=="CLEANUP"))return null;
            return response==PriorityResponse.Yes?"Responses available":null;
        }
        public bool Claim(ProjectedDecisionFrame frame)
        {
            if(Evaluate(frame)==null)return false;
            return Current.Attempted.Add(frame.Decision.DecisionId);
        }
    }
}

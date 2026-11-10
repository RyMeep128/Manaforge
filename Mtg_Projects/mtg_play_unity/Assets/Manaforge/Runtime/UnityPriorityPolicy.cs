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
        public string Yield {get;internal set;}
        public string Reason {get;internal set;}="Waiting for priority";
        internal long? YieldTurn;
        internal string YieldStack;
        internal string ResolveBoundary;
        internal bool? YieldManual;
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
        public void CancelYield(){if(Current.YieldManual.HasValue && !Current.Manual)Current.Manual=Current.YieldManual.Value;Current.YieldManual=null;Current.Yield=null;Current.YieldTurn=null;Current.YieldStack=null;Current.ResolveBoundary=null;}
        public void Suspend(){CancelYield();Current.Paused=true;Current.Reason="Automatic passing suspended";}
        public void Failed(){CancelYield();Current.Paused=true;Current.Reason="Automatic passing paused after a command failure";}
        public void Resume(){Current.Paused=false;}
        public void BeginYield(string mode,ProjectedDecisionFrame frame)
        {
            Observe(frame);if(frame==null || (mode!="turn" && mode!="stack" && mode!="end-turn" && mode!="resolve-stack") || frame.Status!="active" || frame.Result!=null)return;
            if(mode=="resolve-stack" && frame.StackIds.Count==0)return;
            CancelYield();Current.YieldManual=mode=="resolve-stack"?(bool?)Current.Manual:null;
            Current.Yield=mode;Current.YieldTurn=frame.Turn;Current.YieldStack=StackKey(frame);Current.Manual=false;
        }
        public bool SetStop(string kind,string value,bool enabled)
        {
            if(!(kind=="step" && Steps.Contains(value) || kind=="phase" && Phases.Contains(value)))return false;
            string key=kind+":"+value;if(enabled)Current.Stops.Add(key);else Current.Stops.Remove(key);return true;
        }
        public void Observe(ProjectedDecisionFrame frame)
        {
            if(frame==null)return;
            var key=Tuple.Create(frame.Context.SessionId,frame.Context.ViewerId);
            if(!Equals(key,context)){
                CancelYield();context=key;
                if(!seats.TryGetValue(key,out var state)){state=new UnityPrioritySettings();seats.Add(key,state);}
                Current=state;CancelYield();
            }
            if(frame.Context.Revision<Current.Revision)return;
            Current.Revision=frame.Context.Revision;
            if(frame.Status!="active" || frame.Result!=null){Suspend();return;}
            if(Current.Yield=="turn" && (!frame.Turn.HasValue || !Current.YieldTurn.HasValue
                || frame.Turn<Current.YieldTurn || frame.ActivePlayerId==frame.Context.ViewerId && frame.Turn!=Current.YieldTurn))CancelYield();
            if(Current.Yield=="end-turn" && (!frame.Turn.HasValue || frame.Turn!=Current.YieldTurn))CancelYield();
            if(Current.Yield=="stack" && StackKey(frame)!=Current.YieldStack)CancelYield();
            if(Current.Yield=="resolve-stack"){
                if(frame.StackIds.Count==0){CancelYield();Current.ResolveBoundary=frame.Decision?.DecisionId;}
                else if(frame.StackIds.Any(id=>!(Current.YieldStack??"").Split('|').Contains(id)))CancelYield();
            }
        }
        public ProjectedAction Evaluate(ProjectedDecisionFrame frame)
        {
            Observe(frame);
            string reason=null;
            if(frame==null || frame.Status!="active" || frame.Result!=null)reason="Waiting for priority";
            else if(frame.Context.Revision<Current.Revision)reason="Waiting for current state";
            else if(Current.Paused)reason="Automatic passing paused after a command failure";
            else if(Current.ResolveBoundary!=null && Current.ResolveBoundary==frame.Decision?.DecisionId)reason="Stack resolved";
            else if(Current.Manual)reason="Manual control";
            else if(frame.Decision==null || !frame.Decision.IsPriority || frame.Decision.Family!="selection"
                || frame.Decision.PlayerId!=frame.Context.ViewerId || frame.PriorityPlayerId!=frame.Context.ViewerId)reason="Decision requires input";
            else if(frame.Step==null || !Steps.Contains(frame.Step) || !frame.Turn.HasValue || frame.ActivePlayerId==null)reason="Priority context unavailable";
            else if(Current.Stops.Contains("step:"+frame.Step) || Current.Stops.Contains("phase:"+frame.Phase))reason="Phase / step stop";
            else if(Current.Attempted.Contains(frame.Decision.DecisionId))reason="Waiting for engine confirmation";
            else if(Current.Yield==null && !Current.Automatic)reason="Automatic passing off";
            else if(Current.Yield==null && frame.Phase!="BEGINNING" && Responses(frame)!=PriorityResponse.No)reason=Responses(frame)==PriorityResponse.Unknown?"Response information unavailable":"Responses available";
            if(reason!=null){Current.Reason=reason;return null;}
            var passes=frame.Actions.Where(action=>action.Kind=="pass" && action.ObjectId==null).ToArray();
            if(passes.Length!=1){Current.Reason="Pass action unavailable";return null;}
            Current.Reason=Current.Yield=="resolve-stack"?"Resolving stack":Current.Yield=="end-turn"?"Yielding until this turn ends":Current.Yield=="turn"?"Yielding until my next turn":Current.Yield=="stack"?"Yielding until stack changes":"Automatic priority";
            return passes[0];
        }
        public bool Claim(ProjectedDecisionFrame frame)
        {
            if(Evaluate(frame)==null)return false;
            return Current.Attempted.Add(frame.Decision.DecisionId);
        }
    }
}

using System.Linq;
namespace Manaforge.Play
{
    public enum YieldPresentationMode { Normal, Yielding, RequiredInput, Stopped, Failed }
    // Shared presentation policy: no VisualElements, dispatch or game-rule changes.
    public sealed class YieldPresentation
    {
        public YieldPresentationMode Mode {get;}
        public string Text {get;}
        public string CancelLabel {get;}
        public bool Compact=>Mode==YieldPresentationMode.Yielding;
        private YieldPresentation(YieldPresentationMode mode,string text="",string cancel="Cancel yield")
        {Mode=mode;Text=text;CancelLabel=cancel;}
        public static YieldPresentation Resolve(UnityPrioritySettings settings,ProjectedDecisionFrame frame,bool controlsOpen=false,bool completed=false)
        {
            if(completed || frame!=null && (frame.Status!="active" || frame.Result!=null))return new YieldPresentation(YieldPresentationMode.Normal);
            if(settings.Paused)return new YieldPresentation(YieldPresentationMode.Failed,"Automatic passing paused. Check the current decision or resume automatic passing.");
            if(settings.Yield==null)return new YieldPresentation(YieldPresentationMode.Normal);
            if(controlsOpen || settings.Manual || frame!=null && (settings.Stops.Contains("step:"+frame.Step) || settings.Stops.Contains("phase:"+frame.Phase)))return new YieldPresentation(YieldPresentationMode.Stopped);
            if(frame!=null && (frame.Decision?.IsPriority!=true || frame.Decision.Family!="selection" || frame.Decision.PlayerId!=frame.Context.ViewerId || frame.PriorityPlayerId!=frame.Context.ViewerId || !frame.Turn.HasValue || frame.ActivePlayerId==null || !UnityPriorityPolicy.Steps.Contains(frame.Step) || frame.Actions.Count(a=>a.Kind=="pass" && a.ObjectId==null)!=1))return new YieldPresentation(YieldPresentationMode.RequiredInput);
            return new YieldPresentation(YieldPresentationMode.Yielding,settings.Yield=="end-turn"?"Ending your turn...":settings.Yield=="turn"?"Passing to your turn...":"Yielding until the stack changes...");
        }
    }
}

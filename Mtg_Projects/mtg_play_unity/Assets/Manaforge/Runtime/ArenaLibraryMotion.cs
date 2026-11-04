using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Decorative movement after authoritative library/hand count changes. Never draws a card.
    public sealed class ArenaLibraryMotion : IDisposable
    {
        [Serializable] private sealed class MotionPack { public float[] times,values,lift; }
        private readonly VisualElement root;private readonly Label local,opponent;private readonly Func<bool> reduced;
        private readonly List<VisualElement> ghosts=new List<VisualElement>();private readonly Dictionary<string,long?> libraries=new Dictionary<string,long?>(),hands=new Dictionary<string,long?>();
        private AnimationCurve easing=AnimationCurve.EaseInOut(0,0,1,1);private float[] lift;private string session,viewer;private long revision=-1;private int epoch;private bool disposed;
        private readonly List<IVisualElementScheduledItem> ticking=new List<IVisualElementScheduledItem>();
        public ArenaLibraryMotion(VisualElement root,Label local,Label opponent,Func<bool> reduced)
        {
            this.root=root;this.local=local;this.opponent=opponent;this.reduced=reduced;
            var asset=Resources.Load<TextAsset>("LocalCardVisuals/Motion/LibraryToHand");
            if(asset!=null)try{
                var pack=JsonUtility.FromJson<MotionPack>(asset.text);
                if(pack?.times!=null && pack.values!=null && pack.times.Length==pack.values.Length && pack.times.Length>=2 && pack.times.Length<=32){
                    var keys=pack.times.Select((time,i)=>new Keyframe(time,pack.values[i],0,0)).ToArray();
                    if(keys.All(k=>!float.IsNaN(k.time+k.value) && !float.IsInfinity(k.time+k.value))){easing=new AnimationCurve(keys);if(pack.lift!=null && pack.lift.Length>=2 && pack.lift.Length<=32 && pack.lift.All(v=>!float.IsNaN(v) && !float.IsInfinity(v)))lift=pack.lift;}
                }
            }catch(ArgumentException){}
        }
        public static int ConfirmedHandArrivals(long? priorLibrary,long? nextLibrary,long? priorHand,long? nextHand)
        {
            if(!priorLibrary.HasValue || !nextLibrary.HasValue || !priorHand.HasValue || !nextHand.HasValue)return 0;
            // No identity/ability reconstruction. A card back depicts only the observed count change.
            return (int)Math.Min(6,Math.Max(0,Math.Min(priorLibrary.Value-nextLibrary.Value,nextHand.Value-priorHand.Value)));
        }
        public void Observe(ProjectedDecisionFrame frame)
        {
            if(disposed || revision==frame.Context.Revision && session==frame.Context.SessionId && viewer==frame.Context.ViewerId)return;
            Cancel();bool initial=session!=frame.Context.SessionId || viewer!=frame.Context.ViewerId;
            if(initial){libraries.Clear();hands.Clear();}session=frame.Context.SessionId;viewer=frame.Context.ViewerId;revision=frame.Context.Revision;
            foreach(var pair in frame.PlayerLibraryCounts){
                frame.PlayerHandCounts.TryGetValue(pair.Key,out var hand);libraries.TryGetValue(pair.Key,out var oldLibrary);hands.TryGetValue(pair.Key,out var oldHand);
                int count=initial || frame.Phase==null || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase) || frame.Result!=null?0:ConfirmedHandArrivals(oldLibrary,pair.Value,oldHand,hand);
                var pile=pair.Key==viewer?local:opponent;var badge=pile.Q<Label>("zone-count");
                if(badge!=null)badge.text=pair.Value?.ToString()??"?";
                else pile.text="LIBRARY\n"+(pair.Value?.ToString()??"?")+"\nHand "+(hand?.ToString()??"?");
                libraries[pair.Key]=pair.Value;hands[pair.Key]=hand;
                if(count>0 && !reduced())Start(pile,pair.Key==viewer,count);
            }
        }
        private void Start(VisualElement pile,bool isLocal,int count)
        {
            var origin=root.WorldToLocal(pile.worldBound.center);float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            var destination=new Vector2(width*.48f,isLocal?height-130:65);int captured=epoch;float started=Time.unscaledTime;
            var batch=new List<VisualElement>();
            for(int i=0;i<count;i++){var card=new Label("◇"){pickingMode=PickingMode.Ignore,enableRichText=false};card.AddToClassList("library-flight");if(ArenaTableArt.Back(card))card.text="";root.Add(card);ghosts.Add(card);batch.Add(card);}
            var ticker=root.schedule.Execute(()=>{
                if(disposed || captured!=epoch || root.panel==null || reduced()){Cancel();return;}
                bool done=true;
                for(int i=0;i<batch.Count;i++){
                    float t=Mathf.Clamp01((Time.unscaledTime-started-i*.08f)/.6f);if(t<1)done=false;
                    float progress=Mathf.Clamp01(easing.Evaluate(t)),arch=Mathf.Sin(progress*Mathf.PI);
                    if(lift!=null && lift.Length>=2){float at=progress*(lift.Length-1);int index=Mathf.Min(lift.Length-2,(int)at);arch=Mathf.Lerp(lift[index],lift[index+1],at-index);}
                    var point=Vector2.Lerp(origin,destination,progress)+new Vector2(0,-arch*65);
                    point.x=Mathf.Clamp(point.x,45,Mathf.Max(45,width-45));point.y=Mathf.Clamp(point.y,70,Mathf.Max(70,height-70));
                    var card=batch[i];card.style.left=point.x-40;card.style.top=point.y-56;card.style.rotate=new Rotate(new Angle((1-progress)*-18));card.style.opacity=t>=1?0:1;
                }
                if(done)Cancel();
            }).Every(16);ticking.Add(ticker);
        }
        public void Cancel(){epoch++;foreach(var item in ticking)item.Pause();ticking.Clear();foreach(var card in ghosts)card.RemoveFromHierarchy();ghosts.Clear();}
        public void Dispose(){if(disposed)return;Cancel();disposed=true;libraries.Clear();hands.Clear();}
    }
}

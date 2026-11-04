using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public readonly struct LibraryMotionAnchors
    {
        public readonly Vector2 Source, Destination;
        public LibraryMotionAnchors(Vector2 source,Vector2 destination){Source=source;Destination=destination;}
    }
    // Decorative movement after authoritative library/hand count changes. Never draws a card.
    public sealed class ArenaLibraryMotion : IDisposable
    {
        private readonly VisualElement root;private readonly Func<string,LibraryMotionAnchors?> anchors;private readonly Func<bool> reduced;
        private readonly List<VisualElement> ghosts=new List<VisualElement>();private readonly Dictionary<string,long?> libraries=new Dictionary<string,long?>(),hands=new Dictionary<string,long?>();
        private AnimationCurve easing=AnimationCurve.EaseInOut(0,0,1,1);private string session,viewer;private long revision=-1;private int epoch;private bool disposed;
        private readonly List<IVisualElementScheduledItem> ticking=new List<IVisualElementScheduledItem>();
        public ArenaLibraryMotion(VisualElement root,Func<string,LibraryMotionAnchors?> anchors,Func<bool> reduced)
        {
            this.root=root;this.anchors=anchors ?? throw new ArgumentNullException(nameof(anchors));this.reduced=reduced;
            root.RegisterCallback<DetachFromPanelEvent>(Detached);
        }
        private void Detached(DetachFromPanelEvent e){if(e.target==root)Clear();}
        public static int ConfirmedHandArrivals(long? priorLibrary,long? nextLibrary,long? priorHand,long? nextHand)
        {
            if(!priorLibrary.HasValue || !nextLibrary.HasValue || !priorHand.HasValue || !nextHand.HasValue)return 0;
            // No identity/ability reconstruction. A card back depicts only the observed count change.
            return (int)Math.Min(6,Math.Max(0,Math.Min(priorLibrary.Value-nextLibrary.Value,nextHand.Value-priorHand.Value)));
        }
        public void Observe(ProjectedDecisionFrame frame)
        {
            if(disposed || revision==frame.Context.Revision && session==frame.Context.SessionId && viewer==frame.Context.ViewerId)return;
            bool initial=session!=frame.Context.SessionId || viewer!=frame.Context.ViewerId;
            if(initial){Cancel();libraries.Clear();hands.Clear();}
            if(reduced() || frame.Result!=null)Cancel();session=frame.Context.SessionId;viewer=frame.Context.ViewerId;revision=frame.Context.Revision;
            foreach(var pair in frame.PlayerLibraryCounts){
                frame.PlayerHandCounts.TryGetValue(pair.Key,out var hand);libraries.TryGetValue(pair.Key,out var oldLibrary);hands.TryGetValue(pair.Key,out var oldHand);
                int count=initial || frame.Phase==null || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase) || frame.Result!=null?0:ConfirmedHandArrivals(oldLibrary,pair.Value,oldHand,hand);
                libraries[pair.Key]=pair.Value;hands[pair.Key]=hand;
                if(count>0 && !reduced()){var points=anchors(pair.Key);if(points.HasValue)Start(points.Value,count);}
            }
        }
        private void Start(LibraryMotionAnchors anchors,int count)
        {
            var origin=anchors.Source;var destination=anchors.Destination;float width=root.resolvedStyle.width,height=root.resolvedStyle.height;int captured=epoch;float started=Time.unscaledTime;
            var batch=new List<VisualElement>();
            for(int i=0;i<count;i++){var card=new Label("◇"){pickingMode=PickingMode.Ignore,enableRichText=false};card.AddToClassList("library-flight");card.text="";GameplayTheme.Back(card);root.Add(card);ghosts.Add(card);batch.Add(card);}
            IVisualElementScheduledItem ticker=null;ticker=root.schedule.Execute(()=>{
                if(disposed || captured!=epoch || root.panel==null || reduced()){Cancel();return;}
                bool done=true;
                for(int i=0;i<batch.Count;i++){
                    float t=Mathf.Clamp01((Time.unscaledTime-started-i*.08f)/.6f);if(t<1)done=false;
                    float progress=Mathf.Clamp01(easing.Evaluate(t)),arch=Mathf.Sin(progress*Mathf.PI);
                    var point=Vector2.Lerp(origin,destination,progress)+new Vector2(0,-arch*65);
                    point.x=Mathf.Clamp(point.x,45,Mathf.Max(45,width-45));point.y=Mathf.Clamp(point.y,70,Mathf.Max(70,height-70));
                    var card=batch[i];card.style.left=point.x-40;card.style.top=point.y-56;card.style.rotate=new Rotate(new Angle((1-progress)*-18));card.style.opacity=t>=1?0:1;
                }
                if(done){ticker.Pause();ticking.Remove(ticker);foreach(var card in batch){card.RemoveFromHierarchy();ghosts.Remove(card);}}
            }).Every(16);ticking.Add(ticker);
        }
        public void Cancel(){epoch++;foreach(var item in ticking)item.Pause();ticking.Clear();foreach(var card in ghosts)card.RemoveFromHierarchy();ghosts.Clear();}
        public void Clear(){Cancel();libraries.Clear();hands.Clear();session=viewer=null;revision=-1;}
        public void Dispose(){if(disposed)return;Clear();disposed=true;root.UnregisterCallback<DetachFromPanelEvent>(Detached);}
    }
}

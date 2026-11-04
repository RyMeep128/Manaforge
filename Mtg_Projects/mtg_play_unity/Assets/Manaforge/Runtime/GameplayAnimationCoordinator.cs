using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // All movement is decorative. Authoritative CardViews, stats and input stay current.
    public sealed class GameplayAnimationCoordinator : IDisposable
    {
        public const int MaximumActive=8,MaximumParticles=64,MaximumPending=32;
        private readonly VisualElement root,layer;
        private readonly ViewerCardSurface surface;
        private readonly Func<string,string,Vector2?> zoneAnchor;
        private readonly Func<string,Vector2?> playerAnchor;
        private readonly Func<bool> reduced;
        private readonly Func<float> clock;
        private readonly IVisualElementScheduledItem ticker;
        private readonly Queue<List<Work>> pending=new Queue<List<Work>>();
        private readonly List<Run> active=new List<Run>();
        private readonly Dictionary<string,Vector2> points=new Dictionary<string,Vector2>();
        private readonly Dictionary<string,(ProjectedCard card,CardView view)> bindings=new Dictionary<string,(ProjectedCard,CardView)>();
        private string session,viewer;private long revision=-1,lastBatchRevision=-1;private float? holdStarted;
        private bool disposed,lastReduced,showingResult;private string lastResult;
        private sealed class Work
        {public GameplayMotionCue Cue;public Vector2? Prior;public float Ready,Queued;}
        private sealed class Run
        {
            public Work Work;public VisualElement Root;public Image Card;public Label Text;public ForgeMotionVisual Effect;
            public float Started,Duration;public Vector2 From,To,Size;public Texture Texture;public bool Reduced;
        }
        public int ActiveCount=>active.Count;
        public int PendingCount=>pending.Count;
        public int ParticleCount=>active.Sum(run=>run.Effect.ParticleCount);
        public bool HoldAutomaticPassing
        {
            get{
                if(disposed || !(HasMajor || surface.HasPendingMajorAnimations))return false;
                if(!holdStarted.HasValue)holdStarted=clock();
                return clock()-holdStarted.Value<2f;
            }
        }
        private bool HasMajor=>active.Any(run=>run.Work.Cue.Major) || pending.Any(group=>group.Any(work=>work.Cue.Major));
        public GameplayAnimationCoordinator(VisualElement root,ViewerCardSurface surface,Func<string,string,Vector2?> zoneAnchor,
            Func<string,Vector2?> playerAnchor,Func<bool> reduced,Func<float> clock=null)
        {
            this.root=root??throw new ArgumentNullException(nameof(root));this.surface=surface??throw new ArgumentNullException(nameof(surface));
            this.zoneAnchor=zoneAnchor??throw new ArgumentNullException(nameof(zoneAnchor));this.playerAnchor=playerAnchor??throw new ArgumentNullException(nameof(playerAnchor));
            this.reduced=reduced??throw new ArgumentNullException(nameof(reduced));this.clock=clock??(()=>Time.unscaledTime);
            layer=new VisualElement{name="gameplay-animation-layer",pickingMode=PickingMode.Ignore};
            layer.style.position=Position.Absolute;layer.style.left=layer.style.right=layer.style.top=layer.style.bottom=0;layer.style.overflow=Overflow.Hidden;
            root.Add(layer);root.RegisterCallback<DetachFromPanelEvent>(Detached);surface.Clearing+=Clear;
            ticker=root.schedule.Execute(()=>Advance()).Every(16);
        }
        private void Detached(DetachFromPanelEvent ev){if(ev.target==root)Clear();}
        public void Observe(ProjectedDecisionFrame frame,IEnumerable<GameplayMotionBatch> batches)
        {
            if(disposed || frame==null)return;
            if(session!=frame.Context.SessionId || viewer!=frame.Context.ViewerId){Clear();session=frame.Context.SessionId;viewer=frame.Context.ViewerId;}
            if(frame.Context.Revision<revision)return;revision=frame.Context.Revision;
            RefreshBindings();
            var incoming=batches.ToList();
            if(frame.Result!=null && lastResult!=frame.Result){
                if(!incoming.Any(batch=>batch.Cues.Any(cue=>cue.Kind==GameplayMotionKind.Result)))
                    incoming.Add(new GameplayMotionBatch(frame.Context,new[]{new GameplayMotionCue(GameplayMotionKind.Result,text:frame.Result=="win"?"Victory":frame.Result=="loss"?"Defeat":frame.Result=="draw"?"Draw":"Game complete")}));
                lastResult=frame.Result;showingResult=true;
            }
            foreach(var batch in incoming){
                if(batch.Context.SessionId!=session || batch.Context.ViewerId!=viewer || batch.Context.Revision>revision || batch.Context.Revision<=lastBatchRevision)continue;
                lastBatchRevision=batch.Context.Revision;
                var cues=batch.Cues;
                if(cues.Any(cue=>cue.Kind==GameplayMotionKind.Result)){ClearEffects();}
                if(pending.Count>=MaximumPending){pending.Clear();cues=new[]{new GameplayMotionCue(GameplayMotionKind.Summary,text:"Battlefield updated")};}
                float now=clock();int arrival=0;var group=new List<Work>();
                foreach(var cue in cues){
                    if(Revoked(cue))continue;
                    bool stagger=cue.Kind==GameplayMotionKind.Draw || cue.Kind==GameplayMotionKind.Arrive;
                    group.Add(new Work{Cue=cue,Prior=cue.SubjectId!=null && points.TryGetValue(cue.SubjectId,out var old)?old:(Vector2?)null,
                        Queued=now,Ready=now+(stagger?Mathf.Min(arrival++,6)*.1f:0)});
                }
                if(group.Count>0)pending.Enqueue(group);
            }
            // Capture screen positions only, never old textures or card characteristics.
            points.Clear();foreach(var pair in bindings)if(Displayed(pair.Value.view))points[pair.Key]=Center(pair.Value.view);
            if(HasMajor && !holdStarted.HasValue)holdStarted=clock();
        }
        private void RefreshBindings()
        {
            bindings.Clear();surface.VisitAnimationBindings((card,view)=>bindings[card.RenderId]=(card,view));
        }
        private bool Revoked(GameplayMotionCue cue)
        {
            foreach(var id in new[]{cue.SubjectId,cue.RelatedId})if(id!=null){var card=surface.AnimationCard(id);if(card==null){if(!playerAnchor(id).HasValue)return true;}else if(card.Hidden || card.FaceDown!=false)return true;}
            return false;
        }
        private static bool Displayed(CardView view)=>view.parent!=null && view.style.display.value!=DisplayStyle.None && view.worldBound.width>1 && view.worldBound.height>1;
        private Vector2 Center(VisualElement element)=>root.WorldToLocal(element.worldBound.center);
        private Vector2 Middle=>new Vector2(Mathf.Max(1,root.resolvedStyle.width)*.5f,Mathf.Max(1,root.resolvedStyle.height)*.42f);
        private Vector2? Anchor(string id)
        {
            if(id==null)return null;
            if(bindings.TryGetValue(id,out var binding) && !binding.card.Hidden && binding.card.FaceDown==false){
                if(Displayed(binding.view))return Center(binding.view);
                return zoneAnchor(binding.card.OwnerId,binding.card.Zone);
            }
            return playerAnchor(id);
        }
        private static bool Conflicts(GameplayMotionCue a,GameplayMotionCue b)
            =>a.SubjectId!=null && (a.SubjectId==b.SubjectId || a.SubjectId==b.RelatedId) || a.RelatedId!=null && (a.RelatedId==b.SubjectId || a.RelatedId==b.RelatedId);
        public void Advance()
        {
            if(disposed)return;
            if(!surface.CanAnimate && !showingResult){ClearEffects();return;}
            if(float.IsNaN(root.resolvedStyle.width) || root.resolvedStyle.width<1 || root.resolvedStyle.height<1)return;
            RefreshBindings();float now=clock();bool minimal=reduced();
            if(minimal && !lastReduced){
                foreach(var run in active){run.Reduced=true;run.Started=now;run.Duration=.15f;run.Effect.Reduced=true;run.Effect.ParticleCount=0;run.Effect.Link=false;if(run.Card!=null)run.Card.style.display=DisplayStyle.None;}
            }lastReduced=minimal;
            for(int i=active.Count-1;i>=0;i--){
                var run=active[i];var admitted=surface.AnimationCard(run.Work.Cue.SubjectId);
                bool lost=Revoked(run.Work.Cue) || run.Texture!=null && (admitted==null || !bindings.TryGetValue(run.Work.Cue.SubjectId??"",out var bound)
                    || bound.view.Artwork!=run.Texture || admitted.Printing?.PrintingId!=bound.card.Printing?.PrintingId || admitted.Printing?.OracleId!=bound.card.Printing?.OracleId);
                float t=Mathf.Clamp01((now-run.Started)/run.Duration);
                if(lost || t>=1){run.Root.RemoveFromHierarchy();active.RemoveAt(i);continue;}
                Render(run,t);
            }
            while(active.Count<MaximumActive && pending.Count>0){
                var group=pending.Peek();bool started=false;
                for(int i=0;i<group.Count && active.Count<MaximumActive;){
                    var work=group[i];
                    if(Revoked(work.Cue)){group.RemoveAt(i);continue;}
                    if(now-work.Queued>4 && work.Cue.Kind!=GameplayMotionKind.Result){group.Clear();group.Add(new Work{Cue=new GameplayMotionCue(GameplayMotionKind.Summary,text:"Battlefield updated"),Queued=now,Ready=now});i=0;continue;}
                    if(work.Ready>now || active.Any(run=>Conflicts(run.Work.Cue,work.Cue))){i++;continue;}
                    group.RemoveAt(i);Start(work,now,minimal);started=true;
                }
                if(group.Count==0)pending.Dequeue();else if(!started)break;
            }
            if(!HasMajor && !surface.HasPendingMajorAnimations)holdStarted=null;
            foreach(var pair in bindings)if(Displayed(pair.Value.view))points[pair.Key]=Center(pair.Value.view);
            if(active.Count>0)layer.BringToFront();
        }
        private void Start(Work work,float now,bool minimal)
        {
            var cue=work.Cue;var point=Anchor(cue.SubjectId)??zoneAnchor(cue.OwnerId,cue.ToZone??cue.FromZone)??Middle;
            if(cue.Kind==GameplayMotionKind.Cast)point=zoneAnchor(cue.OwnerId,"stack")??point;
            if(cue.Kind==GameplayMotionKind.Depart && cue.ToZone!=null)point=zoneAnchor(cue.OwnerId,cue.ToZone)??point;
            if(cue.Kind==GameplayMotionKind.Turn || cue.Kind==GameplayMotionKind.Result || cue.Kind==GameplayMotionKind.Summary)point=Middle;
            var run=new Run{Work=work,Started=now,Duration=minimal?.15f:cue.Duration,Reduced=minimal,From=point,To=point,Size=new Vector2(100,140)};
            if(cue.Kind==GameplayMotionKind.Draw){run.From=zoneAnchor(cue.OwnerId,"library")??point;run.To=zoneAnchor(cue.OwnerId,"hand")??point;}
            else if(cue.Kind==GameplayMotionKind.Cast || cue.Kind==GameplayMotionKind.Arrive){run.From=work.Prior??(cue.FromZone==null?(Vector2?)null:zoneAnchor(cue.OwnerId,cue.FromZone))??point+new Vector2(0,-35);}
            else if(cue.Kind==GameplayMotionKind.Depart){run.From=work.Prior??zoneAnchor(cue.OwnerId,cue.FromZone)??point;run.To=cue.ToZone==null?run.From+new Vector2(0,-45):point;}
            else if(cue.Kind==GameplayMotionKind.Attack || cue.Kind==GameplayMotionKind.Block){var target=Anchor(cue.RelatedId);if(target.HasValue)run.To=Vector2.Lerp(point,target.Value,.22f);}
            run.Root=new VisualElement{name="motion-"+cue.Kind.ToString().ToLowerInvariant(),pickingMode=PickingMode.Ignore};
            run.Root.style.position=Position.Absolute;run.Root.style.left=run.Root.style.right=run.Root.style.top=run.Root.style.bottom=0;layer.Add(run.Root);
            var color=cue.Kind==GameplayMotionKind.Boost?new Color(.3f,.88f,.48f):cue.Kind==GameplayMotionKind.Block?new Color(.35f,.7f,1):new Color(1,.48f,.16f);
            if(cue.Kind==GameplayMotionKind.Result && cue.Text=="Defeat")color=new Color(.85f,.22f,.12f);
            run.Effect=new ForgeMotionVisual{Tint=color,Reduced=minimal,ParticleCount=minimal?0:Mathf.Min(cue.Kind==GameplayMotionKind.Result?32:8,MaximumParticles-ParticleCount),
                Radius=cue.Kind==GameplayMotionKind.Result?145:cue.Kind==GameplayMotionKind.Turn?105:55,Link=cue.Kind==GameplayMotionKind.Attack || cue.Kind==GameplayMotionKind.Block};run.Root.Add(run.Effect);
            bool moving=cue.Kind==GameplayMotionKind.Draw || cue.Kind==GameplayMotionKind.Cast || cue.Kind==GameplayMotionKind.Arrive || cue.Kind==GameplayMotionKind.Depart
                || cue.Kind==GameplayMotionKind.Tap || cue.Kind==GameplayMotionKind.Untap || cue.Kind==GameplayMotionKind.Attack || cue.Kind==GameplayMotionKind.Block;
            if(!minimal && moving){
                run.Card=new Image{name="motion-card",pickingMode=PickingMode.Ignore,scaleMode=ScaleMode.ScaleToFit};run.Card.style.position=Position.Absolute;
                if(cue.Kind==GameplayMotionKind.Draw)GameplayTheme.Back(run.Card);
                else if(cue.SubjectId!=null && bindings.TryGetValue(cue.SubjectId,out var bound) && !bound.card.Hidden && bound.card.FaceDown==false){
                    var admitted=surface.AnimationCard(cue.SubjectId);
                    bool same=admitted!=null && !admitted.Hidden && admitted.FaceDown==false && admitted.Printing?.PrintingId==bound.card.Printing?.PrintingId && admitted.Printing?.OracleId==bound.card.Printing?.OracleId;
                    run.Texture=same?bound.view.Artwork:null;run.Card.image=run.Texture;
                    if(Displayed(bound.view))run.Size=new Vector2(Mathf.Clamp(bound.view.layout.width,65,170),Mathf.Clamp(bound.view.layout.height,90,238));
                }
                var visible=surface.AnimationCard(cue.SubjectId);
                bool generic=visible!=null && !visible.Hidden && visible.FaceDown==false;
                if(run.Texture==null && generic)GameplayTheme.Back(run.Card);
                if(cue.Kind==GameplayMotionKind.Draw || run.Texture!=null || generic)run.Root.Add(run.Card);else run.Card=null;
            }
            string text=cue.Text;
            if(text==null)text=cue.Kind==GameplayMotionKind.Cast?"Casting":cue.Kind==GameplayMotionKind.Arrive?"Entered battlefield":cue.Kind==GameplayMotionKind.Tap?"Tapped":cue.Kind==GameplayMotionKind.Untap?"Untapped":cue.Kind==GameplayMotionKind.StackChange?"Stack updated":null;
            if(text!=null){
                run.Text=new Label(text){name="motion-caption",enableRichText=false,pickingMode=PickingMode.Ignore};run.Text.style.position=Position.Absolute;
                bool banner=cue.Kind==GameplayMotionKind.Turn || cue.Kind==GameplayMotionKind.Result || cue.Kind==GameplayMotionKind.Summary;
                run.Text.style.fontSize=cue.Kind==GameplayMotionKind.Result?52:banner?34:24;run.Text.style.unityFontStyleAndWeight=FontStyle.Bold;
                run.Text.style.unityTextAlign=TextAnchor.MiddleCenter;run.Text.style.color=color;run.Text.style.whiteSpace=WhiteSpace.Normal;
                run.Text.style.backgroundColor=new Color(.055f,.035f,.025f,.88f);run.Text.style.borderTopWidth=run.Text.style.borderBottomWidth=1;
                run.Text.style.borderTopColor=run.Text.style.borderBottomColor=color;run.Text.style.paddingTop=run.Text.style.paddingBottom=6;
                run.Text.style.width=banner?Mathf.Min(500,Mathf.Max(180,root.resolvedStyle.width-80)):190;
                CardTypography.Apply(run.Text,banner?CardTextRole.Title:CardTextRole.PowerToughness);run.Root.Add(run.Text);
            }
            active.Add(run);Render(run,0);
        }
        private void Render(Run run,float t)
        {
            var cue=run.Work.Cue;float eased=Mathf.SmoothStep(0,1,t);
            bool banner=cue.Kind==GameplayMotionKind.Turn || cue.Kind==GameplayMotionKind.Result || cue.Kind==GameplayMotionKind.Summary;
            var point=run.Reduced?run.To:Vector2.Lerp(run.From,run.To,eased);
            if(!run.Reduced && run.From!=run.To && cue.Kind!=GameplayMotionKind.Attack && cue.Kind!=GameplayMotionKind.Block)point.y-=Mathf.Sin(t*Mathf.PI)*65;
            point.x=Mathf.Clamp(point.x,24,Mathf.Max(24,root.resolvedStyle.width-24));point.y=Mathf.Clamp(point.y,24,Mathf.Max(24,root.resolvedStyle.height-24));
            float envelope=run.Reduced?1-t:Mathf.Min(1,t*6)*Mathf.Min(1,(1-t)*5);
            run.Effect.Center=point;run.Effect.Target=Anchor(cue.RelatedId)??point;run.Effect.Progress=t;run.Effect.MarkDirtyRepaint();
            if(run.Card!=null){
                float scale=1+Mathf.Sin(t*Mathf.PI)*.16f;
                run.Card.style.width=run.Size.x*scale;run.Card.style.height=run.Size.y*scale;
                run.Card.style.left=point.x-run.Size.x*scale/2;run.Card.style.top=point.y-run.Size.y*scale/2;run.Card.style.opacity=envelope*.95f;
                float rotation=cue.Kind==GameplayMotionKind.Tap?eased*90:cue.Kind==GameplayMotionKind.Untap?(1-eased)*90:(1-eased)*-12;
                run.Card.style.rotate=new Rotate(new Angle(rotation));
            }
            if(run.Text!=null){
                run.Text.style.left=point.x-run.Text.style.width.value.value/2;run.Text.style.top=point.y+(banner?-35:-65)-(run.Reduced?0:t*24);
                run.Text.style.opacity=envelope;run.Text.style.scale=new Scale(Vector3.one*(run.Reduced?1:1+Mathf.Sin(t*Mathf.PI)*.05f));
            }
        }
        private void ClearEffects(){foreach(var run in active)run.Root.RemoveFromHierarchy();active.Clear();pending.Clear();holdStarted=null;}
        public void Clear(){ClearEffects();bindings.Clear();points.Clear();session=viewer=null;revision=-1;lastBatchRevision=-1;lastReduced=false;showingResult=false;lastResult=null;}
        public void Dispose(){if(disposed)return;Clear();disposed=true;ticker.Pause();surface.Clearing-=Clear;root.UnregisterCallback<DetachFromPanelEvent>(Detached);layer.RemoveFromHierarchy();}
    }
}

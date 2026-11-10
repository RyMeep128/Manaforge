using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    public sealed class ProjectedTargetReference
    {
        public string ObjectId {get;} public string PlayerId {get;} public long? Ordinal {get;} public long? Amount {get;}
        public string Key=>ObjectId!=null?"object:"+ObjectId:"player:"+PlayerId;
        internal ProjectedTargetReference(JToken row){ObjectId=(string)row["object_id"];PlayerId=(string)row["player_id"];Ordinal=(long?)row["ordinal"];Amount=(long?)row["amount"];}
        internal ProjectedTargetReference(ProjectedChoiceOption option){ObjectId=option.ObjectId;PlayerId=option.PlayerId;}
    }
    public sealed class ProjectedTargetingContext
    {
        public string SourceId {get;} public long? Minimum {get;} public long? Maximum {get;} public bool Complete {get;}
        public IReadOnlyList<ProjectedTargetReference> Selected {get;}
        internal ProjectedTargetingContext(JToken row){SourceId=(string)row["source_id"];Minimum=(long?)row["minimum"];Maximum=(long?)row["maximum"];Complete=(bool)row["complete"];Selected=Array.AsReadOnly(row["selected"].Select(value=>new ProjectedTargetReference(value)).ToArray());}
    }
    public sealed class ProjectedStackTargets
    {
        public string SourceId {get;} public bool Complete {get;} public IReadOnlyList<ProjectedTargetReference> Targets {get;}
        internal ProjectedStackTargets(JToken row){SourceId=(string)row["source_id"];Complete=(bool)row["complete"];Targets=Array.AsReadOnly(row["targets"].Select(value=>new ProjectedTargetReference(value)).ToArray());}
    }
    // Presentation data only. Native context explicitly identifies targeting; generic card choices never enter it.
    public sealed class TargetingState
    {
        public bool Active {get;} public string SourceId {get;} public string Prompt {get;}
        public IReadOnlyList<ProjectedTargetReference> Legal {get;} public IReadOnlyList<ProjectedTargetReference> Selected {get;}
        public TargetingState(ProjectedDecisionFrame frame)
        {
            var context=frame?.Decision?.Targeting;Active=context!=null && frame.Status=="active" && frame.Result==null;
            SourceId=Active?context.SourceId:null;
            Legal=Array.AsReadOnly(Active?frame.Decision.Options.Where(o=>o.ObjectId!=null || o.PlayerId!=null).Select(o=>new ProjectedTargetReference(o)).ToArray():Array.Empty<ProjectedTargetReference>());
            Selected=Active?context.Selected:Array.Empty<ProjectedTargetReference>();
            Prompt=Active?OpeningHandFan.PlainPrompt(frame.Decision.Prompt):"";
            if(Active && context.Maximum.HasValue && context.Minimum.HasValue && context.Maximum<=256)
                Prompt+=(context.Complete?" | Selected ":" | Known selected ")+Selected.Count+" ("+context.Minimum+"-"+context.Maximum+")";
            if(Active && !context.Complete)Prompt+=" | Some selected targets unavailable";
        }
    }
    // Passive reusable geometry/status component. Theme custom properties supply line appearance.
    public sealed class TargetingOverlay : VisualElement
    {
        public readonly Label Status=new Label{name="targeting-status",enableRichText=false};
        private readonly BattlefieldLinks arrows=new BattlefieldLinks();
        private readonly Dictionary<string,Label> markers=new Dictionary<string,Label>();
        public Color LegalColor {get;private set;}=new Color(.52f,.80f,.91f);
        public Color HoverColor {get;private set;}=new Color(.94f,.76f,.43f);
        private static readonly CustomStyleProperty<Color> lineColor=new CustomStyleProperty<Color>("--target-line-color");
        private static readonly CustomStyleProperty<Color> hoverColor=new CustomStyleProperty<Color>("--target-hover-color");
        private static readonly CustomStyleProperty<float> lineWidth=new CustomStyleProperty<float>("--target-line-width");
        public TargetingOverlay(VisualElement statusParent)
        {
            name="targeting-overlay";AddToClassList("mf-target-overlay");pickingMode=PickingMode.Ignore;arrows.AddToClassList("mf-target-lines");Add(arrows);
            Status.AddToClassList("mf-target-status");statusParent.Insert(0,Status);Status.style.display=DisplayStyle.None;
            RegisterCallback<CustomStyleResolvedEvent>(ev=>{if(customStyle.TryGetValue(lineColor,out var color))LegalColor=color;if(customStyle.TryGetValue(hoverColor,out color))HoverColor=color;if(customStyle.TryGetValue(lineWidth,out var width))arrows.LineWidth=width;});
        }
        public void Present(IEnumerable<BattlefieldLinks.Link> links,IDictionary<string,(Vector2 position,string text)> labels,string status)
        {
            arrows.Set(links);Status.text=status??"";Status.style.display=string.IsNullOrEmpty(status)?DisplayStyle.None:DisplayStyle.Flex;
            foreach(var key in markers.Keys.Where(key=>!labels.ContainsKey(key)).ToArray()){markers[key].RemoveFromHierarchy();markers.Remove(key);}
            foreach(var pair in labels){if(!markers.TryGetValue(pair.Key,out var label)){label=new Label{enableRichText=false,pickingMode=PickingMode.Ignore};label.AddToClassList("mf-target-marker");markers.Add(pair.Key,label);Add(label);}label.text=pair.Value.text;label.style.left=pair.Value.position.x;label.style.top=pair.Value.position.y;}
        }
        public void ClearPresentation(){Present(Array.Empty<BattlefieldLinks.Link>(),new Dictionary<string,(Vector2,string)>(),null);}
        public void Dispose(){ClearPresentation();Status.RemoveFromHierarchy();RemoveFromHierarchy();}
    }
    // UI controller shared by layouts. Anchors are supplied/bound components, not inferred game rules.
    public sealed class ViewerTargetingController : IDisposable
    {
        private readonly VisualElement root;private readonly ViewerCardSurface surface;private readonly ViewerDecisionPanel decisions;private readonly Func<IEnumerable<PlayerPanel>> players;
        private readonly TargetingOverlay overlay;private readonly IVisualElementScheduledItem ticker;
        private readonly Dictionary<string,VisualElement> anchors=new Dictionary<string,VisualElement>();private readonly HashSet<VisualElement> decorated=new HashSet<VisualElement>();
        private ProjectedDecisionFrame frame;private TargetingState state=new TargetingState(null);private ViewerDecisionOffer observed,dragOffer;
        private string pressedTarget;private bool sourceDrag;
        private Vector2 cursor,start;private bool hasCursor,pressed,dragging,disposed;private int pointer;
        public ViewerTargetingController(VisualElement root,ViewerCardSurface surface,ViewerDecisionPanel decisions,IEnumerable<PlayerPanel> players)
            :this(root,surface,decisions,()=>players) {}
        public ViewerTargetingController(VisualElement root,ViewerCardSurface surface,ViewerDecisionPanel decisions,Func<IEnumerable<PlayerPanel>> players)
        {
            this.root=root;this.surface=surface;this.decisions=decisions;this.players=players;overlay=new TargetingOverlay(decisions.Root);root.Add(overlay);
            root.RegisterCallback<PointerMoveEvent>(Move,TrickleDown.TrickleDown);root.RegisterCallback<PointerDownEvent>(Down,TrickleDown.TrickleDown);root.RegisterCallback<PointerUpEvent>(Up,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerLeaveEvent>(Leave);root.RegisterCallback<PointerCaptureOutEvent>(Lost);root.RegisterCallback<FocusInEvent>(Focus);root.RegisterCallback<KeyDownEvent>(Key,TrickleDown.TrickleDown);
            surface.Clearing+=Clear;ticker=root.schedule.Execute(Tick).Every(16);
        }
        public void Observe(ProjectedDecisionFrame value){if(disposed)return;if(frame!=null && (value.Context.SessionId!=frame.Context.SessionId || value.Context.ViewerId!=frame.Context.ViewerId))Clear();frame=value;Tick();}
        private static bool Displayed(VisualElement element){for(var e=element;e!=null;e=e.parent){if(e.resolvedStyle.display==DisplayStyle.None || e.resolvedStyle.visibility==Visibility.Hidden)return false;if(e!=element && e.ClassListContains("unity-scroll-view__content-viewport") && !e.worldBound.Contains(element.worldBound.center))return false;}return element.panel!=null && element.worldBound.width>0 && element.worldBound.height>0;}
        private static bool Within(VisualElement child,VisualElement parent){for(var e=child;e!=null;e=e.parent)if(e==parent)return true;return false;}
        private string Hit(Vector2 point,IEnumerable<string> candidates){var hit=root.panel?.Pick(point);return candidates.FirstOrDefault(key=>anchors.TryGetValue(key,out var element) && Displayed(element) && Within(hit,element));}
        private Vector2? Center(string key)=>key!=null && anchors.TryGetValue(key,out var element) && Displayed(element) && root.worldBound.Contains(element.worldBound.center)?root.WorldToLocal(element.worldBound.center):(Vector2?)null;
        private string SourceKey=>state.SourceId==null?null:"object:"+state.SourceId;
        private void Move(PointerMoveEvent ev){cursor=ev.position;hasCursor=true;if(pressed && Vector2.Distance(start,cursor)>=10)dragging=true;}
        private void Focus(FocusInEvent ev){if(ev.target is VisualElement element){cursor=element.worldBound.center;hasCursor=true;}}
        private void Down(PointerDownEvent ev)
        {
            if(ev.button!=0 || !state.Active || observed?.CanSubmit!=true)return;
            VisualElement source=SourceKey!=null && anchors.TryGetValue(SourceKey,out var anchored) && Displayed(anchored)?anchored:overlay.Status;
            var element=ev.target as VisualElement;string legal=Hit(ev.position,state.Legal.Select(value=>value.Key));
            sourceDrag=Within(element,source);
            if(!sourceDrag && (legal==null || !anchors.TryGetValue(legal,out var target) || !Within(element,target) || state.Legal.Count(value=>value.Key==legal)!=1))return;
            for(var child=element;child!=null && child!=source && child!=root;child=child.parent)if(child is Button || child is TextField || child is Toggle)return;
            pressedTarget=legal;pressed=true;dragging=false;dragOffer=observed;pointer=ev.pointerId;start=ev.position;root.CapturePointer(pointer);ev.StopImmediatePropagation();
        }
        private void Up(PointerUpEvent ev)
        {
            if(!pressed || ev.pointerId!=pointer)return;var captured=dragOffer;bool submit=dragging && sourceDrag;bool moved=dragging;string clicked=pressedTarget;cursor=ev.position;CancelDrag();ev.StopImmediatePropagation();
            if(!ReferenceEquals(captured,observed) || captured?.CanSubmit!=true)return;
            string key=Hit(cursor,state.Legal.Select(target=>target.Key));var target=state.Legal.FirstOrDefault(value=>value.Key==key);if(target==null || !submit && (moved || key!=clicked))return;
            if(target.ObjectId!=null)decisions.TryActivateObject(captured,target.ObjectId);else decisions.TryActivatePlayer(captured,target.PlayerId);
        }
        private void Leave(PointerLeaveEvent ev){if(ev.target==root && !pressed)hasCursor=false;}
        private void Lost(PointerCaptureOutEvent ev){if(ev.target==root)CancelDrag();}
        private void Key(KeyDownEvent ev)
        {
            if(ev.keyCode==KeyCode.Escape){if(pressed){CancelDrag();ev.StopImmediatePropagation();}else if(state.Active && decisions.TryCancelCurrentChoice())ev.StopImmediatePropagation();return;}
            if(!state.Active || observed?.CanSubmit!=true || ev.keyCode!=KeyCode.Return && ev.keyCode!=KeyCode.KeypadEnter)return;
            var element=ev.target as VisualElement;for(var child=element;child!=null && child!=root;child=child.parent)if(child is Button || child is TextField || child is Toggle)return;
            var target=state.Legal.FirstOrDefault(value=>anchors.TryGetValue(value.Key,out var anchor) && Within(element,anchor));
            if(target!=null && (target.ObjectId!=null?decisions.TryActivateObject(observed,target.ObjectId):decisions.TryActivatePlayer(observed,target.PlayerId))){ev.StopImmediatePropagation();}
        }
        private void CancelDrag(){pressed=dragging=false;dragOffer=null;pressedTarget=null;sourceDrag=false;if(root.HasPointerCapture(pointer))root.ReleasePointer(pointer);}
        public void Tick()
        {
            if(disposed)return;var current=decisions.PriorityFrame;
            if(!ReferenceEquals(observed,decisions.CurrentOffer)){CancelDrag();observed=decisions.CurrentOffer;}
            state=new TargetingState(current!=null && frame!=null && current.Context.Revision==frame.Context.Revision && current.Context.SessionId==frame.Context.SessionId && current.Context.ViewerId==frame.Context.ViewerId?current:null);
            anchors.Clear();surface.VisitPresented((card,view)=>anchors["object:"+card.ObjectId]=view);foreach(var player in players())if(player.PlayerId!=null)anchors["player:"+player.PlayerId]=player;
            var desired=new Dictionary<VisualElement,HashSet<string>>();
            void Decorate(string key,string style){if(key!=null && anchors.TryGetValue(key,out var element)){if(element.Q<VisualElement>("targeting-outline")==null){var outline=new VisualElement{name="targeting-outline",pickingMode=PickingMode.Ignore};outline.AddToClassList("mf-target-outline");element.Add(outline);}if(!desired.TryGetValue(element,out var styles)){styles=new HashSet<string>();desired.Add(element,styles);}styles.Add(style);}}
            var links=new List<BattlefieldLinks.Link>();var labels=new Dictionary<string,(Vector2,string)>();string status=null;
            if(state.Active){
                status=state.Prompt;if(observed?.CanSubmit!=true)status+=" | Waiting for confirmation";
                foreach(var target in state.Legal)Decorate(target.Key,"mf-target-legal");Decorate(SourceKey,"mf-target-source");
                var origin=Center(SourceKey)??root.WorldToLocal(overlay.Status.worldBound.center);
                foreach(var target in state.Selected){Decorate(target.Key,"mf-target-selected");var end=Center(target.Key);if(end.HasValue){links.Add(new BattlefieldLinks.Link(origin,end.Value,overlay.LegalColor));string text=target.Ordinal?.ToString()??"Selected";if(target.Amount.HasValue)text+=" ("+target.Amount+")";if(labels.TryGetValue(target.Key,out var old))text=old.Item2+", "+text;labels[target.Key]=(end.Value,text);}}
                if(hasCursor){string hover=Hit(cursor,state.Legal.Select(target=>target.Key));Decorate(hover,"mf-target-hover");var end=Center(hover)??root.WorldToLocal(cursor);links.Add(new BattlefieldLinks.Link(origin,end,hover==null?overlay.LegalColor:overlay.HoverColor));if(hover!=null && !labels.ContainsKey(hover))labels[hover]=(end,"Target");}
            }else if(frame!=null && hasCursor){
                string source=Hit(cursor,(frame.StackTargets??Array.Empty<ProjectedStackTargets>()).Select(value=>"object:"+value.SourceId));var relation=frame.StackTargets?.FirstOrDefault(value=>"object:"+value.SourceId==source);var origin=Center(source);
                if(relation!=null && origin.HasValue){status=relation.Complete && relation.Targets.All(value=>Center(value.Key).HasValue)?"Confirmed targets":"Confirmed targets | Some targets unavailable";Decorate(source,"mf-target-source");foreach(var target in relation.Targets){var end=Center(target.Key);if(!end.HasValue)continue;Decorate(target.Key,"mf-target-selected");links.Add(new BattlefieldLinks.Link(origin.Value,end.Value,overlay.LegalColor));string label=target.Ordinal?.ToString()??"Target";if(labels.TryGetValue(target.Key,out var previous))label=previous.Item2+", "+label;labels[target.Key]=(end.Value,label);}}
            }
            foreach(var element in decorated.Concat(desired.Keys).Distinct().ToArray())foreach(string style in new[]{"mf-target-legal","mf-target-hover","mf-target-source","mf-target-selected"})element.EnableInClassList(style,desired.TryGetValue(element,out var styles) && styles.Contains(style));
            decorated.Clear();foreach(var element in desired.Keys)decorated.Add(element);
            overlay.Present(links,labels,decisions.SuppressSpatialInput?null:status);overlay.BringToFront();
        }
        public void Clear(){CancelDrag();frame=null;observed=null;state=new TargetingState(null);hasCursor=false;cursor=start=Vector2.zero;foreach(var element in decorated){element.RemoveFromClassList("mf-target-legal");element.RemoveFromClassList("mf-target-hover");element.RemoveFromClassList("mf-target-source");element.RemoveFromClassList("mf-target-selected");}decorated.Clear();anchors.Clear();overlay.ClearPresentation();}
        public void Dispose(){if(disposed)return;Clear();disposed=true;ticker.Pause();surface.Clearing-=Clear;root.UnregisterCallback<PointerMoveEvent>(Move,TrickleDown.TrickleDown);root.UnregisterCallback<PointerDownEvent>(Down,TrickleDown.TrickleDown);root.UnregisterCallback<PointerUpEvent>(Up,TrickleDown.TrickleDown);root.UnregisterCallback<PointerLeaveEvent>(Leave);root.UnregisterCallback<PointerCaptureOutEvent>(Lost);root.UnregisterCallback<FocusInEvent>(Focus);root.UnregisterCallback<KeyDownEvent>(Key,TrickleDown.TrickleDown);overlay.Dispose();}
    }
}

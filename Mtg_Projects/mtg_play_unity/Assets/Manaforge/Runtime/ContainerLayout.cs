using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace Manaforge.Play
{
    public enum ContainerMode { Panel, Drawer }
    public enum ContainerDockEdge { None, Left, Right, Top, Bottom }

    public sealed class ContainerLayoutState
    {
        public string Id { get; }
        public Rect FloatingRect { get; }
        public ContainerMode Mode { get; }
        public string DockTarget { get; }
        public ContainerDockEdge Edge { get; }
        public int Order { get; }
        // A null target with an edge means viewport docking, not an absent parent.
        public ContainerLayoutState(string id,Rect floatingRect,ContainerMode mode=ContainerMode.Panel,
            string dockTarget=null,ContainerDockEdge edge=ContainerDockEdge.None,int order=0)
        { Id=id;FloatingRect=floatingRect;Mode=mode;DockTarget=dockTarget;Edge=edge;Order=order; }
    }

    public sealed class ContainerConstraints
    {
        public Vector2 Minimum { get; }
        public Vector2 Maximum { get; }
        public GameplayHudCapabilities Capabilities { get; }
        public bool AcceptsDockedContainers { get; }
        private readonly HashSet<string> targets;
        public ContainerConstraints(Vector2 minimum,Vector2 maximum,GameplayHudCapabilities capabilities,
            bool acceptsDockedContainers=false,IEnumerable<string> permittedTargets=null)
        {
            if(!ContainerLayoutResolver.Finite(minimum.x) || !ContainerLayoutResolver.Finite(minimum.y) ||
                !ContainerLayoutResolver.Finite(maximum.x) || !ContainerLayoutResolver.Finite(maximum.y) ||
                minimum.x<80 || minimum.y<60 || maximum.x<minimum.x || maximum.y<minimum.y)
                throw new ArgumentException("CONTAINER_CONSTRAINTS");
            Minimum=minimum;Maximum=maximum;Capabilities=capabilities;AcceptsDockedContainers=acceptsDockedContainers;
            targets=permittedTargets==null?null:new HashSet<string>(permittedTargets,StringComparer.Ordinal);
        }
        public bool Supports(GameplayHudCapabilities capability)=>(Capabilities&capability)==capability;
        public bool PermitsTarget(string target)=>targets==null || targets.Contains(target??"$viewport");
    }

    public sealed class ContainerLayoutResult
    {
        private readonly IReadOnlyDictionary<string,Rect> bounds;
        public Vector2 Extent { get; }
        internal ContainerLayoutResult(Dictionary<string,Rect> bounds,Vector2 extent)
        { this.bounds=new System.Collections.ObjectModel.ReadOnlyDictionary<string,Rect>(bounds);Extent=extent; }
        public Rect this[string id]=>bounds[id];
    }

    public sealed class ContainerLayoutResolver
    {
        public static bool Finite(float value)=>!float.IsNaN(value) && !float.IsInfinity(value);
        public static Rect Normalize(Rect rect,Vector2 viewport)=>new Rect(rect.x/viewport.x,rect.y/viewport.y,rect.width/viewport.x,rect.height/viewport.y);
        public ContainerLayoutResult Resolve(IReadOnlyDictionary<string,ContainerLayoutState> states,
            IReadOnlyDictionary<string,ContainerConstraints> constraints,Vector2 viewport)
        {
            var bounds=new Dictionary<string,Rect>(StringComparer.Ordinal);var visiting=new HashSet<string>();
            Vector2 canvas=viewport;
            foreach(var c in constraints.Values)canvas=Vector2.Max(canvas,c.Minimum);
            Rect Size(ContainerLayoutState state){
                var c=constraints[state.Id];var n=state.FloatingRect;
                return new Rect(n.x*viewport.x,n.y*viewport.y,Mathf.Clamp(n.width*viewport.x,c.Minimum.x,c.Maximum.x),
                    state.Mode==ContainerMode.Drawer?32:Mathf.Clamp(n.height*viewport.y,c.Minimum.y,c.Maximum.y));
            }
            Rect Place(string id){
                if(bounds.TryGetValue(id,out var existing))return existing;
                if(!visiting.Add(id))throw new ArgumentException("CONTAINER_CYCLE");
                var state=states[id];var rect=Size(state);
                if(state.Edge==ContainerDockEdge.None){
                    rect.x=Mathf.Clamp(rect.x,0,Mathf.Max(0,canvas.x-rect.width));
                    rect.y=Mathf.Clamp(rect.y,0,Mathf.Max(0,canvas.y-rect.height));
                }else{
                    Rect target=state.DockTarget==null?new Rect(Vector2.zero,canvas):Place(state.DockTarget);
                    bool vertical=state.Edge==ContainerDockEdge.Left || state.Edge==ContainerDockEdge.Right;
                    float offset=0;
                    foreach(var sibling in states.Values.Where(s=>s.Edge==state.Edge && s.DockTarget==state.DockTarget)
                        .OrderBy(s=>s.Order).ThenBy(s=>s.Id,StringComparer.Ordinal)){
                        if(sibling.Id==id)break;
                        var size=Size(sibling);offset+=(vertical?size.height:size.width)+8;
                    }
                    bool inside=state.DockTarget==null;
                    switch(state.Edge){
                        case ContainerDockEdge.Left:rect.position=new Vector2(inside?target.x:target.x-rect.width-8,target.y+offset);break;
                        case ContainerDockEdge.Right:rect.position=new Vector2(inside?target.xMax-rect.width:target.xMax+8,target.y+offset);break;
                        case ContainerDockEdge.Top:rect.position=new Vector2(target.x+offset,inside?target.y:target.y-rect.height-8);break;
                        case ContainerDockEdge.Bottom:rect.position=new Vector2(target.x+offset,inside?target.yMax-rect.height:target.yMax+8);break;
                    }
                    // Content scrolls rather than shrinking below minimum. Headers stay nonnegative.
                    rect.x=Mathf.Max(0,rect.x);rect.y=Mathf.Max(0,rect.y);
                }
                visiting.Remove(id);bounds.Add(id,rect);return rect;
            }
            foreach(string id in states.Keys)Place(id);
            foreach(var rect in bounds.Values)canvas=Vector2.Max(canvas,new Vector2(rect.xMax,rect.yMax));
            return new ContainerLayoutResult(bounds,canvas);
        }
    }

    // Committed state only. Gesture previews resolve a copy and never enter this store.
    public sealed class ContainerLayoutController
    {
        private readonly Dictionary<string,ContainerLayoutState> states=new Dictionary<string,ContainerLayoutState>(StringComparer.Ordinal);
        private readonly Dictionary<string,ContainerConstraints> constraints=new Dictionary<string,ContainerConstraints>(StringComparer.Ordinal);
        private readonly ContainerLayoutResolver resolver=new ContainerLayoutResolver();
        public Vector2 Viewport { get; private set; }
        public ContainerLayoutResult Resolved { get; private set; }
        public event Action Changed;
        public IEnumerable<string> Ids=>states.Keys;
        public ContainerLayoutState State(string id)=>states[id];
        public ContainerConstraints Constraints(string id)=>constraints[id];
        public ContainerLayoutController(Vector2 viewport){SetViewport(viewport);}
        public void SetViewport(Vector2 viewport)
        {
            if(!ContainerLayoutResolver.Finite(viewport.x) || !ContainerLayoutResolver.Finite(viewport.y) || viewport.x<1 || viewport.y<1)
                throw new ArgumentException("CONTAINER_VIEWPORT");
            Viewport=viewport;Refresh();
        }
        private bool Valid(ContainerLayoutState state,IReadOnlyDictionary<string,ContainerLayoutState> prospective=null)
        {
            if(state==null || string.IsNullOrWhiteSpace(state.Id) || !states.ContainsKey(state.Id) || !Enum.IsDefined(typeof(ContainerMode),state.Mode) ||
                !Enum.IsDefined(typeof(ContainerDockEdge),state.Edge))return false;
            var r=state.FloatingRect;
            if(!ContainerLayoutResolver.Finite(r.x) || !ContainerLayoutResolver.Finite(r.y) || !ContainerLayoutResolver.Finite(r.width) ||
                !ContainerLayoutResolver.Finite(r.height) || r.width<=0 || r.height<=0 || !ContainerLayoutResolver.Finite(r.x*Viewport.x) ||
                !ContainerLayoutResolver.Finite(r.y*Viewport.y) || !ContainerLayoutResolver.Finite(r.width*Viewport.x) ||
                !ContainerLayoutResolver.Finite(r.height*Viewport.y))return false;
            var c=constraints[state.Id];var old=states[state.Id];
            if(state.Mode!=old.Mode && !c.Supports(GameplayHudCapabilities.ConvertDrawer))return false;
            if((r.width!=old.FloatingRect.width || r.height!=old.FloatingRect.height) && !c.Supports(GameplayHudCapabilities.Resize))return false;
            if((r.x!=old.FloatingRect.x || r.y!=old.FloatingRect.y) && !c.Supports(GameplayHudCapabilities.Move))return false;
            if((state.Edge!=old.Edge || state.DockTarget!=old.DockTarget || state.Order!=old.Order) && !c.Supports(GameplayHudCapabilities.Dock))return false;
            if(state.Edge==ContainerDockEdge.None)return state.DockTarget==null;
            if(!c.Supports(GameplayHudCapabilities.Dock) || !c.PermitsTarget(state.DockTarget))return false;
            if(state.DockTarget!=null && (!states.ContainsKey(state.DockTarget) || !constraints[state.DockTarget].AcceptsDockedContainers))return false;
            var graph=prospective??states;
            var seen=new HashSet<string>{state.Id};string parent=state.DockTarget;
            while(parent!=null){if(!seen.Add(parent) || !graph.ContainsKey(parent))return false;parent=graph[parent].DockTarget;}
            return true;
        }
        public void Register(ContainerLayoutState state,ContainerConstraints limits)
        {
            if(state==null || string.IsNullOrWhiteSpace(state.Id) || limits==null || states.ContainsKey(state.Id))throw new ArgumentException("CONTAINER_REGISTRATION");
            states.Add(state.Id,state);constraints.Add(state.Id,limits);
            if(!Valid(state) || state.Mode==ContainerMode.Drawer && !limits.Supports(GameplayHudCapabilities.ConvertDrawer)){
                states.Remove(state.Id);constraints.Remove(state.Id);throw new ArgumentException("CONTAINER_STATE");
            }
            Refresh();
        }
        public ContainerLayoutResult Preview(ContainerLayoutState candidate)
        {
            if(!Valid(candidate))return null;
            var copy=new Dictionary<string,ContainerLayoutState>(states){[candidate.Id]=candidate};
            return resolver.Resolve(copy,constraints,Viewport);
        }
        public bool TrySet(ContainerLayoutState candidate)
        {
            var result=Preview(candidate);if(result==null)return false;
            states[candidate.Id]=candidate;Resolved=result;Changed?.Invoke();return true;
        }
        // Validate against the entire prospective graph, never an intermediate dock order.
        public ContainerLayoutResult PreviewLayout(IEnumerable<ContainerLayoutState> layout)
        {
            if(layout==null)return null;
            var proposed=new Dictionary<string,ContainerLayoutState>(StringComparer.Ordinal);
            foreach(var state in layout){if(state==null || state.Id==null || proposed.ContainsKey(state.Id))return null;proposed.Add(state.Id,state);}
            if(proposed.Count!=states.Count || proposed.Keys.Any(id=>!states.ContainsKey(id)))return null;
            if(proposed.Values.Any(state=>!Valid(state,proposed)))return null;
            return resolver.Resolve(proposed,constraints,Viewport);
        }
        public bool TryApplyLayout(IEnumerable<ContainerLayoutState> layout)
        {
            if(layout==null)return false;var proposed=layout.ToArray();var resolved=PreviewLayout(proposed);if(resolved==null)return false;
            foreach(var state in proposed)states[state.Id]=state;
            Resolved=resolved;Changed?.Invoke();return true;
        }
        public bool Undock(string id)
        {
            var s=states[id];return TrySet(new ContainerLayoutState(id,s.FloatingRect,s.Mode));
        }
        public bool Reorder(string id,int direction)
        {
            var state=states[id];if(state.Edge==ContainerDockEdge.None || !constraints[id].Supports(GameplayHudCapabilities.Dock))return false;
            var siblings=states.Values.Where(s=>s.Edge==state.Edge && s.DockTarget==state.DockTarget).OrderBy(s=>s.Order).ThenBy(s=>s.Id,StringComparer.Ordinal).ToList();
            int index=siblings.FindIndex(s=>s.Id==id),next=index+Math.Sign(direction);
            if(next<0 || next>=siblings.Count || next==index)return false;
            var moving=siblings[index];siblings.RemoveAt(index);siblings.Insert(next,moving);
            var copy=new Dictionary<string,ContainerLayoutState>(states);
            for(int i=0;i<siblings.Count;i++){
                var old=siblings[i];var updated=new ContainerLayoutState(old.Id,old.FloatingRect,old.Mode,old.DockTarget,old.Edge,i);
                if(!Valid(updated))return false;copy[old.Id]=updated;
            }
            var resolved=resolver.Resolve(copy,constraints,Viewport);
            foreach(var entry in copy)states[entry.Key]=entry.Value;
            Resolved=resolved;Changed?.Invoke();return true;
        }
        public void Remove(string id)
        {
            if(!states.ContainsKey(id))return;
            foreach(var child in states.Values.Where(s=>s.DockTarget==id).ToArray()){
                var floating=ContainerLayoutResolver.Normalize(Resolved[child.Id],Viewport);
                if(child.Mode==ContainerMode.Drawer)floating.height=child.FloatingRect.height;
                states[child.Id]=new ContainerLayoutState(child.Id,floating,child.Mode);
            }
            states.Remove(id);constraints.Remove(id);Refresh();
        }
        private void Refresh(){Resolved=resolver.Resolve(states,constraints,Viewport);Changed?.Invoke();}
    }
}

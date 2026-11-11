using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Borrows content. Dispose unhooks the shell, but never disposes borrowed content.
    public sealed class GameplayContainerShell : VisualElement,IGameplayContainerBinding,IDisposable
    {
        public VisualElement Element=>this;
        VisualElement IGameplayContainerBinding.MoveHandle=>MoveHandle;
        public string ComponentId { get; }
        public Label MoveHandle { get; }
        public Label Title { get; }
        public GameplayDrawer Drawer { get; }
        public VisualElement BorrowedContent { get; }
        public event Action Disposing;
        public IReadOnlyList<(VisualElement handle,Vector2 axes)> ResizeHandles=>resizeHandles;
        private readonly List<(VisualElement handle,Vector2 axes)> resizeHandles=new List<(VisualElement,Vector2)>();
        private readonly ScrollView panelBody=new ScrollView(ScrollViewMode.Vertical);
        private ContainerMode mode=ContainerMode.Panel;
        private bool drawerOpen=true,disposed;
        public GameplayContainerShell(string id,string title,VisualElement content,ContainerConstraints limits)
        {
            ComponentId=id;BorrowedContent=content??throw new ArgumentNullException(nameof(content));
            name="container-"+id;AddToClassList("mf-layout-shell");GameplayTheme.Attach(this);
            panelBody.AddToClassList("mf-layout-panel-body");panelBody.Add(content);Add(panelBody);
            Drawer=new GameplayDrawer(title,GameplayDrawerDirection.Down,true);Drawer.AddToClassList("mf-layout-drawer");
            Drawer.style.display=DisplayStyle.None;Add(Drawer);
            var header=new VisualElement{pickingMode=PickingMode.Ignore};header.AddToClassList("mf-layout-header");Add(header);
            MoveHandle=new Label("↕"){name="container-move-"+id,focusable=true,tooltip="Drag handle; keyboard controls are in the workspace toolbar"};
            MoveHandle.AddToClassList("mf-layout-move");MoveHandle.SetEnabled(limits.Supports(GameplayHudCapabilities.Move));header.Add(MoveHandle);
            Title=new Label(title){pickingMode=PickingMode.Ignore};Title.AddToClassList("mf-layout-title");header.Add(Title);
            foreach(var spec in new[]{("right",new Vector2(1,0)),("bottom",new Vector2(0,1)),("corner",Vector2.one)}){
                var grip=new VisualElement{name="container-resize-"+id+"-"+spec.Item1,focusable=true,tooltip="Resize "+spec.Item1};
                grip.AddToClassList("mf-layout-resize");grip.AddToClassList("mf-layout-resize-"+spec.Item1);
                grip.SetEnabled(limits.Supports(GameplayHudCapabilities.Resize));Add(grip);resizeHandles.Add((grip,spec.Item2));
            }
        }
        public void SetMode(ContainerMode next)
        {
            if(disposed || mode==next)return;
            var focused=panel?.focusController?.focusedElement as VisualElement;
            bool restore=focused!=null && BorrowedContent.Contains(focused);
            bool leavingDrawer=mode==ContainerMode.Drawer;
            if(leavingDrawer)drawerOpen=Drawer.IsOpen;
            mode=next;
            if(leavingDrawer)Drawer.SetOpen(true);
            // Reuse the same element. Do not duplicate data bindings or game views.
            BorrowedContent.RemoveFromHierarchy();
            if(mode==ContainerMode.Drawer){Drawer.Content.Add(BorrowedContent);Drawer.SetOpen(drawerOpen);}
            else panelBody.Add(BorrowedContent);
            panelBody.style.display=mode==ContainerMode.Panel?DisplayStyle.Flex:DisplayStyle.None;
            Drawer.style.display=mode==ContainerMode.Drawer?DisplayStyle.Flex:DisplayStyle.None;
            Title.style.display=mode==ContainerMode.Panel?DisplayStyle.Flex:DisplayStyle.None;
            Drawer.RefreshInput();
            foreach(var grip in resizeHandles)grip.handle.style.display=mode==ContainerMode.Panel?DisplayStyle.Flex:DisplayStyle.None;
            if(restore){if(mode==ContainerMode.Panel || Drawer.IsOpen)focused.Focus();else Drawer.Tab.Focus();}
        }
        public void Apply(Rect bounds,ContainerLayoutState state,ContainerConstraints limits,Vector2 viewport)
        {
            SetMode(state.Mode);style.left=bounds.x;style.top=bounds.y;style.width=bounds.width;style.height=bounds.height;
            float expandedHeight=Mathf.Clamp(state.FloatingRect.height*viewport.y,limits.Minimum.y,limits.Maximum.y);
            Drawer.Content.style.maxHeight=expandedHeight-32;Drawer.Viewport.style.maxHeight=expandedHeight;
        }
        public bool DrawerExpandedPreference=>mode==ContainerMode.Drawer?Drawer.IsOpen:drawerOpen;
        public void RestoreDrawerExpanded(bool value){drawerOpen=value;if(mode==ContainerMode.Drawer)Drawer.SetOpen(value);}
        public void SetReducedMotion(bool value)=>Drawer.SetReducedMotion(value);
        public void Dispose()
        {
            if(disposed)return;Disposing?.Invoke();Disposing=null;disposed=true;
            // Restore suppressed content input before returning it to its owner.
            Drawer.SetOpen(true);BorrowedContent.RemoveFromHierarchy();Drawer.Dispose();RemoveFromHierarchy();
        }
    }

    // Workspace gesture transaction. It has no reference to rules, offers or session dispatch.
    public sealed class ContainerGestureController : IDisposable
    {
        private readonly ContainerLayoutController controller;
        private readonly VisualElement canvas;
        private readonly Action<ContainerLayoutResult> render;
        private readonly List<Attachment> attachments=new List<Attachment>();
        private sealed class Attachment : IDisposable
        {
            private Action cleanup;
            internal Attachment(Action cleanup){this.cleanup=cleanup;}
            public void Dispose(){var action=cleanup;cleanup=null;action?.Invoke();}
        }
        private readonly EventCallback<KeyDownEvent> key;
        private readonly Action changed;
        private string active;
        private Vector2 start,axes;
        private Rect initial;
        private ContainerLayoutState original,candidate;
        private bool resize,deliberate,committing,disposed;
        private VisualElement captured;
        private int pointer;
        public bool IsActive=>active!=null;
        public string ActiveId=>active;
        public ContainerLayoutState PreviewState=>candidate;
        public string DockPreviewTarget { get; private set; }
        public ContainerDockEdge DockPreviewEdge { get; private set; }
        public ContainerGestureController(ContainerLayoutController controller,VisualElement canvas,Action<ContainerLayoutResult> render)
        {
            this.controller=controller;this.canvas=canvas;this.render=render;
            key=ev=>{if(ev.keyCode==KeyCode.Escape && IsActive){Cancel();ev.StopImmediatePropagation();}};
            canvas.RegisterCallback(key,TrickleDown.TrickleDown);
            changed=()=>{if(!committing && IsActive)Cancel();};controller.Changed+=changed;
        }
        public IDisposable Attach(IGameplayContainerBinding shell,Func<float?> drawerHeight=null)
        {
            if(disposed)throw new ObjectDisposedException(nameof(ContainerGestureController));
            var unbind=new List<Action>();
            Bind(shell.MoveHandle,shell.ComponentId,false,Vector2.zero,unbind);
            foreach(var grip in shell.ResizeHandles)Bind(grip.handle,shell.ComponentId,true,grip.axes,unbind,()=>shell.ResizeHandles.First(g=>g.handle==grip.handle).axes,drawerHeight);
            EventCallback<DetachFromPanelEvent> detached=ev=>{if(ev.target==shell.Element && active==shell.ComponentId)Cancel();};
            shell.Element.RegisterCallback(detached);unbind.Add(()=>shell.Element.UnregisterCallback(detached));
            Attachment attachment=null;
            Action disposing=()=>attachment?.Dispose();shell.Disposing+=disposing;unbind.Add(()=>shell.Disposing-=disposing);
            attachment=new Attachment(()=>{if(active==shell.ComponentId)Cancel();foreach(var action in unbind)action();attachments.Remove(attachment);});
            attachments.Add(attachment);return attachment;
        }
        private void Bind(VisualElement handle,string id,bool sizing,Vector2 direction,List<Action> unbind,Func<Vector2> currentDirection=null,Func<float?> drawerHeight=null)
        {
            EventCallback<PointerDownEvent> down=ev=>{
                if(ev.button!=0 || !handle.enabledInHierarchy)return;
                if(!Begin(id,canvas.WorldToLocal(ev.position),sizing,currentDirection?.Invoke()??direction,drawerHeight?.Invoke()))return;
                captured=handle;pointer=ev.pointerId;handle.CapturePointer(pointer);handle.Focus();ev.StopPropagation();
            };
            EventCallback<PointerMoveEvent> move=ev=>{if(captured!=handle || ev.pointerId!=pointer)return;Move(canvas.WorldToLocal(ev.position));ev.StopPropagation();};
            EventCallback<PointerUpEvent> up=ev=>{if(captured!=handle || ev.pointerId!=pointer)return;Move(canvas.WorldToLocal(ev.position));Commit();ev.StopPropagation();};
            EventCallback<PointerCaptureOutEvent> lost=ev=>{if(captured==handle)Cancel();};
            handle.RegisterCallback(down);handle.RegisterCallback(move);handle.RegisterCallback(up);handle.RegisterCallback(lost);
            unbind.Add(()=>{handle.UnregisterCallback(down);handle.UnregisterCallback(move);handle.UnregisterCallback(up);handle.UnregisterCallback(lost);});
        }
        public bool Begin(string id,Vector2 position,bool sizing=false,Vector2 direction=default,float? presentedHeight=null)
        {
            if(disposed)return false;Cancel();
            var limits=controller.Constraints(id);
            if(!limits.Supports(sizing?GameplayHudCapabilities.Resize:GameplayHudCapabilities.Move))return false;
            if(sizing && controller.State(id).Mode==ContainerMode.Drawer && !limits.ResizeDrawer)return false;
            active=id;start=position;resize=sizing;axes=direction;original=controller.State(id);initial=controller.Resolved[id];if(sizing && original.Mode==ContainerMode.Drawer)initial.height=Mathf.Clamp(presentedHeight??original.FloatingRect.height*controller.Viewport.y,limits.Minimum.y,limits.Maximum.y);candidate=null;
            return true;
        }
        public void Move(Vector2 position)
        {
            if(active==null)return;Vector2 delta=position-start;
            if(!deliberate && delta.magnitude<10)return;deliberate=true;
            var limits=controller.Constraints(active);var rect=initial;
            if(resize){rect.width=Mathf.Clamp(rect.width+delta.x*axes.x,limits.Minimum.x,limits.Maximum.x);rect.height=Mathf.Clamp(rect.height+delta.y*axes.y,limits.Minimum.y,limits.Maximum.y);}
            else{rect.position+=delta;rect.x=Mathf.Max(0,rect.x);rect.y=Mathf.Max(0,rect.y);}
            var normalized=ContainerLayoutResolver.Normalize(rect,controller.Viewport);
            if(!resize)normalized.size=original.FloatingRect.size;
            else if(original.Edge!=ContainerDockEdge.None)normalized.position=original.FloatingRect.position;
            DockPreviewTarget=null;DockPreviewEdge=ContainerDockEdge.None;
            if(!resize && limits.Supports(GameplayHudCapabilities.Dock))FindDock(position,limits);
            candidate=new ContainerLayoutState(active,normalized,original.Mode,resize?original.DockTarget:DockPreviewTarget,
                resize?original.Edge:DockPreviewEdge,original.Order);
            var preview=controller.Preview(candidate);if(preview!=null)render(preview);
        }
        private void FindDock(Vector2 point,ContainerConstraints limits)
        {
            // Concrete targets win over viewport edges. Never infer a target from content events.
            foreach(string id in controller.Ids){
                if(id==active || !controller.Constraints(id).AcceptsDockedContainers || !limits.PermitsTarget(id))continue;
                var rect=controller.Resolved[id];var expanded=rect;expanded.xMin-=24;expanded.xMax+=24;expanded.yMin-=24;expanded.yMax+=24;
                if(!expanded.Contains(point) || Mathf.Min(Mathf.Abs(point.x-rect.x),Mathf.Abs(point.x-rect.xMax),
                    Mathf.Abs(point.y-rect.y),Mathf.Abs(point.y-rect.yMax))>24)continue;
                var edge=NearestEdge(point,rect);
                var test=new ContainerLayoutState(active,original.FloatingRect,original.Mode,id,edge,original.Order);
                if(controller.Preview(test)==null)continue;DockPreviewTarget=id;DockPreviewEdge=edge;return;
            }
            var viewport=new Rect(Vector2.zero,controller.Viewport);
            if(limits.PermitsTarget(null) && viewport.Contains(point) &&
                Mathf.Min(point.x,point.y,viewport.width-point.x,viewport.height-point.y)<=24)
                DockPreviewEdge=NearestEdge(point,viewport);
        }
        private static ContainerDockEdge NearestEdge(Vector2 point,Rect rect)
        {
            float best=Mathf.Abs(point.x-rect.x);var edge=ContainerDockEdge.Left;
            foreach(var pair in new[]{(Mathf.Abs(point.x-rect.xMax),ContainerDockEdge.Right),(Mathf.Abs(point.y-rect.y),ContainerDockEdge.Top),(Mathf.Abs(point.y-rect.yMax),ContainerDockEdge.Bottom)})
                if(pair.Item1<best){best=pair.Item1;edge=pair.Item2;}
            return edge;
        }
        public bool Commit()
        {
            var next=candidate;bool apply=deliberate && next!=null;Release();committing=true;
            try{return apply && controller.TrySet(next);}finally{committing=false;render(controller.Resolved);}
        }
        public void Cancel(){Release();render(controller.Resolved);}
        private void Release()
        {
            var old=captured;captured=null;active=null;candidate=null;deliberate=false;DockPreviewTarget=null;DockPreviewEdge=ContainerDockEdge.None;
            if(old!=null && old.HasPointerCapture(pointer))old.ReleasePointer(pointer);
        }
        public void Dispose()
        {
            if(disposed)return;Cancel();disposed=true;controller.Changed-=changed;canvas.UnregisterCallback(key,TrickleDown.TrickleDown);
            foreach(var attachment in attachments.ToArray())attachment.Dispose();
        }
    }
}

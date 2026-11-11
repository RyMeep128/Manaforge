using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Synthetic, opt-in host for container primitives. Never binds a live game surface.
    public sealed class GameplayLayoutWorkspace : VisualElement,IDisposable
    {
        public ContainerLayoutController Controller { get; }
        public ContainerGestureController Gestures { get; }
        public GameplayHudRegistry Registry { get; }=new GameplayHudRegistry();
        public LayoutPresetPanel Presets { get; }
        public LayoutPresetApplicator PresetBinding { get; }
        public VisualElement Canvas { get; }=new VisualElement();
        public ScrollView Scroll { get; }=new ScrollView(ScrollViewMode.VerticalAndHorizontal);
        private readonly Dictionary<string,GameplayContainerShell> shells=new Dictionary<string,GameplayContainerShell>();
        private readonly Dictionary<string,IDisposable> attachments=new Dictionary<string,IDisposable>();
        private readonly Dictionary<string,GameplayHudRegistry.Registration> registrations=new Dictionary<string,GameplayHudRegistry.Registration>();
        private readonly List<Action> cleanup=new List<Action>();
        private readonly List<(Button button,GameplayHudCapabilities required)> operationButtons=new List<(Button,GameplayHudCapabilities)>();
        private readonly Dictionary<string,Action<bool>> drawerChanged=new Dictionary<string,Action<bool>>();
        private readonly EventCallback<GeometryChangedEvent> geometry;
        private readonly PopupField<string> selected;
        private readonly Label status=new Label();
        private bool disposed;
        public GameplayContainerShell Shell(string id)=>shells[id];
        public GameplayLayoutWorkspace(ILayoutPresetStore presetStore=null)
        {
            name="layout-workspace";AddToClassList("mf-layout-workspace");GameplayTheme.Attach(this);
            Controller=new ContainerLayoutController(new Vector2(1000,600));
            var toolbar=new VisualElement();toolbar.AddToClassList("mf-layout-toolbar");Add(toolbar);
            selected=new PopupField<string>("Component",new List<string>{"panel","drawer","restricted","host"},0){name="layout-component-selector"};toolbar.Add(selected);
            void Button(string text,Action action){
                var b=new UnityEngine.UIElements.Button(action){text=text};toolbar.Add(b);cleanup.Add(()=>b.clickable=null);
                var cap=text.StartsWith("Move ")?GameplayHudCapabilities.Move:
                    new[]{"Narrower","Wider","Shorter","Taller"}.Contains(text)?GameplayHudCapabilities.Resize:
                    text.StartsWith("Dock ") || new[]{"Previous","Next","Undock"}.Contains(text)?GameplayHudCapabilities.Dock:
                    text=="Panel / drawer"?GameplayHudCapabilities.ConvertDrawer:GameplayHudCapabilities.None;
                operationButtons.Add((b,cap));
            }
            var motion=new Toggle("Reduced motion");toolbar.Add(motion);
            EventCallback<ChangeEvent<bool>> reduced=ev=>{foreach(var shell in shells.Values)shell.SetReducedMotion(ev.newValue);};
            motion.RegisterValueChangedCallback(reduced);cleanup.Add(()=>motion.UnregisterValueChangedCallback(reduced));
            Button("Move ←",()=>Nudge(-8,0,false));Button("Move →",()=>Nudge(8,0,false));
            Button("Move ↑",()=>Nudge(0,-8,false));Button("Move ↓",()=>Nudge(0,8,false));
            Button("Narrower",()=>Nudge(-8,0,true));Button("Wider",()=>Nudge(8,0,true));
            Button("Shorter",()=>Nudge(0,-8,true));Button("Taller",()=>Nudge(0,8,true));
            var target=new PopupField<string>("Dock target",new List<string>{"Viewport","host","panel","drawer"},0);toolbar.Add(target);
            foreach(var edge in new[]{ContainerDockEdge.Left,ContainerDockEdge.Right,ContainerDockEdge.Top,ContainerDockEdge.Bottom}){
                var value=edge;Button("Dock "+edge,()=>Dock(selected.value,target.value=="Viewport"?null:target.value,value));
            }
            Button("Previous",()=>Report(Controller.Reorder(selected.value,-1)));Button("Next",()=>Report(Controller.Reorder(selected.value,1)));
            Button("Undock",()=>Report(Controller.Undock(selected.value)));
            Button("Panel / drawer",()=>{var old=Controller.State(selected.value);Report(Controller.TrySet(new ContainerLayoutState(old.Id,old.FloatingRect,
                old.Mode==ContainerMode.Panel?ContainerMode.Drawer:ContainerMode.Panel,old.DockTarget,old.Edge,old.Order)));});
            status.text="Synthetic layout workspace — no game engine or private cards";Add(status);
            Scroll.AddToClassList("mf-layout-scroll");Add(Scroll);Canvas.AddToClassList("mf-layout-canvas");Scroll.Add(Canvas);
            Gestures=new ContainerGestureController(Controller,Canvas,Render);
            Controller.Changed+=Changed;
            EventCallback<ChangeEvent<string>> selectionChanged=ev=>UpdateControls();
            selected.RegisterValueChangedCallback(selectionChanged);cleanup.Add(()=>selected.UnregisterValueChangedCallback(selectionChanged));
            geometry=ev=>{var size=Scroll.contentViewport.layout.size;if(size.x<1 || size.y<1 || size==Controller.Viewport)return;Gestures.Cancel();Controller.SetViewport(size);};
            Scroll.contentViewport.RegisterCallback(geometry);
            var all=GameplayHudCapabilities.Move|GameplayHudCapabilities.Resize|GameplayHudCapabilities.Dock|GameplayHudCapabilities.ConvertDrawer;
            AddSample("panel","Movable panel",new Rect(.04f,.08f,.25f,.38f),all,true);
            AddSample("drawer","Convertible panel",new Rect(.34f,.08f,.25f,.38f),all,false);
            AddSample("restricted","Fixed panel",new Rect(.04f,.58f,.22f,.28f),GameplayHudCapabilities.None,false);
            AddSample("host","Docking target",new Rect(.66f,.38f,.25f,.38f),all,true);
            Render(Controller.Resolved);UpdateControls();
            PresetBinding=new LayoutPresetApplicator(Controller,Registry,Gestures.Cancel);
            Presets=new LayoutPresetPanel(presetStore??new MemoryLayoutPresetStore(),PresetBinding,
                locked=>{if(locked)Gestures.Cancel();toolbar.SetEnabled(!locked);Canvas.SetEnabled(!locked);});
            Insert(0,Presets);
        }
        private void AddSample(string id,string title,Rect rect,GameplayHudCapabilities caps,bool host)
        {
            var content=new VisualElement();content.Add(new Label(title+" / synthetic content"));
            var field=new TextField("Notes"){value="Content survives conversion"};content.Add(field);
            var button=new Button(()=>status.text="Synthetic button clicked: "+id){text="Fixture action"};content.Add(button);cleanup.Add(()=>button.clickable=null);
            content.Add(new Label(id=="restricted"?"Movement, resize, docking and conversion unavailable":"Use the handle, grips, or workspace controls"));
            var limits=new ContainerConstraints(new Vector2(180,120),new Vector2(900,700),caps,host);
            Controller.Register(new ContainerLayoutState(id,rect),limits);
            var shell=new GameplayContainerShell(id,title,content,limits);shells.Add(id,shell);Canvas.Add(shell);
            attachments.Add(id,Gestures.Attach(shell));
            Action<bool> openChanged=value=>{Render(Controller.Resolved);Presets?.RefreshDirty();};shell.Drawer.OpenChanged+=openChanged;drawerChanged.Add(id,openChanged);
            registrations.Add(id,Registry.Register(new GameplayHudDescriptor("fixture/"+id,title,"layout-workspace",caps,presetKey:"fixture."+id),shell));
        }
        private void Changed(){Render(Controller.Resolved);UpdateControls();Presets?.RefreshDirty();}
        private void UpdateControls()
        {
            if(!shells.ContainsKey(selected.value))return;
            var limits=Controller.Constraints(selected.value);
            foreach(var operation in operationButtons)operation.button.SetEnabled(limits.Supports(operation.required) &&
                !(operation.required==GameplayHudCapabilities.Resize && Controller.State(selected.value).Mode==ContainerMode.Drawer));
        }
        private void Report(bool applied){status.text=applied?"Layout updated":"Operation unavailable or incompatible";}
        public bool Dock(string id,string target,ContainerDockEdge edge)
        {
            var old=Controller.State(id);bool applied=Controller.TrySet(new ContainerLayoutState(id,old.FloatingRect,old.Mode,target,edge));Report(applied);return applied;
        }
        public bool Nudge(float x,float y,bool resize)
        {
            var old=Controller.State(selected.value);var n=old.FloatingRect;
            var bounds=Controller.Resolved[old.Id];
            if(resize){
                if(old.Mode==ContainerMode.Drawer){Report(false);return false;}
                n.width=(bounds.width+x)/Controller.Viewport.x;n.height=(bounds.height+y)/Controller.Viewport.y;
            }else{
                n.position=new Vector2((bounds.x+x)/Controller.Viewport.x,(bounds.y+y)/Controller.Viewport.y);
            }
            bool applied=Controller.TrySet(new ContainerLayoutState(old.Id,n,old.Mode,resize?old.DockTarget:null,
                resize?old.Edge:ContainerDockEdge.None,resize?old.Order:0));Report(applied);return applied;
        }
        public void Render(ContainerLayoutResult result)
        {
            if(disposed)return;Vector2 extent=result.Extent;
            foreach(var pair in shells){
                var state=Controller.State(pair.Key);var limits=Controller.Constraints(pair.Key);var shell=pair.Value;
                shell.Apply(result[pair.Key],state,limits,Controller.Viewport);
                bool target=Gestures!=null && Gestures.IsActive && Gestures.DockPreviewTarget==pair.Key && Gestures.DockPreviewEdge!=ContainerDockEdge.None;
                shell.EnableInClassList("mf-layout-drop-target",target);
                if(state.Mode==ContainerMode.Drawer && shell.Drawer.IsOpen)
                    extent.y=Mathf.Max(extent.y,result[pair.Key].y+Mathf.Clamp(state.FloatingRect.height*Controller.Viewport.y,limits.Minimum.y,limits.Maximum.y));
            }
            Canvas.EnableInClassList("mf-layout-drop-target",Gestures!=null && Gestures.IsActive && Gestures.DockPreviewTarget==null && Gestures.DockPreviewEdge!=ContainerDockEdge.None);
            Canvas.style.width=extent.x;Canvas.style.height=extent.y;
        }
        public void Reset(){Presets?.RestoreDefault();}
        public void Remove(string id)
        {
            Gestures.Cancel();attachments[id].Dispose();attachments.Remove(id);registrations[id].Dispose();registrations.Remove(id);
            shells[id].Drawer.OpenChanged-=drawerChanged[id];drawerChanged.Remove(id);
            shells[id].Dispose();shells.Remove(id);Controller.Remove(id);
            selected.choices=shells.Keys.ToList();if(selected.choices.Count>0)selected.value=selected.choices[0];
        }
        public void Dispose()
        {
            if(disposed)return;Presets?.Dispose();Gestures.Dispose();disposed=true;Controller.Changed-=Changed;
            Scroll.contentViewport.UnregisterCallback(geometry);
            foreach(var attachment in attachments.Values)attachment.Dispose();attachments.Clear();
            foreach(var pair in shells){pair.Value.Drawer.OpenChanged-=drawerChanged[pair.Key];pair.Value.Dispose();}
            drawerChanged.Clear();shells.Clear();Registry.Dispose();
            foreach(var action in cleanup)action();cleanup.Clear();RemoveFromHierarchy();
        }
    }
}

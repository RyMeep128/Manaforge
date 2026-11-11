using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Presentation transaction. No game state, commands, card ownership or network writes.
    public sealed class HudLayoutEditor : IDisposable
    {
        public const GameplayHudCapabilities DrawerCapabilities=GameplayHudCapabilities.Drawer|GameplayHudCapabilities.Move|GameplayHudCapabilities.Resize|GameplayHudCapabilities.Dock;
        private readonly VisualElement root,canvas,layer,toolbar,controls,dockHint;
        private readonly VisualElement[] previewRoots;private readonly Action closePreviews;
        private readonly GameplayHudRegistry registry;
        private readonly Dictionary<string,LiveDrawerLayoutAdapter> adapters=new Dictionary<string,LiveDrawerLayoutAdapter>();
        private readonly List<Action> cleanup=new List<Action>();
        private readonly HashSet<string> pendingAvailability=new HashSet<string>();
        private readonly HashSet<string> committedOverrides=new HashSet<string>(),draftOverrides=new HashSet<string>();
        private readonly Action interrupt,relayout,focusGameplay;
        private readonly Action<bool> gate;
        private readonly Func<bool> blocked;
        private readonly Label status,storageStatus,viewportWarning;
        private readonly PopupField<string> component,presets;
        private readonly TextField presetName;
        private readonly Button apply,save,saveAs,rename,delete;
        private readonly HudLayoutPresetSession storage;
        private readonly ContainerGestureController gestures;
        private readonly LayoutPresetApplicator binding;
        private readonly Dictionary<string,ContainerLayoutState> lastStates=new Dictionary<string,ContainerLayoutState>();
        private LayoutPresetApplication committed,retained;
        private HudLayoutPreset working,committedWorking;
        private string selectedId,committedSelected;
        private string context;
        private int generation;
        private VisualElement returnFocus;
        private bool suppress,disposed,temporary,hasFrame,heldEscape,confirmDelete,updatingViewport;
        public GameplayViewportContext Viewport {get;private set;}=new GameplayViewportContext(new Rect(0,0,1280,720));
        public bool ViewportSupported=>Viewport.SupportsCustomization;
        public bool CanReset=>!disposed;
        public bool GestureActive=>gestures.IsActive;
        public ContainerLayoutController Controller { get; }
        public bool IsEditing { get; private set; }
        public bool HasRetainedDraft=>retained!=null;
        public bool NeedsApply=>IsEditing && (!SameStates(committed,Snapshot()) || !committedOverrides.SetEquals(draftOverrides) || selectedId!=committedSelected);
        public Task Initialization { get; }
        public string Status=>status.text;
        public HudLayoutEditor(VisualElement root,VisualElement canvas,GameplayHudRegistry registry,
            IEnumerable<(string id,string title,GameplayDrawer drawer)> drawers,ILayoutPresetStore store,
            Action interrupt,Action relayout,Action<bool> gate,Func<bool> blocked,Action focusGameplay=null,IEnumerable<VisualElement> previewRoots=null,Action closePreviews=null)
        {
            this.previewRoots=(previewRoots??Array.Empty<VisualElement>()).Where(e=>e!=null).ToArray();this.closePreviews=closePreviews;
            this.focusGameplay=focusGameplay;this.root=root;this.canvas=canvas;this.registry=registry;this.interrupt=interrupt;this.relayout=relayout;this.gate=gate;this.blocked=blocked;
            layer=new VisualElement{name="hud-layout-editor",pickingMode=PickingMode.Ignore};layer.style.position=Position.Absolute;layer.style.left=layer.style.top=layer.style.right=layer.style.bottom=0;canvas.Add(layer);GameplayTheme.Attach(layer);
            viewportWarning=new Label("Layout customization needs 1024 x 768 UI units, or 1280 x 720 widescreen. Default placement is temporarily active. Enlarge the window, or use Esc > Reset Layout for This Game."){name="layout-viewport-warning",enableRichText=false,focusable=true,pickingMode=PickingMode.Ignore};
            viewportWarning.style.position=Position.Absolute;viewportWarning.style.left=12;viewportWarning.style.bottom=12;viewportWarning.style.right=12;viewportWarning.style.maxWidth=620;viewportWarning.style.whiteSpace=WhiteSpace.Normal;viewportWarning.style.backgroundColor=new Color(.08f,.06f,.02f,.96f);viewportWarning.style.color=new Color(1,.85f,.6f);viewportWarning.style.display=DisplayStyle.None;layer.Add(viewportWarning);
            dockHint=new VisualElement{name="layout-dock-preview",pickingMode=PickingMode.Ignore};dockHint.style.position=Position.Absolute;dockHint.style.backgroundColor=new Color(.2f,.8f,.85f,.55f);dockHint.style.display=DisplayStyle.None;layer.Add(dockHint);
            Controller=new ContainerLayoutController(Viewport.Size);
            foreach(var entry in drawers){
                var adapter=new LiveDrawerLayoutAdapter(entry.id,entry.title,entry.drawer,canvas,layer);adapters.Add(entry.id,adapter);
                var registration=registry.Find(entry.id);registration.SetContainerBinding(adapter,DrawerCapabilities);
                Controller.Register(DefaultState(entry.id,Controller.Viewport),new ContainerConstraints(new Vector2(entry.id==GameplayHudIds.Priority?285:entry.id==GameplayHudIds.Actions?275:252,100),new Vector2(720,900),DrawerCapabilities,permittedTargets:new[]{"$viewport"},resizeDrawer:true,headerHeight:30,wrapViewportRails:true));
            }
            gestures=new ContainerGestureController(Controller,canvas,Render);
            foreach(var adapter in adapters.Values){cleanup.Add(gestures.Attach(adapter,()=>adapter.PresentedBodyHeight).Dispose);
                EventCallback<KeyDownEvent> key=ev=>HandleArrow(ev,adapter.ComponentId);adapter.MoveHandle.RegisterCallback(key);cleanup.Add(()=>adapter.MoveHandle.UnregisterCallback(key));
                foreach(var grip in adapter.ResizeHandles){grip.handle.RegisterCallback(key);cleanup.Add(()=>grip.handle.UnregisterCallback(key));}
            }
            binding=new LayoutPresetApplicator(Controller,registry,gestures.Cancel);storage=new HudLayoutPresetSession(store);
            toolbar=new ScrollView(ScrollViewMode.Vertical){name="layout-editor-controls",focusable=true};toolbar.style.position=Position.Absolute;toolbar.style.left=Length.Percent(28);toolbar.style.top=8;toolbar.style.width=Length.Percent(44);toolbar.style.maxHeight=Length.Percent(46);toolbar.style.backgroundColor=new Color(.035f,.045f,.06f,.98f);toolbar.style.paddingLeft=toolbar.style.paddingRight=12;toolbar.style.paddingTop=toolbar.style.paddingBottom=10;layer.Add(toolbar);
            toolbar.Add(new Label("Customize Layout | drag headers and resize corners"));
            toolbar.Add(new Label("Drop near a screen edge to dock. Open a drawer preview to see its contents."));
            controls=new VisualElement();toolbar.Add(controls);
            component=new PopupField<string>("Drawer",adapters.Keys.ToList(),0){name="layout-editor-component"};
            var row=new VisualElement();row.style.flexDirection=FlexDirection.Row;row.style.flexWrap=Wrap.Wrap;controls.Add(row);
            Button Button(string title,Action action,VisualElement parent=null){var button=new Button(action){text=title,name="layout-editor-"+title.ToLowerInvariant().Replace(" ","-")};GameplayTheme.Button(button);(parent??row).Add(button);cleanup.Add(()=>button.clickable=null);return button;}
            apply=Button("Apply",()=>Apply());Button("Cancel",Cancel);Button("Restore Default",RestoreDefault);
            var library=new Foldout{text="Presets and keyboard controls",value=false,name="layout-editor-presets"};controls.Add(library);library.Add(component);
            presets=new PopupField<string>("Preset",new List<string>{"Default"},0){name="live-preset-selector"};library.Add(presets);
            presetName=new TextField("Name"){name="live-preset-name"};library.Add(presetName);
            var presetRow=new VisualElement();presetRow.style.flexDirection=FlexDirection.Row;presetRow.style.flexWrap=Wrap.Wrap;library.Add(presetRow);
            Button("Stage preset",()=>StagePreset(storage.Library.Presets.FirstOrDefault(p=>p.Name==presets.value)?.Id),presetRow);
            save=Button("Save",()=>Run(()=>SaveAsync(false)),presetRow);saveAs=Button("Save As",()=>Run(()=>SaveAsync(true)),presetRow);
            rename=Button("Rename applied",()=>Run(RenameAsync),presetRow);delete=Button("Delete applied",()=>{if(!confirmDelete){confirmDelete=true;status.text="Delete applied preset "+storage.Library.Find(selectedId)?.Name+"? Press Delete applied again to confirm. Current layout is kept.";}else Run(DeleteAsync);},presetRow);
            Button("Refresh list",()=>Run(RefreshPresetsAsync),presetRow);
            status=new Label{enableRichText=false};status.style.whiteSpace=WhiteSpace.Normal;toolbar.Add(status);storageStatus=new Label{enableRichText=false};storageStatus.style.whiteSpace=WhiteSpace.Normal;toolbar.Add(storageStatus);
            library.Add(new Label("Apply keeps placement; Save keeps a preset. Arrows move, Shift+arrows resize, Ctrl+arrows dock, Alt+arrows reorder. Escape cancels."));
            toolbar.style.display=DisplayStyle.None;
            foreach(var adapter in adapters.Values){var current=adapter;Action preview=()=>{if(IsEditing && !suppress){component.SetValueWithoutNotify(current.ComponentId);Render(Controller.Resolved);RefreshControls();}};current.PreviewChanged+=preview;cleanup.Add(()=>current.PreviewChanged-=preview);EventCallback<PointerDownEvent> select=ev=>component.SetValueWithoutNotify(current.ComponentId);current.MoveHandle.RegisterCallback(select,TrickleDown.TrickleDown);cleanup.Add(()=>current.MoveHandle.UnregisterCallback(select,TrickleDown.TrickleDown));}
            committed=Snapshot();RememberStates();Controller.Changed+=Changed;
            root.RegisterCallback<KeyDownEvent>(Key,TrickleDown.TrickleDown);root.RegisterCallback<KeyUpEvent>(KeyUp,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerDownEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<PointerMoveEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<PointerUpEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<ClickEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<WheelEvent>(Block,TrickleDown.TrickleDown);
            root.RegisterCallback<NavigationSubmitEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<NavigationMoveEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<NavigationCancelEvent>(NavigationCancel,TrickleDown.TrickleDown);root.RegisterCallback<FocusInEvent>(Focus,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerEnterEvent>(Block,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerLeaveEvent>(Block,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerOverEvent>(Block,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerOutEvent>(Block,TrickleDown.TrickleDown);
            Initialization=InitializeAsync();
        }
        public static ContainerLayoutState DefaultState(string id,Vector2 viewport)
        {
            Rect rect;
            switch(id){
                case GameplayHudIds.Priority:rect=new Rect(viewport.x-301,16,285,Mathf.Max(100,viewport.y*.7f-32));break;
                case GameplayHudIds.Actions:rect=new Rect(viewport.x-295,viewport.y-65,275,285);break;
                case GameplayHudIds.Zones:rect=new Rect(16,viewport.y-122,252,Mathf.Max(100,viewport.y-182));break;
                default:rect=new Rect(16,54+Mathf.Max(170,viewport.y-70)-162,252,400);break;
            }
            return new ContainerLayoutState(id,ContainerLayoutResolver.Normalize(rect,viewport),ContainerMode.Drawer);
        }
        private bool SameStates(LayoutPresetApplication a,LayoutPresetApplication b)
        {
            if(a==null || b==null)return false;
            return a.States.Where(s=>committedOverrides.Contains(s.Id) || draftOverrides.Contains(s.Id)).All(s=>b.States.Any(t=>t.Id==s.Id && t.FloatingRect==s.FloatingRect && t.Edge==s.Edge && t.Order==s.Order && t.DockTarget==s.DockTarget)) && a.DrawerExpansion.All(p=>b.DrawerExpansion.TryGetValue(p.Key,out bool open) && open==p.Value);
        }
        private LayoutPresetApplication Snapshot()=>new LayoutPresetApplication(Controller.Ids.Select(Controller.State),adapters.ToDictionary(p=>p.Key,p=>p.Value.DrawerExpandedPreference),new List<string>());
        private void RememberStates(){foreach(string id in Controller.Ids)lastStates[id]=Controller.State(id);}
        private void Changed()
        {
            if(!suppress && IsEditing){foreach(string id in Controller.Ids)if(!ReferenceEquals(lastStates[id],Controller.State(id)))draftOverrides.Add(id);}
            RememberStates();Render(Controller.Resolved);RefreshControls();
        }
        public void BringToFront(){if(IsEditing){layer.BringToFront();toolbar.BringToFront();}}
        public bool CanOpen=>!disposed && ViewportSupported && hasFrame && !temporary && !storage.Busy && !(blocked?.Invoke()??false);
        public bool Open(VisualElement origin=null)
        {
            if(IsEditing || !CanOpen)return false;interrupt?.Invoke();returnFocus=origin??root.panel?.focusController.focusedElement as VisualElement;
            IsEditing=true;gate?.Invoke(true);confirmDelete=false;
            if(retained!=null){suppress=true;binding.Apply(retained);suppress=false;retained=null;}
            else{
                suppress=true;
                foreach(var pair in adapters)if(!committedOverrides.Contains(pair.Key)){
                    var state=DefaultState(pair.Key,Controller.Viewport);var header=pair.Value.HeaderBounds;
                    if(header.width>0 && ContainerLayoutResolver.Finite(header.x)){var n=ContainerLayoutResolver.Normalize(header,Controller.Viewport);state=new ContainerLayoutState(pair.Key,new Rect(n.x,n.y,n.width,state.FloatingRect.height),ContainerMode.Drawer);}
                    Controller.TrySet(state);
                }
                suppress=false;committed=Snapshot();draftOverrides.Clear();draftOverrides.UnionWith(committedOverrides);working=committedWorking;selectedId=committedSelected;
            }
            toolbar.style.display=DisplayStyle.Flex;layer.BringToFront();status.text="Drag a header to move it. Open previews to inspect the live layout. Apply before saving.";Render(Controller.Resolved);RefreshControls();toolbar.Focus();return true;
        }
        public bool Apply()
        {
            if(!IsEditing || storage.Busy)return false;gestures.Cancel();committed=Snapshot();committedOverrides.Clear();committedOverrides.UnionWith(draftOverrides);committedWorking=working;committedSelected=selectedId;pendingAvailability.Clear();foreach(string id in committedOverrides)if(registry.Find(id)?.Available!=true)pendingAvailability.Add(id);retained=null;status.text="Layout applied in memory; Save to keep it between games.";RefreshControls();return true;
        }
        public void Cancel(){if(!IsEditing)return;retained=null;RestoreCommitted();CloseEditor();}
        private void RestoreCommitted(){suppress=true;binding.Apply(committed);suppress=false;working=committedWorking;selectedId=committedSelected;relayout?.Invoke();}
        private void CloseEditor()
        {
            gestures.Cancel();IsEditing=false;closePreviews?.Invoke();gate?.Invoke(false);toolbar.style.display=DisplayStyle.None;foreach(var adapter in adapters.Values)adapter.SetEditing(false);BeforeLegacyLayout();relayout?.Invoke();Render(Controller.Resolved);
            var origin=returnFocus;returnFocus=null;if(origin?.panel!=null && origin.enabledInHierarchy)origin.Focus();
        }
        public void Suspend()
        {
            if(!IsEditing)return;gestures.Cancel();retained=Snapshot();var draftWorking=working;string draftSelected=selectedId;RestoreCommitted();CloseEditor();working=draftWorking;selectedId=draftSelected;
        }
        public void Observe(string session,string viewer,bool required,bool transientLayout,bool ended=false)
        {
            string next=session+"/"+viewer;
            if(context!=null && context!=next)EndSession();
            bool wasTemporary=temporary;context=next;hasFrame=!ended;temporary=required || transientLayout || ended;
            if(ended){Cancel();retained=null;}else if(temporary)Suspend();
            if(wasTemporary!=temporary)relayout?.Invoke();
            RefreshControls();
        }
        public void EndSession()
        {generation++;Cancel();retained=null;hasFrame=false;context=null;committedOverrides.Clear();draftOverrides.Clear();pendingAvailability.Clear();working=committedWorking=null;selectedId=committedSelected=null;gate?.Invoke(false);BeforeLegacyLayout();relayout?.Invoke();}
        public void BeforeDecisionTick(bool attentionRequired)
        {if(attentionRequired)Suspend();}
        public bool OwnsGeometry(string id)=>ViewportSupported && !temporary && ((IsEditing?draftOverrides:committedOverrides).Contains(id) || IsEditing && gestures?.PreviewState?.Id==id);
        public void BeforeLegacyLayout()
        {RefreshViewport();foreach(var pair in adapters)if(!OwnsGeometry(pair.Key))pair.Value.RestoreLegacy();}
        public void AfterLegacyLayout()
        {
            if(disposed)return;
            foreach(string id in pendingAvailability.ToArray())if(!IsEditing && registry.Find(id)?.Available==true){
                var application=binding.Prepare(committedWorking);var state=application?.States.FirstOrDefault(s=>s.Id==id);
                if(state!=null){suppress=true;Controller.TrySet(state);if(application.DrawerExpansion.TryGetValue(id,out bool open))adapters[id].RestoreDrawerExpanded(open);suppress=false;committed=Snapshot();}pendingAvailability.Remove(id);
            }
            RefreshViewport();
            Render(Controller.Resolved);
        }
        private void RefreshViewport()
        {if(!updatingViewport && GameplayViewportContext.TryRead(canvas,out var viewport))UpdateViewport(viewport);}
        public void UpdateViewport(GameplayViewportContext viewport)
        {
            if(viewport.Size.x<1 || viewport.Size.y<1)throw new ArgumentException("GAMEPLAY_VIEWPORT");
            if(disposed || updatingViewport || Viewport.Equals(viewport))return;updatingViewport=true;
            try{
                Viewport=viewport;gestures.Cancel();bool wasEditing=IsEditing;
                if(!ViewportSupported)Suspend();
                suppress=true;try{
                    Controller.SetViewport(viewport.Size);RebaseControllerDefaults();
                    committed=RebaseSnapshot(committed,committedOverrides);retained=RebaseSnapshot(retained,draftOverrides);
                }finally{suppress=false;}
                viewportWarning.style.display=ViewportSupported?DisplayStyle.None:DisplayStyle.Flex;
                if(!ViewportSupported){viewportWarning.BringToFront();if(wasEditing)focusGameplay?.Invoke();}
                RefreshControls();
            }finally{updatingViewport=false;}
        }
        private LayoutPresetApplication RebaseSnapshot(LayoutPresetApplication snapshot,HashSet<string> overrides)
            =>snapshot==null?null:new LayoutPresetApplication(snapshot.States.Select(s=>overrides.Contains(s.Id)?s:DefaultState(s.Id,Controller.Viewport)),snapshot.DrawerExpansion.ToDictionary(p=>p.Key,p=>p.Value),new List<string>());
        private void RebaseControllerDefaults()
        {
            bool previous=suppress;suppress=true;
            try{foreach(string id in Controller.Ids.ToArray())if(!(IsEditing?draftOverrides:committedOverrides).Contains(id))Controller.TrySet(DefaultState(id,Controller.Viewport));}
            finally{suppress=previous;}
        }
        public void ResetForGame()
        {
            if(disposed)return;generation++;gestures.Cancel();
            // Do not restore snapshot expansion: attention and current game choices own it.
            IsEditing=false;retained=null;returnFocus=null;heldEscape=false;gate?.Invoke(false);
            toolbar.style.display=DisplayStyle.None;foreach(var adapter in adapters.Values)adapter.SetEditing(false);
            committedOverrides.Clear();draftOverrides.Clear();pendingAvailability.Clear();working=committedWorking=null;selectedId=committedSelected=null;
            suppress=true;try{Controller.TryApplyLayout(Controller.Ids.Select(id=>DefaultState(id,Controller.Viewport)).ToArray());}finally{suppress=false;}
            committed=Snapshot();BeforeLegacyLayout();relayout?.Invoke();Render(Controller.Resolved);PresetChoices();RefreshControls();
            status.text="Default layout restored for this game. Saved presets are unchanged.";focusGameplay?.Invoke();
        }
        private void Render(ContainerLayoutResult result)
        {
            if(disposed || canvas.panel==null || !ContainerLayoutResolver.Finite(canvas.resolvedStyle.width) || !ContainerLayoutResolver.Finite(canvas.resolvedStyle.height))return;bool restored=false;
            foreach(var pair in adapters){bool available=registry.Find(pair.Key)?.Available==true;pair.Value.SetEditing(IsEditing && available);
                var state=gestures?.PreviewState?.Id==pair.Key?gestures.PreviewState:Controller.State(pair.Key);
                float requested=Mathf.Clamp(state.FloatingRect.height*Controller.Viewport.y,Controller.Constraints(pair.Key).Minimum.y,Controller.Constraints(pair.Key).Maximum.y);
                if(OwnsGeometry(pair.Key) && available)pair.Value.Apply(GameplayDrawerGeometry.Resolve(result[pair.Key],requested,Viewport));
                else{restored|=pair.Value.RestoreLegacy();pair.Value.PositionHandles(GameplayDrawerGeometry.Resolve(pair.Value.HeaderBounds,requested,Viewport));}
            }
            if(restored)relayout?.Invoke();
            dockHint.style.display=IsEditing && gestures?.IsActive==true && gestures.DockPreviewEdge!=ContainerDockEdge.None?DisplayStyle.Flex:DisplayStyle.None;
            if(dockHint.style.display.value==DisplayStyle.Flex){var edge=gestures.DockPreviewEdge;dockHint.style.left=edge==ContainerDockEdge.Right?Controller.Viewport.x-8:0;dockHint.style.top=edge==ContainerDockEdge.Bottom?Controller.Viewport.y-8:0;dockHint.style.width=edge==ContainerDockEdge.Left || edge==ContainerDockEdge.Right?8:Controller.Viewport.x;dockHint.style.height=edge==ContainerDockEdge.Top || edge==ContainerDockEdge.Bottom?8:Controller.Viewport.y;}
            if(IsEditing){layer.BringToFront();toolbar.BringToFront();}
        }
        public void RestoreDefault()
        {
            if(!IsEditing || storage.Busy)return;gestures.Cancel();suppress=true;
            Controller.TryApplyLayout(Controller.Ids.Select(id=>DefaultState(id,Controller.Viewport)).ToArray());suppress=false;
            draftOverrides.Clear();working=null;selectedId=null;status.text="Default staged. Apply to keep it.";relayout?.Invoke();RefreshControls();
        }
        public bool StagePreset(string id)
        {
            if(!IsEditing || storage.Busy)return false;if(id==null){RestoreDefault();return true;}
            var preset=storage.Library.Find(id);if(preset==null)return false;var application=binding.Prepare(preset);if(application==null){status.text="Preset cannot be applied.";return false;}
            suppress=true;bool success=binding.Apply(application);suppress=false;if(!success)return false;
            draftOverrides.Clear();foreach(var entry in registry.Entries)if(entry.Container!=null && preset.Components.ContainsKey(entry.Descriptor.PresetKey))draftOverrides.Add(entry.Container.ComponentId);
            RebaseControllerDefaults();working=preset;selectedId=id;status.text="Preset staged. Apply to keep it."+(application.Adjustments.Count>0?" "+string.Join("; ",application.Adjustments):"");Render(Controller.Resolved);RefreshControls();return true;
        }
        private void EditSelected(Action<string> edit)
        {if(IsEditing && !storage.Busy && registry.Find(component.value)?.Available==true)edit(component.value);}
        public void Dock(string id,ContainerDockEdge edge)
        {if(!IsEditing || registry.Find(id)?.Available!=true)return;var s=Controller.State(id);Controller.TrySet(new ContainerLayoutState(id,s.FloatingRect,s.Mode,edge:edge,order:s.Order));}
        public void Adjust(string id,float x,float y,bool resize)
        {
            if(!IsEditing || registry.Find(id)?.Available!=true || storage.Busy)return;var s=Controller.State(id);var rect=s.FloatingRect;
            if(resize){var limits=Controller.Constraints(id);rect.width=Mathf.Clamp(rect.width*Controller.Viewport.x+x,limits.Minimum.x,limits.Maximum.x)/Controller.Viewport.x;rect.height=Mathf.Clamp(rect.height*Controller.Viewport.y+y,limits.Minimum.y,limits.Maximum.y)/Controller.Viewport.y;}
            else{var current=Controller.Resolved[id];current.position+=new Vector2(x,y);var clamped=LiveDrawerLayoutAdapter.ClampHeader(current,Controller.Viewport);rect.position=ContainerLayoutResolver.Normalize(clamped,Controller.Viewport).position;}
            Controller.TrySet(new ContainerLayoutState(id,rect,s.Mode,resize?s.DockTarget:null,resize?s.Edge:ContainerDockEdge.None,s.Order));
        }
        private void HandleArrow(KeyDownEvent ev,string id)
        {
            if(!IsEditing)return;Vector2 delta;
            switch(ev.keyCode){case KeyCode.LeftArrow:delta=Vector2.left;break;case KeyCode.RightArrow:delta=Vector2.right;break;case KeyCode.UpArrow:delta=Vector2.down;break;case KeyCode.DownArrow:delta=Vector2.up;break;default:return;}
            component.SetValueWithoutNotify(id);if(ev.ctrlKey)Dock(id,ev.keyCode==KeyCode.LeftArrow?ContainerDockEdge.Left:ev.keyCode==KeyCode.RightArrow?ContainerDockEdge.Right:ev.keyCode==KeyCode.UpArrow?ContainerDockEdge.Top:ContainerDockEdge.Bottom);else if(ev.altKey)Controller.Reorder(id,delta.x+delta.y<0?-1:1);else Adjust(id,delta.x*8,delta.y*8,ev.shiftKey);ev.StopImmediatePropagation();
        }
        private bool Inside(object target)
        {
            if(!(target is VisualElement element))return false;
            if(element==layer || layer.Contains(element) || previewRoots.Any(preview=>preview==element || preview.Contains(element)) || adapters.Values.Any(adapter=>ReferenceEquals(adapter.PreviewTab,element)))return true;
            for(var e=element;e!=null && e!=root;e=e.parent)if(e is Scroller && adapters.Values.Any(adapter=>adapter.Element.Contains(e)))return true;
            // UI Toolkit mounts PopupField menus at the panel root, outside their field.
            for(var e=element;e!=null && e!=root;e=e.parent)if(e.ClassListContains("unity-base-dropdown") && root.Contains(e))return true;
            return false;
        }
        private static bool CardTarget(object target){for(var e=target as VisualElement;e!=null;e=e.parent)if(e is CardView)return true;return false;}
        private static bool InspectionEvent(EventBase ev)=>ev is PointerEnterEvent || ev is PointerLeaveEvent || ev is PointerOverEvent || ev is PointerOutEvent || ev is PointerMoveEvent || ev is PointerDownEvent down && down.button==1 || ev is PointerUpEvent up && up.button==1 || ev is ClickEvent click && click.button==1;
        private void Block<T>(T ev) where T:EventBase<T>,new(){if(IsEditing && !Inside(ev.target) && !(CardTarget(ev.target) && InspectionEvent(ev)) && !(ev is WheelEvent && ev.target is VisualElement target && adapters.Values.Any(adapter=>adapter.Element.Contains(target)))){ev.StopImmediatePropagation();}}
        private void Focus(FocusInEvent ev){if(IsEditing && !Inside(ev.target) && !CardTarget(ev.target)){ev.StopImmediatePropagation();toolbar.Focus();}}
        private void NavigationCancel(NavigationCancelEvent ev){if(IsEditing){if(gestures.IsActive)gestures.Cancel();else Cancel();ev.StopImmediatePropagation();}}
        private void Key(KeyDownEvent ev)
        {
            if(!IsEditing || ev.keyCode==KeyCode.F11)return;
            if(ev.keyCode==KeyCode.Escape){if(!heldEscape){heldEscape=true;if(gestures.IsActive)gestures.Cancel();else Cancel();}ev.StopImmediatePropagation();return;}
            if(ev.keyCode==KeyCode.Tab){var focusables=layer.Query<VisualElement>().ToList().Concat(previewRoots.SelectMany(preview=>preview.Query<VisualElement>().ToList())).Distinct().Where(e=>e.focusable && e.enabledInHierarchy && Visible(e)).ToArray();if(focusables.Length>0){int index=Array.IndexOf(focusables,root.panel?.focusController.focusedElement as VisualElement);focusables[(index+(ev.shiftKey?-1:1)+focusables.Length)%focusables.Length].Focus();}ev.StopImmediatePropagation();return;}
            if(!Inside(ev.target) && !(CardTarget(ev.target) && ev.keyCode==KeyCode.Space)){ev.StopImmediatePropagation();}
        }
        private static bool Visible(VisualElement element){for(var e=element;e!=null;e=e.parent)if(e.resolvedStyle.display==DisplayStyle.None || e.resolvedStyle.visibility==Visibility.Hidden)return false;return true;}
        private void KeyUp(KeyUpEvent ev){if(ev.keyCode==KeyCode.Escape && heldEscape){heldEscape=false;ev.StopImmediatePropagation();}else Block(ev);}
        private void RefreshControls()
        {
            if(disposed || apply==null)return;bool busy=storage.Busy;storageStatus.text=HudLayoutPresetSession.Describe(storage.Receipt?.Status??PresetStoreStatus.Busy)+(busy?" | Busy":"");controls.SetEnabled(!busy);apply.SetEnabled(!busy && NeedsApply);
            bool write=storage.CanWrite && !NeedsApply;save.SetEnabled(write && selectedId!=null);saveAs.SetEnabled(write);rename.SetEnabled(write && selectedId!=null);delete.SetEnabled(write && selectedId!=null);
            foreach(var pair in adapters){bool enabled=!busy && registry.Find(pair.Key)?.Available==true;pair.Value.MoveHandle.SetEnabled(enabled);pair.Value.PreviewToggle.SetEnabled(enabled);foreach(var grip in pair.Value.ResizeHandles)grip.handle.SetEnabled(enabled);}
        }
        private void PresetChoices(){presets.choices=new[]{"Default"}.Concat(storage.Library.Presets.Select(p=>p.Name)).ToList();presets.SetValueWithoutNotify(storage.Library.Find(selectedId)?.Name??"Default");}
        private async void Run(Func<Task<bool>> action)
        {try{var task=action();RefreshControls();await task;}catch(Exception){if(!disposed)status.text="Preset operation failed; layout is unchanged.";}finally{if(!disposed){confirmDelete=false;PresetChoices();RefreshControls();}}}
        private async Task InitializeAsync()
        {
            int initialGeneration=generation;await storage.RefreshAsync();if(disposed || generation!=initialGeneration)return;var preset=storage.Receipt?.Success==true?storage.Library.Find(storage.Library.LastSelectedId):null;
            if(preset!=null){suppress=true;var application=binding.Prepare(preset);bool ok=binding.Apply(application);suppress=false;if(ok){foreach(var entry in registry.Entries)if(entry.Container!=null && preset.Components.ContainsKey(entry.Descriptor.PresetKey))committedOverrides.Add(entry.Container.ComponentId);working=committedWorking=preset;selectedId=committedSelected=preset.Id;foreach(string id in committedOverrides)if(registry.Find(id)?.Available!=true)pendingAvailability.Add(id);committed=Snapshot();}}
            status.text="Preset storage: "+storage.Receipt?.Status;PresetChoices();RefreshControls();relayout?.Invoke();
        }
        public async Task<bool> RefreshPresetsAsync()
        {if(NeedsApply)return false;bool ok=await storage.RefreshAsync();if(!disposed){status.text="Preset storage: "+storage.Receipt?.Status;PresetChoices();}return ok;}
        public async Task<bool> SaveAsync(bool asNew,string name=null)
        {
            if(!IsEditing || NeedsApply || !storage.CanWrite)return false;
            try{
                var target=storage.Library.Find(selectedId);if(!asNew && target==null)return false;
                var captured=binding.Capture(asNew?Guid.NewGuid().ToString("N"):target.Id,asNew?(name??presetName.value):target.Name,working??target);
                var components=captured.Components.ToDictionary(p=>p.Key,p=>p.Value);
                foreach(var entry in registry.Entries)if(entry.Container!=null && entry.Available && !committedOverrides.Contains(entry.Container.ComponentId))components.Remove(entry.Descriptor.PresetKey);
                var snapshot=new HudLayoutPreset(captured.Id,captured.Name,components,captured.ToJson());
                int epoch=generation;bool ok=await storage.WriteAsync(storage.Library.Save(snapshot));if(disposed || epoch!=generation)return false;
                if(ok){working=committedWorking=snapshot;selectedId=committedSelected=snapshot.Id;status.text="Preset saved.";}else status.text="Preset was not saved: "+storage.Receipt?.Status;
                PresetChoices();RefreshControls();return ok;
            }catch(ArgumentException){status.text="Use a unique name of 1-64 characters; Default is reserved.";return false;}
        }
        private async Task<bool> RenameAsync()
        {
            if(!IsEditing || NeedsApply || !storage.CanWrite || selectedId==null)return false;
            try{int epoch=generation;bool ok=await storage.WriteAsync(storage.Library.Rename(selectedId,presetName.value));if(disposed || epoch!=generation)return false;status.text=ok?"Preset renamed.":"Rename failed: "+storage.Receipt?.Status;return ok;}
            catch(ArgumentException){status.text="Invalid or duplicate preset name.";return false;}
        }
        private async Task<bool> DeleteAsync()
        {
            if(!IsEditing || NeedsApply || !storage.CanWrite || selectedId==null)return false;
            int epoch=generation;bool ok=await storage.WriteAsync(storage.Library.Delete(selectedId));if(disposed || epoch!=generation)return false;
            if(ok){selectedId=committedSelected=null;status.text="Preset deleted; applied layout kept in memory.";}else status.text="Delete failed: "+storage.Receipt?.Status;return ok;
        }
        public void Dispose()
        {
            if(disposed)return;Cancel();retained=null;disposed=true;gate?.Invoke(false);storage.Dispose();Controller.Changed-=Changed;gestures.Dispose();
            foreach(var action in cleanup)action();foreach(var adapter in adapters.Values){registry.Find(adapter.ComponentId)?.SetContainerBinding(null);adapter.Dispose();}
            root.UnregisterCallback<PointerEnterEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<PointerLeaveEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<PointerOverEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<PointerOutEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<KeyDownEvent>(Key,TrickleDown.TrickleDown);root.UnregisterCallback<KeyUpEvent>(KeyUp,TrickleDown.TrickleDown);
            root.UnregisterCallback<PointerDownEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<PointerMoveEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<PointerUpEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<ClickEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<WheelEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<NavigationSubmitEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<NavigationMoveEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<NavigationCancelEvent>(NavigationCancel,TrickleDown.TrickleDown);root.UnregisterCallback<FocusInEvent>(Focus,TrickleDown.TrickleDown);layer.RemoveFromHierarchy();
        }
    }
}

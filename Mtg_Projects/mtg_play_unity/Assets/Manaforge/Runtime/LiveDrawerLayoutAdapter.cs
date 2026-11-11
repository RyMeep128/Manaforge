using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // A borrowed layout participant: neither registry nor editor owns its view or content.
    public interface IGameplayContainerBinding
    {
        string ComponentId { get; }
        VisualElement Element { get; }
        VisualElement MoveHandle { get; }
        IReadOnlyList<(VisualElement handle,Vector2 axes)> ResizeHandles { get; }
        bool DrawerExpandedPreference { get; }
        void RestoreDrawerExpanded(bool expanded);
        event Action Disposing;
    }

    public sealed class LiveDrawerLayoutAdapter : IGameplayContainerBinding,IDisposable
    {
        public string ComponentId { get; }
        public VisualElement Element=>drawer;
        public VisualElement MoveHandle { get; }
        private readonly List<(VisualElement handle,Vector2 axes)> resizeHandles=new List<(VisualElement,Vector2)>();
        public IReadOnlyList<(VisualElement handle,Vector2 axes)> ResizeHandles=>resizeHandles;
        public bool DrawerExpandedPreference=>drawer.IsOpen;
        public event Action Disposing;
        private readonly GameplayDrawer drawer;
        private readonly VisualElement canvas,handles;
        private readonly VisualElement grip;
        private readonly List<Action> restore=new List<Action>();
        private bool custom,disposed;
        public LiveDrawerLayoutAdapter(string id,string title,GameplayDrawer drawer,VisualElement canvas,VisualElement editorLayer)
        {
            ComponentId=id;this.drawer=drawer;this.canvas=canvas;
            Remember(drawer);Remember(drawer.Viewport);Remember(drawer.Content);
            foreach(var scroll in drawer.Content.Query<ScrollView>().ToList()){var height=scroll.style.maxHeight;restore.Add(()=>scroll.style.maxHeight=height);}
            handles=new VisualElement{name="layout-handles-"+id,pickingMode=PickingMode.Ignore};handles.style.position=Position.Absolute;
            MoveHandle=new Button(){name="layout-move-"+id,text=title+" - move",tooltip="Drag to move; arrows move, Shift+arrows resize",focusable=true};
            MoveHandle.style.height=30;GameplayTheme.Button((Button)MoveHandle);handles.Add(MoveHandle);
            grip=new Label("Resize"){name="layout-resize-"+id,focusable=true,tooltip="Drag to resize expanded drawer"};grip.style.position=Position.Absolute;grip.style.right=0;grip.style.width=48;grip.style.height=28;grip.style.backgroundColor=new Color(.3f,.2f,.08f,1);grip.style.color=Color.white;handles.Add(grip);
            resizeHandles.Add((grip,Vector2.one));editorLayer.Add(handles);SetEditing(false);
        }
        private void Remember(VisualElement element)
        {
            var s=element.style;var left=s.left;var right=s.right;var top=s.top;var bottom=s.bottom;var width=s.width;var height=s.height;var maxWidth=s.maxWidth;var maxHeight=s.maxHeight;var position=s.position;var padding=s.paddingTop;
            restore.Add(()=>{var target=element.style;target.left=left;target.right=right;target.top=top;target.bottom=bottom;target.width=width;target.height=height;target.maxWidth=maxWidth;target.maxHeight=maxHeight;target.position=position;target.paddingTop=padding;});
        }
        public void SetEditing(bool editing)=>handles.style.display=editing?DisplayStyle.Flex:DisplayStyle.None;
        public Rect HeaderBounds=>canvas.WorldToLocal(drawer.Tab.worldBound);
        public void PositionHandles(GameplayDrawerGeometry geometry)
        {
            var header=geometry.Header;handles.style.left=header.x;handles.style.top=header.y;handles.style.width=header.width;handles.style.height=30;
            grip.style.right=StyleKeyword.Auto;grip.style.left=geometry.GripPosition.x;grip.style.top=geometry.GripPosition.y;
            resizeHandles[0]=(grip,new Vector2(1,geometry.BodyBelow?1:-1));
        }
        public static Rect ClampHeader(Rect rect,Vector2 viewport)=>GameplayDrawerGeometry.ClampHeader(rect,new Rect(Vector2.zero,viewport));
        public void Apply(GameplayDrawerGeometry geometry)
        {
            if(disposed || drawer.parent==null)return;custom=true;var header=geometry.Header;
            var point=drawer.parent.WorldToLocal(canvas.LocalToWorld(header.position));
            drawer.style.position=Position.Absolute;drawer.style.left=point.x;drawer.style.top=point.y;drawer.style.right=StyleKeyword.Auto;drawer.style.bottom=StyleKeyword.Auto;
            drawer.style.width=header.width;drawer.style.height=30;drawer.style.maxHeight=30;
            var body=drawer.Viewport;body.style.position=Position.Absolute;body.style.left=0;body.style.right=StyleKeyword.Auto;body.style.width=header.width;body.style.paddingTop=0;
            body.style.top=geometry.BodyBelow?new StyleLength(32):new StyleLength(StyleKeyword.Auto);body.style.bottom=geometry.BodyBelow?new StyleLength(StyleKeyword.Auto):new StyleLength(32);
            body.style.maxHeight=geometry.BodyHeight;drawer.Content.style.maxHeight=geometry.BodyHeight;
            foreach(var scroll in drawer.Content.Query<ScrollView>().ToList())scroll.style.maxHeight=geometry.BodyHeight;
            PositionHandles(geometry);
        }
        public bool RestoreLegacy(){if(!custom)return false;foreach(var action in restore)action();custom=false;return true;}
        public void RestoreDrawerExpanded(bool expanded)=>drawer.SetOpen(expanded);
        public void Dispose(){if(disposed)return;Disposing?.Invoke();Disposing=null;RestoreLegacy();disposed=true;handles.RemoveFromHierarchy();}
    }
}

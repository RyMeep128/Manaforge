using System;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Borrowed content; caller retains rendering and authorization ownership.
    public sealed class GameplayOverlay : IDisposable
    {
        private readonly VisualElement content;
        private readonly Button close;
        private VisualElement returnFocus;
        private bool disposed;
        public GameplayOverlay(VisualElement content,Button close)
        {this.content=content;this.close=close;GameplayTheme.Button(close);content.RegisterCallback<DetachFromPanelEvent>(Detached);}
        private void Detached(DetachFromPanelEvent e){if(e.target==content)Hide(false);}
        public void Show(bool interactive,VisualElement origin=null)
        {
            if(disposed)return;
            if(interactive && origin!=null)returnFocus=origin;
            content.pickingMode=interactive?PickingMode.Position:PickingMode.Ignore;
            content.style.display=DisplayStyle.Flex;close.style.display=interactive?DisplayStyle.Flex:DisplayStyle.None;
            content.BringToFront();if(interactive)close.BringToFront();
        }
        public void Place(Rect viewport,Vector2 size,Vector2? source=null,float inset=24,float top=90)
        {
            float left=source.HasValue && source.Value.x<viewport.center.x?viewport.xMax-size.x-inset:viewport.x+inset;
            content.style.left=Mathf.Clamp(left,viewport.x,Mathf.Max(viewport.x,viewport.xMax-size.x));
            content.style.top=Mathf.Clamp(viewport.y+top,viewport.y,Mathf.Max(viewport.y,viewport.yMax-size.y));
            close.style.left=content.style.left;close.style.top=Mathf.Max(viewport.y,content.style.top.value.value-34);close.style.width=size.x;
        }
        public void Hide(bool restoreFocus)
        {
            content.style.display=DisplayStyle.None;close.style.display=DisplayStyle.None;content.pickingMode=PickingMode.Position;
            var origin=returnFocus;returnFocus=null;
            if(restoreFocus && origin?.panel!=null && origin.style.display.value!=DisplayStyle.None)origin.Focus();
        }
        public void Dispose(){if(disposed)return;Hide(false);disposed=true;content.UnregisterCallback<DetachFromPanelEvent>(Detached);}
    }
}

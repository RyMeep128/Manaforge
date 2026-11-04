using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Gesture state only. Every submission uses the exact offer captured on pointer-down.
    public sealed class ViewerBoardInput : IDisposable
    {
        private readonly VisualElement root;private readonly ViewerCardSurface surface;private readonly ViewerSessionHost host;private readonly ViewerDecisionPanel panel;private readonly Action<VisualElement> decorateMenu;
        private readonly Dictionary<CardView,Binding> bindings=new Dictionary<CardView,Binding>();
        private readonly Label hint,ghost;private readonly Image ghostArtwork;private readonly VisualElement menu;
        private ViewerDecisionOffer offer,gestureOffer;private Binding pressed;private Vector2 start;private int pointer;private bool dragging,disposed;
        private readonly EventCallback<KeyDownEvent> key;
        private sealed class Binding : IDisposable
        {
            internal readonly CardView View;internal readonly string Id;
            private readonly EventCallback<PointerDownEvent> down;private readonly EventCallback<PointerMoveEvent> move;private readonly EventCallback<PointerUpEvent> up;
            private readonly EventCallback<PointerCaptureOutEvent> lost;private readonly EventCallback<DetachFromPanelEvent> detach;private readonly EventCallback<NavigationSubmitEvent> submit;
            internal Binding(ViewerBoardInput owner,CardView view,string id)
            {
                View=view;Id=id;down=ev=>owner.Down(this,ev);move=ev=>owner.Move(this,ev);up=ev=>owner.Up(this,ev);
                lost=ev=>{if(owner.pressed==this)owner.CancelGesture();};detach=ev=>{if(ev.target==View && owner.pressed==this)owner.CancelGesture();};
                submit=ev=>{if(ev.target==View && owner.offer?.Frame?.Decision.Family!="mana"){owner.Activate(owner.offer,this,View.worldBound.center);ev.StopPropagation();}};
                view.RegisterCallback(down);view.RegisterCallback(move);view.RegisterCallback(up);view.RegisterCallback(lost);view.RegisterCallback(detach);view.RegisterCallback(submit);
            }
            public void Dispose(){View.UnregisterCallback(down);View.UnregisterCallback(move);View.UnregisterCallback(up);View.UnregisterCallback(lost);View.UnregisterCallback(detach);View.UnregisterCallback(submit);View.RemoveFromClassList("actionable");View.RemoveFromClassList("targetable");View.RemoveFromClassList("gesture-source");}
        }
        public ViewerBoardInput(VisualElement root,ViewerCardSurface surface,ViewerSessionHost host,ViewerDecisionPanel panel,Action<VisualElement> decorateMenu=null)
        {
            this.root=root;this.surface=surface;this.host=host;this.panel=panel;this.decorateMenu=decorateMenu;
            hint=new Label{name="board-input-hint",enableRichText=false,pickingMode=PickingMode.Ignore};root.Add(hint);
            ghost=new Label{name="board-drag-ghost",enableRichText=false,pickingMode=PickingMode.Ignore};root.Add(ghost);ghost.style.display=DisplayStyle.None;ghostArtwork=new Image{name="board-drag-art",pickingMode=PickingMode.Ignore,scaleMode=ScaleMode.ScaleToFit};ghostArtwork.style.width=100;ghostArtwork.style.height=140;ghost.Add(ghostArtwork);
            menu=new VisualElement{name="board-object-menu"};root.Add(menu);menu.style.display=DisplayStyle.None;
            key=ev=>{if(ev.keyCode==KeyCode.Escape){CancelGesture();CloseMenu();}};root.RegisterCallback(key);
        }
        public void Refresh()
        {
            if(disposed)return;var current=host.PresentedDecision;
            if(!ReferenceEquals(current,offer)){CancelGesture();CloseMenu();offer=current;}
            if(offer?.CanSubmit!=true){CancelGesture();CloseMenu();}
            var captured=offer;var frame=captured?.Frame;var decision=frame?.Decision;
            var seen=new HashSet<CardView>();
            surface.VisitPresented((card,view)=>{
                if(card.Hidden)return;seen.Add(view);if(bindings.TryGetValue(view,out var existing) && existing.Id!=card.ObjectId){existing.Dispose();bindings.Remove(view);}if(!bindings.ContainsKey(view))bindings.Add(view,new Binding(this,view,card.ObjectId));
                bool available=decision!=null && captured?.CanSubmit==true && panel.ObjectChoiceCount(captured,card.ObjectId)>0;
                view.EnableInClassList("actionable",available);view.EnableInClassList("targetable",available && decision.Options.Any(o=>o.ObjectId==card.ObjectId));
                if(available)view.tooltip="Click or press Enter to choose. Drag to the battlefield to use the offered action. Right-click or Space to inspect.";
            });
            foreach(var view in bindings.Keys.Where(v=>!seen.Contains(v)).ToArray()){bindings[view].Dispose();bindings.Remove(view);}
            hint.text=decision==null?"":captured?.CanSubmit!=true?"Waiting for the game to confirm your choice…":frame.Actions.Any(a=>a.Kind=="declare_attacker")?"Choose attackers on the battlefield · Finish attacks when ready":frame.Actions.Any(a=>a.Kind=="declare_blocker")?"Choose a blocker, then choose its attacker when prompted":decision.Options.Any(o=>o.ObjectId!=null || o.PlayerId!=null)?"Choose a highlighted card or player":frame.Actions.Any(a=>a.ObjectId!=null)?"Click a highlighted card, or drag it onto the battlefield":"";
            hint.style.display=string.IsNullOrEmpty(hint.text)?DisplayStyle.None:DisplayStyle.Flex;
        }
        private bool Current(ViewerDecisionOffer captured)=>!disposed && captured!=null && ReferenceEquals(captured,host.PresentedDecision) && captured.CanSubmit;
        private static bool Embedded(VisualElement target,CardView view){for(var e=target;e!=null && e!=view;e=e.parent)if(e is Button || e is TextField || e is Toggle)return true;return false;}
        private void Down(Binding binding,PointerDownEvent ev)
        {
            var captured=offer;var frame=captured?.Frame;
            if(ev.button!=0 || Embedded(ev.target as VisualElement,binding.View) || frame==null || !Current(captured) || frame.Decision?.Family=="mana" || panel.ObjectChoiceCount(captured,binding.Id)==0)return;
            CancelGesture();CloseMenu();pressed=binding;gestureOffer=captured;start=ev.position;pointer=ev.pointerId;binding.View.CapturePointer(pointer);ev.StopPropagation();
        }
        private void Move(Binding binding,PointerMoveEvent ev)
        {
            if(pressed!=binding)return;if(!Current(gestureOffer)){CancelGesture();return;}
            if(Vector2.Distance(start,ev.position)<10 && !dragging)return;
            dragging=true;binding.View.AddToClassList("gesture-source");ghostArtwork.image=binding.View.Artwork;ghostArtwork.style.display=ghostArtwork.image==null?DisplayStyle.None:DisplayStyle.Flex;ghost.text=ghostArtwork.image==null?"Choose action":"";ghost.style.display=DisplayStyle.Flex;
            var point=root.WorldToLocal(ev.position);ghost.style.left=point.x+14;ghost.style.top=point.y-26;ghost.BringToFront();ev.StopPropagation();
        }
        private void Up(Binding binding,PointerUpEvent ev)
        {
            if(pressed!=binding || ev.pointerId!=pointer)return;var captured=gestureOffer;bool wasDrag=dragging;var position=(Vector2)ev.position;
            CancelGesture();ev.StopPropagation();if(!Current(captured))return;
            if(wasDrag){
                var local=root.WorldToLocal(position);float height=root.resolvedStyle.height;
                if(local.x<145 || local.x>root.resolvedStyle.width-285 || local.y<height*.08f || local.y>height*.78f)return;
                var frame=captured.Frame;if(frame==null || !(frame.Actions.Any(a=>a.ObjectId==binding.Id && new[]{"play_land","cast_spell","select_object","activate","declare_attacker","declare_blocker"}.Contains(a.Kind)) || frame.Decision.Options.Any(o=>o.ObjectId==binding.Id)))return;
            }
            Activate(captured,binding,position);
        }
        private void Activate(ViewerDecisionOffer captured,Binding binding,Vector2 position)
        {
            if(!Current(captured))return;int count=panel.ObjectChoiceCount(captured,binding.Id);if(count==0)return;
            if(count==1){panel.TryActivateObject(captured,binding.Id);return;}
            menu.Clear();menu.Add(new Label("Choose an action"){enableRichText=false});var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.maxHeight=180;scroll.Add(panel.ObjectChoices(captured,binding.Id));menu.Add(scroll);
            var close=new Button(CloseMenu){text="Close"};menu.Add(close);var point=root.WorldToLocal(position);
            menu.style.left=Mathf.Clamp(point.x,10,Mathf.Max(10,root.resolvedStyle.width-310));menu.style.top=Mathf.Clamp(point.y,50,Mathf.Max(50,root.resolvedStyle.height-270));menu.style.display=DisplayStyle.Flex;decorateMenu?.Invoke(menu);menu.BringToFront();menu.Q<Button>()?.Focus();
        }
        private void CloseMenu(){menu.Clear();menu.style.display=DisplayStyle.None;}
        private void CancelGesture()
        {
            var old=pressed;pressed=null;gestureOffer=null;dragging=false;ghost.style.display=DisplayStyle.None;ghost.text="";ghostArtwork.image=null;
            if(old!=null){old.View.RemoveFromClassList("gesture-source");if(old.View.HasPointerCapture(pointer))old.View.ReleasePointer(pointer);}
        }
        public void Dispose(){if(disposed)return;CancelGesture();CloseMenu();disposed=true;foreach(var value in bindings.Values)value.Dispose();bindings.Clear();root.UnregisterCallback(key);hint.RemoveFromHierarchy();ghost.RemoveFromHierarchy();menu.RemoveFromHierarchy();offer=null;}
    }
}

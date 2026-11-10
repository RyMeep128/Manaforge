using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public enum GameplayDrawerDirection { Left, Right, Up, Down }
    // Presentation only. Content retains its own state, bindings and command authority.
    public sealed class GameplayDrawer : VisualElement, IDisposable
    {
        public Button Tab {get;}
        public VisualElement Content {get;}
        public VisualElement Viewport {get;}
        public bool IsOpen {get;private set;}
        public bool ReducedMotion {get;private set;}
        public bool NeedsAttention {get;private set;}
        public event Action<bool> OpenChanged;
        private readonly string title;
        private readonly DrawerGlyph glyph=new DrawerGlyph();
        private readonly Dictionary<VisualElement,(PickingMode picking,bool focusable)> suppressed=new Dictionary<VisualElement,(PickingMode,bool)>();
        private IVisualElementScheduledItem closing;
        private VisualElement returnFocus;
        private bool disposed;
        public GameplayDrawer(string title,GameplayDrawerDirection direction=GameplayDrawerDirection.Right,bool open=false)
        {
            this.title=title??throw new ArgumentNullException(nameof(title));AddToClassList("mf-gameplay-drawer");AddToClassList("drawer-"+direction.ToString().ToLowerInvariant());pickingMode=PickingMode.Ignore;
            GameplayTheme.Attach(this);
            Tab=new Button(Toggle){name="drawer-tab",text=title,focusable=true};Tab.AddToClassList("mf-drawer-tab");GameplayTheme.Button(Tab);Tab.Add(glyph);
            Viewport=new VisualElement{name="drawer-viewport",pickingMode=PickingMode.Ignore};Viewport.AddToClassList("mf-drawer-viewport");
            Content=new VisualElement{name="drawer-content",pickingMode=PickingMode.Ignore,focusable=true};Content.AddToClassList("mf-drawer-content");Viewport.Add(Content);Add(Viewport);Add(Tab);
            RegisterCallback<KeyDownEvent>(Key);RegisterCallback<DetachFromPanelEvent>(Detached);
            IsOpen=open;ApplyState(true);
        }
        private sealed class DrawerGlyph : VisualElement
        {
            internal bool Open;
            internal DrawerGlyph(){name="drawer-glyph";pickingMode=PickingMode.Ignore;generateVisualContent+=Draw;}
            private void Draw(MeshGenerationContext context){
                var pen=context.painter2D;pen.strokeColor=new Color(.94f,.85f,.66f);pen.lineWidth=1.8f;
                pen.BeginPath();pen.MoveTo(new Vector2(1,9));pen.LineTo(new Vector2(1,15));pen.LineTo(new Vector2(17,15));pen.LineTo(new Vector2(17,9));pen.Stroke();
                pen.BeginPath();pen.MoveTo(new Vector2(5,Open?4:1));pen.LineTo(new Vector2(9,Open?0:5));pen.LineTo(new Vector2(13,Open?4:1));pen.Stroke();
            }
        }
        private void Toggle(){SetOpen(!IsOpen,IsOpen==false);}
        public void SetOpen(bool open,bool focusContent=false)
        {
            if(disposed)return;
            if(open==IsOpen){if(open && focusContent)FocusContent();return;}
            var focused=panel?.focusController?.focusedElement as VisualElement;
            if(!open && Contains(Content,focused)){returnFocus=focused;Tab.Focus();}
            IsOpen=open;ApplyState(ReducedMotion);OpenChanged?.Invoke(open);
            if(open && focusContent)FocusContent();
        }
        private static bool Contains(VisualElement parent,VisualElement child){for(var item=child;item!=null;item=item.parent)if(item==parent)return true;return false;}
        public void FocusContent()
        {
            if(!IsOpen || disposed)return;
            if(returnFocus!=null && Contains(Content,returnFocus) && returnFocus.focusable && returnFocus.enabledInHierarchy){returnFocus.Focus();return;}
            var first=Content.Query<VisualElement>().ToList().FirstOrDefault(item=>item!=Content && item.focusable && item.enabledInHierarchy && item.resolvedStyle.display!=DisplayStyle.None);
            (first??Content).Focus();
        }
        private void ApplyState(bool immediate)
        {
            glyph.Open=IsOpen;glyph.MarkDirtyRepaint();closing?.Pause();closing=null;EnableInClassList("drawer-open",IsOpen);Tab.tooltip=title+(IsOpen?" — collapse":" — expand")+(NeedsAttention?" — attention required":"");
            Content.SetEnabled(IsOpen);RefreshInput();
            if(IsOpen)Content.style.visibility=Visibility.Visible;
            else if(immediate || panel==null)Content.style.visibility=Visibility.Hidden;
            else closing=schedule.Execute(()=>{closing=null;if(!IsOpen)Content.style.visibility=Visibility.Hidden;}).StartingIn(230);
        }
        // Invoke after content rebuilds. Ignore the entire closed subtree so it cannot
        // intercept battlefield pointers or enter the keyboard traversal order.
        public void RefreshInput()
        {
            if(disposed)return;
            if(IsOpen){foreach(var pair in suppressed){pair.Key.pickingMode=pair.Value.picking;pair.Key.focusable=pair.Value.focusable;}suppressed.Clear();return;}
            foreach(var stale in suppressed.Keys.Where(item=>!Contains(Content,item)).ToArray())suppressed.Remove(stale);
            foreach(var item in Content.Query<VisualElement>().ToList().Prepend(Content)) {
                if(!suppressed.ContainsKey(item))suppressed.Add(item,(item.pickingMode,item.focusable));item.pickingMode=PickingMode.Ignore;item.focusable=false;
            }
        }
        public void SetReducedMotion(bool value){if(disposed || ReducedMotion==value)return;ReducedMotion=value;EnableInClassList("drawer-reduced-motion",value);ApplyState(value);}
        public void SetAttention(bool value,string summary=null){NeedsAttention=value;EnableInClassList("drawer-attention",value);Tab.text=title+(value?" • "+(summary??"Attention"):"");Tab.tooltip=title+(IsOpen?" — collapse":" — expand")+(value?" — "+(summary??"Attention required"):"");}
        public void Reset(bool open=false){if(disposed)return;if(!open && Contains(Content,panel?.focusController?.focusedElement as VisualElement))Tab.Focus();returnFocus=null;NeedsAttention=false;SetAttention(false);bool changed=IsOpen!=open;IsOpen=open;ApplyState(true);if(changed)OpenChanged?.Invoke(open);}
        private void Key(KeyDownEvent ev)
        {
            if(ev.keyCode==KeyCode.Escape && IsOpen){SetOpen(false);Tab.Focus();ev.StopPropagation();}
            else if(ReferenceEquals(ev.target,Tab) && (ev.keyCode==KeyCode.RightArrow || ev.keyCode==KeyCode.DownArrow)){SetOpen(true,true);ev.StopPropagation();}
        }
        private void Detached(DetachFromPanelEvent ev){if(ev.target!=this)return;closing?.Pause();closing=null;if(!IsOpen)Content.style.visibility=Visibility.Hidden;}
        public void Dispose(){if(disposed)return;closing?.Pause();closing=null;foreach(var pair in suppressed){pair.Key.pickingMode=pair.Value.picking;pair.Key.focusable=pair.Value.focusable;}suppressed.Clear();returnFocus=null;disposed=true;OpenChanged=null;UnregisterCallback<KeyDownEvent>(Key);UnregisterCallback<DetachFromPanelEvent>(Detached);RemoveFromHierarchy();}
    }
}

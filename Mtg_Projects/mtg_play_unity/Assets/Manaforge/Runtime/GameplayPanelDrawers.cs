using System;
using System.Linq;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Coalesce passive status changes without delaying commands or input gating.
    internal static class StableStatusText
    {
        private sealed class Pending {public string Text;public IVisualElementScheduledItem Job;}
        private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<Label,Pending> labels=new System.Runtime.CompilerServices.ConditionalWeakTable<Label,Pending>();
        internal static void Set(Label label,string value,bool immediate=false)
        {
            value=value??"";var pending=labels.GetOrCreateValue(label);
            if(immediate || string.IsNullOrEmpty(label.text) || label.panel==null){pending.Job?.Pause();pending.Job=null;pending.Text=null;if(label.text!=value)label.text=value;return;}
            if(label.text==value){pending.Job?.Pause();pending.Job=null;pending.Text=null;return;}
            if(pending.Text==value)return;
            pending.Job?.Pause();pending.Text=value;
            pending.Job=label.schedule.Execute(()=>{if(label.text!=pending.Text)label.text=pending.Text;pending.Text=null;pending.Job=null;}).StartingIn(90);
        }
    }
    // Persistent phase controls, following the inspected Arena ladder interaction:
    // highlight the active phase and let each fixed button toggle a phase stop.
    internal sealed class GameplayPhaseStrip
    {
        internal VisualElement Root {get;}=new VisualElement{name="table-phase-strip"};
        private readonly (string phase,Button button)[] buttons;
        private string scope="own";
        internal GameplayPhaseStrip(VisualElement parent,Func<UnityPriorityPolicy> policy,Action changed)
        {
            var phases=new[]{("BEGINNING","Begin"),("PRECOMBAT_MAIN","Main 1"),("COMBAT","Combat"),("POSTCOMBAT_MAIN","Main 2"),("END","End")};
            buttons=phases.Select(phase=>{var button=new Button(()=>{var current=policy();if(current==null)return;bool stop=!current.Current.Stops.Contains(scope+":phase:"+phase.Item1);current.SetStop(scope,"phase",phase.Item1,stop,current.Current.RepeatStops);changed();}){name="phase-stop-"+phase.Item1,text=phase.Item2,tooltip="Toggle stop in "+phase.Item2};button.AddToClassList("phase-strip-button");Root.Add(button);return (phase.Item1,button);}).ToArray();
            parent.Add(Root);
        }
        internal void Present(ProjectedDecisionFrame frame,UnityPriorityPolicy policy)
        {
            string phase=frame.Phase=="ENDING"?"END":frame.Phase;
            scope=frame.ActivePlayerId==frame.Context.ViewerId?"own":"opponent";
            foreach(var entry in buttons){entry.button.tooltip=(scope=="own"?"Your turn: ":"Opponents' turns: ")+entry.phase.Replace('_',' ');entry.button.EnableInClassList("phase-active",entry.phase==phase);entry.button.EnableInClassList("phase-stopped",policy?.Current.Stops.Contains(scope+":phase:"+entry.phase)==true || policy?.Current.Stops.Contains("phase:"+entry.phase)==true);entry.button.SetEnabled(policy!=null && frame.Result==null);}
        }
    }
    // One persistent action area for normal priority and explicit yielding.
    // Buttons resolve the current authenticated offer at click time, never a retired capture.
    internal sealed class GameplayPriorityActions
    {
        internal VisualElement Root {get;}=new VisualElement{name="priority-actions"};
        private readonly ViewerDecisionPanel panel;
        private readonly Label heading=new Label("Priority"){name="priority-actions-heading",enableRichText=false};
        private readonly Label detail=new Label{name="priority-actions-detail",enableRichText=false};
        private readonly Label mana=new Label{name="priority-actions-mana",enableRichText=false};
        private readonly Button primary,secondary,settings,more;
        private readonly VisualElement yieldMenu=new VisualElement{name="priority-actions-yield-menu"};
        private readonly Button yieldTurn,yieldStack,yieldEnd,yieldResolve;
        private readonly Foldout alternatives=new Foldout{text="Card and player choices",value=false,name="priority-actions-alternatives"};
        private readonly ScrollView alternativeList=new ScrollView(ScrollViewMode.Vertical);
        private ViewerDecisionOffer bound;
        internal bool HasPresented {get;private set;}
        internal GameplayPriorityActions(ViewerDecisionPanel panel,Action openSettings)
        {
            this.panel=panel;Root.AddToClassList("mf-priority-actions");
            var header=new VisualElement();header.AddToClassList("priority-actions-header");header.Add(heading);
            settings=new Button(openSettings){name="priority-actions-settings",text="Stops & settings"};GameplayTheme.Button(settings);header.Add(settings);
            Root.Add(header);Root.Add(detail);Root.Add(mana);
            alternativeList.horizontalScrollerVisibility=alternativeList.verticalScrollerVisibility=ScrollerVisibility.Hidden;alternativeList.style.maxHeight=96;alternatives.Add(alternativeList);Root.Add(alternatives);
            primary=new Button(Primary){name="priority-actions-primary",text="Next"};secondary=new Button(){name="priority-actions-secondary",text="Pass turn"};
            secondary.clickable.clickedWithEventInfo+=Secondary;
            secondary.clickable.activators.Add(new ManipulatorActivationFilter{button=MouseButton.LeftMouse,modifiers=UnityEngine.EventModifiers.Shift});
            GameplayTheme.Button(primary,true);GameplayTheme.Button(secondary);Root.Add(primary);Root.Add(secondary);
            more=new Button(()=>{yieldMenu.style.display=yieldMenu.style.display.value==DisplayStyle.Flex?DisplayStyle.None:DisplayStyle.Flex;yieldMenu.BringToFront();}){name="priority-actions-more",text="…",tooltip="More passing options"};GameplayTheme.Button(more);more.style.width=more.style.minWidth=36;more.style.minHeight=more.style.height=36;more.style.fontSize=18;secondary.style.minWidth=0;secondary.style.right=46;secondary.style.height=secondary.style.minHeight=36;Root.Add(more);
            yieldTurn=YieldButton("turn","Until my next turn");yieldStack=YieldButton("stack","Until stack changes");yieldEnd=YieldButton("end-turn","Pass turn (ignore responses)");yieldResolve=YieldButton("resolve-stack","Resolve All");
            yieldMenu.Add(YieldButton("response","Pass until response"));yieldMenu.Add(yieldTurn);yieldMenu.Add(yieldStack);yieldMenu.Add(yieldEnd);yieldMenu.Add(yieldResolve);Root.Add(yieldMenu);yieldMenu.style.display=DisplayStyle.None;
            alternatives.RegisterValueChangedCallback(ev=>{if(ReferenceEquals(ev.target,alternatives) && ev.newValue){yieldMenu.style.display=DisplayStyle.None;alternatives.BringToFront();}});
            Root.RegisterCallback<PointerDownEvent>(ev=>{if(ev.target is VisualElement target && target!=more && !more.Contains(target) && target!=yieldMenu && !yieldMenu.Contains(target))yieldMenu.style.display=DisplayStyle.None;},TrickleDown.TrickleDown);
            Root.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==UnityEngine.KeyCode.Escape && yieldMenu.style.display.value==DisplayStyle.Flex){yieldMenu.style.display=DisplayStyle.None;more.Focus();ev.StopImmediatePropagation();}},TrickleDown.TrickleDown);
            Root.style.display=DisplayStyle.None;
        }
        private Button YieldButton(string mode,string label)
        {
            var button=new Button(()=>{yieldMenu.style.display=DisplayStyle.None;panel.TryBeginPriorityYield(mode);Refresh();}){name="priority-actions-yield-"+mode,text=label};GameplayTheme.Button(button);return button;
        }
        private void Primary()
        {
            if(panel.Priority.Current.Paused)panel.ResumePriority();
            else if(panel.Presentation?.Compact==true)panel.CancelPriorityYield();
            else panel.TryPassPriority();
            Refresh();
        }
        private void Secondary(EventBase ev)
        {
            if(panel.Priority.Current.Yield!=null)panel.CancelPriorityYield();
            else panel.TryBeginPriorityYield(ev is IPointerEvent pointer && pointer.shiftKey || ev is IMouseEvent mouse && mouse.shiftKey?"end-turn":panel.PriorityFrame?.StackIds.Count>0?"resolve-stack":"response");
            Refresh();
        }
        internal void Refresh()
        {
            var offer=panel.CurrentOffer;var frame=offer?.Frame;var state=panel.Priority.Current;
            bool yielding=panel.Presentation?.Compact==true;
            bool priority=frame?.Decision?.IsPriority==true;
            if(priority)HasPresented=true;
            bool canPass=panel.CanPassPriority;
            if(priority && !ReferenceEquals(bound,offer)){
                bound=offer;alternativeList.Clear();
                if(priority)foreach(var choice in panel.PriorityAlternatives())alternativeList.Add(choice);
            }
            alternatives.SetEnabled(canPass && !yielding);settings.SetEnabled(!panel.LayoutEditing);
            more.SetEnabled(canPass && !panel.PriorityControlsOpen && !yielding && !state.Paused);yieldTurn.SetEnabled(canPass);yieldStack.SetEnabled(canPass);yieldEnd.SetEnabled(canPass && frame?.ActivePlayerId==frame?.Context.ViewerId);yieldResolve.SetEnabled(canPass && frame?.StackIds.Count>0);
            if(!canPass || yielding)yieldMenu.style.display=DisplayStyle.None;
            string text=state.Paused?"Automatic passing paused. Resume when ready.":yielding?panel.Presentation.Text:!priority?"Waiting for opponent…":!offer.CanSubmit || panel.PriorityCommandPending?"Passing priority…":frame.StackIds.Count>0?"Respond to the stack, or resolve the next object.":"Play an available card or ability, or continue.";
            StableStatusText.Set(detail,text,state.Paused);
            string floating=frame?.ViewerMana==null?"":string.Join(", ",frame.ViewerMana.Where(pair=>pair.Value>0).Select(pair=>pair.Key+" "+pair.Value));
            mana.text=string.IsNullOrEmpty(floating)?"":"Mana: "+floating;
            // Keep the last label through offer gaps; only availability changes immediately.
            if(priority || yielding || state.Paused){primary.text=state.Paused?"Resume":yielding?"Cancel":frame.StackIds.Count>0?"Resolve":frame.ActivePlayerId==frame.Context.ViewerId?"Next":"Pass";secondary.text=state.Yield!=null?"Cancel passing":frame.StackIds.Count>0?"Resolve All":frame.ActivePlayerId==frame.Context.ViewerId?"End turn":"Pass turn";}
            primary.SetEnabled(!panel.LayoutEditing && (state.Paused && panel.PrioritySessionActive || yielding && panel.PrioritySessionActive || canPass));
            secondary.SetEnabled(!panel.LayoutEditing && (state.Yield!=null && panel.PrioritySessionActive || canPass && !panel.PriorityControlsOpen && !state.Paused));
            primary.tooltip=yielding?"Stop explicit passing. Ordinary auto-pass follows your settings.":frame?.Actions.FirstOrDefault(action=>action.Kind=="pass" && action.ObjectId==null)?.Label;
            secondary.tooltip=frame?.StackIds.Count>0?"Resolve this stack; stop for new objects. Shift-click to pass the turn even through responses.":"Pass until an opponent responds. Shift-click to ignore optional responses. Stops and required choices always interrupt.";
        }
        internal void Reset(){bound=null;HasPresented=false;yieldMenu.style.display=DisplayStyle.None;alternativeList.Clear();alternatives.SetValueWithoutNotify(false);Root.style.display=DisplayStyle.None;primary.SetEnabled(false);secondary.SetEnabled(false);}
    }
    // Binds attention to the existing authenticated decision UI; never dispatches commands.
    public sealed class GameplayActionDrawer : IDisposable
    {
        public GameplayDrawer Drawer {get;}
        private readonly ViewerDecisionPanel decisions;
        private string context,decision;private bool failed;
        public GameplayActionDrawer(GameplayDrawer drawer,ViewerDecisionPanel decisions){Drawer=drawer;this.decisions=decisions;}
        public void Refresh(ProjectedDecisionFrame frame)
        {
            string next=frame.Context.SessionId+"/"+frame.Context.ViewerId;
            if(context!=next){Reset();context=next;}
            bool mandatory=frame.Decision!=null && !frame.Decision.IsPriority && frame.Decision.PlayerId==frame.Context.ViewerId;
            bool error=frame.UnsupportedFields.Contains("decision") || decisions.Root.ClassListContains("command-uncertain") || decisions.Presentation?.Mode==YieldPresentationMode.Failed;
            if(mandatory && decision!=frame.Decision.DecisionId || error && !failed)Drawer.SetOpen(true);
            decision=frame.Decision?.DecisionId;failed=error;
            Drawer.SetAttention(mandatory || error,error?"Needs attention":mandatory?"Choice required":null);Drawer.RefreshInput();
        }
        public void Reset(){context=decision=null;failed=false;Drawer.Reset();}
        public void Dispose(){Drawer.Dispose();}
    }
    public sealed class GameplayPriorityDrawer : IDisposable
    {
        public GameplayDrawer Drawer {get;}
        public UnityPriorityControls Controls {get;}
        private readonly ViewerDecisionPanel decisions;
        public GameplayPriorityDrawer(GameplayDrawer drawer,ViewerDecisionPanel decisions)
        {
            Drawer=drawer;this.decisions=decisions;var scroll=new ScrollView(ScrollViewMode.Vertical);scroll.style.flexShrink=1;scroll.style.maxHeight=Length.Percent(100);drawer.Content.Add(scroll);Controls=new UnityPriorityControls(scroll,decisions);drawer.OpenChanged+=Visible;Visible(drawer.IsOpen);
        }
        private void Visible(bool open){Controls.SetPresentationVisible(open);}
        public void Refresh()
        {
            Controls.Refresh();var state=decisions.Priority.Current;
            bool failed=state.Paused || decisions.Presentation?.Mode==YieldPresentationMode.Failed;
            Drawer.SetAttention(failed || state.Manual,failed?"Paused":state.Manual?"Manual":null);Drawer.RefreshInput();
        }
        public void Dispose(){Drawer.OpenChanged-=Visible;Controls.Dispose();Drawer.Dispose();}
    }
}

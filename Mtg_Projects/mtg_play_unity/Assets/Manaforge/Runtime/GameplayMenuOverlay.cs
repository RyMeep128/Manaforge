using System;
using System.Linq;
using System.Threading.Tasks;
using Manaforge.Play.Protocol;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // UI-only modal. Session authority and rendering remain with the caller.
    public sealed class GameplayMenuOverlay : IDisposable
    {
        private readonly VisualElement root,shade,card,main,options,confirm,resetConfirm;
        private readonly Button resume,concede,confirmConcede,cancel;
        private readonly Label title,message;
        private Button customize,resetLayout,confirmReset,cancelReset;private HudLayoutEditor layoutEditor;
        private readonly Func<bool> canConcede;
        private readonly Func<Task<TrackedCommand>> send;
        private readonly Func<string,TrackedCommand> receipt;
        private readonly Action interrupt;
        private readonly IVisualElementScheduledItem ticker;
        private VisualElement returnFocus;
        private int page,lastCancelFrame=-1;
        private bool held,disposed,submitting,ended;
        private Task<TrackedCommand> pending;
        private string commandId;
        public bool IsOpen {get;private set;}
        public VisualElement OptionsContent {get;}
        public GameplayMenuOverlay(VisualElement root,Func<bool> canConcede,Func<Task<TrackedCommand>> send,Func<string,TrackedCommand> receipt,Action interrupt=null,Action returnToManaforge=null)
        {
            this.root=root;this.canConcede=canConcede;this.send=send;this.receipt=receipt;this.interrupt=interrupt;
            shade=new VisualElement{name="game-menu-overlay"};shade.AddToClassList("mf-game-menu-overlay");GameplayTheme.Attach(shade);root.Add(shade);
            card=new ScrollView(ScrollViewMode.Vertical){name="game-menu-card",horizontalScrollerVisibility=ScrollerVisibility.Hidden};card.AddToClassList("mf-game-menu-card");shade.Add(card);
            title=new Label("Game Menu"){name="game-menu-title"};card.Add(title);
            main=new VisualElement{name="game-menu-main"};card.Add(main);
            resume=MakeButton("game-menu-resume","Resume",Close);main.Add(resume);
            main.Add(MakeButton("game-menu-options","Options",()=>Navigate(1)));
            concede=MakeButton("game-menu-concede","Concede",()=>Navigate(2));concede.AddToClassList("mf-concede");main.Add(concede);
            if(returnToManaforge!=null)main.Add(MakeButton("game-leave","Return to Manaforge",()=>{Close();returnToManaforge();}));
            options=new VisualElement{name="game-menu-options-page"};card.Add(options);
            OptionsContent=new VisualElement{name="game-menu-display-options"};options.Add(OptionsContent);
            options.Add(MakeButton("game-menu-back","Back",()=>Navigate(0)));
            confirm=new VisualElement{name="game-menu-confirm"};card.Add(confirm);
            var warning=new Label("Concede this game? This cannot be undone.");warning.style.whiteSpace=WhiteSpace.Normal;confirm.Add(warning);
            cancel=MakeButton("game-menu-cancel-concede","Cancel",()=>Navigate(0));confirm.Add(cancel);
            confirmConcede=MakeButton("game-menu-confirm-concede","Concede",Submit);confirmConcede.AddToClassList("mf-concede");confirm.Add(confirmConcede);
            resetConfirm=new VisualElement{name="game-menu-reset-layout-page"};card.Add(resetConfirm);
            var resetWarning=new Label("Restore default drawer placement for this game and discard the current layout draft? Saved presets and your startup selection will be kept.");resetWarning.style.whiteSpace=WhiteSpace.Normal;resetConfirm.Add(resetWarning);
            cancelReset=MakeButton("game-menu-cancel-reset-layout","Cancel",()=>Navigate(0));resetConfirm.Add(cancelReset);
            confirmReset=MakeButton("game-menu-confirm-reset-layout","Reset Layout for This Game",()=>{Close();layoutEditor?.ResetForGame();});resetConfirm.Add(confirmReset);
            message=new Label{name="game-menu-status",enableRichText=false};message.style.whiteSpace=WhiteSpace.Normal;card.Add(message);
            var note=new Label("The game continues while this menu is open.");note.AddToClassList("mf-game-menu-note");card.Add(note);
            shade.style.display=DisplayStyle.None;
            root.RegisterCallback<KeyDownEvent>(Down,TrickleDown.TrickleDown);root.RegisterCallback<KeyUpEvent>(Up,TrickleDown.TrickleDown);
            root.RegisterCallback<PointerDownEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<PointerUpEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<PointerMoveEvent>(Block,TrickleDown.TrickleDown);
            root.RegisterCallback<WheelEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<ClickEvent>(Block,TrickleDown.TrickleDown);
            root.RegisterCallback<NavigationSubmitEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<NavigationMoveEvent>(Block,TrickleDown.TrickleDown);root.RegisterCallback<NavigationCancelEvent>(NavigationCancel,TrickleDown.TrickleDown);
            root.RegisterCallback<FocusInEvent>(Focus,TrickleDown.TrickleDown);
            ticker=root.schedule.Execute(Tick).Every(100);
        }
        private static Button MakeButton(string name,string text,Action action){var button=new Button(action){name=name,text=text};GameplayTheme.Button(button);return button;}
        private bool Inside(object target)=>target is VisualElement element && (element==shade || shade.Contains(element));
        private void Block<T>(T ev) where T:EventBase<T>,new(){if(IsOpen && !Inside(ev.target))ev.StopImmediatePropagation();}
        private void NavigationCancel(NavigationCancelEvent ev){if(IsOpen){if(!held && lastCancelFrame!=Time.frameCount){lastCancelFrame=Time.frameCount;Back();}ev.StopImmediatePropagation();}}
        private void Focus(FocusInEvent ev){if(IsOpen && !Inside(ev.target)){ev.StopImmediatePropagation();DefaultFocus();}}
        private void DefaultFocus(){if(page==0)resume.Focus();else if(page==2)cancel.Focus();else if(page==3)cancelReset.Focus();else options.Q<Button>()?.Focus();}
        public void SetLayoutEditor(HudLayoutEditor editor)
        {
            if(editor==null || customize!=null)return;layoutEditor=editor;
            customize=MakeButton("game-menu-customize-layout","Customize Layout",()=>{Close();editor.Open();});main.Insert(2,customize);
            resetLayout=MakeButton("game-menu-reset-layout","Reset Layout for This Game",()=>Navigate(3));main.Insert(3,resetLayout);
        }
        public void Open()
        {
            if(disposed || IsOpen || layoutEditor?.IsEditing==true)return;returnFocus=root.panel?.focusController.focusedElement as VisualElement;
            IsOpen=true;interrupt?.Invoke();shade.style.display=DisplayStyle.Flex;shade.BringToFront();Navigate(0);Tick();
        }
        public void Close()
        {
            if(!IsOpen)return;IsOpen=false;shade.style.display=DisplayStyle.None;
            var origin=returnFocus;returnFocus=null;if(origin?.panel!=null && origin.enabledInHierarchy && Visible(origin))origin.Focus();else root.Focus();
        }
        private void Navigate(int value)
        {
            page=value;main.style.display=value==0?DisplayStyle.Flex:DisplayStyle.None;options.style.display=value==1?DisplayStyle.Flex:DisplayStyle.None;confirm.style.display=value==2?DisplayStyle.Flex:DisplayStyle.None;resetConfirm.style.display=value==3?DisplayStyle.Flex:DisplayStyle.None;
            title.text=value==0?"Game Menu":value==1?"Options":value==2?"Concede Game":"Reset Layout for This Game";DefaultFocus();
        }
        private void Back(){if(page==0)Close();else Navigate(0);}
        private void Down(KeyDownEvent ev)
        {
            if(ev.keyCode==KeyCode.F11)return;
            if(ev.keyCode==KeyCode.Escape){if(!held){held=true;if(lastCancelFrame!=Time.frameCount){lastCancelFrame=Time.frameCount;if(IsOpen)Back();else Open();}}ev.StopImmediatePropagation();return;}
            if(!IsOpen)return;
            if(ev.keyCode==KeyCode.Tab){var buttons=card.Query<Button>().ToList().Where(b=>b.enabledInHierarchy && Visible(b)).ToArray();if(buttons.Length>0){int index=Array.IndexOf(buttons,root.panel?.focusController.focusedElement as Button);var next=buttons[(index+(ev.shiftKey?-1:1)+buttons.Length)%buttons.Length];next.Focus();((ScrollView)card).ScrollTo(next);}ev.StopImmediatePropagation();return;}
            if(!Inside(ev.target))ev.StopImmediatePropagation();
        }
        private static bool Visible(VisualElement element){for(var e=element;e!=null;e=e.parent)if(e.resolvedStyle.display==DisplayStyle.None || e.resolvedStyle.visibility==Visibility.Hidden)return false;return true;}
        private void Up(KeyUpEvent ev){if(ev.keyCode==KeyCode.Escape){held=false;ev.StopImmediatePropagation();}else if(IsOpen && ev.keyCode!=KeyCode.F11 && !Inside(ev.target))ev.StopImmediatePropagation();}
        private void Submit()
        {
            if(submitting || !canConcede())return;submitting=true;message.text="Submitting concession...";
            try{pending=send();}catch(Exception error){submitting=false;message.text="Concession was not submitted: "+error.Message;}Tick();
        }
        private void Tick()
        {
            if(disposed)return;
            if(pending?.IsCompleted==true){var task=pending;pending=null;if(task.Status==TaskStatus.RanToCompletion)commandId=task.Result.CommandId;else{var error=task.Exception?.GetBaseException();var local=error as WireEnvelope.EnvelopeException;bool known=local!=null && new[]{"COMMAND_PENDING","SESSION_STOPPED","ACTION_UNAVAILABLE","SESSION_RESULT","SESSION_SHUTDOWN_PENDING"}.Contains(local.Code);submitting=!known;message.text=(known?"Concession was not submitted: ":"Concession status is uncertain: ")+(error?.Message??"Cancelled");}}
            if(commandId!=null){var state=receipt(commandId);if(state?.State==CommandState.Rejected){commandId=null;submitting=false;message.text="Concession rejected ("+state.Code+"). You can try again.";}else if(state?.State==CommandState.Uncertain || state==null){message.text="Concession status is uncertain. Waiting for the game result.";}else message.text="Waiting for the game result...";}
            if(customize!=null){customize.SetEnabled(!ended && !submitting && layoutEditor.CanOpen);customize.text=layoutEditor.HasRetainedDraft?"Resume Customization":"Customize Layout";}
            if(resetLayout!=null){resetLayout.SetEnabled(!ended && layoutEditor.CanReset);confirmReset.SetEnabled(!ended && layoutEditor.CanReset);}
            bool enabled=!ended && !submitting && canConcede();concede.SetEnabled(enabled);confirmConcede.SetEnabled(enabled);
            if(IsOpen)shade.BringToFront();
        }
        public void EndMatch(){ended=true;Close();}
        public void Dispose()
        {
            if(disposed)return;Close();disposed=true;ticker.Pause();pending?.ContinueWith(task=>{_=task.Exception;},TaskScheduler.Default);
            root.UnregisterCallback<KeyDownEvent>(Down,TrickleDown.TrickleDown);root.UnregisterCallback<KeyUpEvent>(Up,TrickleDown.TrickleDown);
            root.UnregisterCallback<PointerDownEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<PointerUpEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<PointerMoveEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<WheelEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<ClickEvent>(Block,TrickleDown.TrickleDown);
            root.UnregisterCallback<NavigationSubmitEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<NavigationMoveEvent>(Block,TrickleDown.TrickleDown);root.UnregisterCallback<NavigationCancelEvent>(NavigationCancel,TrickleDown.TrickleDown);root.UnregisterCallback<FocusInEvent>(Focus,TrickleDown.TrickleDown);
            shade.RemoveFromHierarchy();
        }
    }
}

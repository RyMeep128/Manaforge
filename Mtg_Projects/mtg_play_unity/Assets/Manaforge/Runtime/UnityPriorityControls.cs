using System;
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Unity in-game controls. Settings belong to this viewer session, never Qt.
    public sealed class UnityPriorityControls : IDisposable
    {
        private readonly ViewerDecisionPanel panel;
        public VisualElement Root {get;}=new VisualElement{name="unity-priority-controls"};
        private readonly Toggle automatic=new Toggle("Auto-pass priority");
        private readonly Toggle manual=new Toggle("Hold Full Control");
        private readonly Toggle temporary=new Toggle("Full Control for this phase");
        private readonly Toggle repeat=new Toggle("Repeat stops every turn");
        private readonly Label state=new Label{name="unity-priority-status",enableRichText=false};
        private readonly Button cancel,resume,untilTurn,untilStack;
        private readonly Foldout details=new Foldout{text="Yield / phase stops",value=false};
        private readonly Dictionary<string,Toggle> stops=new Dictionary<string,Toggle>(StringComparer.Ordinal);
        private bool disposed;
        public bool PresentationVisible {get;private set;}=true;
        public void SetPresentationVisible(bool visible){if(disposed || PresentationVisible==visible)return;PresentationVisible=visible;panel.PriorityControlsOpen=visible && details.value;Changed();}
        public UnityPriorityControls(VisualElement parent,ViewerDecisionPanel panel)
        {
            this.panel=panel??throw new ArgumentNullException(nameof(panel));panel.EnablePriority();
            Root.Add(automatic);Root.Add(manual);Root.Add(temporary);Root.Add(state);
            temporary.name="unity-priority-temporary";
            temporary.RegisterValueChangedCallback(change=>{panel.Priority.SetTemporaryFullControl(change.newValue,panel.PriorityFrame);Changed();});
            automatic.name="unity-priority-automatic";manual.name="unity-priority-manual";
            automatic.tooltip="Advance priority windows and main phases with no available plays. Hold for floating mana in your main phase, meaningful responses, Full Control, or a stop.";
            manual.tooltip="Hold every priority opportunity until Manual control is switched off.";
            automatic.RegisterValueChangedCallback(change=>{panel.Priority.Current.Automatic=change.newValue;Changed();});
            manual.RegisterValueChangedCallback(change=>{panel.Priority.SetTemporaryFullControl(false,panel.PriorityFrame);panel.Priority.Current.Manual=change.newValue;Changed();});
            cancel=new Button(()=>{panel.Priority.CancelPassing(panel.PriorityFrame);Changed();}){text="Cancel yield",name="unity-priority-cancel"};Root.Add(cancel);
            resume=new Button(()=>{panel.Priority.Resume();Changed();}){text="Resume automatic passing",name="unity-priority-resume"};Root.Add(resume);
            if(panel.UnifiedPriorityActions)details.text="Phase and step stops";Root.Add(details);details.RegisterValueChangedCallback(change=>{if(!ReferenceEquals(change.target,details))return;panel.PriorityControlsOpen=PresentationVisible && change.newValue;Changed();});
            untilTurn=new Button(()=>Yield("turn")){text="Yield until my next turn",name="unity-priority-yield-turn"};
            untilStack=new Button(()=>Yield("stack")){text="Yield until stack changes",name="unity-priority-yield-stack"};
            untilTurn.tooltip="Pass priority even when responses are available, until your next turn. Phase stops still apply.";
            untilStack.tooltip="Pass priority even when responses are available, until the stack changes. Phase stops still apply.";
            cancel.tooltip="End the explicit yield. Ordinary auto-pass still follows its checkbox.";
            details.Add(untilTurn);details.Add(untilStack);
            repeat.name="unity-priority-repeat-stops";details.Add(repeat);repeat.RegisterValueChangedCallback(change=>{panel.Priority.Current.RepeatStops=change.newValue;Changed();});
            var list=new ScrollView(ScrollViewMode.Vertical){name="unity-priority-stops"};details.Add(list);
            foreach(var scopeValue in new[]{"own","opponent"}) foreach(var group in new[]{"phase","step"}){
                list.Add(new Label((scopeValue=="own"?"Your turn: ":"Opponents' turns: ")+(group=="phase"?"Phase stops":"Step stops")){enableRichText=false});
                foreach(var value in group=="phase"?UnityPriorityPolicy.Phases:UnityPriorityPolicy.Steps){
                    string scope=scopeValue,kind=group,item=value,key=scope+":"+kind+":"+item;
                    var toggle=new Toggle(System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(item.Replace('_',' ').ToLowerInvariant()));
                    toggle.name="unity-priority-stop-"+key;toggle.tooltip="Hold priority on the selected player's turn.";
                    toggle.RegisterValueChangedCallback(change=>{panel.Priority.SetStop(scope,kind,item,change.newValue,panel.Priority.Current.RepeatStops);Changed();});
                    stops.Add(key,toggle);list.Add(toggle);
                }
            }
            parent.Add(Root);Refresh();
        }
        private void Yield(string mode)
        {
            panel.Priority.BeginYield(mode,panel.PriorityFrame);details.value=false;Changed();
        }
        private void Changed(){panel.PrioritySettingsChanged();Refresh();}
        public void Refresh()
        {
            if(disposed)return;var current=panel.Priority.Current;
            Root.SetEnabled(panel.PrioritySessionActive);
            temporary.SetValueWithoutNotify(current.TemporaryFullControl);
            repeat.SetValueWithoutNotify(current.RepeatStops);
            automatic.SetValueWithoutNotify(current.Automatic);manual.SetValueWithoutNotify(current.Manual);
            foreach(var stop in stops)stop.Value.SetValueWithoutNotify(current.Stops.Contains(stop.Key));
            StableStatusText.Set(state,PresentationVisible && details.value?"Close these controls to resume automatic passing.":panel.Presentation?.Compact==true?panel.Presentation.Text:current.Reason,current.Paused);
            cancel.style.display=!panel.UnifiedPriorityActions && current.Yield!=null && panel.Presentation?.Compact!=true?DisplayStyle.Flex:DisplayStyle.None;
            untilTurn.style.display=untilStack.style.display=panel.UnifiedPriorityActions?DisplayStyle.None:DisplayStyle.Flex;
            resume.style.display=current.Paused?DisplayStyle.Flex:DisplayStyle.None;
            var frame=panel.PriorityFrame;bool active=frame?.Status=="active" && frame.Result==null;
            untilTurn.SetEnabled(active && !current.Paused);untilStack.SetEnabled(active && !current.Paused);
        }
        public void Dispose(){if(disposed)return;disposed=true;panel.Priority.Suspend();Root.RemoveFromHierarchy();}
    }
}

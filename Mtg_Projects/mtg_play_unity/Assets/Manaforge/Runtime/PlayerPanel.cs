using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Explicit seat identity; never searches a frame for an opponent.
    public sealed class PlayerPanel : Label, IDisposable
    {
        private readonly Label life, caption, state;
        private readonly VisualElement commanderDamage;
        public float SummaryHeight {get;private set;}=78;
        private IVisualElementScheduledItem pulse;
        private long? lastLife;
        private bool disposed, targetable;
        public string PlayerId { get; private set; }
        public event Action<string> Activated;
        public PlayerPanel()
        {
            text=""; enableRichText=false; focusable=true; AddToClassList("mf-player");
            life=new Label("?"){name="seat-life",enableRichText=false}; life.AddToClassList("mf-player-life"); Add(life);
            caption=new Label(){name="seat-caption",enableRichText=false}; caption.AddToClassList("mf-player-name"); Add(caption);
            state=new Label(){enableRichText=false}; state.AddToClassList("mf-player-state"); Add(state);
            commanderDamage=new VisualElement{name="player-commander-damage",pickingMode=PickingMode.Ignore};commanderDamage.style.position=Position.Absolute;commanderDamage.style.top=82;commanderDamage.style.left=4;commanderDamage.style.right=4;commanderDamage.style.display=DisplayStyle.None;Add(commanderDamage);
            RegisterCallback<ClickEvent>(Clicked); RegisterCallback<NavigationSubmitEvent>(Submitted);
            RegisterCallback<DetachFromPanelEvent>(Detached);
        }
        private void Clicked(ClickEvent e) { if(e.button==0) Activate(); }
        private void Submitted(NavigationSubmitEvent e) { Activate(); e.StopPropagation(); }
        private void Detached(DetachFromPanelEvent e) { if(e.target==this) StopPulse(); }
        public void Activate() { if(!disposed && targetable && PlayerId!=null) Activated?.Invoke(PlayerId); }
        public void Bind(string playerId, string displayName)
        {
            if(disposed) return;
            if(PlayerId!=playerId) ClearBinding();
            PlayerId=playerId; caption.text=displayName ?? "Player";
        }
        public void Present(long? total, bool priority, bool canTarget, bool reducedMotion, bool active=false)
        {
            if(disposed || PlayerId==null) return;
            bool changed=lastLife.HasValue && total.HasValue && lastLife!=total;
            if(changed || reducedMotion)StopPulse(); life.text=total?.ToString() ?? "?"; lastLife=total;
            targetable=canTarget; EnableInClassList("targetable",canTarget); EnableInClassList("has-priority",priority);
            EnableInClassList("is-active",active);
            state.text=canTarget ? "Choose target" : priority ? "Priority" : active ? "Active" : "";
            tooltip=caption.text+" | Life "+life.text+(state.text.Length>0?" | "+state.text:"");
            if(changed && !reducedMotion) { life.AddToClassList("life-changed"); pulse=life.schedule.Execute(StopPulse).StartingIn(400); }
        }
        public void PresentCommanderDamage(ProjectedDecisionFrame frame,bool show){
            commanderDamage.Clear();commanderDamage.style.display=show?DisplayStyle.Flex:DisplayStyle.None;SummaryHeight=78;
            if(show){
                var heading=new Label("Commander damage received"){enableRichText=false,pickingMode=PickingMode.Ignore};heading.style.fontSize=10;heading.style.height=28;heading.style.flexShrink=0;heading.style.whiteSpace=WhiteSpace.Normal;heading.style.color=new Color(.78f,.84f,.9f);commanderDamage.Add(heading);
                var commanders=frame.Commanders;
                if(commanders==null || commanders.Count==0){var missing=new Label("Unavailable"){enableRichText=false};missing.style.fontSize=11;commanderDamage.Add(missing);SummaryHeight=130;}
                else{foreach(var commander in commanders){long damage=0;bool known=commander.DamageDealt!=null && commander.DamageDealt.TryGetValue(PlayerId,out damage);
                    var row=new Label((known?damage.ToString():"?")+" / 21 — "+commander.Name){name="life-commander-"+commander.CommanderId,enableRichText=false,pickingMode=PickingMode.Ignore,tooltip=commander.Name+" — combat damage received by "+caption.text};row.style.fontSize=11;row.style.whiteSpace=WhiteSpace.Normal;row.style.height=44;row.style.minHeight=44;row.style.maxHeight=44;row.style.flexShrink=0;row.style.overflow=Overflow.Hidden;row.style.color=known && damage>=21?new Color(1,.55f,.4f):Color.white;commanderDamage.Add(row);
                }SummaryHeight=118+commanders.Count*44;}
            }
            style.height=SummaryHeight;
        }
        private void StopPulse() { pulse?.Pause(); pulse=null; life.RemoveFromClassList("life-changed"); }
        public void SetTargetable(bool value)
        {
            if(disposed || PlayerId==null)return;
            targetable=value;EnableInClassList("targetable",value);
            state.text=value?"Choose target":ClassListContains("has-priority")?"Priority":ClassListContains("is-active")?"Active":"";
        }
        public void ClearBinding()
        {
            StopPulse();commanderDamage.Clear();commanderDamage.style.display=DisplayStyle.None;SummaryHeight=78;style.height=78; PlayerId=null; lastLife=null; targetable=false; life.text="?"; caption.text=""; state.text=""; tooltip="";
            RemoveFromClassList("is-active"); RemoveFromClassList("has-priority"); RemoveFromClassList("targetable"); Blur();
        }
        public void Dispose()
        {
            if(disposed)return; ClearBinding(); disposed=true; Activated=null;
            UnregisterCallback<ClickEvent>(Clicked); UnregisterCallback<NavigationSubmitEvent>(Submitted); UnregisterCallback<DetachFromPanelEvent>(Detached);
        }
    }
}

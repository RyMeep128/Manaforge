using System;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Explicit seat identity; never searches a frame for an opponent.
    public sealed class PlayerPanel : Label, IDisposable
    {
        private readonly Label life, caption, state;
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
        public void Present(long? total, bool priority, bool canTarget, bool reducedMotion)
        {
            if(disposed || PlayerId==null) return;
            bool changed=lastLife.HasValue && total.HasValue && lastLife!=total;
            StopPulse(); life.text=total?.ToString() ?? "?"; lastLife=total;
            targetable=canTarget; EnableInClassList("targetable",canTarget); EnableInClassList("has-priority",priority);
            state.text=canTarget ? "Choose target" : priority ? "Priority" : "";
            tooltip=caption.text+" | Life "+life.text+(state.text.Length>0?" | "+state.text:"");
            if(changed && !reducedMotion) { life.AddToClassList("life-changed"); pulse=life.schedule.Execute(StopPulse).StartingIn(400); }
        }
        private void StopPulse() { pulse?.Pause(); pulse=null; life.RemoveFromClassList("life-changed"); }
        public void SetTargetable(bool value)
        {
            if(disposed || PlayerId==null)return;
            targetable=value;EnableInClassList("targetable",value);
            state.text=value?"Choose target":ClassListContains("has-priority")?"Priority":"";
        }
        public void ClearBinding()
        {
            StopPulse(); PlayerId=null; lastLife=null; targetable=false; life.text="?"; caption.text=""; state.text=""; tooltip="";
            RemoveFromClassList("has-priority"); RemoveFromClassList("targetable"); Blur();
        }
        public void Dispose()
        {
            if(disposed)return; ClearBinding(); disposed=true; Activated=null;
            UnregisterCallback<ClickEvent>(Clicked); UnregisterCallback<NavigationSubmitEvent>(Submitted); UnregisterCallback<DetachFromPanelEvent>(Detached);
        }
    }
}

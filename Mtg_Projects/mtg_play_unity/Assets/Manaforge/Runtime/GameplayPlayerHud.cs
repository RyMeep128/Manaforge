using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Composes the existing independent player and Commander views. No rules/state store.
    public sealed class GameplayPlayerHud : VisualElement, IDisposable
    {
        private readonly ScrollView players=new ScrollView(ScrollViewMode.Vertical){name="hud-players"};
        private readonly ScrollView commanders=new ScrollView(ScrollViewMode.Vertical){name="hud-commanders"};
        private readonly Dictionary<string,PlayerPanel> seats=new Dictionary<string,PlayerPanel>(StringComparer.Ordinal);
        private readonly Dictionary<string,CommanderDashboard> commanderViews=new Dictionary<string,CommanderDashboard>(StringComparer.Ordinal);
        private string session,viewer,format;private long revision=-1;private int artwork=-1;
        private bool disposed;
        public event Action<string> PlayerActivated;
        public IEnumerable<PlayerPanel> Players=>seats.Values;
        public PlayerPanel Player(string id)=>id!=null && seats.TryGetValue(id,out var panel)?panel:null;
        public static bool HasCommanderContent(string format)=>format=="commander" || format=="unrestricted_commander";
        public GameplayPlayerHud(){name="gameplay-player-hud";AddToClassList("mf-player-hud");pickingMode=PickingMode.Ignore;GameplayTheme.Attach(this);players.AddToClassList("mf-hud-players");players.contentContainer.style.flexDirection=FlexDirection.Row;players.contentContainer.style.flexWrap=Wrap.Wrap;commanders.AddToClassList("mf-hud-commanders");Add(players);Add(commanders);}
        private void Activate(string id){PlayerActivated?.Invoke(id);}
        public void Present(ProjectedDecisionFrame frame,ViewerCardSurface surface,string activeFormat,bool reducedMotion=false,Action<string> inspect=null)
        {
            if(disposed || frame==null)return;
            if(session!=frame.Context.SessionId || viewer!=frame.Context.ViewerId){ClearPresentation();session=frame.Context.SessionId;viewer=frame.Context.ViewerId;}
            bool rebuild=revision!=frame.Context.Revision || format!=activeFormat || artwork!=surface.PresentedArtworkCount;
            revision=frame.Context.Revision;format=activeFormat;artwork=surface.PresentedArtworkCount;
            foreach(string id in seats.Keys.Where(id=>!frame.PlayerLifeTotals.ContainsKey(id)).ToArray()){seats[id].Activated-=Activate;seats[id].Dispose();seats[id].RemoveFromHierarchy();seats.Remove(id);commanderViews[id].Dispose();commanderViews.Remove(id);}
            foreach(string id in frame.PlayerLifeTotals.Keys.OrderBy(id=>id==viewer?1:0)) {
                if(!seats.TryGetValue(id,out var panel)) {
                    panel=new PlayerPanel();panel.AddToClassList("mf-hud-player");panel.Activated+=Activate;seats.Add(id,panel);players.Add(panel);
                    var commander=new CommanderDashboard(false);commander.name="commander-info-"+id;commander.AddToClassList("mf-hud-commander-info");commanderViews.Add(id,commander);commanders.Add(commander);rebuild=true;
                }
                panel.name=id==viewer?"local-seat":frame.PlayerLifeTotals.Count==2?"opponent-seat":"player-seat-"+id;
                panel.Bind(id,frame.PlayerNames.TryGetValue(id,out var name)?name:"Player");panel.Present(frame.PlayerLifeTotals[id],frame.PriorityPlayerId==id,false,reducedMotion,frame.ActivePlayerId==id);
                if(rebuild){if(HasCommanderContent(activeFormat))commanderViews[id].Present(frame,surface,inspect,id);else commanderViews[id].ClearPresentation();}
            }
            commanders.style.display=HasCommanderContent(activeFormat)?DisplayStyle.Flex:DisplayStyle.None;
        }
        public void SetTargetable(Func<string,bool> available){foreach(var pair in seats)pair.Value.SetTargetable(available?.Invoke(pair.Key)==true);}
        public void ClearPresentation(){foreach(var seat in seats.Values){seat.Activated-=Activate;seat.Dispose();}seats.Clear();foreach(var view in commanderViews.Values)view.Dispose();commanderViews.Clear();players.Clear();commanders.Clear();session=viewer=format=null;revision=-1;artwork=-1;}
        public void Dispose(){if(disposed)return;ClearPresentation();disposed=true;PlayerActivated=null;RemoveFromHierarchy();}
    }
}

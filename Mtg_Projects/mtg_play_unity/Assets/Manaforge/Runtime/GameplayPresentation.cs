using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Layouts consume the same immutable frame and session controls for every format.
    // Session startup, transport, rules and lifetime belong to LiveGameScene/ViewerSessionHost.
    public interface IGameplayPresentation : IDisposable
    {
        ViewerCardSurface Surface {get;}
        ViewerDecisionPanel Decisions {get;}
        void Bind(ViewerSessionHost host);
        void Present(ProjectedDecisionFrame frame);
    }

    public sealed class TableGameplayPresentation : IGameplayPresentation
    {
        private readonly VisualElement root,choices;
        private readonly Label status;private readonly GameplayPlayerHud hud;private ViewerSessionHost session;
        public ViewerCardSurface Surface {get;}
        public ViewerDecisionPanel Decisions {get;private set;}
        public TableGameplayPresentation(VisualElement parent)
        {
            root=new VisualElement();root.style.flexGrow=1;parent.Add(root);
            status=new Label("Connecting to game…"){enableRichText=false};status.style.color=Color.white;status.style.fontSize=20;root.Add(status);
            hud=new GameplayPlayerHud();hud.style.maxHeight=240;root.Add(hud);hud.PlayerActivated+=ActivatePlayer;
            var stage=new VisualElement();stage.style.flexDirection=FlexDirection.Row;stage.style.flexGrow=1;root.Add(stage);
            Surface=new ViewerCardSurface(stage);Surface.CardsRoot.style.width=720;Surface.CardsRoot.style.flexShrink=0;Surface.InspectionView.SetPresentation(CardPresentationMode.Full,210);Surface.Clearing+=hud.ClearPresentation;
            choices=new VisualElement();choices.style.width=300;stage.Add(choices);
        }
        public void Bind(ViewerSessionHost host)
        {if(Decisions!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_BOUND");session=host;Decisions=new ViewerDecisionPanel(choices,host);}
        public void Present(ProjectedDecisionFrame frame)
        {
            string life=string.Join("  ",frame.PlayerLifeTotals.Select(seat=>(seat.Key==frame.Context.ViewerId?"You":"Opponent")+": "+seat.Value));
            status.text=frame.UnsupportedFields.Contains("decision")?"This choice cannot be displayed. Report code: "+(frame.DecisionError??"DECISION_UNSUPPORTED"):frame.Result!=null?"Result: "+frame.Result:life+"  Turn "+frame.Turn+" — "+frame.Phase;
            if(frame.SessionNotice!=null)status.text+="\nA permission request could not be displayed. Code: "+frame.SessionNotice;
            hud.Present(frame,Surface,session?.GameplayFormat);hud.SetTargetable(id=>session?.PresentedDecision?.CanSubmit==true && frame.Decision?.Options.Any(option=>option.PlayerId==id)==true);
            foreach(var child in Surface.CardsRoot.Children())if(child is CardView card)card.SetPresentation(CardPresentationMode.Compact,130);
        }
        private void ActivatePlayer(string id){Decisions?.TryActivatePlayer(session?.PresentedDecision,id);}
        public void Dispose(){Decisions?.Dispose();hud.PlayerActivated-=ActivatePlayer;Surface.Clearing-=hud.ClearPresentation;hud.Dispose();Surface.Dispose();root.RemoveFromHierarchy();}
    }
}

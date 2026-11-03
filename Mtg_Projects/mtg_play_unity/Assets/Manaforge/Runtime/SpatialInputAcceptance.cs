using System;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Explicit public-deck acceptance only. Route the existing driver's selected button
    // through the actual card keyboard input when it represents one unambiguous offer.
    internal sealed class SpatialInputAcceptance : IDisposable
    {
        private readonly ViewerDecisionPanel panel;private readonly ViewerCardSurface surface;private readonly ViewerSessionHost host;
        public int Inputs {get;private set;}
        public SpatialInputAcceptance(ViewerDecisionPanel panel,ViewerCardSurface surface,ViewerSessionHost host)
        {this.panel=panel;this.surface=surface;this.host=host;panel.Root.RegisterCallback<NavigationSubmitEvent>(Route,TrickleDown.TrickleDown);}
        private void Route(NavigationSubmitEvent ev)
        {
            if(!(ev.target is Button button))return;var offer=host.PresentedDecision;var frame=offer?.Frame;if(offer?.CanSubmit!=true || frame==null)return;
            string id=null;int index;
            if(button.name.StartsWith("decision-action-") && int.TryParse(button.name.Substring(16),out index) && index>=0 && index<frame.Actions.Count)id=frame.Actions[index].ObjectId;
            if(button.name.StartsWith("decision-option-") && int.TryParse(button.name.Substring(16),out index) && index>=0 && index<frame.Decision.Options.Count)id=frame.Decision.Options[index].ObjectId;
            if(id==null || panel.ObjectChoiceCount(offer,id)!=1)return;CardView selected=null;
            surface.VisitPresented((card,view)=>{if(card.ObjectId==id && !card.Hidden && view.resolvedStyle.display!=DisplayStyle.None && view.ClassListContains("actionable"))selected=view;});
            if(selected==null)return;ev.StopImmediatePropagation();Inputs++;
            using(var submit=NavigationSubmitEvent.GetPooled()){submit.target=selected;selected.SendEvent(submit);}
        }
        public void Dispose(){panel.Root.UnregisterCallback<NavigationSubmitEvent>(Route,TrickleDown.TrickleDown);}
    }
}

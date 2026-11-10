using System;
using System.Linq;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
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

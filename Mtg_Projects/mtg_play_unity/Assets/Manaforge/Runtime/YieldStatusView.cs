using System;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Passive reusable view. Text/actions are supplied; geometry and transitions use the theme.
    public sealed class YieldStatusView : IDisposable
    {
        public VisualElement Root {get;}=new VisualElement{name="yield-status"};
        private readonly Label text=new Label{name="yield-status-text",enableRichText=false};
        private readonly Button cancel;
        private bool visible;
        public YieldStatusView(VisualElement parent,Action cancelAction)
        {
            Root.AddToClassList("mf-yield-status");cancel=new Button(cancelAction){name="yield-status-cancel"};
            Root.Add(text);Root.Add(cancel);parent.Add(Root);Root.style.display=DisplayStyle.None;
        }
        public void Bind(YieldPresentation state)
        {
            text.text=state.Text;cancel.text=state.CancelLabel;
            if(visible==state.Compact)return;visible=state.Compact;
            Root.style.display=visible?DisplayStyle.Flex:DisplayStyle.None;
            Root.RemoveFromClassList("mf-yield-visible");
            if(visible)Root.schedule.Execute(()=>{if(visible)Root.AddToClassList("mf-yield-visible");});
        }
        public void Dispose(){visible=false;Root.RemoveFromHierarchy();}
    }
}

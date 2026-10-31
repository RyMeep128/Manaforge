using System;
using System.Collections.Generic;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // UI-only input binding. Addressable cards are not advertised as legally usable mana sources.
    internal sealed class ViewerManaSourceInput : IDisposable
    {
        private readonly ViewerSessionHost host;private readonly Action<ViewerDecisionOffer,ProjectedManaSource> choose;
        private readonly List<Binding> bindings=new List<Binding>();private ViewerDecisionOffer offer;private bool enabled,disposed;
        private sealed class Binding : IDisposable
        {
            private readonly CardView view;private readonly bool focusable;private readonly string tooltip;
            private readonly Action activate;
            internal Binding(CardView view,Action activate)
            {
                this.view=view;this.activate=activate;focusable=view.focusable;tooltip=view.tooltip;
                view.RegisterCallback<ClickEvent>(Click);view.RegisterCallback<NavigationSubmitEvent>(Submit);
            }
            private void Click(ClickEvent input)
            {
                if(input.button!=0)return;
                // Embedded inspection controls retain their own meaning.
                for(var target=input.target as VisualElement;target!=null && target!=view;target=target.parent)
                    if(target is Button || target is TextField || target is Toggle)return;
                activate();
            }
            private void Submit(NavigationSubmitEvent input){if(ReferenceEquals(input.target,view))activate();}
            internal void SetEnabled(bool value){view.focusable=value || focusable;view.tooltip=value?"Choose this card as a mana source":"Waiting for the current decision";}
            public void Dispose(){view.UnregisterCallback<ClickEvent>(Click);view.UnregisterCallback<NavigationSubmitEvent>(Submit);view.focusable=focusable;view.tooltip=tooltip;}
        }
        internal ViewerManaSourceInput(ViewerSessionHost host,Action<ViewerDecisionOffer,ProjectedManaSource> choose){this.host=host;this.choose=choose;}
        internal void Refresh(ViewerDecisionOffer supplied)
        {
            if(disposed || ReferenceEquals(offer,supplied))return;Clear();offer=supplied;var frame=supplied?.Frame;
            if(frame?.Decision.Family!="mana")return;
            foreach(var source in frame.ManaSourceReferences) {
                var view=host.ManaSourceView(supplied,source);if(view==null)continue;
                bindings.Add(new Binding(view,()=>{
                    if(!disposed && enabled && ReferenceEquals(offer,supplied) && ReferenceEquals(host.PresentedDecision,supplied) && supplied.CanSubmit)choose(supplied,source);
                }));
            }
        }
        internal void SetEnabled(bool value){if(disposed || enabled==value)return;enabled=value;foreach(var binding in bindings)binding.SetEnabled(value);}
        private void Clear(){foreach(var binding in bindings)binding.Dispose();bindings.Clear();offer=null;enabled=false;}
        public void Dispose(){if(disposed)return;disposed=true;Clear();}
    }
}

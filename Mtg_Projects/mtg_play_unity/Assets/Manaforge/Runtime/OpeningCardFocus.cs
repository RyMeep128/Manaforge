using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Pure presentation: never inspects engine objects or submits a command.
    public sealed class OpeningCardFocus : IDisposable
    {
        private readonly VisualElement root;
        private readonly List<CardView> cards;
        private readonly List<Action> unregister=new List<Action>();
        private CardView active,hovered,focused;private bool disposed;
        public OpeningCardFocus(VisualElement root)
        {
            this.root=root;cards=root.Query<CardView>().ToList();
            foreach(var card in cards){
                bool wasFocusable=card.focusable;card.focusable=true;
                EventCallback<PointerEnterEvent> enter=ev=>{hovered=card;Show(hovered);};
                EventCallback<PointerLeaveEvent> leave=ev=>{if(hovered==card)hovered=null;Show(hovered??focused);};
                EventCallback<FocusInEvent> focus=ev=>{focused=card;Show(hovered??focused);};
                EventCallback<FocusOutEvent> blur=ev=>{if(focused==card)focused=null;Show(hovered??focused);};
                card.RegisterCallback(enter);card.RegisterCallback(leave);card.RegisterCallback(focus);card.RegisterCallback(blur);
                unregister.Add(()=>{card.UnregisterCallback(enter);card.UnregisterCallback(leave);card.UnregisterCallback(focus);card.UnregisterCallback(blur);card.focusable=wasFocusable;});
            }
        }
        public void Show(CardView card)
        {
            if(disposed || card!=null && (!cards.Contains(card) || card.parent!=root))return;
            if(active!=null){active.style.scale=new Scale(Vector3.one);active.style.translate=new Translate(0,0);}
            active=null;
            root.Sort((a,b)=>cards.IndexOf(a as CardView).CompareTo(cards.IndexOf(b as CardView)));
            if(card==null)return;
            var bounds=card.worldBound;var viewport=root.worldBound;float offset=0;
            if(bounds.width>0 && viewport.width>bounds.width*1.12f){
                float left=bounds.center.x-bounds.width*.56f,right=bounds.center.x+bounds.width*.56f;
                offset=Mathf.Clamp(0,viewport.xMin-left,viewport.xMax-right);
            }
            active=card;card.BringToFront();card.style.scale=new Scale(new Vector3(1.12f,1.12f,1));card.style.translate=new Translate(offset,-18);
        }
        public void Dispose()
        {
            if(disposed)return;Show(null);hovered=focused=null;disposed=true;foreach(var remove in unregister)remove();unregister.Clear();cards.Clear();
        }
    }
}

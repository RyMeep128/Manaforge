using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Geometry and paging of admitted views. Caller supplies space and identity-keyed page state.
    public static class GameplayCardLayout
    {
        public static void Row(System.Collections.Generic.List<(ProjectedCard card,CardView view)> row,VisualElement navigation,System.Collections.Generic.Dictionary<string,int> rowPages,Action relayout,float width,float top,float left,float span,float size,bool full=false,string key=null,Vector2? reservedInterval=null){
                if(row.Count==0)return;
                bool reserveSeat=reservedInterval.HasValue;float gapStart=reservedInterval?.x??left,gapEnd=reservedInterval?.y??left;
                int leftSlots=Mathf.Max(1,Mathf.FloorToInt((gapStart-left)/(size+18))),rightSlots=Mathf.Max(1,Mathf.FloorToInt((left+span-gapEnd)/(size+18)));
                if(key!=null){
                    int capacity=reserveSeat?leftSlots+rightSlots:Mathf.Max(1,Mathf.FloorToInt(span/(size+18))),last=(row.Count-1)/capacity;
                    int page=rowPages.TryGetValue(key,out var requested)?Mathf.Clamp(requested,0,last):0;rowPages[key]=page;
                    if(last>0){
                        var nav=new VisualElement();nav.AddToClassList("row-navigation");nav.style.left=Mathf.Min(width-120,left+span+8);nav.style.top=top;navigation.Add(nav);
                        var previous=new Button(()=>{rowPages[key]=Mathf.Max(0,page-1);relayout();}){text="‹",name=key+"-previous"};previous.SetEnabled(page>0);nav.Add(previous);
                        nav.Add(new Label((page+1)+" / "+(last+1)){enableRichText=false});
                        var next=new Button(()=>{rowPages[key]=Mathf.Min(last,page+1);relayout();}){text="›",name=key+"-next"};next.SetEnabled(page<last);nav.Add(next);
                    }
                    row=row.Skip(page*capacity).Take(capacity).ToList();
                }
                float step=Mathf.Min(size+18,(span-size)/Mathf.Max(1,row.Count-1));
                float start=left+(span-size-step*(row.Count-1))*.5f;
                for(int i=0;i<row.Count;i++){var v=row[i].view;v.style.display=DisplayStyle.Flex;v.SetPresentation(full?CardPresentationMode.Full:CardPresentationMode.Compact,size);v.style.left=reserveSeat?(i<leftSlots?gapStart-Mathf.Min(leftSlots,row.Count)*(size+18)+9+i*(size+18):gapEnd+9+(i-leftSlots)*(size+18)):start+i*step;v.style.top=top;v.style.rotate=new Rotate(new Angle(row[i].card.Tapped==true?90:0));}
            }

        public static void Hand(List<(ProjectedCard card,CardView view)> hand,VisualElement navigation,Dictionary<string,int> rowPages,Action relayout,Action closeInspection,Rect bounds,float navigationY,bool opening,float handWidth)
        {
            float handSpan=Mathf.Max(handWidth,bounds.width);
            // Bound overlap and retain access to every card instead of shrinking large hands to slivers.
            int handCapacity=Mathf.Max(1,Mathf.FloorToInt((handSpan-handWidth)/45)+1);
            int handLast=Mathf.Max(0,(hand.Count-1)/handCapacity),handPage=rowPages.TryGetValue("hand",out var hp)?Mathf.Clamp(hp,0,handLast):0;
            rowPages["hand"]=handPage;
            if(handLast>0){
                var nav=new VisualElement{name="hand-navigation"};nav.AddToClassList("row-navigation");nav.style.left=bounds.center.x-75;nav.style.top=navigationY;navigation.Add(nav);
                var previous=new Button(()=>{closeInspection();rowPages["hand"]=handPage-1;relayout();}){text="‹",name="hand-previous"};previous.SetEnabled(handPage>0);nav.Add(previous);
                nav.Add(new Label("Hand "+(handPage+1)+" / "+(handLast+1)));
                var next=new Button(()=>{closeInspection();rowPages["hand"]=handPage+1;relayout();}){text="›",name="hand-next"};next.SetEnabled(handPage<handLast);nav.Add(next);
            }
            hand=hand.Skip(handPage*handCapacity).Take(handCapacity).ToList();
            var placements=OpeningHandFan.Arrange(hand.Count,handSpan);
            float handStep=Mathf.Min(handWidth*.72f,(handSpan-handWidth)/Mathf.Max(1,hand.Count-1));
            for(int i=0;i<hand.Count;i++){
                hand[i].view.AddToClassList("in-hand");
                float offset=i-(hand.Count-1)*.5f,angle=offset*Mathf.Min(4,28f/Mathf.Max(1,hand.Count));var v=hand[i].view;
                v.style.display=DisplayStyle.Flex;v.SetPresentation(CardPresentationMode.Full,handWidth);
                v.style.left=opening?bounds.x+placements[i].Left+(placements[i].Width-handWidth)*.5f:bounds.center.x-handWidth*.5f+offset*handStep;
                v.style.top=opening?bounds.y+placements[i].Top:bounds.y+Mathf.Abs(offset)*3;
                v.style.rotate=new Rotate(new Angle(opening?placements[i].Angle:angle));v.BringToFront();
            }

        }
        public static void HiddenHand(VisualElement root,long? count,float span,float rotation,string owner=null,ICardBackProvider cardBacks=null)
        {
            int shown=count.HasValue?(int)Math.Min(12,Math.Max(0,count.Value)):0;
            while(root.childCount>shown){if(root[root.childCount-1] is CardBackView old)old.ClearBinding();root.RemoveAt(root.childCount-1);}
            while(root.childCount<shown){var cardBack=new CardBackView(cardBacks);cardBack.AddToClassList("opponent-hand-back");root.Add(cardBack);}
            for(int i=0;i<shown;i++){
                float offset=i-(shown-1)*.5f;
                var back=(CardBackView)root[i];back.Bind(owner);
                back.style.left=span*.5f-35+offset*24;back.style.top=Mathf.Abs(offset)*2;back.style.rotate=new Rotate(new Angle(rotation-offset*3));
            }
        }
    }
}

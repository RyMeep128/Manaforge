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
        // Persistent chrome only. Drawer state deliberately is not an input.
        // Opponents share rows until a dedicated multiplayer composition is introduced.
        public readonly struct BattlefieldGeometry
        {
            public readonly float Left, Span, CardWidth, OpponentLands, OpponentPermanents, LocalPermanents, LocalLands, HandTop;
            public BattlefieldGeometry(float width,float height)
            {
                Left=280; // compact player/Commander rail, independent of zone drawer
                Span=Mathf.Max(100,width-Left-24);
                HandTop=height-148;
                float top=78,bottom=HandTop-24;
                // Include tapped extent and the existing attachment/land fan offsets.
                CardWidth=Mathf.Clamp((bottom-top-3*24-24)/4,62,110);
                float extent=CardWidth;
                float gap=Mathf.Max(24,(bottom-top-24-4*extent)/3);
                OpponentLands=top+24;
                OpponentPermanents=top+extent+gap;
                LocalPermanents=top+2*(extent+gap);
                LocalLands=top+3*(extent+gap)+24;
            }
            public float PermanentSpan(bool activeStack)=>Mathf.Max(100,Span-(activeStack?220:0));
        }

        // Viewer-local presentation continuity. A changed opaque command reference
        // or native collection order must not reverse the player's visible hand.
        public static void RetainHandOrder(List<string> order,IEnumerable<string> current)
        {
            var present=current.ToList();var ids=new HashSet<string>(present,StringComparer.Ordinal);
            order.RemoveAll(id=>!ids.Contains(id));
            foreach(var id in present)if(!order.Contains(id))order.Add(id);
        }
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

        public static IReadOnlyDictionary<string,IReadOnlyList<ProjectedCard>> AttachmentGroups(IEnumerable<ProjectedCard> cards,IEnumerable<string> players)
        {
            var visible=cards.Where(c=>c.Zone=="battlefield" && !c.Hidden && c.FaceDown==false).ToDictionary(c=>c.ObjectId);var seats=new HashSet<string>(players);var groups=new Dictionary<string,List<ProjectedCard>>();
            foreach(var card in visible.Values.OrderBy(c=>c.RenderId,StringComparer.Ordinal)){
                if(card.AttachedTo==null)continue;string parent=card.AttachedTo;var seen=new HashSet<string>{card.ObjectId};bool valid=false;
                for(int depth=0;depth<32;depth++){
                    if(!seen.Add(parent))break;if(seats.Contains(parent)){valid=true;break;}
                    if(!visible.TryGetValue(parent,out var host))break;if(host.AttachedTo==null){valid=true;break;}parent=host.AttachedTo;
                }
                if(!valid)continue;if(!groups.TryGetValue(parent,out var group)){group=new List<ProjectedCard>();groups.Add(parent,group);}group.Add(card);
            }
            return new System.Collections.ObjectModel.ReadOnlyDictionary<string,IReadOnlyList<ProjectedCard>>(groups.ToDictionary(pair=>pair.Key,pair=>(IReadOnlyList<ProjectedCard>)pair.Value.AsReadOnly()));
        }
        public const int MaximumLandStack=2;
        public static float LandSize(int count,float maximum=110)=>Mathf.Clamp(maximum/(1+.045f*Mathf.Max(0,count-4)),62,maximum);
        private static string LandIdentity(ProjectedCard card)
        {
            var c=card.Characteristics;
            if(card.Hidden || card.FaceDown!=false || card.Zone!="battlefield" || !card.Tapped.HasValue || c==null
                || string.IsNullOrEmpty(c.Name) || c.Counters==null || c.Counters.Count!=0 || card.Attachments==null || card.Attachments.Count!=0
                || card.AttachedTo!=null || card.CommanderId!=null || c.IsCopy==true || c.Transformed==true || c.Flipped==true
                || Array.IndexOf((c.TypeLine??"").Split('—')[0].Split(' '),"Land")<0
                || Array.IndexOf((c.TypeLine??"").Split('—')[0].Split(' '),"Creature")>=0
                || c.CurrentAbilities==null && c.EngineViewText==null)return "single:"+card.RenderId;
            var fields=new[]{card.Printing?.OracleId??c.Name,c.Name,c.TypeLine,c.Color,card.ControllerId,card.OwnerId,
                card.Tapped.ToString(),c.Power,c.Toughness,card.Damage?.ToString(),
                c.CurrentAbilities==null?"view":"live",string.Join("\n",c.CurrentAbilities??c.EngineViewText)};
            return string.Concat(fields.Select(value=>(value?.Length??-1)+":"+value));
        }
        // Keep every native object/view separate; piles are geometry, never a combined action.
        public static IReadOnlyList<IReadOnlyList<ProjectedCard>> LandStacks(IEnumerable<ProjectedCard> cards)
        {
            var result=new List<IReadOnlyList<ProjectedCard>>();
            foreach(var group in cards.OrderBy(c=>c.Characteristics?.Name,StringComparer.Ordinal).ThenBy(c=>c.Tapped)
                .ThenBy(c=>c.RenderId,StringComparer.Ordinal).GroupBy(LandIdentity)){
                var same=group.ToArray();for(int i=0;i<same.Length;i+=MaximumLandStack)result.Add(Array.AsReadOnly(same.Skip(i).Take(MaximumLandStack).ToArray()));
            }return result.AsReadOnly();
        }
        public static void LandRow(List<(ProjectedCard card,CardView view)> cards,VisualElement navigation,Dictionary<string,int> pages,Action relayout,
            float width,float top,float left,float span,float maximum,string key,Vector2 reserved)
        {
            if(cards.Count==0){pages.Remove(key);return;}
            foreach(var item in cards)item.view.style.display=DisplayStyle.None;
            var stacks=LandStacks(cards.Select(item=>item.card));var views=cards.ToDictionary(item=>item.card,item=>item.view);
            float size=LandSize(cards.Count,maximum);
            float leftSpan=Mathf.Max(0,reserved.x-left),rightStart=Mathf.Max(left,reserved.y),rightSpan=Mathf.Max(0,left+span-rightStart);
            float Pitch(float value)=>value*1.15f+Mathf.Max(12,value*.14f)+18;
            while(size>62 && Mathf.FloorToInt(leftSpan/Pitch(size))+Mathf.FloorToInt(rightSpan/Pitch(size))<stacks.Count)size=Mathf.Max(62,size-2);
            float offset=Mathf.Max(12,size*.14f),pitch=Pitch(size);
            int leftSlots=Mathf.Max(0,Mathf.FloorToInt(leftSpan/pitch)),rightSlots=Mathf.Max(0,Mathf.FloorToInt(rightSpan/pitch));
            if(leftSlots+rightSlots==0){if(leftSpan>=rightSpan)leftSlots=1;else rightSlots=1;}
            int capacity=leftSlots+rightSlots,last=(stacks.Count-1)/capacity,page=pages.TryGetValue(key,out var requested)?Mathf.Clamp(requested,0,last):0;pages[key]=page;
            if(last>0){
                var nav=new VisualElement();nav.AddToClassList("row-navigation");nav.style.left=Mathf.Min(width-120,left+span+8);nav.style.top=top;navigation.Add(nav);
                var previous=new Button(()=>{pages[key]=Mathf.Max(0,page-1);relayout();}){text="‹",name=key+"-previous"};previous.SetEnabled(page>0);nav.Add(previous);
                nav.Add(new Label((page+1)+" / "+(last+1)){enableRichText=false});
                var next=new Button(()=>{pages[key]=Mathf.Min(last,page+1);relayout();}){text="›",name=key+"-next"};next.SetEnabled(page<last);nav.Add(next);
            }
            var shown=stacks.Skip(page*capacity).Take(capacity).ToArray();int onLeft=Mathf.Min(leftSlots,shown.Length),onRight=shown.Length-onLeft;
            for(int i=0;i<shown.Length;i++){
                bool first=i<onLeft;int slot=first?i:i-onLeft,slots=first?onLeft:onRight;float start=first?left:rightStart,available=first?leftSpan:rightSpan;
                float step=Mathf.Min(pitch,available/Mathf.Max(1,slots)),x=start+(available-step*slots)*.5f+slot*step+8;
                var stack=shown[i];for(int depth=0;depth<stack.Count;depth++){
                    var card=stack[depth];var view=views[card];int behind=stack.Count-depth-1;
                    view.SetPresentation(CardPresentationMode.Compact,size);view.style.left=x+behind*offset;view.style.top=top-behind*Mathf.Max(20,size*.22f);
                    view.style.rotate=new Rotate(new Angle(card.Tapped==true?90:0));view.style.display=DisplayStyle.Flex;view.BringToFront();
                }
            }
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

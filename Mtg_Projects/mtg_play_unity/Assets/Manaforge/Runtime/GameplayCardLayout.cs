using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Continuous card strips, panned directly without scrollbar chrome or pages.
    // Card instances stay surface-owned; only overflowing regions acquire a clipped parent.
    internal sealed class GameplayScrollRegions : IDisposable
    {
        private readonly VisualElement owner;private readonly Dictionary<string,ScrollView> regions=new Dictionary<string,ScrollView>();
        private readonly HashSet<string> used=new HashSet<string>();
        internal GameplayScrollRegions(VisualElement owner){this.owner=owner;}
        private Action<CardView> handLayout;
        internal VisualElement Owner=>owner;
        internal void SetHandLayout(Action<CardView> layout){handLayout=layout;}
        internal void ClearHandLayout(){handLayout=null;}
        internal void FocusHand(CardView view){handLayout?.Invoke(view);}
        internal static void HideBars(ScrollView scroll){scroll.horizontalScrollerVisibility=scroll.verticalScrollerVisibility=ScrollerVisibility.Hidden;}
        private static void DirectPan(ScrollView scroll,bool horizontal)
        {
            int pointer=-1;Vector2 origin=default,offset=default;
            scroll.tooltip="Mouse wheel or middle-drag to pan; Tab to focus individual cards";
            scroll.RegisterCallback<PointerDownEvent>(ev=>{if(ev.button!=2)return;pointer=ev.pointerId;origin=ev.position;offset=scroll.scrollOffset;scroll.CapturePointer(pointer);ev.StopImmediatePropagation();},TrickleDown.TrickleDown);
            scroll.RegisterCallback<PointerMoveEvent>(ev=>{if(pointer!=ev.pointerId || !scroll.HasPointerCapture(pointer))return;var delta=(Vector2)ev.position-origin;scroll.scrollOffset=offset-(horizontal?new Vector2(delta.x,0):new Vector2(0,delta.y));ev.StopImmediatePropagation();},TrickleDown.TrickleDown);
            scroll.RegisterCallback<PointerUpEvent>(ev=>{if(pointer!=ev.pointerId || ev.button!=2)return;scroll.ReleasePointer(pointer);pointer=-1;ev.StopImmediatePropagation();},TrickleDown.TrickleDown);
            scroll.RegisterCallback<PointerCaptureOutEvent>(ev=>{if(ev.pointerId==pointer)pointer=-1;});
            if(horizontal)scroll.RegisterCallback<WheelEvent>(ev=>{float delta=Mathf.Abs(ev.delta.x)>Mathf.Abs(ev.delta.y)?ev.delta.x:ev.delta.y;float limit=Mathf.Max(0,scroll.contentContainer.resolvedStyle.width-scroll.contentViewport.resolvedStyle.width);scroll.scrollOffset=new Vector2(Mathf.Clamp(scroll.scrollOffset.x+delta*45,0,limit),0);ev.StopImmediatePropagation();},TrickleDown.TrickleDown);
        }
        internal void Begin(){used.Clear();}
        internal VisualElement Configure(string key,Rect bounds,Vector2 content,bool horizontal=false,VisualElement foreground=null)
        {
            var destination=foreground??owner;
            if(horizontal?content.x<=bounds.width+.5f:content.y<=bounds.height+.5f)return destination;
            used.Add(key);
            if(!regions.TryGetValue(key,out var scroll)){
                scroll=new ScrollView(horizontal?ScrollViewMode.Horizontal:ScrollViewMode.Vertical){name="card-scroll-"+key,pickingMode=PickingMode.Ignore};
                scroll.contentViewport.pickingMode=scroll.contentContainer.pickingMode=PickingMode.Ignore;
                scroll.style.position=Position.Absolute;scroll.style.backgroundColor=Color.clear;scroll.contentViewport.style.overflow=Overflow.Hidden;
                HideBars(scroll);DirectPan(scroll,horizontal);scroll.mouseWheelScrollSize=45;
                regions.Add(key,scroll);owner.Add(scroll);
            }
            if(scroll.parent!=destination)destination.Add(scroll);
            scroll.style.display=DisplayStyle.Flex;scroll.style.left=bounds.x;scroll.style.top=bounds.y;scroll.style.width=bounds.width;scroll.style.height=bounds.height;
            scroll.contentContainer.style.width=content.x;scroll.contentContainer.style.height=content.y;return scroll.contentContainer;
        }
        internal static void Place(CardView view,VisualElement parent,float x,float y,Rect bounds,VisualElement owner)
        {
            if(parent!=null && view.parent!=parent)parent.Add(view);
            view.style.left=x-(parent!=null && parent!=owner?bounds.x:0);view.style.top=y-(parent!=null && parent!=owner?bounds.y:0);
        }
        internal void End(){foreach(var pair in regions)if(!used.Contains(pair.Key))pair.Value.style.display=DisplayStyle.None;}
        public void Dispose(){handLayout=null;foreach(var scroll in regions.Values){foreach(var card in scroll.contentContainer.Children().ToArray())owner.Add(card);scroll.RemoveFromHierarchy();}regions.Clear();used.Clear();}
    }
    // Geometry of admitted views. Crowded rows overlap before becoming directly pannable strips.
    public static class GameplayCardLayout
    {
        private static void Show(CardView view,ISet<CardView> visible)
        {if(visible==null)view.style.display=DisplayStyle.Flex;else visible.Add(view);}

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
        public static void Row(System.Collections.Generic.List<(ProjectedCard card,CardView view)> row,VisualElement navigation,System.Collections.Generic.Dictionary<string,int> rowPages,Action relayout,float width,float top,float left,float span,float size,bool full=false,string key=null,Vector2? reservedInterval=null)
            =>Row(row,navigation,rowPages,relayout,width,top,left,span,size,full,key,reservedInterval,null);
        internal static void Row(System.Collections.Generic.List<(ProjectedCard card,CardView view)> row,VisualElement navigation,System.Collections.Generic.Dictionary<string,int> rowPages,Action relayout,float width,float top,float left,float span,float size,bool full,string key,Vector2? reservedInterval,ISet<CardView> visible,GameplayScrollRegions scrolling=null,float viewportHeight=0) {
                if(row.Count==0)return;
                size=Mathf.Min(size,Mathf.Max(24,span));
                float extent=size*(full?1:Mathf.Max(1,BattlefieldFrame.Aspect));
                float step=Mathf.Min(size+18,Mathf.Max(size*.56f,(span-extent)/Mathf.Max(1,row.Count-1)));
                float contentSpan=Mathf.Max(span,extent+step*(row.Count-1));
                var bounds=new Rect(left,top,span,viewportHeight>0?viewportHeight:size*(full?1.4f:BattlefieldFrame.Aspect)+24);
                var parent=scrolling?.Configure(key??"row",bounds,new Vector2(contentSpan,bounds.height),true);
                float start=left+Mathf.Max(0,(span-extent-step*(row.Count-1))*.5f);
                for(int i=0;i<row.Count;i++){
                    var v=row[i].view;Show(v,visible);v.SetPresentation(full?CardPresentationMode.Full:CardPresentationMode.Compact,size);
                    GameplayScrollRegions.Place(v,parent,start+i*step,top,bounds,scrolling?.Owner);v.style.rotate=new Rotate(new Angle(row[i].card.Tapped==true?90:0));
                }
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
            =>LandRow(cards,navigation,pages,relayout,width,top,left,span,maximum,key,reserved,null);
        internal static void LandRow(List<(ProjectedCard card,CardView view)> cards,VisualElement navigation,Dictionary<string,int> pages,Action relayout,
            float width,float top,float left,float span,float maximum,string key,Vector2 reserved,ISet<CardView> visible,GameplayScrollRegions scrolling=null,float viewportHeight=0) {
            if(cards.Count==0){pages.Remove(key);return;}
            if(visible==null)foreach(var item in cards)item.view.style.display=DisplayStyle.None;
            var stacks=LandStacks(cards.Select(item=>item.card));var views=cards.ToDictionary(item=>item.card,item=>item.view);
            float size=LandSize(cards.Count,maximum);
            float offset=Mathf.Max(12,size*.14f),extent=size*1.15f+offset+18;
            var shown=stacks.ToArray();float step=Mathf.Min(extent,Mathf.Max(size*.65f,(span-extent)/Mathf.Max(1,shown.Length-1)));
            float contentSpan=Mathf.Max(span,extent+step*(shown.Length-1));
            var bounds=new Rect(left,top-24,span,viewportHeight>0?viewportHeight+24:size+offset+48);
            var parent=scrolling?.Configure(key,bounds,new Vector2(contentSpan,bounds.height),true);
            for(int i=0;i<shown.Length;i++){
                float x=left+i*step+8;
                var stack=shown[i];for(int depth=0;depth<stack.Count;depth++){
                    var card=stack[depth];var view=views[card];int behind=stack.Count-depth-1;
                    view.SetPresentation(CardPresentationMode.Compact,size);
                    GameplayScrollRegions.Place(view,parent,x+behind*offset,top-behind*Mathf.Max(20,size*.22f),bounds,scrolling?.Owner);
                    view.style.rotate=new Rotate(new Angle(card.Tapped==true?90:0));Show(view,visible);view.BringToFront();
                }
            }
        }

        public static void Hand(List<(ProjectedCard card,CardView view)> hand,VisualElement navigation,Dictionary<string,int> rowPages,Action relayout,Action closeInspection,Rect bounds,float navigationY,bool opening,float handWidth)
            =>Hand(hand,navigation,rowPages,relayout,closeInspection,bounds,navigationY,opening,handWidth,null);
        internal static void Hand(List<(ProjectedCard card,CardView view)> hand,VisualElement navigation,Dictionary<string,int> rowPages,Action relayout,Action closeInspection,Rect bounds,float navigationY,bool opening,float handWidth,ISet<CardView> visible,GameplayScrollRegions scrolling=null,CardView focusedCard=null) {
            void Arrange(CardView focused)
            {
                float span=Mathf.Max(handWidth,bounds.width),edge=handWidth*.12f;
                float available=Mathf.Max(0,span-handWidth-2*edge);
                float step=Mathf.Min(handWidth*.72f,available/Mathf.Max(1,hand.Count-1));
                float start=bounds.x+(span-handWidth-step*(hand.Count-1))*.5f;
                int focus=hand.FindIndex(item=>item.view==focused);
                var openingFan=opening?OpeningHandFan.Arrange(hand.Count,span):null;
                for(int i=0;i<hand.Count;i++){
                    var v=hand[i].view;v.AddToClassList("in-hand");Show(v,visible);v.SetPresentation(CardPresentationMode.Full,handWidth);
                    float x=opening?bounds.x+openingFan[i].Left+(openingFan[i].Width-handWidth)*.5f:start+i*step;
                    // Preserve both outer endpoints; distribute a larger gap beside the focused card.
                    if(!opening && focus>=0 && step<handWidth*.55f && hand.Count>2){
                        float anchor=start+focus*step,space=Mathf.Min(handWidth*.65f,available*.22f);
                        if(i<focus)x=Mathf.Lerp(start,Mathf.Max(start,anchor-space),(float)i/Mathf.Max(1,focus-1));
                        else if(i>focus)x=Mathf.Lerp(Mathf.Min(start+available,anchor+space),start+available,(float)(i-focus-1)/Mathf.Max(1,hand.Count-focus-2));
                    }
                    float ratio=hand.Count<=1?0:(x-(bounds.x+span*.5f-handWidth*.5f))/Mathf.Max(1,available*.5f);
                    float angle=opening?openingFan[i].Angle:ratio*Mathf.Min(14,(hand.Count-1)*2);
                    float y=bounds.y+(opening?openingFan[i].Top:Mathf.Abs(ratio)*Mathf.Min(18,(hand.Count-1)*1.5f));
                    GameplayScrollRegions.Place(v,scrolling?.Owner,x,y,bounds,scrolling?.Owner);
                    v.style.rotate=new Rotate(new Angle(angle));v.BringToFront();
                }
                focused?.BringToFront();
            }
            scrolling?.SetHandLayout(Arrange);Arrange(focusedCard);

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

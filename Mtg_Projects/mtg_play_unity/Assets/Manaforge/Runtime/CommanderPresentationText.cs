using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Optional shared formatting; alternative presentations can render the immutable data directly.
    public static class CommanderPresentationText
    {
        public static string Format(ProjectedDecisionFrame frame)
        {
            if(frame.Commanders==null)return "";
            return string.Join("\n",frame.Commanders.Select(commander=>
                (commander.OwnerId==frame.Context.ViewerId?"Your ":"Opponent’s ")+commander.Name+
                " · "+(commander.Zone??"location not visible")+
                " · command casts "+(commander.CommandZonePlays?.ToString()??"unknown")+
                " · additional command-zone cost "+(commander.AdditionalCastCost==null?"unknown":commander.AdditionalCastCost.Length==0?"none":commander.AdditionalCastCost)+
                " · damage "+(commander.DamageDealt==null?"unknown":string.Join(", ",commander.DamageDealt.Select(pair=>(pair.Key==frame.Context.ViewerId?"you ":"opponent ")+pair.Value)))));
        }
    }
    // Public commander information only; previews borrow the surface's artwork.
    public sealed class CommanderDashboard : VisualElement, IDisposable
    {
        private readonly VisualElement rows;
        private readonly List<CardView> previews=new List<CardView>();
        public CommanderDashboard(bool scroll=true)
        {
            rows=scroll?(VisualElement)new ScrollView(ScrollViewMode.Vertical):new VisualElement();
            name="game-commanders";style.display=DisplayStyle.None;rows.style.flexGrow=1;Add(rows);
        }
        private static Label Text(string text,string tooltip=null)
        {
            var label=new Label(text){enableRichText=false,tooltip=tooltip};label.style.color=Color.white;label.style.fontSize=12;return label;
        }
        public void ClearPresentation(){foreach(var preview in previews)preview.Dispose();previews.Clear();rows.Clear();style.display=DisplayStyle.None;}
        public void Present(ProjectedDecisionFrame frame,ViewerCardSurface surface,Action<string> inspect=null,string ownerId=null)
        {
            ClearPresentation();if(frame?.Commanders==null || frame.Commanders.Count==0)return;style.display=DisplayStyle.Flex;
            foreach(string owner in frame.PlayerLifeTotals.Keys.Where(id=>ownerId==null || id==ownerId)){
                var group=frame.Commanders.Where(c=>c.OwnerId==owner).ToArray();if(group.Length==0)continue;
                var heading=Text(frame.PlayerNames.TryGetValue(owner,out var ownerName)?ownerName:"Player");heading.style.unityFontStyleAndWeight=FontStyle.Bold;rows.Add(heading);
                foreach(var commander in group){
                    var tile=new VisualElement{name="commander-tile",tooltip=commander.Name};tile.style.flexDirection=FlexDirection.Row;tile.style.flexShrink=0;tile.style.minHeight=68;tile.style.marginBottom=5;tile.style.paddingTop=3;tile.style.paddingBottom=3;tile.style.paddingLeft=3;tile.style.paddingRight=3;tile.style.backgroundColor=new Color(.07f,.10f,.13f,.94f);tile.style.borderTopLeftRadius=tile.style.borderTopRightRadius=tile.style.borderBottomLeftRadius=tile.style.borderBottomRightRadius=6;
                    var preview=commander.ObjectId==null?null:surface.ChoicePreview(commander.ObjectId);
                    if(preview!=null){preview.SetPresentation(CardPresentationMode.Compact,42);preview.style.flexShrink=0;previews.Add(preview);tile.Add(preview);string id=commander.ObjectId;preview.focusable=true;preview.tooltip=commander.Name;preview.RegisterCallback<PointerDownEvent>(ev=>{if(ev.button==0 || ev.button==1){inspect?.Invoke(id);ev.StopPropagation();}});preview.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Return || ev.keyCode==KeyCode.Space){inspect?.Invoke(id);ev.StopPropagation();}});}
                    var details=new VisualElement();details.style.flexGrow=1;details.style.minWidth=0;details.style.marginLeft=5;tile.Add(details);
                    var title=Text(commander.Name);title.style.overflow=Overflow.Hidden;title.style.textOverflow=TextOverflow.Ellipsis;title.style.whiteSpace=WhiteSpace.NoWrap;details.Add(title);
                    var badges=new VisualElement();badges.style.flexDirection=FlexDirection.Row;badges.style.alignItems=Align.Center;details.Add(badges);
                    var tax=new ManaCostView{name="commander-tax",tooltip="Additional commander cost"};tax.style.position=Position.Relative;tax.SetCost(commander.AdditionalCastCost==null?null:commander.AdditionalCastCost.Length==0?"{0}":commander.AdditionalCastCost);tax.Resize(17);badges.Add(tax);
                    badges.Add(Text(" ×"+(commander.CommandZonePlays?.ToString()??"?"),"Casts from the command zone"));
                    var zone=Text((commander.Zone??"—").ToUpperInvariant(),"Current zone");zone.style.fontSize=9;zone.style.marginLeft=5;badges.Add(zone);
                    var damage=new VisualElement{name="commander-damage"};damage.style.flexDirection=FlexDirection.Row;damage.style.flexWrap=Wrap.Wrap;details.Add(damage);
                    foreach(var seat in frame.PlayerLifeTotals.Keys){long dealt=0;bool known=commander.DamageDealt!=null && commander.DamageDealt.TryGetValue(seat,out dealt);var meter=new ProgressBar{lowValue=0,highValue=21,value=known?Mathf.Min(dealt,21):0,title=(frame.PlayerNames.TryGetValue(seat,out var seatName)?seatName+" ":"Player ")+(known?dealt.ToString():"?")+"/21",tooltip="Commander combat damage"};meter.style.width=72;meter.style.height=17;meter.style.marginRight=3;damage.Add(meter);}
                    rows.Add(tile);
                }
            }
        }
        public void Dispose(){ClearPresentation();RemoveFromHierarchy();}
    }
}

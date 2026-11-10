using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Only composes admitted piles. Browsing remains the owning view's ZoneBrowser.
    public sealed class GameplayZonePanel : VisualElement, IDisposable
    {
        private readonly Dictionary<string,ZonePile[]> seats=new Dictionary<string,ZonePile[]>(StringComparer.Ordinal);
        private readonly ICardBackProvider backs;private string session,viewer;
        public event Action<string,string> BrowseRequested;
        public GameplayZonePanel(ICardBackProvider backs=null){this.backs=backs;name="gameplay-zone-panel";AddToClassList("mf-zone-panel");GameplayTheme.Attach(this);pickingMode=PickingMode.Ignore;}
        public ZonePile Pile(string owner,string zone)=>owner!=null && seats.TryGetValue(owner,out var piles)?piles.FirstOrDefault(p=>p.Zone==zone):null;
        private void Browse(string zone,string owner){BrowseRequested?.Invoke(zone,owner);}
        public void Present(ProjectedDecisionFrame frame,ViewerCardSurface surface,float bankSeparation,string openZone=null,string openOwner=null)
        {
            if(session!=frame.Context.SessionId || viewer!=frame.Context.ViewerId){ClearBinding();session=frame.Context.SessionId;viewer=frame.Context.ViewerId;}
            foreach(string old in seats.Keys.Where(id=>!frame.PlayerLifeTotals.ContainsKey(id)).ToArray()){foreach(var pile in seats[old]){pile.Dispose();pile.RemoveFromHierarchy();}seats.Remove(old);}
            var cards=new List<(ProjectedCard card,CardView view)>();surface.VisitPresented((card,view)=>cards.Add((card,view)));
            var ids=frame.PlayerLifeTotals.Keys.OrderBy(id=>id==viewer?1:0).ToArray();
            for(int seat=0;seat<ids.Length;seat++){
                string owner=ids[seat];
                if(!seats.TryGetValue(owner,out var piles)){
                    piles=new[]{"library","graveyard","exile"}.Select(zone=>new ZonePile(zone,backs)).ToArray();seats.Add(owner,piles);
                    foreach(var pile in piles){pile.Bind(owner);pile.BrowseRequested+=Browse;Add(pile);pile.style.position=Position.Absolute;pile.style.width=66;pile.style.height=92;}
                }
                for(int index=0;index<piles.Length;index++){
                    var pile=piles[index];string zone=pile.Zone;pile.name=(owner==viewer?"local-":ids.Length==2?"opponent-":owner+"-")+zone;
                    pile.style.left=6+76*index;pile.style.top=ids.Length==2?(owner==viewer?bankSeparation:0):seat*126;
                    var admitted=cards.Where(item=>item.card.Zone==zone && item.card.OwnerId==owner).ToArray();
                    var visible=admitted.Where(item=>!item.card.Hidden && item.card.FaceDown!=true).ToArray();int concealed=admitted.Length-visible.Length;
                    long? count=zone=="library"?(frame.PlayerLibraryCounts.TryGetValue(owner,out var library)?library:null):admitted.Length;
                    var preview=zone=="library"?null:visible.FirstOrDefault(item=>item.view.Artwork!=null).view;
                    pile.Present(count,preview?.Artwork,visible.FirstOrDefault().card?.Characteristics?.Name,zone==openZone && owner==openOwner,concealed>0 && visible.Length==0);
                    string player=frame.PlayerNames.TryGetValue(owner,out var playerName)?playerName:"Player";pile.tooltip=player+" | "+pile.tooltip;
                    pile.Q<Label>("zone-caption").text=ids.Length>2?player+" · "+ZonePile.Title(zone):ZonePile.Title(zone);
                }
            }
            style.height=ids.Length==2?bankSeparation+118:ids.Length*126;
        }
        public void ClearArtwork(){foreach(var pile in seats.Values.SelectMany(p=>p))pile.ClearArtwork();}
        public void ClearBinding(){foreach(var pile in seats.Values.SelectMany(p=>p)){pile.BrowseRequested-=Browse;pile.Dispose();}seats.Clear();Clear();session=viewer=null;}
        public void Dispose(){ClearBinding();BrowseRequested=null;RemoveFromHierarchy();}
    }
}

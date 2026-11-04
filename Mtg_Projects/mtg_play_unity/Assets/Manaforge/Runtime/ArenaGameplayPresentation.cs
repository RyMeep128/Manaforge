using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class ArenaGameplayPresentation : IGameplayPresentation
    {
        private readonly VisualElement root,choices,navigation,opponentHand,zoneChoices,zoneDrawer;
        private readonly Label zoneTitle,zoneSummary,stackTitle;private readonly VisualElement zoneTabs,unknownLibrary;
        private readonly Label localGraveyard,opponentGraveyard,localExile,opponentExile;private string openZone,openZoneOwner,previewId;private bool previewing;
        private CardView hoveredCard,focusedCard,emphasizedCard;private string hoveredId,focusedId,emphasizedId;
        private readonly System.Collections.Generic.Dictionary<string,int> rowPages=new System.Collections.Generic.Dictionary<string,int>();
        private readonly Label status,localPlayer,opponent,result,zones,commanders,localLibrary,opponentLibrary;
        private readonly BattlefieldLinks links;private readonly ArenaLibraryMotion libraryMotion;private ViewerBoardInput boardInput;private ArenaPriorityGlow priorityGlow;private bool disposed;
        private readonly System.Collections.Generic.HashSet<CardView> wired=new System.Collections.Generic.HashSet<CardView>();
        private ViewerSessionHost host;private ProjectedDecisionFrame frame;private bool inspecting;private int artworkCount=-1;
        public ViewerCardSurface Surface {get;}
        public ViewerDecisionPanel Decisions {get;private set;}
        public ArenaGameplayPresentation(VisualElement parent)
        {
            root=new VisualElement{name="arena-table"};root.style.flexGrow=1;parent.Add(root);
            var theme=Resources.Load<StyleSheet>("ArenaTable");if(theme!=null)root.styleSheets.Add(theme);
            ArenaOpeningBackdrop.AttachLocal(root);
            Surface=new ViewerCardSurface(root);Surface.CardsRoot.AddToClassList("table-cards");Surface.CardsRoot.pickingMode=PickingMode.Ignore;
            Surface.InspectionView.AddToClassList("table-inspection");Surface.InspectionView.SetPresentation(CardPresentationMode.Full,290);Surface.InspectionView.style.display=DisplayStyle.None;
            links=new BattlefieldLinks();root.Add(links);
            navigation=new VisualElement{name="board-navigation",pickingMode=PickingMode.Ignore};root.Add(navigation);
            status=Label("table-phase","Connecting…");opponent=Label("opponent-seat","");localPlayer=Label("local-seat","");
            localLibrary=Label("local-library","");opponentLibrary=Label("opponent-library","");CardTypography.Apply(localLibrary,CardTextRole.Title);CardTypography.Apply(opponentLibrary,CardTextRole.Title);
            localGraveyard=Label("local-graveyard","");opponentGraveyard=Label("opponent-graveyard","");
            localExile=Label("local-exile","");opponentExile=Label("opponent-exile","");
            ConfigurePile(localLibrary,"library",()=>frame?.Context.ViewerId);ConfigurePile(opponentLibrary,"library",OpponentId);
            ConfigurePile(localGraveyard,"graveyard",()=>frame?.Context.ViewerId);ConfigurePile(opponentGraveyard,"graveyard",OpponentId);
            ConfigurePile(localExile,"exile",()=>frame?.Context.ViewerId);ConfigurePile(opponentExile,"exile",OpponentId);
            Surface.Clearing+=ClearZoneResources;Surface.Rebinding+=ClearPileArt;
            ArenaTableArt.Player(localPlayer,"YOU");ArenaTableArt.Player(opponent,"OPPONENT");
            opponentHand=new VisualElement{name="opponent-hand",pickingMode=PickingMode.Ignore};root.Add(opponentHand);
            WirePlayer(localPlayer,()=>frame?.Context.ViewerId);WirePlayer(opponent,()=>frame?.PlayerLifeTotals.Keys.FirstOrDefault(id=>id!=frame.Context.ViewerId));
            zones=Label("table-zones","");zones.style.display=DisplayStyle.None;
            zoneChoices=new VisualElement{name="public-zone-choices"};zoneChoices.style.display=DisplayStyle.None;root.Add(zoneChoices);
            zoneDrawer=new VisualElement{name="public-zone-drawer"};root.Add(zoneDrawer);zoneDrawer.style.display=DisplayStyle.None;
            zoneTitle=new Label{name="public-zone-title",enableRichText=false};zoneDrawer.Add(zoneTitle);CardTypography.Apply(zoneTitle,CardTextRole.Title);
            zoneTabs=new VisualElement{name="zone-browser-tabs"};zoneDrawer.Add(zoneTabs);
            zoneSummary=new Label{name="zone-browser-summary",enableRichText=false};zoneDrawer.Add(zoneSummary);
            unknownLibrary=new VisualElement{name="zone-browser-back",pickingMode=PickingMode.Ignore};ArenaTableArt.Back(unknownLibrary);zoneDrawer.Add(unknownLibrary);unknownLibrary.style.display=DisplayStyle.None;
            zoneDrawer.Add(new Button(()=>ClosePublicZone()){name="close-public-zone",text="Back to battlefield  ·  Esc"});
            stackTitle=Label("stack-title","");stackTitle.pickingMode=PickingMode.Ignore;
            commanders=Label("game-commanders","");
            choices=new ScrollView(ScrollViewMode.Vertical){name="table-choices"};root.Add(choices);
            var motion=new Toggle("Reduced motion"){name="table-motion",value=false};motion.RegisterValueChangedCallback(ev=>root.EnableInClassList("reduced-motion",ev.newValue));root.Add(motion);
            libraryMotion=new ArenaLibraryMotion(root,localLibrary,opponentLibrary,()=>motion.value);
            result=Label("table-result","");CardTypography.Apply(result,CardTextRole.Title);result.style.display=DisplayStyle.None;
            var close=new Button(()=>CloseInspection()){text="Close inspection  ·  Esc",name="close-inspection"};root.Add(close);close.style.display=DisplayStyle.None;
            root.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Escape){CloseInspection();openZone=null;Layout();}});
            root.RegisterCallback<GeometryChangedEvent>(ev=>Layout());
        }
        private string OpponentId()=>frame?.PlayerLifeTotals.Keys.FirstOrDefault(id=>id!=frame.Context.ViewerId);
        private static string ZoneName(string zone)=>zone=="library"?"Library":zone=="graveyard"?"Graveyard":"Exile";
        private void ConfigurePile(Label pile,string zone,Func<string> owner)
        {
            pile.text="";pile.AddToClassList("zone-pile");pile.AddToClassList("zone-"+zone);pile.focusable=true;
            pile.style.width=66;pile.style.height=92;pile.style.right=StyleKeyword.Auto;pile.style.bottom=StyleKeyword.Auto;
            for(int i=0;i<2;i++){var sheet=new VisualElement{pickingMode=PickingMode.Ignore};sheet.AddToClassList("zone-pile-sheet");sheet.style.left=-3-i*3;sheet.style.top=3+i*3;pile.Add(sheet);}
            var back=new VisualElement{name="zone-back",pickingMode=PickingMode.Ignore};back.AddToClassList("zone-pile-face");
            if(zone=="library")ArenaTableArt.Back(back);pile.Add(back);
            var art=new Image{name="zone-art",pickingMode=PickingMode.Ignore,scaleMode=ScaleMode.ScaleToFit};art.AddToClassList("zone-pile-face");pile.Add(art);
            var fallback=new Label(zone=="library"?"":"—"){name="zone-fallback",enableRichText=false,pickingMode=PickingMode.Ignore};pile.Add(fallback);
            pile.Add(new Label("?"){name="zone-count",enableRichText=false,pickingMode=PickingMode.Ignore});
            var caption=new Label(ZoneName(zone)){name="zone-caption",enableRichText=false,pickingMode=PickingMode.Ignore};CardTypography.Apply(caption,CardTextRole.Title);pile.Add(caption);
            pile.RegisterCallback<ClickEvent>(ev=>{if(ev.button==0)BrowsePublicZone(zone,owner());});
            pile.RegisterCallback<NavigationSubmitEvent>(ev=>{BrowsePublicZone(zone,owner());ev.StopPropagation();});
        }
        private void ClearPileArt()
        {
            foreach(var pile in new[]{localLibrary,opponentLibrary,localGraveyard,opponentGraveyard,localExile,opponentExile}){
                if(pile==null)continue;pile.Q<Image>("zone-art").image=null;pile.Q<Label>("zone-fallback").text="";
            }
        }
        private void ClearZoneResources()
        {
            ClearCardFocus();CloseInspection();openZone=openZoneOwner=null;
            if(zoneDrawer!=null)zoneDrawer.style.display=DisplayStyle.None;
            root.RemoveFromClassList("browsing-public-zone");
            foreach(var pile in new[]{localLibrary,opponentLibrary,localGraveyard,opponentGraveyard,localExile,opponentExile}){
                if(pile==null)continue;pile.Q<Image>("zone-art").image=null;pile.Q<Label>("zone-count").text="?";pile.Q<Label>("zone-fallback").text="";
            }
        }
        private Label Label(string name,string text){var label=new Label(text){name=name,enableRichText=false};root.Add(label);return label;}
        public void CloseInspection(){inspecting=false;previewing=false;previewId=null;Surface.InspectionView.pickingMode=PickingMode.Position;Surface.InspectionView.style.display=DisplayStyle.None;root.Q<Button>("close-inspection").style.display=DisplayStyle.None;}
        public void Bind(ViewerSessionHost value)
        {if(Decisions!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_BOUND");host=value;Decisions=new ViewerDecisionPanel(choices,host);Decisions.SetSpatialPresentation(true);priorityGlow=new ArenaPriorityGlow(Decisions.Root);boardInput=new ViewerBoardInput(root,Surface,host,Decisions,ArenaTableArt.Menu);}
        public void Present(ProjectedDecisionFrame value)
        {
            if(frame!=null && frame.Context.Revision==value.Context.Revision){boardInput?.Refresh();priorityGlow?.Refresh();RefreshPlayers();if(artworkCount!=Surface.PresentedArtworkCount){artworkCount=Surface.PresentedArtworkCount;Layout();}return;}
            artworkCount=Surface.PresentedArtworkCount;
            ClearCardFocus();frame=value;CloseInspection();
            string viewer=frame.Context.ViewerId;
            UpdateLife(localPlayer,frame.PlayerLifeTotals.TryGetValue(viewer,out var life)?life:null);
            var other=frame.PlayerLifeTotals.FirstOrDefault(p=>p.Key!=viewer);UpdateLife(opponent,other.Value);
            UpdateOpponentHand(other.Key);
            localPlayer.EnableInClassList("has-priority",frame.Decision?.PlayerId==viewer);
            opponent.EnableInClassList("has-priority",frame.Decision!=null && frame.Decision.PlayerId!=viewer);
            status.text=frame.UnsupportedFields.Contains("decision")?"This choice is not supported yet. Return to Manaforge to end the session.":(frame.ActivePlayerId==viewer?"Your turn":"Opponent’s turn")+" · "+frame.Turn+"\n"+PhaseName(frame.Phase);
            if(frame.Turn==0 || frame.Decision?.Family=="mulligan" || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase))status.text="Opening hand\nChoose your starting hand";
            result.text=frame.Result==null?"":frame.Result=="win"?"Victory":frame.Result=="loss"?"Defeat":frame.Result=="draw"?"Draw":"Game complete\n"+frame.Result;result.style.display=frame.Result==null?DisplayStyle.None:DisplayStyle.Flex;if(frame.Result!=null)result.BringToFront();
            commanders.text=CommanderPresentationText.Format(frame);
            if(Decisions!=null)ArenaTableArt.Decision(Decisions,frame);
            OpenOfferedZone();Layout();libraryMotion.Observe(frame);priorityGlow?.Refresh();
        }
        private static string PhaseName(string phase)
        {switch(phase){case "PRECOMBAT_MAIN":return "Main phase";case "POSTCOMBAT_MAIN":return "Second main phase";case "COMBAT":return "Combat";case "BEGINNING":return "Beginning phase";case "ENDING":return "Ending phase";default:return (phase??"Opening hand").Replace('_',' ');}}
        private void UpdateLife(Label seat,long? value)
        {
            var life=seat.Q<Label>("seat-life");string next=value?.ToString()??"?";bool changed=life.text!="?" && life.text!=next;life.text=next;
            if(changed && !root.ClassListContains("reduced-motion")){long revision=frame.Context.Revision;life.AddToClassList("life-changed");life.schedule.Execute(()=>{if(!disposed && frame.Context.Revision==revision)life.RemoveFromClassList("life-changed");}).StartingIn(400);}
            else life.RemoveFromClassList("life-changed");
        }
        private void UpdateOpponentHand(string player)
        {
            opponentHand.Clear();if(player==null || !frame.PlayerHandCounts.TryGetValue(player,out var count) || !count.HasValue)return;
            int shown=(int)Math.Min(12,count.Value);for(int i=0;i<shown;i++){
                var back=new VisualElement{pickingMode=PickingMode.Ignore};back.AddToClassList("opponent-hand-back");ArenaTableArt.Back(back);
                back.style.left=200+(i-(shown-1)*.5f)*24;back.style.top=Mathf.Abs(i-(shown-1)*.5f)*2;back.style.rotate=new Rotate(new Angle(180+(i-(shown-1)*.5f)*-3));opponentHand.Add(back);
            }
        }
        private void WirePlayer(Label seat,Func<string> player)
        {
            seat.focusable=true;seat.RegisterCallback<ClickEvent>(ev=>{if(ev.button==0)Decisions?.TryActivatePlayer(host?.PresentedDecision,player());});
            seat.RegisterCallback<NavigationSubmitEvent>(ev=>{Decisions?.TryActivatePlayer(host?.PresentedDecision,player());ev.StopPropagation();});
        }
        private void RefreshPlayers()
        {
            var offer=host?.PresentedDecision;var current=offer?.Frame;bool can=offer?.CanSubmit==true;
            localPlayer.EnableInClassList("targetable",can && current.Decision.Options.Any(o=>o.PlayerId==frame.Context.ViewerId));
            opponent.EnableInClassList("targetable",can && current.Decision.Options.Any(o=>o.PlayerId!=null && o.PlayerId!=frame.Context.ViewerId));
        }
        private void UpdateLinks()
        {
            if(disposed || frame==null)return;var centers=new System.Collections.Generic.Dictionary<string,Vector2>();
            Surface.VisitPresented((card,view)=>{if(!card.Hidden && view.resolvedStyle.display!=DisplayStyle.None)centers[card.ObjectId]=links.WorldToLocal(view.worldBound.center);});
            centers[frame.Context.ViewerId]=links.WorldToLocal(localPlayer.worldBound.center);
            foreach(var player in frame.PlayerLifeTotals.Keys)if(player!=frame.Context.ViewerId)centers[player]=links.WorldToLocal(opponent.worldBound.center);
            var paths=new System.Collections.Generic.List<BattlefieldLinks.Link>();
            foreach(var group in frame.Combat){
                foreach(var attacker in group.AttackerIds)if(centers.TryGetValue(attacker,out var start) && group.DefenderId!=null && centers.TryGetValue(group.DefenderId,out var end))paths.Add(new BattlefieldLinks.Link(start,end,new Color(1,.42f,.18f,.8f)));
                if(group.AttackerIds.Count==1 && centers.TryGetValue(group.AttackerIds[0],out var target))foreach(var blocker in group.BlockerIds)if(centers.TryGetValue(blocker,out var start))paths.Add(new BattlefieldLinks.Link(start,target,new Color(.3f,.7f,1,.9f)));
            }links.Set(paths);
        }
        private void ClearCardFocus()
        {
            if(emphasizedCard!=null)Lower(emphasizedCard,emphasizedId);
            hoveredCard=focusedCard=emphasizedCard=null;hoveredId=focusedId=emphasizedId=null;
        }
        private void RefreshCardFocus()
        {
            if(disposed)return;
            if(emphasizedCard!=null)Lower(emphasizedCard,emphasizedId);
            emphasizedCard=hoveredCard??focusedCard;emphasizedId=hoveredCard!=null?hoveredId:focusedId;
            bool admitted=false;
            Surface.VisitPresented((card,view)=>{if(view==emphasizedCard && card.ObjectId==emphasizedId && !card.Hidden)admitted=true;});
            if(admitted && emphasizedCard.parent!=null && emphasizedCard.style.display.value!=DisplayStyle.None)Raise(emphasizedCard,emphasizedId);
        }
        private void Raise(CardView view,string id)
        {
            view.style.scale=new Scale(new Vector3(1.12f,1.12f,1));view.style.translate=new Translate(0,view.ClassListContains("in-hand")?-90:-15);view.BringToFront();view.parent?.BringToFront();
            // The shared inspector borrows only the currently admitted surface binding.
            // No second texture, printing lookup or speculative characteristic is created.
            if(!inspecting && host?.Inspect(id)==true){
                previewing=true;previewId=id;Surface.InspectionView.style.display=DisplayStyle.Flex;
                Surface.InspectionView.pickingMode=PickingMode.Ignore;PlaceInspection(view);Surface.InspectionView.BringToFront();
            }
            choices.BringToFront();result.BringToFront();if(inspecting){Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();}root.Q<VisualElement>("board-object-menu")?.BringToFront();
        }
        private void PlaceInspection(CardView source=null)
        {
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            Surface.InspectionView.SetPresentation(CardPresentationMode.Full,Mathf.Clamp((height-130)/1.4f,240,300));
            bool left=source==null || source.layout.center.x>width*.5f;
            Surface.InspectionView.style.left=left?24:width-Surface.InspectionView.style.width.value.value-24;
            Surface.InspectionView.style.top=90;
        }
        private void Lower(CardView view,string id)
        {
            view.style.scale=new Scale(Vector3.one);view.style.translate=new Translate(0,0);
            if(previewing && previewId==id && !inspecting)CloseInspection();
        }
        public void InspectCard(string id)
        {
            if(host==null || !host.Inspect(id))return;
            previewing=false;previewId=null;inspecting=true;Surface.InspectionView.pickingMode=PickingMode.Position;PlaceInspection();Surface.InspectionView.style.display=DisplayStyle.Flex;Surface.InspectionView.BringToFront();
            var close=root.Q<Button>("close-inspection");close.style.display=DisplayStyle.Flex;close.BringToFront();
        }
        private void OpenOfferedZone()
        {
            var options=frame.Decision?.Options;
            if(options==null || options.Count==0 || options.Any(o=>o.ObjectId==null))return;
            var offered=new System.Collections.Generic.List<ProjectedCard>();
            Surface.VisitPresented((card,view)=>{if(!card.Hidden && card.FaceDown!=true && new[]{"library","graveyard","exile"}.Contains(card.Zone) && options.Any(o=>o.ObjectId==card.ObjectId))offered.Add(card);});
            if(offered.Count==0 || options.Any(o=>!offered.Any(card=>card.ObjectId==o.ObjectId)))return;
            string zone=offered[0].Zone,owner=offered[0].OwnerId;
            if(owner==null || offered.Any(card=>card.Zone!=zone || card.OwnerId!=owner))return;
            // A browser opens only; every selection/confirmation still requires explicit input.
            openZone=zone;openZoneOwner=owner;rowPages["public-zone"]=0;
        }
        // Pure viewer-scoped navigation, also available to keyboard/accessibility callers.
        public bool BrowsePublicZone(string zone,string owner)
        {
            if(disposed || frame==null || (zone!="library" && zone!="graveyard" && zone!="exile") || owner==null || !frame.PlayerLifeTotals.ContainsKey(owner))return false;
            ClearCardFocus();CloseInspection();openZone=zone;openZoneOwner=owner;rowPages["public-zone"]=0;Layout();return true;
        }
        public void ClosePublicZone(){if(disposed || openZone==null)return;ClearCardFocus();CloseInspection();openZone=null;Layout();}
        private void Layout()
        {
            if(frame==null)return;
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;if(float.IsNaN(width) || width<1 || height<1)return;
            var items=new System.Collections.Generic.List<(ProjectedCard card,CardView view)>();Surface.VisitPresented((c,v)=>items.Add((c,v)));
            wired.RemoveWhere(v=>v.parent==null);
            foreach(var item in items){
                var card=item.card;var view=item.view;view.style.position=Position.Absolute;
                view.style.display=DisplayStyle.None;
                if(wired.Add(view)){
                    string id=card.ObjectId;view.focusable=true;view.AddToClassList("table-card");
                    view.RegisterCallback<PointerEnterEvent>(ev=>{hoveredCard=view;hoveredId=id;RefreshCardFocus();});
                    view.RegisterCallback<PointerLeaveEvent>(ev=>{if(hoveredCard==view){hoveredCard=null;hoveredId=null;}RefreshCardFocus();});
                    view.RegisterCallback<FocusInEvent>(ev=>{focusedCard=view;focusedId=id;RefreshCardFocus();});
                    view.RegisterCallback<FocusOutEvent>(ev=>{if(focusedCard==view){focusedCard=null;focusedId=null;}RefreshCardFocus();});
                    view.RegisterCallback<DetachFromPanelEvent>(ev=>{
                        if(ev.target!=view)return;
                        if(hoveredCard==view){hoveredCard=null;hoveredId=null;}
                        if(focusedCard==view){focusedCard=null;focusedId=null;}
                        RefreshCardFocus();
                    });
                    view.RegisterCallback<PointerDownEvent>(ev=>{if(ev.button==1){InspectCard(id);ev.StopPropagation();}});
                    view.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Space){InspectCard(id);ev.StopPropagation();}});
                }
                view.EnableInClassList("selected",frame.Decision?.Options.Any(o=>o.ObjectId==card.ObjectId && o.Selected)==true);
                view.EnableInClassList("attacking",frame.Combat.Any(g=>g.AttackerIds.Contains(card.ObjectId)));
                view.EnableInClassList("blocking",frame.Combat.Any(g=>g.BlockerIds.Contains(card.ObjectId)));
                view.SetLiveMarkers(card.Hidden?"":string.Join(" · ",(card.Characteristics?.Counters??Array.Empty<ProjectedCounter>()).Select(c=>c.Name+" "+c.Amount))+(card.Damage>0?"  Damage "+card.Damage:""));
            }
            navigation.Clear();
            string viewer=frame.Context.ViewerId;
            bool Land(ProjectedCard c)=>!c.Hidden && (c.Characteristics?.TypeLine??"").Split('—')[0].Split(' ').Contains("Land");
            void Row(System.Collections.Generic.List<(ProjectedCard card,CardView view)> row,float top,float left,float span,float size,bool full=false,string key=null,bool reserveSeat=false){
                if(row.Count==0)return;
                float gapStart=width*.5f-90,gapEnd=width*.5f+90;
                int leftSlots=Mathf.Max(1,Mathf.FloorToInt((gapStart-left)/(size+18))),rightSlots=Mathf.Max(1,Mathf.FloorToInt((left+span-gapEnd)/(size+18)));
                if(key!=null){
                    int capacity=reserveSeat?leftSlots+rightSlots:Mathf.Max(1,Mathf.FloorToInt(span/(size+18))),last=(row.Count-1)/capacity;
                    int page=rowPages.TryGetValue(key,out var requested)?Mathf.Clamp(requested,0,last):0;rowPages[key]=page;
                    if(last>0){
                        var nav=new VisualElement();nav.AddToClassList("row-navigation");nav.style.left=Mathf.Min(width-120,left+span+8);nav.style.top=top;navigation.Add(nav);
                        var previous=new Button(()=>{rowPages[key]=Mathf.Max(0,page-1);Layout();}){text="‹",name=key+"-previous"};previous.SetEnabled(page>0);nav.Add(previous);
                        nav.Add(new Label((page+1)+" / "+(last+1)){enableRichText=false});
                        var next=new Button(()=>{rowPages[key]=Mathf.Min(last,page+1);Layout();}){text="›",name=key+"-next"};next.SetEnabled(page<last);nav.Add(next);
                    }
                    row=row.Skip(page*capacity).Take(capacity).ToList();
                }
                float step=Mathf.Min(size+18,(span-size)/Mathf.Max(1,row.Count-1));
                float start=left+(span-size-step*(row.Count-1))*.5f;
                for(int i=0;i<row.Count;i++){var v=row[i].view;v.style.display=DisplayStyle.Flex;v.SetPresentation(full?CardPresentationMode.Full:CardPresentationMode.Compact,size);v.style.left=reserveSeat?(i<leftSlots?gapStart-Mathf.Min(leftSlots,row.Count)*(size+18)+9+i*(size+18):gapEnd+9+(i-leftSlots)*(size+18)):start+i*step;v.style.top=top;v.style.rotate=new Rotate(new Angle(row[i].card.Tapped==true?90:0));}
            }
            float boardLeft=260,boardSpan=Mathf.Max(100,width-425),cardWidth=Mathf.Clamp(boardSpan/7,85,125);
            var battlefield=items.Where(i=>i.card.Zone=="battlefield").ToList();
            Row(battlefield.Where(i=>i.card.ControllerId!=viewer && Land(i.card)).ToList(),height*.15f,boardLeft,boardSpan,Mathf.Min(cardWidth,110),key:"opponent-lands",reserveSeat:true);
            Row(battlefield.Where(i=>i.card.ControllerId!=viewer && !Land(i.card)).ToList(),height*.30f,boardLeft,boardSpan,cardWidth,key:"opponent-permanents");
            Row(battlefield.Where(i=>i.card.ControllerId==viewer && !Land(i.card)).ToList(),height*.53f,boardLeft,boardSpan,cardWidth,key:"local-permanents");
            Row(battlefield.Where(i=>i.card.ControllerId==viewer && Land(i.card)).ToList(),height*.72f,boardLeft,boardSpan,Mathf.Min(cardWidth,110),key:"local-lands",reserveSeat:true);
            foreach(var item in items)item.view.RemoveFromClassList("in-hand");
            var hand=items.Where(i=>i.card.Zone=="hand" && i.card.OwnerId==viewer).ToList();
            bool opening=frame.Turn==0 || frame.Decision?.Family=="mulligan" || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase);
            // Opening uses the existing generous fan; normal hand keeps full proportions and reserves controls.
            root.EnableInClassList("opening-state",opening);
            // During first layout or a resize the panel can briefly be narrower than
            // the desktop target. Always give the fan a positive, bounded viewport.
            float handSpan=opening?Mathf.Max(230,width-240):Mathf.Clamp(width-680,145,900),handWidth=opening?210:145;
            // Bound overlap and retain access to every card instead of shrinking large hands to slivers.
            int handCapacity=Mathf.Max(1,Mathf.FloorToInt((handSpan-handWidth)/45)+1);
            int handLast=Mathf.Max(0,(hand.Count-1)/handCapacity),handPage=rowPages.TryGetValue("hand",out var hp)?Mathf.Clamp(hp,0,handLast):0;
            rowPages["hand"]=handPage;
            if(handLast>0){
                var nav=new VisualElement{name="hand-navigation"};nav.AddToClassList("row-navigation");nav.style.left=width*.5f-75;nav.style.top=height-30;navigation.Add(nav);
                var previous=new Button(()=>{CloseInspection();rowPages["hand"]=handPage-1;Layout();}){text="‹",name="hand-previous"};previous.SetEnabled(handPage>0);nav.Add(previous);
                nav.Add(new Label("Hand "+(handPage+1)+" / "+(handLast+1)));
                var next=new Button(()=>{CloseInspection();rowPages["hand"]=handPage+1;Layout();}){text="›",name="hand-next"};next.SetEnabled(handPage<handLast);nav.Add(next);
            }
            hand=hand.Skip(handPage*handCapacity).Take(handCapacity).ToList();
            var placements=OpeningHandFan.Arrange(hand.Count,handSpan);
            float handStep=Mathf.Min(handWidth*.72f,(handSpan-handWidth)/Mathf.Max(1,hand.Count-1));
            for(int i=0;i<hand.Count;i++){
                hand[i].view.AddToClassList("in-hand");
                float offset=i-(hand.Count-1)*.5f,angle=offset*Mathf.Min(4,28f/Mathf.Max(1,hand.Count));var v=hand[i].view;
                v.style.display=DisplayStyle.Flex;v.SetPresentation(CardPresentationMode.Full,handWidth);
                v.style.left=opening?(width-handSpan)*.5f+placements[i].Left+(placements[i].Width-handWidth)*.5f:width*.5f-handWidth*.5f+offset*handStep;
                v.style.top=opening?height*.24f+placements[i].Top:height-handWidth*1.4f+55+Mathf.Abs(offset)*3;
                v.style.rotate=new Rotate(new Angle(opening?placements[i].Angle:angle));v.BringToFront();
            }
            var stack=items.Where(i=>i.card.Zone=="stack").ToList();
            stackTitle.text=stack.Count==0?"":"STACK  ·  "+stack.Count;stackTitle.style.display=stack.Count==0?DisplayStyle.None:DisplayStyle.Flex;
            stackTitle.style.top=height*.36f-25;
            Row(stack,height*.36f,width-145,130,100,key:"stack");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId!=viewer).ToList(),height*.36f,15,130,65,key:"opponent-command");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId==viewer).ToList(),height*.50f,15,130,65,key:"local-command");
            // Piles use admitted visible artwork only. No card order/top-card identity is inferred.
            void Pile(Label pile,string zone,string owner,float left,float top){
                pile.style.left=left;pile.style.top=top;
                var visible=items.Where(i=>i.card.Zone==zone && i.card.OwnerId==owner && !i.card.Hidden && i.card.FaceDown!=true).ToList();
                long? total=zone=="library" && owner!=null && frame.PlayerLibraryCounts.TryGetValue(owner,out var count)?count:null;
                string countText=zone=="library"?(total?.ToString()??"?"):visible.Count.ToString();
                pile.Q<Label>("zone-count").text=countText;
                var preview=zone=="library"?null:visible.FirstOrDefault(i=>i.view.Artwork!=null).view;
                pile.Q<Image>("zone-art").image=preview?.Artwork;
                pile.Q<Label>("zone-fallback").text=zone=="library" || preview!=null?"":visible.Count==0?"—":visible[0].card.Characteristics?.Name??"Visible card";
                pile.tooltip=(owner==viewer?"Your ":"Opponent’s ")+ZoneName(zone)+" · "+countText+(zone=="library"?" cards":" visible cards")+"\nClick or press Enter to browse known cards.";
                pile.EnableInClassList("zone-open",openZone==zone && openZoneOwner==owner);
            }
            string opponentId=OpponentId();float localPileTop=Mathf.Max(350,height-242);
            Pile(opponentLibrary,"library",opponentId,22,150);Pile(opponentGraveyard,"graveyard",opponentId,98,150);Pile(opponentExile,"exile",opponentId,174,150);
            Pile(localLibrary,"library",viewer,22,localPileTop);Pile(localGraveyard,"graveyard",viewer,98,localPileTop);Pile(localExile,"exile",viewer,174,localPileTop);
            root.EnableInClassList("browsing-public-zone",openZone!=null);
            zoneDrawer.style.display=openZone==null?DisplayStyle.None:DisplayStyle.Flex;
            if(openZone!=null){
                zoneTitle.text=(openZoneOwner==viewer?"Your ":"Opponent’s ")+ZoneName(openZone);
                zoneTabs.Clear();
                foreach(string zone in new[]{"library","graveyard","exile"}){
                    var tab=new Button(()=>BrowsePublicZone(zone,openZoneOwner)){text=ZoneName(zone),name="browse-"+zone};tab.EnableInClassList("zone-tab-selected",zone==openZone);zoneTabs.Add(tab);
                }
                // A drawer is a presentation overlay, never another owner of card views.
                // Hide the table's cards while browsing, then place the same owned card root
                // above the backdrop. Bringing only children forward cannot cross sibling layers.
                foreach(var item in items)item.view.style.display=DisplayStyle.None;
                navigation.Clear();
                zoneDrawer.BringToFront();Surface.CardsRoot.BringToFront();
                var publicCards=items.Where(i=>!i.card.Hidden && i.card.FaceDown!=true && i.card.Zone==openZone && i.card.OwnerId==openZoneOwner).ToList();
                long? total=openZone=="library" && frame.PlayerLibraryCounts.TryGetValue(openZoneOwner,out var libraryCount)?libraryCount:null;
                zoneSummary.text=openZone=="library"?(total.HasValue?total+" cards · ":"Count unavailable · ")+publicCards.Count+" known\nUnrevealed cards and library order remain hidden.":publicCards.Count==0?"No viewer-visible cards in this zone.":publicCards.Count+" visible cards · Hover to inspect. Highlighted choices use the game’s current prompt.";
                unknownLibrary.style.display=openZone=="library" && publicCards.Count==0?DisplayStyle.Flex:DisplayStyle.None;
                Row(publicCards,height*.34f,180,width-360,185,true,"public-zone");
                foreach(var item in publicCards)if(item.view.style.display.value==DisplayStyle.Flex)item.view.BringToFront();
                navigation.BringToFront();zoneChoices.BringToFront();
            }
            zones.text=string.Join("\n",items.Where(i=>i.card.Zone!="hand" && i.card.Zone!="battlefield" && i.card.Zone!="stack").GroupBy(i=>i.card.Zone).Select(g=>g.Key+"  "+g.Count()));
            choices.EnableInClassList("opening-choices",opening);
            if(opening && Decisions!=null){OpeningMulliganControls.Apply(Decisions.Root,hand.Count);OpeningMulliganControls.ApplyLocalSkins(Decisions.Root);}
            if(inspecting)PlaceInspection();
            if(!inspecting && !previewing)Surface.InspectionView.style.display=DisplayStyle.None;
            foreach(var item in items){var availability=item.view.Q<Label>("status");if(availability!=null)availability.style.display=DisplayStyle.None;}
            choices.BringToFront();result.BringToFront();if(inspecting || previewing)Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();
            boardInput?.Refresh();RefreshPlayers();links.schedule.Execute(UpdateLinks);
        }
        public void Dispose(){ClearCardFocus();disposed=true;priorityGlow?.Dispose();boardInput?.Dispose();libraryMotion.Dispose();Decisions?.Dispose();Surface.Dispose();Surface.Clearing-=ClearZoneResources;Surface.Rebinding-=ClearPileArt;wired.Clear();root.RemoveFromHierarchy();}
    }
}

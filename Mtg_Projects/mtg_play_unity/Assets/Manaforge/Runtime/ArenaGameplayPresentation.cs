using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class ArenaGameplayPresentation : IGameplayPresentation
    {
        private readonly VisualElement root,choices,navigation,opponentHand,zoneChoices;
        private readonly ZoneBrowser zoneDrawer;
        private readonly Label stackTitle;
        private readonly ZonePile localGraveyard,opponentGraveyard,localExile,opponentExile,localLibrary,opponentLibrary;private string openZone,openZoneOwner,previewId;private bool previewing;
        private CardView hoveredCard,focusedCard,emphasizedCard;private string hoveredId,focusedId,emphasizedId;
        private readonly System.Collections.Generic.Dictionary<string,int> rowPages=new System.Collections.Generic.Dictionary<string,int>();
        private readonly Label status,result,zones,commanders;
        private readonly PlayerPanel localPlayer,opponent;
        private bool unsupportedTopology,restoringFocus;
        private readonly GameplayOverlay inspector;
        private readonly BattlefieldLinks links;private readonly GameplayAnimationCoordinator animations;private ViewerBoardInput boardInput;private UnityPriorityControls priorityControls;private bool disposed;
        private readonly System.Collections.Generic.HashSet<CardView> wired=new System.Collections.Generic.HashSet<CardView>();
        private ViewerSessionHost host;private ProjectedDecisionFrame frame;private bool inspecting;private int artworkCount=-1;
        public ViewerCardSurface Surface {get;}
        public ViewerDecisionPanel Decisions {get;private set;}
        public ArenaGameplayPresentation(VisualElement parent)
        {
            root=new VisualElement{name="arena-table"};root.style.flexGrow=1;parent.Add(root);
            var theme=Resources.Load<StyleSheet>("ArenaTable");if(theme!=null)root.styleSheets.Add(theme);
            GameplayTheme.Attach(root);
            var material=new GameplayTableSurface();material.style.position=Position.Absolute;material.style.left=12;material.style.right=12;material.style.top=12;material.style.bottom=12;root.Add(material);
            Surface=new ViewerCardSurface(root);Surface.CardsRoot.AddToClassList("table-cards");Surface.CardsRoot.pickingMode=PickingMode.Ignore;
            Surface.InspectionView.AddToClassList("table-inspection");Surface.InspectionView.SetPresentation(CardPresentationMode.Full,290);Surface.InspectionView.style.display=DisplayStyle.None;
            links=new BattlefieldLinks();root.Add(links);
            navigation=new VisualElement{name="board-navigation",pickingMode=PickingMode.Ignore};root.Add(navigation);
            status=Label("table-phase","Connecting...");
            opponent=new PlayerPanel{name="opponent-seat"};localPlayer=new PlayerPanel{name="local-seat"};root.Add(opponent);root.Add(localPlayer);
            localPlayer.Activated+=ActivatePlayer;opponent.Activated+=ActivatePlayer;
            localLibrary=Pile("local-library","library");opponentLibrary=Pile("opponent-library","library");
            localGraveyard=Pile("local-graveyard","graveyard");opponentGraveyard=Pile("opponent-graveyard","graveyard");
            localExile=Pile("local-exile","exile");opponentExile=Pile("opponent-exile","exile");
            Surface.Clearing+=ClearZoneResources;Surface.Rebinding+=ClearPileArt;
            opponentHand=new VisualElement{name="opponent-hand",pickingMode=PickingMode.Ignore};root.Add(opponentHand);
            zones=Label("table-zones","");zones.style.display=DisplayStyle.None;
            zoneChoices=new VisualElement{name="public-zone-choices"};zoneChoices.style.display=DisplayStyle.None;root.Add(zoneChoices);
            zoneDrawer=new ZoneBrowser();root.Add(zoneDrawer);zoneDrawer.BrowseRequested+=BrowseZone;zoneDrawer.Closed+=ClosePublicZone;
            stackTitle=Label("stack-title","");stackTitle.pickingMode=PickingMode.Ignore;
            commanders=Label("game-commanders","");
            choices=new ScrollView(ScrollViewMode.Vertical){name="table-choices"};root.Add(choices);
            var motion=new Toggle("Reduced motion"){name="table-motion",value=false};motion.RegisterValueChangedCallback(ev=>{root.EnableInClassList("reduced-motion",ev.newValue);animations?.Advance();});root.Add(motion);
            animations=new GameplayAnimationCoordinator(root,Surface,MotionZoneAnchor,MotionPlayerAnchor,()=>motion.value);
            result=Label("table-result","");CardTypography.Apply(result,CardTextRole.Title);result.style.display=DisplayStyle.None;
            var close=new Button(()=>CloseInspection()){text="Close inspection | Esc",name="close-inspection"};root.Add(close);close.style.display=DisplayStyle.None;inspector=new GameplayOverlay(Surface.InspectionView,close);
            root.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Escape){CloseInspection();ClosePublicZone();}});
            root.RegisterCallback<GeometryChangedEvent>(ev=>Layout());
        }
        private Vector2? MotionPlayerAnchor(string player)
        {
            var panel=player==localPlayer.PlayerId?localPlayer:player==opponent.PlayerId?opponent:null;
            return panel==null?null:(Vector2?)root.WorldToLocal(panel.worldBound.center);
        }
        private Vector2? MotionZoneAnchor(string owner,string zone)
        {
            if(owner==null || owner!=localPlayer.PlayerId && owner!=opponent.PlayerId)return null;
            bool local=owner==localPlayer.PlayerId;
            var pile=zone=="library"?(local?localLibrary:opponentLibrary):zone=="graveyard"?(local?localGraveyard:opponentGraveyard):zone=="exile"?(local?localExile:opponentExile):null;
            if(pile!=null)return root.WorldToLocal(pile.worldBound.center);
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            if(zone=="hand")return local?new Vector2(width*.48f,height-130):root.WorldToLocal(opponentHand.worldBound.center);
            if(zone=="stack")return new Vector2(width-90,height*.42f);
            if(zone=="battlefield")return new Vector2(width*.55f,height*(local?.6f:.3f));
            return null;
        }
        private string OpponentId()=>opponent.PlayerId;
        private static string ZoneName(string zone)=>ZonePile.Title(zone);
        private ZonePile Pile(string name,string zone)
        {
            var pile=new ZonePile(zone){name=name};pile.style.position=Position.Absolute;pile.style.width=66;pile.style.height=92;
            root.Add(pile);pile.BrowseRequested+=BrowseZone;return pile;
        }
        private void BrowseZone(string zone,string owner){BrowsePublicZone(zone,owner);}
        private void ActivatePlayer(string player){Decisions?.TryActivatePlayer(host?.PresentedDecision,player);}
        private void ClearPileArt()
        {
            foreach(var pile in new[]{localLibrary,opponentLibrary,localGraveyard,opponentGraveyard,localExile,opponentExile}){
                if(pile==null)continue;pile.ClearArtwork();
            }
        }
        private void ClearZoneResources()
        {
            ClearCardFocus();inspecting=false;inspector?.Hide(false);CloseInspection();openZone=openZoneOwner=null;localPlayer.ClearBinding();opponent.ClearBinding();opponentHand.Clear();animations?.Clear();links.Set(Array.Empty<BattlefieldLinks.Link>());
            zoneDrawer?.ClearBinding();
            root.RemoveFromClassList("browsing-public-zone");frame=null;rowPages.Clear();
            foreach(var pile in new[]{localLibrary,opponentLibrary,localGraveyard,opponentGraveyard,localExile,opponentExile}){
                if(pile==null)continue;pile.ClearBinding();
            }
        }
        private Label Label(string name,string text){var label=new Label(text){name=name,enableRichText=false};root.Add(label);return label;}
        public void CloseInspection(){bool restore=inspecting;inspecting=false;previewing=false;previewId=null;restoringFocus=true;try{inspector?.Hide(restore);}finally{restoringFocus=false;}}
        public void Bind(ViewerSessionHost value)
        {if(Decisions!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_BOUND");host=value;Decisions=new ViewerDecisionPanel(choices,host);Decisions.PresentationHold=()=>animations.HoldAutomaticPassing;Decisions.SetSpatialPresentation(true);Decisions.SetChoicePreview(Surface.ChoicePreview);priorityControls=new UnityPriorityControls(root,Decisions);boardInput=new ViewerBoardInput(root,Surface,host,Decisions,GameplayTheme.Menu);}
        public void Present(ProjectedDecisionFrame value)
        {
            if(disposed)return;
            var seatIds=value.PlayerLifeTotals.Keys.ToArray();
            if(seatIds.Length!=2 || !seatIds.Contains(value.Context.ViewerId)){
                unsupportedTopology=true;ClearZoneResources();Surface.CardsRoot.style.display=DisplayStyle.None;choices.style.display=DisplayStyle.None;
                status.text="This view supports two players. Choose a compatible presentation.";return;
            }
            unsupportedTopology=false;Surface.CardsRoot.style.display=DisplayStyle.Flex;choices.style.display=DisplayStyle.Flex;
            localPlayer.Bind(value.Context.ViewerId,"You");opponent.Bind(seatIds.Single(id=>id!=value.Context.ViewerId),"Opponent");
            priorityControls?.Refresh();
            if(frame!=null && frame.Context.Revision==value.Context.Revision && frame.Context.SessionId==value.Context.SessionId && frame.Context.ViewerId==value.Context.ViewerId){boardInput?.Refresh();RefreshPlayers();if(artworkCount!=Surface.PresentedArtworkCount){artworkCount=Surface.PresentedArtworkCount;Layout();}return;}
            artworkCount=Surface.PresentedArtworkCount;
            if(frame==null || frame.Context.SessionId!=value.Context.SessionId || frame.Context.ViewerId!=value.Context.ViewerId || !Surface.HasInspection){
                ClearCardFocus();CloseInspection();
            }
            frame=value;
            string viewer=frame.Context.ViewerId;
            localPlayer.Present(frame.PlayerLifeTotals[viewer],frame.Decision?.PlayerId==viewer,false,root.ClassListContains("reduced-motion"));
            opponent.Present(frame.PlayerLifeTotals[opponent.PlayerId],frame.Decision?.PlayerId==opponent.PlayerId,false,root.ClassListContains("reduced-motion"));
            UpdateOpponentHand(opponent.PlayerId);
            status.text=frame.UnsupportedFields.Contains("decision")?"This choice is not supported yet. Return to Manaforge to end the session.":(frame.ActivePlayerId==viewer?"Your turn":"Opponent’s turn")+" · "+frame.Turn+"\n"+PhaseName(frame.Phase);
            if(frame.Turn==0 || frame.Decision?.Family=="mulligan" || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase))status.text="Opening hand\nChoose your starting hand";
            result.text=frame.Result==null?"":frame.Result=="win"?"Victory":frame.Result=="loss"?"Defeat":frame.Result=="draw"?"Draw":"Game complete\n"+frame.Result;result.style.display=frame.Result==null?DisplayStyle.None:DisplayStyle.Flex;if(frame.Result!=null)result.BringToFront();
            commanders.text=CommanderPresentationText.Format(frame);
            if(Decisions!=null)GameplayTheme.Decision(Decisions,frame);
            OpenOfferedZone();Layout();animations.Observe(frame,Surface.TakeAnimations());
        }
        private static string PhaseName(string phase)
        {switch(phase){case "PRECOMBAT_MAIN":return "Main phase";case "POSTCOMBAT_MAIN":return "Second main phase";case "COMBAT":return "Combat";case "BEGINNING":return "Beginning phase";case "ENDING":return "Ending phase";default:return (phase??"Opening hand").Replace('_',' ');}}
        private void UpdateOpponentHand(string player)
        {
            long? count=player!=null && frame.PlayerHandCounts.TryGetValue(player,out var value)?value:null;
            GameplayCardLayout.HiddenHand(opponentHand,count,470,180);

        }
        private void RefreshPlayers()
        {
            if(frame==null || unsupportedTopology)return;
            var offer=host?.PresentedDecision;var current=offer?.Frame;bool can=offer?.CanSubmit==true;
            foreach(var panel in new[]{localPlayer,opponent}){
                bool target=can && current.Decision!=null && current.Decision.Options.Any(o=>o.PlayerId==panel.PlayerId);
                // Refresh availability without restarting life-change animation.
                panel.SetTargetable(target);
            }
        }
        private void UpdateLinks()
        {
            if(disposed || frame==null)return;var centers=new System.Collections.Generic.Dictionary<string,Vector2>();
            Surface.VisitPresented((card,view)=>{if(!card.Hidden && view.resolvedStyle.display!=DisplayStyle.None)centers[card.ObjectId]=links.WorldToLocal(view.worldBound.center);});
            centers[frame.Context.ViewerId]=links.WorldToLocal(localPlayer.worldBound.center);
            if(opponent.PlayerId!=null)centers[opponent.PlayerId]=links.WorldToLocal(opponent.worldBound.center);
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
            if(!inspecting && !restoringFocus && host?.Inspect(id)==true){
                previewing=true;previewId=id;inspector.Show(false);PlaceInspection(view);Surface.InspectionView.BringToFront();
            }
            choices.BringToFront();result.BringToFront();if(inspecting){Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();}root.Q<VisualElement>("board-object-menu")?.BringToFront();
        }
        private void PlaceInspection(CardView source=null)
        {
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            Surface.InspectionView.SetPresentation(CardPresentationMode.Full,Mathf.Clamp((height-130)/1.4f,240,300));
            inspector.Place(new Rect(0,0,width,height),new Vector2(Surface.InspectionView.style.width.value.value,Surface.InspectionView.style.height.value.value),source==null?(Vector2?)null:root.WorldToLocal(source.worldBound.center));
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
            VisualElement origin=null;Surface.VisitPresented((card,view)=>{if(card.ObjectId==id)origin=view;});inspector.Show(true,origin);
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
            if(disposed || unsupportedTopology || frame==null || (zone!="library" && zone!="graveyard" && zone!="exile") || owner==null || !frame.PlayerLifeTotals.ContainsKey(owner))return false;
            ClearCardFocus();CloseInspection();zoneDrawer.SetReturnFocus(new[]{localLibrary,opponentLibrary,localGraveyard,opponentGraveyard,localExile,opponentExile}.FirstOrDefault(p=>p.OwnerId==owner && p.Zone==zone));openZone=zone;openZoneOwner=owner;rowPages["public-zone"]=0;Layout();return true;
        }
        public void ClosePublicZone(){if(disposed || openZone==null)return;ClearCardFocus();CloseInspection();openZone=null;zoneDrawer.ClearBinding(true);Layout();}
        private void Layout()
        {
            if(disposed || frame==null || unsupportedTopology)return;
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;if(float.IsNaN(width) || width<1 || height<1)return;
            var items=new System.Collections.Generic.List<(ProjectedCard card,CardView view)>();Surface.VisitPresented((c,v)=>items.Add((c,v)));
            wired.RemoveWhere(v=>v.parent==null);
            foreach(var item in items){
                var card=item.card;var view=item.view;view.style.position=Position.Absolute;
                view.style.display=DisplayStyle.None;
                if(wired.Add(view)){
                    view.focusable=true;view.AddToClassList("table-card");
                    view.RegisterCallback<PointerEnterEvent>(ev=>{hoveredCard=view;hoveredId=Surface.CurrentObjectId(view);RefreshCardFocus();});
                    view.RegisterCallback<PointerLeaveEvent>(ev=>{if(hoveredCard==view){hoveredCard=null;hoveredId=null;}RefreshCardFocus();});
                    view.RegisterCallback<FocusInEvent>(ev=>{focusedCard=view;focusedId=Surface.CurrentObjectId(view);RefreshCardFocus();});
                    view.RegisterCallback<FocusOutEvent>(ev=>{if(focusedCard==view){focusedCard=null;focusedId=null;}RefreshCardFocus();});
                    view.RegisterCallback<DetachFromPanelEvent>(ev=>{
                        if(ev.target!=view)return;
                        if(hoveredCard==view){hoveredCard=null;hoveredId=null;}
                        if(focusedCard==view){focusedCard=null;focusedId=null;}
                        RefreshCardFocus();
                    });
                    view.RegisterCallback<PointerDownEvent>(ev=>{if(ev.button==1){InspectCard(Surface.CurrentObjectId(view));ev.StopPropagation();}});
                    view.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Space){InspectCard(Surface.CurrentObjectId(view));ev.StopPropagation();}});
                }
                if(hoveredCard==view)hoveredId=card.ObjectId;if(focusedCard==view)focusedId=card.ObjectId;
                if(emphasizedCard==view){emphasizedId=card.ObjectId;if(previewing)previewId=card.ObjectId;}
                view.EnableInClassList("selected",frame.Decision?.Options.Any(o=>o.ObjectId==card.ObjectId && o.Selected)==true);
                view.EnableInClassList("attacking",frame.Combat.Any(g=>g.AttackerIds.Contains(card.ObjectId)));
                view.EnableInClassList("blocking",frame.Combat.Any(g=>g.BlockerIds.Contains(card.ObjectId)));
                view.SetLiveMarkers(card.Hidden?"":string.Join(" · ",(card.Characteristics?.Counters??Array.Empty<ProjectedCounter>()).Select(c=>c.Name+" "+c.Amount))+(card.Damage>0?"  Damage "+card.Damage:""));
            }
            navigation.Clear();
            string viewer=frame.Context.ViewerId;
            bool Land(ProjectedCard c)=>!c.Hidden && (c.Characteristics?.TypeLine??"").Split('—')[0].Split(' ').Contains("Land");
            void Row(System.Collections.Generic.List<(ProjectedCard card,CardView view)> row,float top,float left,float span,float size,bool full=false,string key=null,bool reserveSeat=false)
                =>GameplayCardLayout.Row(row,navigation,rowPages,Layout,width,top,left,span,size,full,key,reserveSeat?new Vector2(width*.5f-90,width*.5f+90):(Vector2?)null);
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
            int handCount=hand.Count;
            float handSpan=opening?Mathf.Max(230,width-240):Mathf.Clamp(width-680,145,900),handSize=opening?210:145;
            GameplayCardLayout.Hand(hand,navigation,rowPages,Layout,CloseInspection,new Rect((width-handSpan)*.5f,opening?height*.24f:height-handSize*1.4f+55,handSpan,handSize*1.4f),height-30,opening,handSize);
            var stack=items.Where(i=>i.card.Zone=="stack").ToList();
            stackTitle.text=stack.Count==0?"":"STACK  ·  "+stack.Count;stackTitle.style.display=stack.Count==0?DisplayStyle.None:DisplayStyle.Flex;
            stackTitle.style.top=height*.36f-25;
            Row(stack,height*.36f,width-145,130,100,key:"stack");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId!=viewer).ToList(),height*.36f,15,130,65,key:"opponent-command");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId==viewer).ToList(),height*.50f,15,130,65,key:"local-command");
            // Piles use admitted visible artwork only. No card order/top-card identity is inferred.
            void UpdatePile(ZonePile pile,string zone,string owner,float left,float top){
                pile.style.left=left;pile.style.top=top;pile.Bind(owner);
                var visible=items.Where(i=>i.card.Zone==zone && i.card.OwnerId==owner && !i.card.Hidden && i.card.FaceDown!=true).ToList();
                long? total=zone=="library"?(owner!=null && frame.PlayerLibraryCounts.TryGetValue(owner,out var count)?count:null):visible.Count;
                var preview=zone=="library"?null:visible.FirstOrDefault(i=>i.view.Artwork!=null).view;
                pile.Present(total,preview?.Artwork,visible.Count==0?null:visible[0].card.Characteristics?.Name??"Visible card",openZone==zone && openZoneOwner==owner);
            }
            string opponentId=OpponentId();float localPileTop=Mathf.Max(350,height-242);
            UpdatePile(opponentLibrary,"library",opponentId,22,150);UpdatePile(opponentGraveyard,"graveyard",opponentId,98,150);UpdatePile(opponentExile,"exile",opponentId,174,150);
            UpdatePile(localLibrary,"library",viewer,22,localPileTop);UpdatePile(localGraveyard,"graveyard",viewer,98,localPileTop);UpdatePile(localExile,"exile",viewer,174,localPileTop);
            root.EnableInClassList("browsing-public-zone",openZone!=null);
            zoneDrawer.style.display=openZone==null?DisplayStyle.None:DisplayStyle.Flex;
            if(openZone!=null){
                // A drawer is a presentation overlay, never another owner of card views.
                // Hide the table's cards while browsing, then place the same owned card root
                // above the backdrop. Bringing only children forward cannot cross sibling layers.
                foreach(var item in items)item.view.style.display=DisplayStyle.None;
                navigation.Clear();
                zoneDrawer.BringToFront();Surface.CardsRoot.BringToFront();
                var publicCards=items.Where(i=>!i.card.Hidden && i.card.FaceDown!=true && i.card.Zone==openZone && i.card.OwnerId==openZoneOwner).ToList();
                long? total=openZone=="library" && frame.PlayerLibraryCounts.TryGetValue(openZoneOwner,out var libraryCount)?libraryCount:null;
                zoneDrawer.Present(openZoneOwner,openZone,openZoneOwner==viewer?"Your zones":"Opponent zones",publicCards.Count,total);
                Row(publicCards,height*.34f,180,width-360,185,true,"public-zone");
                foreach(var item in publicCards)if(item.view.style.display.value==DisplayStyle.Flex)item.view.BringToFront();
                navigation.BringToFront();zoneChoices.BringToFront();
            }
            zones.text=string.Join("\n",items.Where(i=>i.card.Zone!="hand" && i.card.Zone!="battlefield" && i.card.Zone!="stack").GroupBy(i=>i.card.Zone).Select(g=>g.Key+"  "+g.Count()));
            choices.EnableInClassList("opening-choices",opening);
            choices.EnableInClassList("library-ordering",Decisions!=null && Decisions.IsLibraryOrdering);
            if(opening && Decisions!=null)GameplayTheme.Mulligan(Decisions.Root,handCount);
            if(inspecting)PlaceInspection();
            if(!inspecting && !previewing)Surface.InspectionView.style.display=DisplayStyle.None;
            foreach(var item in items){var availability=item.view.Q<Label>("status");if(availability!=null)availability.style.display=DisplayStyle.None;}
            choices.BringToFront();result.BringToFront();if(inspecting || previewing)Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();
            boardInput?.Refresh();RefreshPlayers();links.schedule.Execute(UpdateLinks);
        }
        public void Dispose(){if(disposed)return;ClearZoneResources();disposed=true;boardInput?.Dispose();animations.Dispose();inspector.Dispose();priorityControls?.Dispose();Decisions?.Dispose();Surface.Clearing-=ClearZoneResources;Surface.Rebinding-=ClearPileArt;Surface.Dispose();
            localPlayer.Dispose();opponent.Dispose();foreach(var pile in new[]{localLibrary,opponentLibrary,localGraveyard,opponentGraveyard,localExile,opponentExile})pile.Dispose();zoneDrawer.Dispose();wired.Clear();root.RemoveFromHierarchy();}
    }
}

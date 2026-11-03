using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class ArenaGameplayPresentation : IGameplayPresentation
    {
        private readonly VisualElement root,choices,navigation,opponentHand,zoneChoices,zoneDrawer;
        private readonly Label zoneTitle,stackTitle;private string openZone,openZoneOwner,previewId;private bool previewing;
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
            ArenaTableArt.Player(localPlayer,"YOU");ArenaTableArt.Player(opponent,"OPPONENT");
            opponentHand=new VisualElement{name="opponent-hand",pickingMode=PickingMode.Ignore};root.Add(opponentHand);
            WirePlayer(localPlayer,()=>frame?.Context.ViewerId);WirePlayer(opponent,()=>frame?.PlayerLifeTotals.Keys.FirstOrDefault(id=>id!=frame.Context.ViewerId));
            zones=Label("table-zones","");zones.style.display=DisplayStyle.None;
            zoneChoices=new VisualElement{name="public-zone-choices"};root.Add(zoneChoices);
            zoneDrawer=new VisualElement{name="public-zone-drawer"};root.Add(zoneDrawer);zoneDrawer.style.display=DisplayStyle.None;
            zoneTitle=new Label{name="public-zone-title",enableRichText=false};zoneDrawer.Add(zoneTitle);
            zoneDrawer.Add(new Button(()=>{openZone=null;Layout();}){name="close-public-zone",text="Back to battlefield  ·  Esc"});
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
        private Label Label(string name,string text){var label=new Label(text){name=name,enableRichText=false};root.Add(label);return label;}
        public void CloseInspection(){inspecting=false;previewing=false;previewId=null;Surface.InspectionView.pickingMode=PickingMode.Position;Surface.InspectionView.style.display=DisplayStyle.None;root.Q<Button>("close-inspection").style.display=DisplayStyle.None;}
        public void Bind(ViewerSessionHost value)
        {if(Decisions!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_BOUND");host=value;Decisions=new ViewerDecisionPanel(choices,host);Decisions.SetSpatialPresentation(true);priorityGlow=new ArenaPriorityGlow(Decisions.Root);boardInput=new ViewerBoardInput(root,Surface,host,Decisions,ArenaTableArt.Menu);}
        public void Present(ProjectedDecisionFrame value)
        {
            if(frame!=null && frame.Context.Revision==value.Context.Revision){boardInput?.Refresh();priorityGlow?.Refresh();RefreshPlayers();if(artworkCount!=Surface.PresentedArtworkCount){artworkCount=Surface.PresentedArtworkCount;Layout();}return;}
            artworkCount=Surface.PresentedArtworkCount;
            frame=value;CloseInspection();
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
            Layout();libraryMotion.Observe(frame);priorityGlow?.Refresh();
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
                    view.RegisterCallback<PointerEnterEvent>(ev=>Raise(view,id));
                    view.RegisterCallback<PointerLeaveEvent>(ev=>Lower(view,id));
                    view.RegisterCallback<FocusInEvent>(ev=>Raise(view,id));
                    view.RegisterCallback<FocusOutEvent>(ev=>Lower(view,id));
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
            float boardLeft=145,boardSpan=width-300,cardWidth=Mathf.Clamp(boardSpan/7,85,125);
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
            float handSpan=opening?width-240:Mathf.Min(width-500,900),handWidth=opening?210:145;
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
            Row(stack,height*.36f,width-145,130,100,key:"stack");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId!=viewer).ToList(),height*.23f,15,130,65,key:"opponent-command");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId==viewer).ToList(),height*.50f,15,130,65,key:"local-command");
            zoneChoices.Clear();
            foreach(var group in items.Where(i=>!i.card.Hidden && (i.card.Zone=="graveyard" || i.card.Zone=="exile")).GroupBy(i=>new{i.card.Zone,i.card.OwnerId})){
                string zone=group.Key.Zone,owner=group.Key.OwnerId;
                var button=new Button(()=>{CloseInspection();openZone=zone;openZoneOwner=owner;rowPages["public-zone"]=0;Layout();}){text=(owner==viewer?"Your ":"Opponent’s ")+zone+" · "+group.Count(),name=(owner==viewer?"local-":"opponent-")+zone};
                button.EnableInClassList("zone-open",openZone==zone && openZoneOwner==owner);zoneChoices.Add(button);
            }
            zoneDrawer.style.display=openZone==null?DisplayStyle.None:DisplayStyle.Flex;
            if(openZone!=null){
                zoneTitle.text=(openZoneOwner==viewer?"Your ":"Opponent’s ")+openZone;
                zoneDrawer.BringToFront();
                var publicCards=items.Where(i=>!i.card.Hidden && i.card.Zone==openZone && i.card.OwnerId==openZoneOwner).ToList();
                Row(publicCards,height*.32f,180,width-360,145,true,"public-zone");
                foreach(var item in publicCards)if(item.view.style.display.value==DisplayStyle.Flex)item.view.BringToFront();
                navigation.BringToFront();
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
        public void Dispose(){disposed=true;priorityGlow?.Dispose();boardInput?.Dispose();libraryMotion.Dispose();Decisions?.Dispose();Surface.Dispose();wired.Clear();root.RemoveFromHierarchy();}
    }
}

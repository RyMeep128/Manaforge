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
        private readonly VisualElement stackBackdrop,stackToolbar;
        private readonly Button stackToggle,resolveAll;
        private bool stackFocused;private float stackAttentionUntil;
        private readonly System.Collections.Generic.HashSet<string> seenStack=new System.Collections.Generic.HashSet<string>();
        private readonly GameplayZonePanel zonePanel;private readonly GameplayDrawer actionDrawer,priorityDrawer,zonePanelDrawer;private GameplayActionDrawer actionBinding;private GameplayPriorityDrawer priorityBinding;private string openZone,openZoneOwner,previewId;private bool previewing;
        private CardView hoveredCard,focusedCard,emphasizedCard;private string hoveredId,focusedId,emphasizedId;
        private readonly System.Collections.Generic.Dictionary<string,int> rowPages=new System.Collections.Generic.Dictionary<string,int>();
        private readonly System.Collections.Generic.List<string> handOrder=new System.Collections.Generic.List<string>();
        private readonly Label status,result,zones;private readonly GameplayPlayerHud hud;
        private bool unsupportedTopology,restoringFocus;
        private readonly GameplayOverlay inspector;
        private readonly BattlefieldLinks links;private readonly GameplayAnimationCoordinator animations;private ViewerBoardInput boardInput;private bool disposed;
        private readonly System.Collections.Generic.HashSet<CardView> wired=new System.Collections.Generic.HashSet<CardView>();
        private ViewerTargetingController targeting;
        private ViewerSessionHost host;private ProjectedDecisionFrame frame;private bool inspecting;private int artworkCount=-1;
        private bool layoutAttentionFocus;
        public HudLayoutEditor LayoutEditor {get;private set;}
        public GameplayHudRegistry HudRegistry {get;}=new GameplayHudRegistry();
        public GameplayPresentationCapabilities Capabilities {get;}
        private readonly ILayoutPresetStore layoutPresetStore;
        private readonly IGameplayLayoutStrategy layoutStrategy=new LegacyGameplayLayoutStrategy();
        public ViewerCardSurface Surface {get;}
        public ViewerDecisionPanel Decisions {get;private set;}
        public ArenaGameplayPresentation(VisualElement parent,ICardBackProvider cardBacks=null,GameplayPresentationCapabilities capabilities=null,ILayoutPresetStore layoutPresetStore=null)
        {
            Capabilities=capabilities??GameplayPresentationCapabilities.Default;this.layoutPresetStore=layoutPresetStore;
            root=new VisualElement{name="arena-table"};root.style.flexGrow=1;parent.Add(root);
            var theme=Resources.Load<StyleSheet>("ArenaTable");if(theme!=null)root.styleSheets.Add(theme);
            GameplayTheme.Attach(root);
            var material=new GameplayTableSurface();material.style.position=Position.Absolute;material.style.left=12;material.style.right=12;material.style.top=12;material.style.bottom=12;root.Add(material);
            stackBackdrop=new VisualElement{name="stack-focus-backdrop",pickingMode=PickingMode.Ignore};stackBackdrop.style.position=Position.Absolute;stackBackdrop.style.backgroundColor=new Color(.025f,.035f,.05f,.94f);stackBackdrop.style.borderTopLeftRadius=stackBackdrop.style.borderTopRightRadius=stackBackdrop.style.borderBottomLeftRadius=stackBackdrop.style.borderBottomRightRadius=12;stackBackdrop.style.display=DisplayStyle.None;root.Add(stackBackdrop);
            Surface=new ViewerCardSurface(root,cardBacks);Surface.CardsRoot.AddToClassList("table-cards");Surface.CardsRoot.pickingMode=PickingMode.Ignore;
            Surface.InspectionView.AddToClassList("table-inspection");Surface.InspectionView.SetPresentation(CardPresentationMode.Full,290);Surface.InspectionView.style.display=DisplayStyle.None;
            links=new BattlefieldLinks();root.Add(links);
            navigation=new VisualElement{name="board-navigation",pickingMode=PickingMode.Ignore};root.Add(navigation);
            status=Label("table-phase","Connecting...");
            hud=new GameplayPlayerHud(localSeatAtBottom:true,registry:HudRegistry);hud.AddToClassList("arena-player-hud");root.Add(hud);hud.PlayerActivated+=ActivatePlayer;
            zonePanelDrawer=new GameplayDrawer("Zones",GameplayDrawerDirection.Left){name="zones-drawer"};root.Add(zonePanelDrawer);
            var zoneScroll=new ScrollView(ScrollViewMode.Vertical){name="zone-panel-scroll",horizontalScrollerVisibility=ScrollerVisibility.Hidden};zoneScroll.pickingMode=PickingMode.Ignore;zoneScroll.contentViewport.pickingMode=PickingMode.Ignore;zoneScroll.contentContainer.pickingMode=PickingMode.Ignore;zoneScroll.style.maxHeight=Length.Percent(100);zonePanelDrawer.Content.Add(zoneScroll);
            zonePanel=new GameplayZonePanel(Surface.CardBacks);zoneScroll.Add(zonePanel);zonePanel.BrowseRequested+=BrowseZone;
            Surface.Clearing+=ClearZoneResources;Surface.Rebinding+=ClearPileArt;
            opponentHand=new VisualElement{name="opponent-hand",pickingMode=PickingMode.Ignore};root.Add(opponentHand);
            zones=Label("table-zones","");zones.style.display=DisplayStyle.None;
            zoneChoices=new VisualElement{name="public-zone-choices"};zoneChoices.style.display=DisplayStyle.None;root.Add(zoneChoices);
            zoneDrawer=new ZoneBrowser(Surface.CardBacks);root.Add(zoneDrawer);zoneDrawer.BrowseRequested+=BrowseZone;zoneDrawer.Closed+=ClosePublicZone;
            stackToolbar=new VisualElement{name="stack-toolbar"};stackToolbar.style.position=Position.Absolute;stackToolbar.style.flexDirection=FlexDirection.Row;stackToolbar.style.alignItems=Align.Center;root.Add(stackToolbar);
            stackTitle=new Label{name="stack-title",enableRichText=false};stackTitle.style.position=Position.Relative;stackTitle.style.top=0;stackTitle.style.right=0;stackTitle.style.width=StyleKeyword.Auto;stackTitle.style.flexGrow=1;stackToolbar.Add(stackTitle);
            stackToggle=new Button(()=>{stackFocused=!stackFocused;Layout();}){name="stack-focus-toggle",text="Minimize"};stackToolbar.Add(stackToggle);GameplayTheme.Button(stackToggle);
            resolveAll=new Button(()=>{if(Decisions==null)return;if(Decisions.Priority.Current.Yield=="resolve-stack")Decisions.Priority.CancelYield();else if(CanResolveStack()){Decisions.Priority.BeginYield("resolve-stack",Decisions.PriorityFrame);stackAttentionUntil=0;}Decisions.PrioritySettingsChanged();RefreshStackControls();}){name="stack-resolve-all",text="Resolve All"};stackToolbar.Add(resolveAll);GameplayTheme.Button(resolveAll,true);stackToolbar.style.display=DisplayStyle.None;
            actionDrawer=new GameplayDrawer("Spells & Abilities",GameplayDrawerDirection.Right){name="action-drawer"};root.Add(actionDrawer);
            choices=new ScrollView(ScrollViewMode.Vertical){name="table-choices"};actionDrawer.Content.Add(choices);
            priorityDrawer=new GameplayDrawer("Priority",GameplayDrawerDirection.Right){name="priority-drawer"};root.Add(priorityDrawer);
            var motion=new Toggle("Reduced motion"){name="table-motion",value=false};motion.RegisterValueChangedCallback(ev=>{root.EnableInClassList("reduced-motion",ev.newValue);animations?.Advance();foreach(var drawer in new[]{actionDrawer,priorityDrawer,zonePanelDrawer,hud.CommanderDrawer})drawer.SetReducedMotion(ev.newValue);if(frame!=null)hud.Present(frame,Surface,host?.GameplayFormat,ev.newValue,InspectCard);});root.Add(motion);
            animations=new GameplayAnimationCoordinator(root,Surface,MotionZoneAnchor,MotionPlayerAnchor,()=>motion.value);
            result=Label("table-result","");CardTypography.Apply(result,CardTextRole.Title);result.style.display=DisplayStyle.None;
            var close=new Button(()=>CloseInspection()){text="Close inspection | Esc",name="close-inspection"};root.Add(close);close.style.display=DisplayStyle.None;inspector=new GameplayOverlay(Surface.InspectionView,close);
            root.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Escape){CloseInspection();ClosePublicZone();}});
            root.RegisterCallback<GeometryChangedEvent>(ev=>Layout());
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Hand,"Hand","hand"),adapter:new GameplayHudLayoutAdapter(GameplayLayoutSlot.Hand));
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Battlefield,"Battlefield","battlefield"),adapter:new GameplayHudLayoutAdapter(GameplayLayoutSlot.Battlefield));
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.GameStack,"Game stack","game-stack"),stackToolbar,new GameplayHudLayoutAdapter(GameplayLayoutSlot.GameStack));
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Priority,"Priority","priority",GameplayHudCapabilities.Drawer,presetKey:"hud.priority"),priorityDrawer);
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Actions,"Spells and abilities","actions",GameplayHudCapabilities.Drawer,presetKey:"hud.actions"),actionDrawer);
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Zones,"Zones","zones",GameplayHudCapabilities.Drawer,presetKey:"hud.zones"),zonePanelDrawer);
            // Zone families share a panel; these are logical child descriptors, not new pile owners.
            foreach(string zone in new[]{"library","graveyard","exile"})
                HudRegistry.Register(new GameplayHudDescriptor("zones/"+zone,ZonePile.Title(zone),"zones",parentId:GameplayHudIds.Zones),zonePanel);
        }
        private Vector2? MotionPlayerAnchor(string player)
        {
            var panel=hud.Player(player);
            return panel==null?null:(Vector2?)root.WorldToLocal(panel.worldBound.center);
        }
        private Vector2? MotionZoneAnchor(string owner,string zone)
        {
            if(hud.Player(owner)==null)return null;
            bool local=owner==frame?.Context.ViewerId;
            var pile=zonePanel.Pile(owner,zone);
            if(pile!=null)return root.WorldToLocal((zonePanelDrawer.IsOpen?(VisualElement)pile:zonePanelDrawer.Tab).worldBound.center);
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            if(zone=="hand")return local?new Vector2(width*.48f,height-130):root.WorldToLocal(opponentHand.worldBound.center);
            if(zone=="stack")return new Vector2(width-90,height*.42f);
            if(zone=="battlefield")return new Vector2(width*.55f,height*(local?.6f:.3f));
            return null;
        }
        private string OpponentId()=>frame?.PlayerLifeTotals.Keys.FirstOrDefault(id=>id!=frame.Context.ViewerId);
        private static string ZoneName(string zone)=>ZonePile.Title(zone);
        private void BrowseZone(string zone,string owner){BrowsePublicZone(zone,owner);}
        private void ActivatePlayer(string player){Decisions?.TryActivatePlayer(host?.PresentedDecision,player);}
        private void ClearPileArt(){zonePanel.ClearArtwork();}
        private void ClearZoneResources()
        {
            LayoutEditor?.EndSession();
            seenStack.Clear();stackFocused=false;stackAttentionUntil=0;stackToolbar.style.display=stackBackdrop.style.display=DisplayStyle.None;hud?.ClearPresentation();ClearCardFocus();inspecting=false;inspector?.Hide(false);CloseInspection();openZone=openZoneOwner=null;opponentHand.Clear();animations?.Clear();links.Set(Array.Empty<BattlefieldLinks.Link>());
            zoneDrawer?.ClearBinding();
            root.RemoveFromClassList("browsing-public-zone");frame=null;rowPages.Clear();handOrder.Clear();
            zonePanel.ClearBinding();actionBinding?.Reset();priorityDrawer.Reset();zonePanelDrawer.Reset();

        }
        private Label Label(string name,string text){var label=new Label(text){name=name,enableRichText=false};root.Add(label);return label;}
        public void InterruptGestures(){boardInput?.InterruptGesture();targeting?.InterruptGesture();}
        public void CloseInspection(){bool restore=inspecting;inspecting=false;previewing=false;previewId=null;restoringFocus=true;try{inspector?.Hide(restore);}finally{restoringFocus=false;}}
        public void Bind(ViewerSessionHost value)
        {if(Decisions!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_BOUND");host=value;Decisions=new ViewerDecisionPanel(choices,host);Decisions.PresentationHold=()=>animations.HoldAutomaticPassing || Time.unscaledTime<stackAttentionUntil;Decisions.SetSpatialPresentation(true);Decisions.SetChoicePreview(Surface.ChoicePreview);actionBinding=new GameplayActionDrawer(actionDrawer,Decisions);priorityBinding=new GameplayPriorityDrawer(priorityDrawer,Decisions);targeting=new ViewerTargetingController(root,Surface,Decisions,()=>hud.Players);boardInput=new ViewerBoardInput(root,Surface,host,Decisions,GameplayTheme.Menu);
            if(Capabilities.PrivateLayout)LayoutEditor=new HudLayoutEditor(root.parent,root,HudRegistry,
                new[]{(GameplayHudIds.Priority,"Priority",priorityDrawer),(GameplayHudIds.Actions,"Spells & Abilities",actionDrawer),(GameplayHudIds.Zones,"Zones",zonePanelDrawer),(GameplayHudIds.Commanders,"Commanders",hud.CommanderDrawer)},
                layoutPresetStore??new JsonLayoutPresetStore(System.IO.Path.Combine(Application.persistentDataPath,"profiles","default","layouts","arena")),
                ()=>{InterruptGestures();ClearCardFocus();CloseInspection();ClosePublicZone();},Layout,Decisions.SetLayoutEditing,()=>LayoutAttentionRequired(),FocusGameplayAttention,previewRoots:new VisualElement[]{zonePanel,zoneDrawer,navigation,Surface.InspectionView,root.Q<Button>("close-inspection")},closePreviews:()=>{CloseInspection();ClosePublicZone();});
        }
        private void FocusGameplayAttention()
        {
            if(host?.PendingReveal!=null){root.parent?.Q<Button>("reveal-acknowledge")?.Focus();return;}
            var current=host?.PresentedDecision?.Frame;
            if(current?.Decision!=null && !current.Decision.IsPriority && current.Decision.PlayerId==current.Context.ViewerId){actionDrawer.SetOpen(true,true);return;}
            if(openZone!=null){root.Q<Button>("close-public-zone")?.Focus();return;}
            if(inspecting){root.Q<Button>("close-inspection")?.Focus();return;}
            priorityDrawer.Tab.Focus();
        }
        private bool LayoutAttentionRequired()
        {
            var current=host?.PresentedDecision;var value=current?.Frame;
            return host==null || !host.Authenticated || host.Completion.IsCompleted || host.PendingReveal!=null || value==null || value.Result!=null
                || value.Decision!=null && !value.Decision.IsPriority && value.Decision.PlayerId==value.Context.ViewerId
                || current?.CanSubmit==false || Decisions?.Root.ClassListContains("command-uncertain")==true || Decisions?.Presentation?.Mode==YieldPresentationMode.Failed;
        }
        public void BeforeDecisionTick()
        {bool editing=LayoutEditor?.IsEditing==true;LayoutEditor?.BeforeDecisionTick(LayoutAttentionRequired());if(editing && LayoutEditor?.IsEditing==false){layoutAttentionFocus=true;if(host?.PendingReveal!=null)root.parent?.Q<Button>("reveal-acknowledge")?.Focus();}}
        public void Present(ProjectedDecisionFrame value)
        {
            if(disposed)return;
            LayoutEditor?.Observe(value.Context.SessionId,value.Context.ViewerId,LayoutAttentionRequired(),value.Turn==0 || Decisions?.IsLibraryOrdering==true,value.Result!=null);
            var seatIds=value.PlayerLifeTotals.Keys.ToArray();
            if(!seatIds.Contains(value.Context.ViewerId)){
                unsupportedTopology=true;ClearZoneResources();Surface.CardsRoot.style.display=DisplayStyle.None;choices.style.display=DisplayStyle.None;
                status.text="The viewer seat is unavailable.";return;
            }
            unsupportedTopology=false;Surface.CardsRoot.style.display=DisplayStyle.Flex;choices.style.display=DisplayStyle.Flex;
            hud.Present(value,Surface,host?.GameplayFormat,root.ClassListContains("reduced-motion"),InspectCard);
            actionBinding?.Refresh(value);if(layoutAttentionFocus){layoutAttentionFocus=false;if(host?.PendingReveal==null && value.Decision!=null && !value.Decision.IsPriority && value.Decision.PlayerId==value.Context.ViewerId)actionDrawer.SetOpen(true,true);}
            priorityBinding?.Refresh();zonePanelDrawer.RefreshInput();RefreshStackControls();
            if(frame!=null && frame.Context.Revision==value.Context.Revision && frame.Context.SessionId==value.Context.SessionId && frame.Context.ViewerId==value.Context.ViewerId){boardInput?.Refresh();RefreshPlayers();targeting?.Observe(frame);if(artworkCount!=Surface.PresentedArtworkCount){artworkCount=Surface.PresentedArtworkCount;Layout();}return;}
            artworkCount=Surface.PresentedArtworkCount;
            if(frame==null || frame.Context.SessionId!=value.Context.SessionId || frame.Context.ViewerId!=value.Context.ViewerId || !Surface.HasInspection){
                ClearCardFocus();CloseInspection();
            }
            bool newStack=value.StackIds.Any(id=>!seenStack.Contains(id));
            seenStack.Clear();foreach(string id in value.StackIds)seenStack.Add(id);
            if(newStack){stackFocused=true;stackAttentionUntil=Time.unscaledTime+.9f;rowPages["stack"]=0;}
            if(value.StackIds.Count==0){stackFocused=false;stackAttentionUntil=0;}
            frame=value;targeting?.Observe(value);
            string viewer=frame.Context.ViewerId;
            UpdateOpponentHand(OpponentId());
            status.text=frame.UnsupportedFields.Contains("decision")?"This choice cannot be displayed. Report code: "+(frame.DecisionError??"DECISION_UNSUPPORTED"):(frame.ActivePlayerId==viewer?"Your turn":"Opponent’s turn")+" · "+frame.Turn+"\n"+PhaseName(frame.Phase);
            if(frame.Turn==0 || frame.Decision?.Family=="mulligan" || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase))status.text="Opening hand";
            if(frame.SessionNotice!=null)status.text+="\nA permission request could not be displayed. Code: "+frame.SessionNotice;
            result.text=frame.Result==null?"":frame.Result=="win"?"Victory":frame.Result=="loss"?"Defeat":frame.Result=="draw"?"Draw":"Game complete\n"+frame.Result;result.style.display=frame.Result==null?DisplayStyle.None:DisplayStyle.Flex;if(frame.Result!=null)result.BringToFront();
            if(Decisions!=null)GameplayTheme.Decision(Decisions,frame);
            OpenOfferedZone();Layout();animations.Observe(frame,Surface.TakeAnimations());
        }
        private bool CanResolveStack(){var offered=Decisions?.CurrentOffer;var value=offered?.Frame;return offered?.CanSubmit==true && value?.StackIds.Count>0 && value.Decision?.IsPriority==true && value.Decision.PlayerId==value.Context.ViewerId && value.PriorityPlayerId==value.Context.ViewerId && value.Actions.Count(a=>a.Kind=="pass" && a.ObjectId==null)==1 && !Decisions.Priority.Current.Paused;}
        private void RefreshStackControls(){if(resolveAll==null)return;bool running=Decisions?.Priority.Current.Yield=="resolve-stack";resolveAll.text=running?"Cancel":"Resolve All";resolveAll.style.display=stackFocused?DisplayStyle.Flex:DisplayStyle.None;resolveAll.SetEnabled(running || CanResolveStack());stackToggle.text=stackFocused?"Minimize":"View";}
        private static string PhaseName(string phase)
        {switch(phase){case "PRECOMBAT_MAIN":return "Main phase";case "POSTCOMBAT_MAIN":return "Second main phase";case "COMBAT":return "Combat";case "BEGINNING":return "Beginning phase";case "ENDING":return "Ending phase";default:return (phase??"Opening hand").Replace('_',' ');}}
        private void UpdateOpponentHand(string player)
        {
            long? count=player!=null && frame.PlayerHandCounts.TryGetValue(player,out var value)?value:null;
            GameplayCardLayout.HiddenHand(opponentHand,count,470,180,player,Surface.CardBacks);

        }
        private void RefreshPlayers()
        {
            if(frame==null || unsupportedTopology)return;
            var offer=host?.PresentedDecision;var current=offer?.Frame;bool can=offer?.CanSubmit==true;
            hud.SetTargetable(id=>can && current.Decision!=null && current.Decision.Options.Any(o=>o.PlayerId==id));
        }
        private void UpdateLinks()
        {
            if(disposed || frame==null)return;var centers=new System.Collections.Generic.Dictionary<string,Vector2>();
            Surface.VisitPresented((card,view)=>{if(!card.Hidden && view.resolvedStyle.display!=DisplayStyle.None)centers[card.ObjectId]=links.WorldToLocal(view.worldBound.center);});
            foreach(var seat in hud.Players)centers[seat.PlayerId]=links.WorldToLocal(seat.worldBound.center);
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
            actionDrawer.BringToFront();result.BringToFront();if(inspecting){Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();}root.Q<VisualElement>("board-object-menu")?.BringToFront();LayoutEditor?.BringToFront();
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
            if(view.ClassListContains("in-hand")){
                var hand=new System.Collections.Generic.List<(string id,CardView view)>();
                Surface.VisitPresented((card,cardView)=>{if(cardView.ClassListContains("in-hand") && cardView.style.display.value!=DisplayStyle.None)hand.Add((card.RenderId,cardView));});
                foreach(var item in hand.OrderBy(item=>handOrder.IndexOf(item.id)))item.view.BringToFront();
            }
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
            ClearCardFocus();CloseInspection();zoneDrawer.SetReturnFocus(zonePanelDrawer.IsOpen?(VisualElement)zonePanel.Pile(owner,zone):zonePanelDrawer.Tab);openZone=zone;openZoneOwner=owner;rowPages["public-zone"]=0;Layout();return true;
        }
        private void BrowseAttachments(string target)
        {
            if(disposed || frame==null)return;ClearCardFocus();CloseInspection();zoneDrawer.SetReturnFocus(null);openZone="attachments";openZoneOwner=target;rowPages["public-zone"]=0;Layout();
        }
        public void ClosePublicZone(){if(disposed || openZone==null)return;ClearCardFocus();CloseInspection();openZone=null;zoneDrawer.ClearBinding(true);Layout();}
        private void Layout()
        {
            if(disposed || frame==null || unsupportedTopology)return;
            LayoutEditor?.BeforeLegacyLayout();
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
            bool opening=frame.Turn==0 || frame.Decision?.Family=="mulligan" || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase);
            bool ordering=Decisions?.IsLibraryOrdering==true;
            var plan=layoutStrategy.Resolve(new GameplayLayoutContext(width,height,opening,stackFocused,ordering));
            var geometry=plan.Battlefield;
            float boardLeft=geometry.Left,boardSpan=geometry.Span,cardWidth=geometry.CardWidth;
            bool activeStack=items.Any(i=>i.card.Zone=="stack");
            var attachmentGroups=GameplayCardLayout.AttachmentGroups(items.Select(i=>i.card),frame.PlayerLifeTotals.Keys);
            if(openZone=="attachments" && !attachmentGroups.ContainsKey(openZoneOwner)){openZone=openZoneOwner=null;zoneDrawer.ClearBinding(true);rowPages.Remove("public-zone");}
            var attachedIds=new System.Collections.Generic.HashSet<string>(attachmentGroups.Values.SelectMany(group=>group).Select(card=>card.ObjectId));
            var battlefield=items.Where(i=>i.card.Zone=="battlefield" && !attachedIds.Contains(i.card.ObjectId)).ToList();
            GameplayCardLayout.LandRow(battlefield.Where(i=>i.card.ControllerId!=viewer && Land(i.card)).ToList(),navigation,rowPages,Layout,width,geometry.OpponentLands,boardLeft,boardSpan,Mathf.Min(cardWidth,110),"opponent-lands",new Vector2(boardLeft,boardLeft));
            Row(battlefield.Where(i=>i.card.ControllerId!=viewer && !Land(i.card)).ToList(),geometry.OpponentPermanents,boardLeft,geometry.PermanentSpan(activeStack),cardWidth,key:"opponent-permanents");
            Row(battlefield.Where(i=>i.card.ControllerId==viewer && !Land(i.card)).ToList(),geometry.LocalPermanents,boardLeft,geometry.PermanentSpan(activeStack),cardWidth,key:"local-permanents");
            GameplayCardLayout.LandRow(battlefield.Where(i=>i.card.ControllerId==viewer && Land(i.card)).ToList(),navigation,rowPages,Layout,width,geometry.LocalLands,boardLeft,boardSpan,Mathf.Min(cardWidth,110),"local-lands",new Vector2(boardLeft,boardLeft));
            var attachmentViews=items.ToDictionary(item=>item.card.ObjectId);
            foreach(var group in attachmentGroups){
                Vector2 anchor;float size=95;CardView parentView=null;
                if(attachmentViews.TryGetValue(group.Key,out var parent)){
                    parentView=parent.view;if(parentView.style.display.value==DisplayStyle.None)continue;anchor=new Vector2(parentView.style.left.value.value,parentView.style.top.value.value);size=parentView.style.width.value.value;
                }else{var seat=hud.Player(group.Key);if(seat==null)continue;anchor=root.WorldToLocal(seat.worldBound.center)+new Vector2(48,-30);size=80;}
                var shown=group.Value.Take(3).ToArray();for(int i=shown.Length-1;i>=0;i--){var child=attachmentViews[shown[i].ObjectId];child.view.SetPresentation(CardPresentationMode.Compact,Mathf.Max(62,size*.88f));child.view.style.left=anchor.x+18+i*16;child.view.style.top=anchor.y+24+i*16;child.view.style.rotate=new Rotate(new Angle(child.card.Tapped==true?90:0));child.view.style.display=DisplayStyle.Flex;child.view.BringToFront();}
                parentView?.BringToFront();string target=group.Key;var count=new Button(()=>BrowseAttachments(target)){name="attachment-count-"+target,text=group.Value.Count.ToString(),tooltip="Attachments"};count.style.position=Position.Absolute;count.style.left=anchor.x+size-9;count.style.top=anchor.y+size*BattlefieldFrame.Aspect-12;count.style.width=28;count.style.height=26;GameplayTheme.Button(count);navigation.Add(count);
            }
            foreach(var item in items)item.view.RemoveFromClassList("in-hand");
            var hand=items.Where(i=>i.card.Zone=="hand" && i.card.OwnerId==viewer).ToList();
            GameplayCardLayout.RetainHandOrder(handOrder,hand.Select(item=>item.card.RenderId));
            hand=hand.OrderBy(item=>handOrder.IndexOf(item.card.RenderId)).ToList();
            // Opening uses the existing generous fan; normal hand keeps full proportions and reserves controls.
            root.EnableInClassList("opening-state",opening);
            // During first layout or a resize the panel can briefly be narrower than
            // the desktop target. Always give the fan a positive, bounded viewport.
            int handCount=hand.Count;
            GameplayCardLayout.Hand(hand,navigation,rowPages,Layout,CloseInspection,plan.HandBounds,plan.HandNavigationY,opening,plan.HandSize);
            var stack=items.Where(i=>i.card.Zone=="stack").ToList();
            stackTitle.text=stack.Count==0?"":"STACK · "+stack.Count;stackToolbar.style.display=stack.Count==0?DisplayStyle.None:DisplayStyle.Flex;
            var stackBounds=plan.StackBounds;var toolbarBounds=plan.StackToolbarBounds;var backdropBounds=plan.StackBackdropBounds;
            stackToolbar.style.left=toolbarBounds.x;stackToolbar.style.top=toolbarBounds.y;stackToolbar.style.width=toolbarBounds.width;
            stackBackdrop.style.display=stackFocused && stack.Count>0?DisplayStyle.Flex:DisplayStyle.None;stackBackdrop.style.left=backdropBounds.x;stackBackdrop.style.top=backdropBounds.y;stackBackdrop.style.width=backdropBounds.width;stackBackdrop.style.height=backdropBounds.height;
            Row(stack,stackBounds.y,stackBounds.x,stackBounds.width,plan.StackCardSize,full:true,key:"stack");
            foreach(var item in items)if(item.card.Zone!="stack")item.view.style.opacity=stackFocused?.72f:1;
            foreach(var item in stack)item.view.BringToFront();RefreshStackControls();stackToolbar.BringToFront();priorityDrawer.BringToFront();
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId!=viewer).ToList(),plan.OpponentCommandTop,15,130,65,key:"opponent-command");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId==viewer).ToList(),plan.LocalCommandTop,15,130,65,key:"local-command");
            zonePanel.Present(frame,Surface,plan.ZoneBankSeparation,openZone,openZoneOwner);zonePanelDrawer.RefreshInput();
            if(LayoutEditor?.OwnsGeometry(GameplayHudIds.Zones)!=true){zonePanelDrawer.Viewport.style.top=plan.ZoneViewportTop;zonePanelDrawer.style.maxHeight=30;zonePanelDrawer.Content.style.maxHeight=plan.ZoneMaxHeight;zonePanelDrawer.Q<ScrollView>("zone-panel-scroll").style.maxHeight=plan.ZoneMaxHeight;}
            hud.style.height=plan.PlayerHudHeight;
            root.EnableInClassList("browsing-public-zone",openZone!=null);
            zoneDrawer.style.display=openZone==null?DisplayStyle.None:DisplayStyle.Flex;
            if(openZone!=null){
                // A drawer is a presentation overlay, never another owner of card views.
                // Hide the table's cards while browsing, then place the same owned card root
                // above the backdrop. Bringing only children forward cannot cross sibling layers.
                foreach(var item in items)item.view.style.display=DisplayStyle.None;
                navigation.Clear();
                zoneDrawer.BringToFront();Surface.CardsRoot.BringToFront();
                var publicCards=openZone=="attachments"?items.Where(i=>attachmentGroups.TryGetValue(openZoneOwner,out var family) && family.Any(card=>card.ObjectId==i.card.ObjectId)).ToList():items.Where(i=>i.card.Zone==openZone && i.card.OwnerId==openZoneOwner && (openZone!="library" || !i.card.Hidden && i.card.FaceDown!=true)).ToList();
                int concealed=publicCards.Count(i=>i.card.Hidden || i.card.FaceDown==true);
                long? total=openZone=="library" && frame.PlayerLibraryCounts.TryGetValue(openZoneOwner,out var libraryCount)?libraryCount:null;
                zoneDrawer.Present(openZoneOwner,openZone,openZone=="attachments"?(attachmentViews.TryGetValue(openZoneOwner,out var enchanted)?enchanted.card.Characteristics?.Name:openZoneOwner==viewer?"You":"Opponent"):openZoneOwner==viewer?"Your zones":"Opponent zones",publicCards.Count-concealed,total,concealed);
                Row(publicCards,plan.PublicZoneBounds.y,plan.PublicZoneBounds.x,plan.PublicZoneBounds.width,plan.PublicZoneCardSize,true,"public-zone");
                foreach(var item in publicCards)if(item.view.style.display.value==DisplayStyle.Flex)item.view.BringToFront();
                navigation.BringToFront();zoneChoices.BringToFront();
            }
            zones.text=string.Join("\n",items.Where(i=>i.card.Zone!="hand" && i.card.Zone!="battlefield" && i.card.Zone!="stack").GroupBy(i=>i.card.Zone).Select(g=>g.Key+"  "+g.Count()));
            choices.EnableInClassList("opening-choices",opening);actionDrawer.EnableInClassList("opening-choices",opening);
            choices.EnableInClassList("library-ordering",Decisions!=null && Decisions.IsLibraryOrdering);actionDrawer.EnableInClassList("library-ordering",Decisions!=null && Decisions.IsLibraryOrdering);
            if(LayoutEditor?.OwnsGeometry(GameplayHudIds.Actions)!=true){
            actionDrawer.Viewport.style.width=plan.ActionViewportWidth;
            actionDrawer.Viewport.style.right=plan.ActionViewportRight;
            actionDrawer.Viewport.style.top=plan.ActionViewportTop.HasValue?(StyleLength)plan.ActionViewportTop.Value:StyleKeyword.Auto;
            actionDrawer.Viewport.style.bottom=plan.ActionViewportBottom.HasValue?(StyleLength)plan.ActionViewportBottom.Value:StyleKeyword.Auto;
            actionDrawer.Content.style.maxHeight=plan.ActionMaxHeight;}
            if(LayoutEditor?.OwnsGeometry(GameplayHudIds.Priority)!=true)priorityDrawer.Content.style.maxHeight=plan.PriorityMaxHeight;
            if(opening && Decisions!=null)GameplayTheme.Mulligan(Decisions.Root,handCount);
            if(inspecting)PlaceInspection();
            if(!inspecting && !previewing)Surface.InspectionView.style.display=DisplayStyle.None;
            foreach(var item in items){var availability=item.view.Q<Label>("status");if(availability!=null)availability.style.display=DisplayStyle.None;}
            actionDrawer.BringToFront();result.BringToFront();if(inspecting || previewing)Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();
            boardInput?.Refresh();RefreshPlayers();targeting?.Observe(frame);links.schedule.Execute(UpdateLinks);LayoutEditor?.AfterLegacyLayout();
        }
        public void Dispose(){if(disposed)return;LayoutEditor?.Dispose();LayoutEditor=null;ClearZoneResources();disposed=true;targeting?.Dispose();boardInput?.Dispose();animations.Dispose();inspector.Dispose();priorityBinding?.Dispose();actionBinding?.Dispose();Decisions?.Dispose();Surface.Clearing-=ClearZoneResources;Surface.Rebinding-=ClearPileArt;Surface.Dispose();
            hud.PlayerActivated-=ActivatePlayer;hud.Dispose();zonePanel.BrowseRequested-=BrowseZone;zonePanel.Dispose();zonePanelDrawer.Dispose();if(actionBinding==null)actionDrawer.Dispose();if(priorityBinding==null)priorityDrawer.Dispose();zoneDrawer.Dispose();HudRegistry.Dispose();wired.Clear();root.RemoveFromHierarchy();}
    }
}

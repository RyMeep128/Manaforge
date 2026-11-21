using System;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class ArenaGameplayPresentation : IGameplayPresentation,IOrganizationPresentation
    {
        private readonly VisualElement inspectionInputRoot;
        private readonly VisualElement root,choices,navigation,opponentHand,zoneChoices;
        private readonly ZoneBrowser zoneDrawer;
        private readonly Label stackTitle;
        private readonly VisualElement stackPanel,stackBackdrop,stackToolbar,stackCards;
        private long stackForegroundOrder;
        private readonly Button stackToggle,resolveNext,resolveAll;
        private bool stackFocused;private float stackAttentionUntil;
        private readonly System.Collections.Generic.HashSet<string> seenStack=new System.Collections.Generic.HashSet<string>();
        private readonly GameplayZonePanel zonePanel;private readonly GameplayDrawer actionDrawer,priorityDrawer,zonePanelDrawer,turnsDrawer;private GameplayActionDrawer actionBinding;private GameplayPriorityDrawer priorityBinding;private string openZone,openZoneOwner,previewId;private bool previewing;
        private string dismissedZoneDecision;
        private CardView hoveredCard,focusedCard,emphasizedCard;private string hoveredId,focusedId,emphasizedId;
        private readonly System.Collections.Generic.Dictionary<string,int> rowPages=new System.Collections.Generic.Dictionary<string,int>();
        private readonly System.Collections.Generic.List<string> handOrder=new System.Collections.Generic.List<string>();
        private readonly Label status,result,zones;private readonly GameplayPlayerHud hud;
        private bool unsupportedTopology,restoringFocus;
        private readonly Button originalCard;
        private readonly VisualElement amountOverlay,amountSurface;private readonly ScrollView amountScroll;private readonly Label amountTitle;private readonly Button reopenAmounts;private string amountDecision;private bool amountMinimized;
        private readonly GameplayDrawer[] foregroundDrawers;
        private readonly GameplayPhaseStrip phaseStrip;
        private readonly GameplayScrollRegions cardScrolling,stackScrolling;
        private readonly GameplayOverlay inspector;
        private readonly IVisualElementScheduledItem combatLinksRefresh;
        private readonly BattlefieldLinks links;private readonly GameplayAnimationCoordinator animations;private ViewerBoardInput boardInput;private bool disposed;
        private readonly System.Collections.Generic.HashSet<CardView> wired=new System.Collections.Generic.HashSet<CardView>();
        private ViewerTargetingController targeting;
        private BattlefieldOrganizationRenderer organizationRenderer;
        private ViewerSessionHost host;private ProjectedDecisionFrame frame;private bool inspecting;private int artworkCount=-1;
        private bool layoutAttentionFocus;
        private IVisualElementScheduledItem focusRefresh;
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
            stackPanel=new VisualElement{name="stack-panel"};stackPanel.style.position=Position.Absolute;stackPanel.style.display=DisplayStyle.None;root.Add(stackPanel);
            stackBackdrop=new VisualElement{name="stack-focus-backdrop",pickingMode=PickingMode.Ignore};stackBackdrop.style.position=Position.Absolute;stackBackdrop.style.left=stackBackdrop.style.right=stackBackdrop.style.top=stackBackdrop.style.bottom=0;stackBackdrop.style.backgroundColor=new Color(.025f,.035f,.05f,.98f);stackBackdrop.style.borderTopLeftRadius=stackBackdrop.style.borderTopRightRadius=stackBackdrop.style.borderBottomLeftRadius=stackBackdrop.style.borderBottomRightRadius=12;stackBackdrop.style.display=DisplayStyle.None;stackPanel.Add(stackBackdrop);
            Surface=new ViewerCardSurface(root,cardBacks);cardScrolling=new GameplayScrollRegions(Surface.CardsRoot);Surface.CardsRoot.AddToClassList("table-cards");Surface.CardsRoot.pickingMode=PickingMode.Ignore;
            stackCards=new VisualElement{name="stack-cards",pickingMode=PickingMode.Ignore};stackCards.AddToClassList("table-cards");stackCards.style.display=DisplayStyle.None;stackPanel.Add(stackCards);stackScrolling=new GameplayScrollRegions(stackCards);
            Surface.InspectionView.AddToClassList("table-inspection");Surface.InspectionView.SetPresentation(CardPresentationMode.Full,290);Surface.InspectionView.style.display=DisplayStyle.None;
            links=new BattlefieldLinks();root.Add(links);links.SetSource(BuildCombatLinks);combatLinksRefresh=links.schedule.Execute(()=>{if(!disposed && frame?.Combat.Count>0)links.MarkDirtyRepaint();}).Every(16);
            navigation=new VisualElement{name="board-navigation",pickingMode=PickingMode.Ignore};root.Add(navigation);
            turnsDrawer=new GameplayDrawer("Turns",GameplayDrawerDirection.Down,true){name="turns-panel"};root.Add(turnsDrawer);
            status=Label("table-phase","Connecting...");turnsDrawer.Content.Add(status);status.style.position=Position.Relative;status.style.left=status.style.top=0;status.style.width=StyleKeyword.Auto;status.style.height=34;status.style.fontSize=13;status.style.paddingLeft=status.style.paddingRight=status.style.paddingTop=status.style.paddingBottom=0;status.style.marginBottom=4;
            phaseStrip=new GameplayPhaseStrip(turnsDrawer.Content,()=>Decisions?.Priority,()=>{Decisions?.PrioritySettingsChanged();if(frame!=null)phaseStrip.Present(frame,Decisions?.Priority);});
            phaseStrip.Root.style.position=Position.Relative;phaseStrip.Root.style.left=phaseStrip.Root.style.top=0;phaseStrip.Root.style.height=28;
            foreach(var button in phaseStrip.Root.Query<Button>().ToList()){button.style.minWidth=0;button.style.flexGrow=1;button.style.flexShrink=1;button.style.fontSize=11;button.style.paddingLeft=button.style.paddingRight=2;button.style.marginRight=2;}
            turnsDrawer.Content.style.paddingLeft=turnsDrawer.Content.style.paddingRight=8;turnsDrawer.Content.style.paddingTop=turnsDrawer.Content.style.paddingBottom=8;
            PlaceTurns();
            hud=new GameplayPlayerHud(localSeatAtBottom:true,registry:HudRegistry,lifePanel:true);hud.AddToClassList("arena-player-hud");root.Add(hud);root.Add(hud.LifeDrawer);hud.PlayerActivated+=ActivatePlayer;
            zonePanelDrawer=new GameplayDrawer("Zones",GameplayDrawerDirection.Left,true){name="zones-drawer"};root.Add(zonePanelDrawer);
            var zoneScroll=new ScrollView(ScrollViewMode.Vertical){name="zone-panel-scroll",horizontalScrollerVisibility=ScrollerVisibility.Hidden};zoneScroll.pickingMode=PickingMode.Ignore;zoneScroll.contentViewport.pickingMode=PickingMode.Ignore;zoneScroll.contentContainer.pickingMode=PickingMode.Ignore;zoneScroll.style.maxHeight=Length.Percent(100);zonePanelDrawer.Content.Add(zoneScroll);
            zonePanel=new GameplayZonePanel(Surface.CardBacks);zoneScroll.Add(zonePanel);zonePanel.BrowseRequested+=BrowseZone;
            Surface.Clearing+=ClearZoneResources;Surface.Rebinding+=ClearPileArt;
            opponentHand=new VisualElement{name="opponent-hand",pickingMode=PickingMode.Ignore};root.Add(opponentHand);
            zones=Label("table-zones","");zones.style.display=DisplayStyle.None;
            zoneChoices=new VisualElement{name="public-zone-choices"};zoneChoices.style.display=DisplayStyle.None;root.Add(zoneChoices);
            zoneDrawer=new ZoneBrowser(Surface.CardBacks);root.Add(zoneDrawer);zoneDrawer.BrowseRequested+=BrowseZone;zoneDrawer.Closed+=ClosePublicZone;
            stackToolbar=new VisualElement{name="stack-toolbar"};stackToolbar.style.position=Position.Absolute;stackToolbar.style.left=stackToolbar.style.right=10;stackToolbar.style.top=6;stackToolbar.style.height=36;stackToolbar.style.flexDirection=FlexDirection.Row;stackToolbar.style.alignItems=Align.Center;stackPanel.Add(stackToolbar);
            stackTitle=new Label{name="stack-title",enableRichText=false};stackTitle.style.position=Position.Relative;stackTitle.style.top=0;stackTitle.style.right=0;stackTitle.style.width=StyleKeyword.Auto;stackTitle.style.flexGrow=1;stackToolbar.Add(stackTitle);
            stackToggle=new Button(()=>{stackFocused=!stackFocused;stackForegroundOrder=GameplayDrawer.NextForegroundOrder();Layout();}){name="stack-focus-toggle",text="Minimize"};stackToolbar.Add(stackToggle);GameplayTheme.Button(stackToggle);
            resolveNext=new Button(()=>{if(Decisions?.Presentation?.Compact==true)Decisions.CancelPriorityYield();else Decisions?.TryPassPriority();RefreshStackControls();}){name="stack-resolve-next",text="Resolve next"};stackToolbar.Add(resolveNext);GameplayTheme.Button(resolveNext,true);
            resolveAll=new Button(()=>{if(Decisions==null)return;if(Decisions.Priority.Current.Yield=="resolve-stack")Decisions.CancelPriorityYield();else if(CanResolveStack()){Decisions.Priority.BeginYield("resolve-stack",Decisions.PriorityFrame);stackAttentionUntil=0;}Decisions.PrioritySettingsChanged();RefreshStackControls();}){name="stack-resolve-all",text="Resolve All"};stackToolbar.Add(resolveAll);GameplayTheme.Button(resolveAll,true);stackToolbar.style.display=DisplayStyle.None;
            stackTitle.style.fontSize=13;stackTitle.style.minWidth=60;
            foreach(var control in new[]{stackToggle,resolveNext,resolveAll}){control.style.height=control.style.minHeight=30;control.style.fontSize=13;control.style.marginTop=control.style.marginBottom=0;control.style.paddingTop=control.style.paddingBottom=4;control.style.paddingLeft=control.style.paddingRight=8;}
            actionDrawer=new GameplayDrawer("Actions",GameplayDrawerDirection.Right){name="action-drawer"};root.Add(actionDrawer);
            choices=new ScrollView(ScrollViewMode.Vertical){name="table-choices"};actionDrawer.Content.Add(choices);
            reopenAmounts=new Button(()=>{ClosePublicZone();amountMinimized=false;PresentAmountPopup();}){name="reopen-amount-assignment",text="Continue assigning amounts"};GameplayTheme.Button(reopenAmounts,true);reopenAmounts.style.display=DisplayStyle.None;choices.Add(reopenAmounts);
            amountOverlay=new VisualElement{name="amount-assignment-overlay"};amountOverlay.style.position=Position.Absolute;amountOverlay.style.left=amountOverlay.style.right=amountOverlay.style.top=amountOverlay.style.bottom=0;amountOverlay.style.justifyContent=Justify.Center;amountOverlay.style.alignItems=Align.Center;amountOverlay.style.backgroundColor=new Color(.015f,.02f,.03f,.82f);amountOverlay.style.display=DisplayStyle.None;root.Add(amountOverlay);
            amountSurface=new VisualElement{name="amount-assignment-popup"};amountSurface.style.backgroundColor=new Color(.075f,.10f,.13f,1);amountSurface.style.paddingLeft=amountSurface.style.paddingRight=16;amountSurface.style.paddingTop=amountSurface.style.paddingBottom=12;amountOverlay.Add(amountSurface);
            var amountHeader=new VisualElement();amountHeader.style.flexDirection=FlexDirection.Row;amountHeader.style.alignItems=Align.Center;amountSurface.Add(amountHeader);
            amountTitle=new Label("Assign amounts"){enableRichText=false};amountTitle.style.flexGrow=1;amountTitle.style.fontSize=23;amountTitle.style.color=Color.white;amountHeader.Add(amountTitle);
            var minimizeAmounts=new Button(MinimizeAmounts){name="minimize-amount-assignment",text="Back to battlefield"};GameplayTheme.Button(minimizeAmounts);amountHeader.Add(minimizeAmounts);
            amountScroll=new ScrollView(ScrollViewMode.Vertical){name="amount-assignment-scroll",horizontalScrollerVisibility=ScrollerVisibility.Hidden,verticalScrollerVisibility=ScrollerVisibility.Hidden};amountScroll.style.flexShrink=1;amountScroll.style.marginTop=10;amountSurface.Add(amountScroll);

            priorityDrawer=new GameplayDrawer("Stops & settings",GameplayDrawerDirection.Right){name="priority-drawer"};root.Add(priorityDrawer);
            var motion=new Toggle("Reduced motion"){name="table-motion",value=false};motion.RegisterValueChangedCallback(ev=>{root.EnableInClassList("reduced-motion",ev.newValue);animations?.Advance();foreach(var drawer in new[]{actionDrawer,priorityDrawer,zonePanelDrawer,turnsDrawer,hud.CommanderDrawer})drawer.SetReducedMotion(ev.newValue);if(frame!=null)hud.Present(frame,Surface,host?.GameplayFormat,ev.newValue,InspectCard);Layout();});root.Add(motion);
            animations=new GameplayAnimationCoordinator(root,Surface,MotionZoneAnchor,MotionPlayerAnchor,()=>motion.value,objectAnchor:ResolveCardAnchor);
            result=Label("table-result","");CardTypography.Apply(result,CardTextRole.Title);result.style.display=DisplayStyle.None;
            var close=new Button(()=>CloseInspection()){text="Close inspection | Esc",name="close-inspection"};root.Add(close);close.style.display=DisplayStyle.None;
            originalCard=new Button(()=>{Surface.InspectionView.SetOriginalPrinting(!Surface.InspectionView.ShowingOriginalPrinting);PlaceInspection();}){name="view-original-card",text="Original card",tooltip="View the original printed card"};GameplayTheme.Button(originalCard);originalCard.style.position=Position.Absolute;originalCard.style.display=DisplayStyle.None;root.Add(originalCard);
            foregroundDrawers=new[]{actionDrawer,priorityDrawer,zonePanelDrawer,turnsDrawer,hud.LifeDrawer,hud.CommanderDrawer};foreach(var drawer in foregroundDrawers)drawer.ForegroundChanged+=RefreshForegroundLayers;
            inspector=new GameplayOverlay(Surface.InspectionView,close);inspectionInputRoot=parent;inspectionInputRoot.RegisterCallback<PointerDownEvent>(DismissZone,TrickleDown.TrickleDown);inspectionInputRoot.RegisterCallback<PointerDownEvent>(DismissInspection,TrickleDown.TrickleDown);inspectionInputRoot.RegisterCallback<KeyDownEvent>(OverlayKey,TrickleDown.TrickleDown);
            root.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Escape){CloseInspection();ClosePublicZone();}});
            root.RegisterCallback<GeometryChangedEvent>(ev=>Layout());
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Hand,"Hand","hand"),adapter:new GameplayHudLayoutAdapter(GameplayLayoutSlot.Hand));
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Battlefield,"Battlefield","battlefield"),adapter:new GameplayHudLayoutAdapter(GameplayLayoutSlot.Battlefield));
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.GameStack,"Game stack","game-stack"),stackToolbar,new GameplayHudLayoutAdapter(GameplayLayoutSlot.GameStack));
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Turns,"Turns","turns",GameplayHudCapabilities.Drawer,presetKey:"hud.turns"),turnsDrawer);
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Priority,"Stops and settings","priority",GameplayHudCapabilities.Drawer,presetKey:"hud.priority"),priorityDrawer);
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Actions,"Actions","actions",GameplayHudCapabilities.Drawer,presetKey:"hud.actions"),actionDrawer);
            HudRegistry.Register(new GameplayHudDescriptor(GameplayHudIds.Zones,"Zones","zones",GameplayHudCapabilities.Drawer,presetKey:"hud.zones"),zonePanelDrawer);
            // Zone families share a panel; these are logical child descriptors, not new pile owners.
            foreach(string zone in new[]{"library","graveyard","exile"})
                HudRegistry.Register(new GameplayHudDescriptor("zones/"+zone,ZonePile.Title(zone),"zones",parentId:GameplayHudIds.Zones),zonePanel);
        }
        private void MinimizeAmounts(){amountMinimized=true;actionDrawer.SetOpen(true);PresentAmountPopup();}
        private void ResetAmountPopup()
        {
            // Restore the decision to its destination regardless of which popup
            // wrapper currently owns it. A hidden popup must not retain the next choice.
            if(Decisions!=null && Decisions.Root.parent!=choices.contentContainer){choices.Add(Decisions.Root);((ScrollView)choices).scrollOffset=Vector2.zero;}
            amountOverlay.style.display=DisplayStyle.None;reopenAmounts.style.display=DisplayStyle.None;amountDecision=null;amountMinimized=false;
        }
        private void PresentAmountPopup()
        {
            bool amounts=frame?.Decision?.Family=="amounts" && Decisions!=null;
            if(!amounts){ResetAmountPopup();return;}
            if(amountDecision!=frame.Decision.DecisionId){amountDecision=frame.Decision.DecisionId;amountMinimized=false;ClearCardFocus();CloseInspection();}
            if(Decisions.Root.parent!=amountScroll.contentContainer)amountScroll.Add(Decisions.Root);
            amountTitle.text=frame.Combat.Count>0 && (frame.Step=="COMBAT_DAMAGE" || frame.Step=="FIRST_COMBAT_DAMAGE")?"Assign combat damage":"Assign amounts";
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            amountSurface.style.width=Mathf.Max(280,Mathf.Min(980,width-48));amountSurface.style.maxHeight=Mathf.Max(200,height-64);amountScroll.style.maxHeight=Mathf.Max(140,height-144);
            amountOverlay.style.display=amountMinimized?DisplayStyle.None:DisplayStyle.Flex;reopenAmounts.style.display=amountMinimized?DisplayStyle.Flex:DisplayStyle.None;
            if(!amountMinimized)amountOverlay.BringToFront();
        }
        private void PlaceTurns()
        {
            if(LayoutEditor?.OwnsGeometry(GameplayHudIds.Turns)==true)return;
            turnsDrawer.style.left=16;turnsDrawer.style.top=12;turnsDrawer.style.width=252;turnsDrawer.style.height=30;
            turnsDrawer.Viewport.style.position=Position.Absolute;turnsDrawer.Viewport.style.left=0;turnsDrawer.Viewport.style.top=32;turnsDrawer.Viewport.style.width=252;turnsDrawer.Viewport.style.height=100;turnsDrawer.Viewport.style.paddingTop=0;turnsDrawer.Content.style.height=100;
        }
        private Vector2? MotionPlayerAnchor(string player)
        {
            return hud.TryPlayerBounds(player,root,out var bounds)?(Vector2?)bounds.center:null;
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
        private void ClearPileArt(){cardScrolling.ClearHandLayout();zonePanel.ClearArtwork();}
        private void ClearZoneResources()
        {
            ResetAmountPopup();focusRefresh?.Pause();focusRefresh=null;StableStatusText.Set(status,status.text,true);cardScrolling?.Dispose();stackScrolling?.Dispose();organizationRenderer?.Clear();LayoutEditor?.EndSession();
            seenStack.Clear();stackFocused=false;stackForegroundOrder=0;stackAttentionUntil=0;stackPanel.style.display=stackCards.style.display=stackToolbar.style.display=stackBackdrop.style.display=DisplayStyle.None;hud?.ClearPresentation();ClearCardFocus();inspecting=false;inspector?.Hide(false);CloseInspection();openZone=openZoneOwner=null;opponentHand.Clear();animations?.Clear();links.MarkDirtyRepaint();
            zoneDrawer?.ClearBinding();
            root.RemoveFromClassList("browsing-public-zone");frame=null;dismissedZoneDecision=null;rowPages.Clear();handOrder.Clear();
            zonePanel.ClearBinding();if(actionBinding!=null)actionBinding.Reset();else actionDrawer.Reset();priorityDrawer.Reset();zonePanelDrawer.Reset(true);

        }
        private Label Label(string name,string text){var label=new Label(text){name=name,enableRichText=false};root.Add(label);return label;}
        public void InterruptGestures(){boardInput?.InterruptGesture();targeting?.InterruptGesture();organizationRenderer?.Interrupt();}
        public void PresentOrganization(ProjectedOrganizationFrame value){if(!disposed)organizationRenderer?.Observe(value);}
        private void OverlayKey(KeyDownEvent ev)
        {
            bool typing=false;for(var element=ev.target as VisualElement;element!=null;element=element.parent)if(element is TextField){typing=true;break;}
            if(!disposed && Decisions?.PrioritySessionActive==true && !Decisions.LayoutEditing && !typing
                && root.parent?.Q("game-menu-overlay")?.resolvedStyle.display!=DisplayStyle.Flex){
                bool handled=false;
                if(ev.keyCode==KeyCode.LeftControl || ev.keyCode==KeyCode.RightControl){
                    if(ev.shiftKey){Decisions.Priority.SetTemporaryFullControl(false,frame);Decisions.Priority.Current.Manual=!Decisions.Priority.Current.Manual;}
                    else Decisions.Priority.SetTemporaryFullControl(!Decisions.Priority.Current.TemporaryFullControl,frame);
                    handled=true;
                }
                else if((ev.keyCode==KeyCode.LeftShift || ev.keyCode==KeyCode.RightShift) && ev.ctrlKey){Decisions.Priority.SetTemporaryFullControl(false,frame);Decisions.Priority.Current.Manual=!Decisions.Priority.Current.Manual;handled=true;}
                else if(ev.keyCode==KeyCode.Space)handled=Decisions.TryPassPriority();
                else if(ev.keyCode==KeyCode.Return || ev.keyCode==KeyCode.KeypadEnter)handled=Decisions.TryBeginPriorityYield(ev.shiftKey?"end-turn":"response");
                if(handled){Decisions.PrioritySettingsChanged();ev.StopImmediatePropagation();return;}
            }
            if(disposed || ev.keyCode!=KeyCode.Escape)return;
            if(amountOverlay.style.display.value==DisplayStyle.Flex){MinimizeAmounts();ev.StopImmediatePropagation();return;}
            if(openZone!=null){ClosePublicZone();ev.StopImmediatePropagation();}
            else if(inspecting || previewing){CloseInspection();ev.StopImmediatePropagation();}
        }
        private void DismissZone(PointerDownEvent ev)
        {
            if(disposed || openZone==null || !(ev.target is VisualElement target))return;
            if(target==reopenAmounts || reopenAmounts.Contains(target) || target==zoneDrawer || zoneDrawer.Contains(target) || target==originalCard || originalCard.Contains(target)
                || inspecting && (target==Surface.InspectionView || Surface.InspectionView.Contains(target) || target==root.Q<Button>("close-inspection")))return;
            for(var element=target;element!=null && element!=root;element=element.parent)if(element is CardView || element is ScrollView && Surface.CardsRoot.Contains(element))return;
            if(zoneDrawer.worldBound.Contains(ev.position))return;
            ClosePublicZone();ev.StopImmediatePropagation();
        }
        private void DismissInspection(PointerDownEvent ev)
        {
            if(disposed || !inspecting && !previewing || !(ev.target is VisualElement target))return;
            var content=Surface.InspectionView;var close=root.Q<Button>("close-inspection");
            if(target==originalCard || originalCard.Contains(target) || target==content || content.Contains(target) || target==close || close!=null && close.Contains(target))return;
            CloseInspection(false);
        }
        public void CloseInspection()=>CloseInspection(true);
        private void CloseInspection(bool restoreFocus){originalCard.style.display=DisplayStyle.None;Surface.InspectionView.SetOriginalPrinting(false);bool restore=inspecting && restoreFocus;inspecting=false;previewing=false;previewId=null;restoringFocus=true;try{inspector?.Hide(restore);}finally{restoringFocus=false;}}
        public void Bind(ViewerSessionHost value)
        {if(Decisions!=null)throw new InvalidOperationException("PRESENTATION_ALREADY_BOUND");host=value;Decisions=new ViewerDecisionPanel(choices,host);Decisions.PresentationHold=()=>animations.HoldAutomaticPassing || Time.unscaledTime<stackAttentionUntil;Decisions.SetSpatialPresentation(true);Decisions.UseUnifiedPriorityActions(()=>priorityDrawer.SetOpen(true,true));Decisions.SetChoicePreview(Surface.ChoicePreview);Decisions.SetChoiceArtworkState(()=>Surface.PresentedArtworkCount);Surface.Rebinding+=Decisions.InvalidateAmountArtwork;actionBinding=new GameplayActionDrawer(actionDrawer,Decisions);priorityBinding=new GameplayPriorityDrawer(priorityDrawer,Decisions);targeting=new ViewerTargetingController(root,Surface,Decisions,()=>hud.Players,ResolveCardAnchor);boardInput=new ViewerBoardInput(root,Surface,host,Decisions,GameplayTheme.Menu);
            if(Capabilities.SharedOrganization)organizationRenderer=new BattlefieldOrganizationRenderer(root,host,Layout,()=>{boardInput.InterruptGesture();targeting.InterruptGesture();},()=>LayoutEditor?.IsEditing==true || Decisions.LayoutEditing || host.PendingReveal!=null || inspecting || openZone!=null,
                id=>{var offered=host.PresentedDecision;var current=offered?.Frame;return offered?.CanSubmit==true && current?.Decision!=null && (current.Decision.Family=="mana"?current.ManaSourceReferences.Any(source=>source.ObjectId==id):Decisions.ObjectChoiceCount(offered,id)>0);},
                ()=>LayoutEditor?.IsEditing==true || Decisions.SuppressSpatialInput || Decisions.IsLibraryOrdering || host.PendingReveal!=null || openZone!=null,RefreshForegroundLayers);
            if(Capabilities.PrivateLayout)LayoutEditor=new HudLayoutEditor(root.parent,root,HudRegistry,
                new[]{(GameplayHudIds.Turns,"Turns",turnsDrawer),(GameplayHudIds.Players,"Players",hud.LifeDrawer),(GameplayHudIds.Priority,"Stops & settings",priorityDrawer),(GameplayHudIds.Actions,"Actions",actionDrawer),(GameplayHudIds.Zones,"Zones",zonePanelDrawer),(GameplayHudIds.Commanders,"Commanders",hud.CommanderDrawer)},
                layoutPresetStore??new JsonLayoutPresetStore(System.IO.Path.Combine(Application.persistentDataPath,"profiles","default","layouts","arena")),
                ()=>{InterruptGestures();ClearCardFocus();CloseInspection();ClosePublicZone();},Layout,Decisions.SetLayoutEditing,()=>LayoutAttentionRequired(),FocusGameplayAttention,previewRoots:new VisualElement[]{zonePanel,zoneDrawer,navigation,Surface.InspectionView,root.Q<Button>("close-inspection")},closePreviews:()=>{CloseInspection();ClosePublicZone();});
        }
        private void RefreshForegroundLayers()
        {
            if(disposed)return;
            var layers=foregroundDrawers.Select(drawer=>(order:drawer.ForegroundOrder,element:drawer.parent==hud?(VisualElement)hud:drawer));
            if(organizationRenderer!=null)layers=layers.Concat(organizationRenderer.ForegroundLayers);
            // Keep the stack's backdrop, cards, and controls together without raising
            // battlefield cards. Later-opened drawers retain their newer order.
            if(seenStack.Count>0)layers=layers.Concat(new[]{(order:stackForegroundOrder,element:stackPanel)});
            foreach(var layer in layers.Where(layer=>layer.element.parent==root).OrderBy(layer=>layer.order))layer.element.BringToFront();
            if(openZone!=null){zoneDrawer.BringToFront();Surface.CardsRoot.BringToFront();navigation.BringToFront();zoneChoices.BringToFront();}
            organizationRenderer?.BringToolsToFront();result.BringToFront();
            if(inspecting || previewing){Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();originalCard.BringToFront();}
            root.Q<VisualElement>("board-object-menu")?.BringToFront();LayoutEditor?.BringToFront();if(amountOverlay.style.display.value==DisplayStyle.Flex)amountOverlay.BringToFront();
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
            var current=host?.PresentedDecision;var value=current?.Frame??frame;
            return host==null || !host.Authenticated || host.Completion.IsCompleted || host.PendingReveal!=null || value==null || value.Result!=null;
        }
        public Vector2? ResolveCardAnchor(string objectId)=>organizationRenderer?.CardAnchor(objectId);
        public bool DismissBattlefieldPrompt()=>organizationRenderer?.DismissPrompt()==true;
        public bool OpenBattlefieldGroups()=>organizationRenderer?.OpenTools()==true;
        public bool OpenBattlefieldMembers(string groupId)=>organizationRenderer?.OpenMembers(groupId)==true;
        public void CloseBattlefieldMembers()=>organizationRenderer?.CloseMembers();
        public void BeforeDecisionTick()
        {organizationRenderer?.ObserveOffer(host?.PresentedDecision);bool editing=LayoutEditor?.IsEditing==true;LayoutEditor?.BeforeDecisionTick(LayoutAttentionRequired());if(editing && LayoutEditor?.IsEditing==false){layoutAttentionFocus=true;if(host?.PendingReveal!=null)root.parent?.Q<Button>("reveal-acknowledge")?.Focus();}}
        public void Present(ProjectedDecisionFrame value)
        {
            if(disposed)return;
            Decisions?.Priority.Observe(value);
            LayoutEditor?.Observe(value.Context.SessionId,value.Context.ViewerId,LayoutAttentionRequired(),false,value.Result!=null);
            var seatIds=value.PlayerLifeTotals.Keys.ToArray();
            if(!seatIds.Contains(value.Context.ViewerId)){
                unsupportedTopology=true;ClearZoneResources();Surface.CardsRoot.style.display=DisplayStyle.None;choices.style.display=DisplayStyle.None;
                StableStatusText.Set(status,"The viewer seat is unavailable.",true);return;
            }
            unsupportedTopology=false;Surface.CardsRoot.style.display=DisplayStyle.Flex;choices.style.display=DisplayStyle.Flex;
            hud.Present(value,Surface,host?.GameplayFormat,root.ClassListContains("reduced-motion"),InspectCard);
            actionBinding?.Refresh(value);if(layoutAttentionFocus){layoutAttentionFocus=false;if(host?.PendingReveal==null && value.Decision!=null && !value.Decision.IsPriority && value.Decision.PlayerId==value.Context.ViewerId)actionDrawer.SetOpen(true,true);}
            priorityBinding?.Refresh();zonePanelDrawer.RefreshInput();RefreshStackControls();
            phaseStrip.Present(value,Decisions?.Priority);
            if(frame!=null && frame.Context.Revision==value.Context.Revision && frame.Context.SessionId==value.Context.SessionId && frame.Context.ViewerId==value.Context.ViewerId){boardInput?.Refresh();RefreshPlayers();targeting?.Observe(frame);if(artworkCount!=Surface.PresentedArtworkCount){artworkCount=Surface.PresentedArtworkCount;Layout();}return;}
            artworkCount=Surface.PresentedArtworkCount;
            if(frame==null || frame.Context.SessionId!=value.Context.SessionId || frame.Context.ViewerId!=value.Context.ViewerId){
                ClearCardFocus();CloseInspection();
            }
            bool newStack=value.StackIds.Any(id=>!seenStack.Contains(id));
            seenStack.Clear();foreach(string id in value.StackIds)seenStack.Add(id);
            if(newStack){stackFocused=true;stackForegroundOrder=GameplayDrawer.NextForegroundOrder();stackAttentionUntil=Time.unscaledTime+.9f;rowPages["stack"]=0;}
            if(value.StackIds.Count==0){stackFocused=false;stackAttentionUntil=0;}
            frame=value;if(frame.Decision?.Family=="amounts" && amountDecision!=frame.Decision.DecisionId && openZone!=null){openZone=openZoneOwner=null;zoneDrawer.ClearBinding();}targeting?.Observe(value);
            string viewer=frame.Context.ViewerId;
            UpdateOpponentHand(OpponentId());
            string phaseText=frame.UnsupportedFields.Contains("decision")?"This choice cannot be displayed. Report code: "+(frame.DecisionError??"DECISION_UNSUPPORTED"):(frame.ActivePlayerId==viewer?"Your turn":"Opponent’s turn")+" · "+frame.Turn+"\n"+PhaseName(frame.Phase);
            if(frame.Turn==0 || frame.Decision?.Family=="mulligan" || (frame.Decision?.Prompt??"").StartsWith("Mulligan",StringComparison.OrdinalIgnoreCase))phaseText="Opening hand";
            if(frame.SessionNotice!=null)phaseText+="\nA permission request could not be displayed. Code: "+frame.SessionNotice;
            StableStatusText.Set(status,phaseText,frame.Result!=null || frame.UnsupportedFields.Contains("decision"));
            result.text=frame.Result==null?"":frame.Result=="win"?"Victory":frame.Result=="loss"?"Defeat":frame.Result=="draw"?"Draw":"Game complete\n"+frame.Result;result.style.display=frame.Result==null?DisplayStyle.None:DisplayStyle.Flex;if(frame.Result!=null)result.BringToFront();
            if(Decisions!=null)GameplayTheme.Decision(Decisions,frame);
            OpenOfferedZone();Layout();animations.Observe(frame,Surface.TakeAnimations());
        }
        private bool CanResolveStack(){var offered=Decisions?.CurrentOffer;var value=offered?.Frame;return offered?.CanSubmit==true && value?.StackIds.Count>0 && value.Decision?.IsPriority==true && value.Decision.PlayerId==value.Context.ViewerId && value.PriorityPlayerId==value.Context.ViewerId && value.Actions.Count(a=>a.Kind=="pass" && a.ObjectId==null)==1 && !Decisions.Priority.Current.Paused;}
        private void RefreshStackControls(){if(resolveAll==null)return;bool running=Decisions?.Priority.Current.Yield=="resolve-stack",yielding=Decisions?.Presentation?.Compact==true;resolveNext.text=yielding?"Cancel passing":"Resolve next";resolveNext.SetEnabled(yielding || CanResolveStack());resolveAll.text=running?"Cancel":"Resolve All";resolveAll.style.display=DisplayStyle.Flex;resolveAll.SetEnabled(running || CanResolveStack());stackToggle.text=stackFocused?"Minimize":"View";}
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
        private System.Collections.Generic.IEnumerable<BattlefieldLinks.Link> BuildCombatLinks()
        {
            if(disposed || frame==null)return Array.Empty<BattlefieldLinks.Link>();var centers=new System.Collections.Generic.Dictionary<string,Vector2>();
            Surface.VisitPresented((card,view)=>{if(!card.Hidden && BattlefieldCardAnchorResolver.TryResolve(links,view,organizationRenderer?.HiddenMemberAnchor(card.ObjectId),out var center))centers[card.ObjectId]=center;});
            var playerBounds=new System.Collections.Generic.Dictionary<string,Rect>();foreach(var seat in hud.Players)if(hud.TryPlayerBounds(seat.PlayerId,links,out var bounds)){playerBounds[seat.PlayerId]=bounds;centers[seat.PlayerId]=bounds.center;}
            var paths=new System.Collections.Generic.List<BattlefieldLinks.Link>();
            foreach(var group in frame.Combat){
                foreach(var attacker in group.AttackerIds)if(centers.TryGetValue(attacker,out var start) && group.DefenderId!=null && centers.TryGetValue(group.DefenderId,out var end))paths.Add(new BattlefieldLinks.Link(start,playerBounds.TryGetValue(group.DefenderId,out var defender)?BattlefieldLinks.OutsideEdge(defender,start):end,new Color(1,.42f,.18f,.8f)));
                if(group.AttackerIds.Count==1 && centers.TryGetValue(group.AttackerIds[0],out var target))foreach(var blocker in group.BlockerIds)if(centers.TryGetValue(blocker,out var start))paths.Add(new BattlefieldLinks.Link(start,target,new Color(.3f,.7f,1,.9f)));
            }return paths;
        }
        private void ClearCardFocus()
        {
            if(emphasizedCard!=null)Lower(emphasizedCard,emphasizedId);
            hoveredCard=focusedCard=emphasizedCard=null;hoveredId=focusedId=emphasizedId=null;
        }
        private void QueueCardFocusRefresh()
        {
            if(disposed || focusRefresh!=null)return;
            // Focus/leave/detach can be dispatched inside UI Toolkit hierarchy mutations.
            // Reordering or reparenting the hand there corrupts native picking handles.
            focusRefresh=root.schedule.Execute(()=>{focusRefresh=null;if(!disposed && frame!=null)RefreshCardFocus();});
        }
        private void RefreshCardFocus()
        {
            if(disposed)return;
            if(emphasizedCard!=null)Lower(emphasizedCard,emphasizedId);
            emphasizedCard=hoveredCard??focusedCard;emphasizedId=hoveredCard!=null?hoveredId:focusedId;
            bool admitted=false;
            Surface.VisitPresented((card,view)=>{if(view==emphasizedCard && card.ObjectId==emphasizedId && !card.Hidden)admitted=true;});
            cardScrolling.FocusHand(admitted?emphasizedCard:null);
            if(admitted && emphasizedCard.parent!=null && emphasizedCard.style.display.value!=DisplayStyle.None)Raise(emphasizedCard,emphasizedId);
        }
        private void Raise(CardView view,string id)
        {
            view.style.scale=new Scale(new Vector3(1.12f,1.12f,1));view.style.translate=new Translate(0,view.ClassListContains("in-hand")?-90:-15);view.BringToFront();view.parent?.BringToFront();hud.LifeDrawer.BringToFront();
            // The shared inspector borrows only the currently admitted surface binding.
            // No second texture, printing lookup or speculative characteristic is created.
            if(!inspecting && !restoringFocus && host?.Inspect(id)==true){
                previewing=true;previewId=id;inspector.Show(false);PlaceInspection(view);Surface.InspectionView.BringToFront();
            }
            actionDrawer.BringToFront();result.BringToFront();if(inspecting){Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();}root.Q<VisualElement>("board-object-menu")?.BringToFront();organizationRenderer?.BringToolsToFront();LayoutEditor?.BringToFront();RefreshForegroundLayers();
        }
        private void PlaceInspection(CardView source=null)
        {
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;
            Surface.InspectionView.SetPresentation(CardPresentationMode.Full,Mathf.Clamp((height-130)/1.4f,240,300));
            inspector.Place(new Rect(0,0,width,height),new Vector2(Surface.InspectionView.style.width.value.value,Surface.InspectionView.style.height.value.value),source==null?(Vector2?)null:root.WorldToLocal(source.worldBound.center));
            originalCard.text=Surface.InspectionView.ShowingOriginalPrinting?"Live card":"Original card";originalCard.SetEnabled(Surface.InspectionView.CanShowOriginalPrinting);
            originalCard.tooltip=Surface.InspectionView.CanShowOriginalPrinting?"Switch between the live card and original printing":"Original artwork is unavailable";
            originalCard.style.left=Surface.InspectionView.style.left.value.value;originalCard.style.top=Mathf.Min(height-34,Surface.InspectionView.style.top.value.value+Surface.InspectionView.style.height.value.value+6);originalCard.style.width=110;originalCard.style.height=26;
            originalCard.style.display=inspecting?DisplayStyle.Flex:DisplayStyle.None;if(inspecting)originalCard.BringToFront();
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
            if(frame.Decision?.DecisionId!=null && frame.Decision.DecisionId==dismissedZoneDecision)return;
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
            organizationRenderer?.CloseMembers(false);ClearCardFocus();CloseInspection();zoneDrawer.SetReturnFocus(zonePanelDrawer.IsOpen?(VisualElement)zonePanel.Pile(owner,zone):zonePanelDrawer.Tab);openZone=zone;openZoneOwner=owner;rowPages["public-zone"]=0;Layout();return true;
        }
        private void BrowseAttachments(string target)
        {
            if(disposed || frame==null)return;organizationRenderer?.CloseMembers(false);ClearCardFocus();CloseInspection();zoneDrawer.SetReturnFocus(null);openZone="attachments";openZoneOwner=target;rowPages["public-zone"]=0;Layout();
        }
        public void ClosePublicZone(){if(disposed || openZone==null)return;dismissedZoneDecision=frame?.Decision?.DecisionId;openZone=null;openZoneOwner=null;ClearCardFocus();CloseInspection();zoneDrawer.ClearBinding(true);Layout();}
        private static bool SameNavigation(VisualElement a,VisualElement b)
        {
            if(a.GetType()!=b.GetType() || a.name!=b.name || a.enabledSelf!=b.enabledSelf || a.childCount!=b.childCount
                || !a.style.left.Equals(b.style.left) || !a.style.top.Equals(b.style.top)
                || !a.style.width.Equals(b.style.width) || !a.style.height.Equals(b.style.height))return false;
            if(a is TextElement text && text.text!=((TextElement)b).text)return false;
            for(int i=0;i<a.childCount;i++)if(!SameNavigation(a[i],b[i]))return false;
            return true;
        }
        private void ReconcileNavigation(VisualElement staged)
        {
            var old=navigation.Children().ToList();var kept=new System.Collections.Generic.HashSet<VisualElement>();
            foreach(var candidate in staged.Children().ToList()){
                var retained=old.FirstOrDefault(element=>!kept.Contains(element) && SameNavigation(element,candidate));
                if(retained!=null)kept.Add(retained);else{navigation.Add(candidate);kept.Add(candidate);}
            }
            foreach(var element in old)if(!kept.Contains(element))element.RemoveFromHierarchy();
        }
        private void ReconcileCardFocus()
        {
            var admitted=new System.Collections.Generic.HashSet<CardView>();
            Surface.VisitPresented((card,view)=>{if(!card.Hidden && card.FaceDown!=true && view.style.display.value!=DisplayStyle.None)admitted.Add(view);});
            bool Admitted(CardView view)=>view!=null && admitted.Contains(view);
            if(!Admitted(hoveredCard)){hoveredCard=null;hoveredId=null;}
            if(!Admitted(focusedCard)){focusedCard=null;focusedId=null;}
            var next=hoveredCard??focusedCard;
            if(emphasizedCard!=next)RefreshCardFocus();
            else if(next!=null)Raise(next,Surface.CurrentObjectId(next));
            if(inspecting && !Surface.HasInspection)CloseInspection();
        }
        private void Layout()
        {
            if(disposed || frame==null || unsupportedTopology)return;
            LayoutEditor?.BeforeLegacyLayout();
            float width=root.resolvedStyle.width,height=root.resolvedStyle.height;if(float.IsNaN(width) || width<1 || height<1)return;
            PlaceTurns();cardScrolling.Begin();stackScrolling.Begin();
            var visible=new System.Collections.Generic.HashSet<CardView>();
            var stagedNavigation=new VisualElement();
            var items=new System.Collections.Generic.List<(ProjectedCard card,CardView view)>();Surface.VisitPresented((c,v)=>items.Add((c,v)));
            var priorGeometry=items.ToDictionary(item=>item.view,item=>(item.view.style.left,item.view.style.top,item.view.style.width,item.view.style.height,item.view.style.display));
            wired.RemoveWhere(v=>v.parent==null);
            foreach(var item in items){
                var card=item.card;var view=item.view;view.style.position=Position.Absolute;
                if(wired.Add(view)){
                    view.focusable=true;view.AddToClassList("table-card");
                    view.RegisterCallback<PointerEnterEvent>(ev=>{hoveredCard=view;hoveredId=Surface.CurrentObjectId(view);QueueCardFocusRefresh();});
                    view.RegisterCallback<PointerLeaveEvent>(ev=>{if(hoveredCard==view){hoveredCard=null;hoveredId=null;}QueueCardFocusRefresh();});
                    view.RegisterCallback<FocusInEvent>(ev=>{focusedCard=view;focusedId=Surface.CurrentObjectId(view);view.GetFirstAncestorOfType<ScrollView>()?.ScrollTo(view);QueueCardFocusRefresh();});
                    view.RegisterCallback<FocusOutEvent>(ev=>{if(focusedCard==view){focusedCard=null;focusedId=null;}QueueCardFocusRefresh();});
                    view.RegisterCallback<DetachFromPanelEvent>(ev=>{
                        if(ev.target!=view)return;
                        if(hoveredCard==view){hoveredCard=null;hoveredId=null;}
                        if(focusedCard==view){focusedCard=null;focusedId=null;}
                        QueueCardFocusRefresh();
                    });
                    view.RegisterCallback<PointerDownEvent>(ev=>{if(ev.button==1){InspectCard(Surface.CurrentObjectId(view));ev.StopPropagation();}});
                    view.RegisterCallback<KeyDownEvent>(ev=>{if(ev.keyCode==KeyCode.Space){InspectCard(Surface.CurrentObjectId(view));ev.StopPropagation();}});
                }
                if(hoveredCard==view)hoveredId=card.ObjectId;if(focusedCard==view)focusedId=card.ObjectId;
                if(emphasizedCard==view){emphasizedId=card.ObjectId;if(previewing)previewId=card.ObjectId;}
                view.EnableInClassList("selected",frame.Decision?.Options.Any(o=>o.ObjectId==card.ObjectId && o.Selected)==true);
                view.EnableInClassList("attacking",frame.Combat.Any(g=>g.AttackerIds.Contains(card.ObjectId)));
                view.EnableInClassList("blocking",frame.Combat.Any(g=>g.BlockerIds.Contains(card.ObjectId)));
                view.SetLiveMarkers(!card.Hidden && card.Damage>0?"Damage "+card.Damage:"");
            }
            string viewer=frame.Context.ViewerId;
            bool Land(ProjectedCard c)=>!c.Hidden && (c.Characteristics?.TypeLine??"").Split('—')[0].Split(' ').Contains("Land");
            void Row(System.Collections.Generic.List<(ProjectedCard card,CardView view)> row,float top,float left,float span,float size,bool full=false,string key=null,bool reserveSeat=false)
                =>GameplayCardLayout.Row(row,stagedNavigation,rowPages,Layout,width,top,left,span,size,full,key,reserveSeat?new Vector2(width*.5f-90,width*.5f+90):(Vector2?)null,visible,key=="stack"?stackScrolling:cardScrolling,full?Mathf.Max(size*1.4f+24,height*.55f):size+20);
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
            var attachmentViews=items.ToDictionary(item=>item.card.ObjectId);
            bool organized=organizationRenderer?.Layout(frame,items,new Rect(boardLeft,132,geometry.PermanentSpan(activeStack),Mathf.Max(100,geometry.HandTop-156)),cardWidth,visible,cardScrolling)==true;
            // The default rows always remain active; only explicitly grouped or
            // positioned cards are handled by the organization overlay.
            battlefield=battlefield.Where(item=>organizationRenderer?.MembersOpen!=true && organizationRenderer?.ManagedCards.Contains(item.card.ObjectId)!=true).ToList();
            {
            GameplayCardLayout.LandRow(battlefield.Where(i=>i.card.ControllerId!=viewer && Land(i.card)).ToList(),stagedNavigation,rowPages,Layout,width,geometry.OpponentLands,boardLeft,boardSpan,Mathf.Min(cardWidth,110),"opponent-lands",new Vector2(boardLeft,boardLeft),visible,cardScrolling,Mathf.Min(cardWidth,110)+20);
            Row(battlefield.Where(i=>i.card.ControllerId!=viewer && !Land(i.card)).ToList(),geometry.OpponentPermanents,boardLeft,geometry.PermanentSpan(activeStack),cardWidth,key:"opponent-permanents");
            Row(battlefield.Where(i=>i.card.ControllerId==viewer && !Land(i.card)).ToList(),geometry.LocalPermanents,boardLeft,geometry.PermanentSpan(activeStack),cardWidth,key:"local-permanents");
            GameplayCardLayout.LandRow(battlefield.Where(i=>i.card.ControllerId==viewer && Land(i.card)).ToList(),stagedNavigation,rowPages,Layout,width,geometry.LocalLands,boardLeft,boardSpan,Mathf.Min(cardWidth,110),"local-lands",new Vector2(boardLeft,boardLeft),visible,cardScrolling,Mathf.Min(cardWidth,110)+20);
            foreach(var group in attachmentGroups.Where(_=>organizationRenderer?.MembersOpen!=true)){
                Vector2 anchor;float size=95;CardView parentView=null;
                if(attachmentViews.TryGetValue(group.Key,out var parent)){
                    parentView=parent.view;if(!visible.Contains(parentView))continue;anchor=new Vector2(parentView.style.left.value.value,parentView.style.top.value.value);size=parentView.style.width.value.value;
                }else{var seat=hud.Player(group.Key);if(seat==null)continue;anchor=root.WorldToLocal(seat.worldBound.center)+new Vector2(48,-30);size=80;}
                var shown=group.Value.Take(3).ToArray();for(int i=shown.Length-1;i>=0;i--){var child=attachmentViews[shown[i].ObjectId];if(parentView!=null && child.view.parent!=parentView.parent)parentView.parent.Add(child.view);child.view.SetPresentation(CardPresentationMode.Compact,Mathf.Max(62,size*.88f));child.view.style.left=anchor.x+18+i*16;child.view.style.top=anchor.y+24+i*16;child.view.style.rotate=new Rotate(new Angle(child.card.Tapped==true?90:0));visible.Add(child.view);child.view.BringToFront();}
                parentView?.BringToFront();string target=group.Key;var count=new Button(()=>BrowseAttachments(target)){name="attachment-count-"+target,text=group.Value.Count.ToString(),tooltip="Attachments"};count.style.position=Position.Absolute;count.style.left=anchor.x+size-9;count.style.top=anchor.y+size*BattlefieldFrame.Aspect-12;count.style.width=28;count.style.height=26;GameplayTheme.Button(count);stagedNavigation.Add(count);
            }
            }
            foreach(var item in items)item.view.EnableInClassList("in-hand",item.card.Zone=="hand" && item.card.OwnerId==viewer);
            var hand=items.Where(i=>i.card.Zone=="hand" && i.card.OwnerId==viewer).ToList();
            GameplayCardLayout.RetainHandOrder(handOrder,hand.Select(item=>item.card.RenderId));
            hand=hand.OrderBy(item=>handOrder.IndexOf(item.card.RenderId)).ToList();
            // Opening uses the existing generous fan; normal hand keeps full proportions and reserves controls.
            root.EnableInClassList("opening-state",opening);
            // During first layout or a resize the panel can briefly be narrower than
            // the desktop target. Always give the fan a positive, bounded viewport.
            int handCount=hand.Count;
            GameplayCardLayout.Hand(hand,stagedNavigation,rowPages,Layout,CloseInspection,plan.HandBounds,plan.HandNavigationY,opening,plan.HandSize,visible,cardScrolling,hoveredCard??focusedCard);
            var stack=items.Where(i=>i.card.Zone=="stack").ToList();
            stackPanel.style.display=stack.Count==0?DisplayStyle.None:DisplayStyle.Flex;
            stackCards.style.display=stack.Count>0 && stackFocused?DisplayStyle.Flex:DisplayStyle.None;
            stackTitle.text=stack.Count==0?"":"STACK · "+stack.Count;stackToolbar.style.display=stack.Count==0?DisplayStyle.None:DisplayStyle.Flex;
            var stackBounds=plan.StackBounds;float stackWidth=Mathf.Min(width-40,Mathf.Max(400,stackBounds.width));
            stackPanel.style.left=Mathf.Max(20,width-stackWidth-20);stackPanel.style.top=Mathf.Max(64,stackBounds.y-46);stackPanel.style.width=stackWidth;stackPanel.style.height=stackFocused?plan.StackCardSize*1.4f+85:48;
            stackBackdrop.style.display=stack.Count>0?DisplayStyle.Flex:DisplayStyle.None;
            GameplayCardLayout.Row(stack,stagedNavigation,rowPages,Layout,stackWidth,64,12,stackWidth-24,plan.StackCardSize,true,"stack",null,visible,stackScrolling,plan.StackCardSize*1.4f+16);
            foreach(var item in items)if(item.card.Zone!="stack")item.view.style.opacity=stackFocused?.72f:1;
            foreach(var item in stack)item.view.BringToFront();RefreshStackControls();stackToolbar.BringToFront();priorityDrawer.BringToFront();
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId!=viewer).ToList(),plan.OpponentCommandTop,15,130,65,key:"opponent-command");
            Row(items.Where(i=>i.card.Zone=="command" && i.card.OwnerId==viewer).ToList(),plan.LocalCommandTop,15,130,65,key:"local-command");
            zonePanel.Present(frame,Surface,plan.ZoneBankSeparation,openZone,openZoneOwner);zonePanelDrawer.RefreshInput();
            if(LayoutEditor?.OwnsGeometry(GameplayHudIds.Zones)!=true){zonePanelDrawer.Viewport.style.top=plan.ZoneViewportTop;zonePanelDrawer.style.maxHeight=30;zonePanelDrawer.Content.style.maxHeight=plan.ZoneMaxHeight;zonePanelDrawer.Viewport.style.height=plan.ZoneMaxHeight;zonePanelDrawer.Content.style.height=plan.ZoneMaxHeight;zonePanelDrawer.Q<ScrollView>("zone-panel-scroll").style.height=plan.ZoneMaxHeight;zonePanelDrawer.Q<ScrollView>("zone-panel-scroll").style.maxHeight=plan.ZoneMaxHeight;}
            hud.style.height=plan.PlayerHudHeight;
            root.EnableInClassList("browsing-public-zone",openZone!=null);
            zoneDrawer.style.display=openZone==null?DisplayStyle.None:DisplayStyle.Flex;
            if(openZone!=null){
                // A drawer is a presentation overlay, never another owner of card views.
                // Hide the table's cards while browsing, then place the same owned card root
                // above the backdrop. Bringing only children forward cannot cross sibling layers.
                visible.Clear();
                stagedNavigation.Clear();
                zoneDrawer.BringToFront();Surface.CardsRoot.BringToFront();
                var publicCards=openZone=="attachments"?items.Where(i=>attachmentGroups.TryGetValue(openZoneOwner,out var family) && family.Any(card=>card.ObjectId==i.card.ObjectId)).ToList():items.Where(i=>i.card.Zone==openZone && i.card.OwnerId==openZoneOwner && (openZone!="library" || !i.card.Hidden && i.card.FaceDown!=true)).ToList();
                int concealed=publicCards.Count(i=>i.card.Hidden || i.card.FaceDown==true);
                long? total=openZone=="library" && frame.PlayerLibraryCounts.TryGetValue(openZoneOwner,out var libraryCount)?libraryCount:null;
                zoneDrawer.Present(openZoneOwner,openZone,openZone=="attachments"?(attachmentViews.TryGetValue(openZoneOwner,out var enchanted)?enchanted.card.Characteristics?.Name:openZoneOwner==viewer?"You":"Opponent"):openZoneOwner==viewer?"Your zones":"Opponent zones",publicCards.Count-concealed,total,concealed);
                Row(publicCards,plan.PublicZoneBounds.y,plan.PublicZoneBounds.x,plan.PublicZoneBounds.width,plan.PublicZoneCardSize,true,"public-zone");
                foreach(var item in publicCards)if(visible.Contains(item.view))item.view.BringToFront();
                navigation.BringToFront();zoneChoices.BringToFront();
            }
            // Commit only the final visibility. Intermediate None/Flex changes
            // invalidate picking, focus and transitions even on phase-only updates.
            foreach(var item in items){var display=visible.Contains(item.view)?DisplayStyle.Flex:DisplayStyle.None;if(item.view.style.display.value!=display)item.view.style.display=display;}
            if(items.Any(item=>!priorGeometry[item.view].Equals((item.view.style.left,item.view.style.top,item.view.style.width,item.view.style.height,item.view.style.display))))animations.AfterLayout();
            cardScrolling.End();stackScrolling.End();
            ReconcileNavigation(stagedNavigation);
            ReconcileCardFocus();
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
            opponentHand.BringToFront();zonePanelDrawer.BringToFront();hud.LifeDrawer.BringToFront();actionDrawer.BringToFront();result.BringToFront();if(inspecting || previewing)Surface.InspectionView.BringToFront();root.Q<Button>("close-inspection").BringToFront();
            foreach(var scroll in root.Query<ScrollView>().ToList())GameplayScrollRegions.HideBars(scroll);
            boardInput?.Refresh();RefreshPlayers();targeting?.Observe(frame);links.MarkDirtyRepaint();organizationRenderer?.BringToolsToFront();LayoutEditor?.AfterLegacyLayout();PresentAmountPopup();RefreshForegroundLayers();
        }
        public void Dispose(){if(disposed)return;combatLinksRefresh.Pause();foreach(var drawer in foregroundDrawers)drawer.ForegroundChanged-=RefreshForegroundLayers;inspectionInputRoot.UnregisterCallback<PointerDownEvent>(DismissZone,TrickleDown.TrickleDown);inspectionInputRoot.UnregisterCallback<PointerDownEvent>(DismissInspection,TrickleDown.TrickleDown);inspectionInputRoot.UnregisterCallback<KeyDownEvent>(OverlayKey,TrickleDown.TrickleDown);organizationRenderer?.Dispose();organizationRenderer=null;LayoutEditor?.Dispose();LayoutEditor=null;ClearZoneResources();disposed=true;targeting?.Dispose();boardInput?.Dispose();animations.Dispose();inspector.Dispose();priorityBinding?.Dispose();actionBinding?.Dispose();if(Decisions!=null)Surface.Rebinding-=Decisions.InvalidateAmountArtwork;Decisions?.Dispose();Surface.Clearing-=ClearZoneResources;Surface.Rebinding-=ClearPileArt;Surface.Dispose();
            turnsDrawer.Dispose();hud.PlayerActivated-=ActivatePlayer;hud.Dispose();zonePanel.BrowseRequested-=BrowseZone;zonePanel.Dispose();zonePanelDrawer.Dispose();if(actionBinding==null)actionDrawer.Dispose();if(priorityBinding==null)priorityDrawer.Dispose();zoneDrawer.Dispose();HudRegistry.Dispose();wired.Clear();root.RemoveFromHierarchy();}
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Borrows card views; never reparents, binds, creates or disposes them.
    public sealed class BattlefieldOrganizationRenderer : IDisposable
    {
        private readonly Dictionary<string,BattlefieldGroupBinding> groups=new Dictionary<string,BattlefieldGroupBinding>();
        private readonly VisualElement root,chrome,controls;private readonly Label ghost;private readonly ViewerSessionHost host;
        private readonly Action relayout,interruptBoard;private readonly Func<bool> suppressed;private readonly Func<bool> memberAccessBlocked;private readonly Func<string,bool> hasChoice;private readonly BattlefieldMemberChooser chooser;private string chooserGroup;private ViewerDecisionOffer observedOffer;private readonly IVisualElementScheduledItem polling;
        private readonly HashSet<string> selected=new HashSet<string>(StringComparer.Ordinal);private readonly Dictionary<string,int> pages=new Dictionary<string,int>();
        private readonly Dictionary<string,(ProjectedCard card,CardView view)> cardViews=new Dictionary<string,(ProjectedCard,CardView)>();
        private readonly Dictionary<string,VisualElement> memberAnchors=new Dictionary<string,VisualElement>();
        private readonly Dictionary<CardView,ProjectedCard> cards=new Dictionary<CardView,ProjectedCard>();private readonly Dictionary<string,Rect> bounds=new Dictionary<string,Rect>();
        private readonly EventCallback<PointerDownEvent> down;private readonly EventCallback<PointerMoveEvent> move;private readonly EventCallback<PointerUpEvent> up;private readonly EventCallback<KeyDownEvent> key;private readonly EventCallback<PointerCaptureOutEvent> lost;private readonly EventCallback<PointerLeaveEvent> leave;
        private ProjectedOrganizationFrame organization;private ProjectedDecisionFrame game;private Rect lane,area;private Vector2 panelSize,start,groupGrabOffset;private int pointer;
        private sealed class CardGestureBinding : IDisposable {
            private readonly CardView view;private readonly EventCallback<PointerMoveEvent> move;private readonly EventCallback<PointerUpEvent> up;
            internal CardGestureBinding(CardView view,EventCallback<PointerMoveEvent> move,EventCallback<PointerUpEvent> up){this.view=view;this.move=move;this.up=up;view.RegisterCallback(move,TrickleDown.TrickleDown);view.RegisterCallback(up,TrickleDown.TrickleDown);}
            public void Dispose(){view.UnregisterCallback(move,TrickleDown.TrickleDown);view.UnregisterCallback(up,TrickleDown.TrickleDown);}
        }
        private readonly Dictionary<CardView,CardGestureBinding> cardGestures=new Dictionary<CardView,CardGestureBinding>();
        private readonly Dictionary<CardView,Vector2> dragOrigins=new Dictionary<CardView,Vector2>();
        private string[] draggingMembers=Array.Empty<string>();private CardView grabbed;private Vector2 cardGrabOffset;
        private bool pressed,dragging,captured,disposed,legacy;private string moving,focused,notice,created;private bool createDrawer;private long createAfterRevision;private string[] createMembers;
        private string addingToGroup;
        private bool menuOpen;private Vector2 menuPoint;private Rect battlefieldViewport;
        private string presentationEpoch,presentationViewer;
        private TextField naming;private bool namingNewDrawer;private int namingCount;private Action<string> confirm;private Task<bool> submission;
        public BattlefieldOrganizationRenderer(VisualElement root,ViewerSessionHost host,Action relayout,Action interruptBoard,Func<bool> suppressed,Func<string,bool> hasChoice=null,Func<bool> memberAccessBlocked=null)
        {
            this.root=root;this.host=host;this.relayout=relayout;this.interruptBoard=interruptBoard;this.suppressed=suppressed;this.hasChoice=hasChoice??(_=>false);this.memberAccessBlocked=memberAccessBlocked??suppressed;
            chrome=new VisualElement{name="battlefield-organization",pickingMode=PickingMode.Ignore};chrome.style.position=Position.Absolute;chrome.style.left=chrome.style.top=0;chrome.style.right=chrome.style.bottom=0;root.Add(chrome);
            chooser=new BattlefieldMemberChooser(chrome,()=>CloseMembers());
            controls=new ScrollView(ScrollViewMode.Vertical){name="organization-controls",horizontalScrollerVisibility=ScrollerVisibility.Hidden};controls.style.position=Position.Absolute;controls.style.flexDirection=FlexDirection.Column;controls.style.backgroundColor=new Color(.035f,.055f,.065f,.96f);controls.AddToClassList("organization-context");GameplayTheme.Attach(controls);root.Add(controls);
            ghost=new Label{name="organization-drag-ghost",pickingMode=PickingMode.Ignore};ghost.style.position=Position.Absolute;ghost.style.display=DisplayStyle.None;ghost.style.color=Color.white;ghost.style.backgroundColor=new Color(.035f,.055f,.075f,.98f);root.Add(ghost);
            down=Down;move=Move;up=Up;key=Key;lost=ev=>{if(ev.target==root)CancelDrag();};leave=ev=>{if(ev.target==root && !captured)CancelDrag();};
            root.RegisterCallback(down,TrickleDown.TrickleDown);root.RegisterCallback(move,TrickleDown.TrickleDown);root.RegisterCallback(up,TrickleDown.TrickleDown);root.RegisterCallback(key,TrickleDown.TrickleDown);root.RegisterCallback(lost);root.RegisterCallback(leave);
            polling=root.schedule.Execute(()=>{if(submission==null || !submission.IsCompleted)return;var done=submission;submission=null;if(done.IsFaulted || done.IsCanceled || !done.Result){_ = done.Exception;notice="Organization rejected or changed. Try again.";created=null;}relayout();}).Every(50);
        }
        public void Clear()
        {
            addingToGroup=null;menuOpen=false;CancelDrag();chooserGroup=null;chooser.Hide();observedOffer=null;presentationEpoch=presentationViewer=null;organization=null;game=null;selected.Clear();pages.Clear();focused=created=notice=null;naming=null;confirm=null;
            foreach(var binding in cardGestures.Values)binding.Dispose();cardGestures.Clear();foreach(var view in cards.Keys)view.RemoveFromClassList("organization-selected");cards.Clear();cardViews.Clear();memberAnchors.Clear();bounds.Clear();foreach(var binding in groups.Values)binding.Dispose();groups.Clear();foreach(var pager in chrome.Query<VisualElement>(className:"organization-pager").ToList())pager.RemoveFromHierarchy();controls.Clear();controls.style.display=DisplayStyle.None;
        }
        public void Observe(ProjectedOrganizationFrame value)
        {
            if(disposed || ReferenceEquals(value,organization))return;CancelDrag();if(value==null || chooserGroup!=null && !value.Groups.Any(g=>g.Id==chooserGroup))CloseMembers(false,false);if(value!=null && presentationEpoch!=null && (value.Epoch!=presentationEpoch || value.Viewer!=presentationViewer))Clear();organization=value;if(value!=null){presentationEpoch=value.Epoch;presentationViewer=value.Viewer;}
            if(value!=null){if(addingToGroup!=null && !value.Groups.Any(g=>g.Id==addingToGroup && g.Seat==value.Viewer))addingToGroup=null;foreach(string id in groups.Keys.Where(id=>!value.Groups.Any(g=>g.Id==id && g.Seat==groups[id].Seat)).ToArray()){groups[id].Dispose();groups.Remove(id);pages.Remove(id);pages.Remove("$chooser-"+id);}selected.RemoveWhere(h=>!value.Handles.Values.Contains(h));}relayout();
        }
        private bool CanEdit=>chooserGroup==null && !disposed && !legacy && organization!=null && game!=null && game.Turn!=0 && game.Result==null && organization.GameplayRevision==game.Context.Revision && host.HasPresentedRevision(game.Context.Revision) && !host.OrganizationPending && !suppressed() && (game.Decision==null || game.Decision.IsPriority);
        private Button Button(string text,Action click){var button=new Button(click){text=text,name="organization-"+text.ToLowerInvariant().Replace(" ","-")};GameplayTheme.Button(button);return button;}
        public void Interrupt(){addingToGroup=null;menuOpen=false;CloseMembers(false,false);CancelDrag();selected.Clear();naming=null;confirm=null;relayout();}
        public bool Layout(ProjectedDecisionFrame frame,List<(ProjectedCard card,CardView view)> items,Rect viewport,float maximumSize)
        {
            battlefieldViewport=viewport;game=frame;if(chooserGroup==null)chooser.Hide();if(memberAccessBlocked() || frame.Result!=null)CloseMembers(false,false);foreach(var pager in chrome.Query<VisualElement>(className:"organization-pager").ToList())pager.RemoveFromHierarchy();bool keepDraft=naming!=null && controls.Contains(naming);if(!keepDraft)controls.Clear();cards.Clear();cardViews.Clear();memberAnchors.Clear();bounds.Clear();foreach(var item in items){cards[item.view]=item.card;cardViews[item.card.ObjectId]=(item.card,item.view);item.view.EnableInClassList("organization-selected",!legacy && organization!=null && organization.GameplayRevision==frame.Context.Revision && organization.Handles.TryGetValue(item.card.ObjectId,out var h) && selected.Contains(h));}
            foreach(var stale in cardGestures.Keys.Where(view=>!cards.ContainsKey(view)).ToArray()){cardGestures[stale].Dispose();cardGestures.Remove(stale);}
            foreach(var item in items)if(!cardGestures.ContainsKey(item.view))cardGestures.Add(item.view,new CardGestureBinding(item.view,move,up));
            bool valid=organization!=null && organization.GameplayRevision==frame.Context.Revision && organization.Viewer==frame.Context.ViewerId;controls.style.display=(valid || naming!=null) && (menuOpen || naming!=null || notice!=null)?DisplayStyle.Flex:DisplayStyle.None;if(!valid){RefreshControlAvailability();foreach(var binding in groups.Values)binding.Root.style.display=DisplayStyle.None;return false;}
            if(!keepDraft){
            controls.style.left=Mathf.Clamp(menuPoint.x,12,Mathf.Max(12,root.resolvedStyle.width-352));controls.style.top=Mathf.Clamp(menuPoint.y,70,Mathf.Max(70,root.resolvedStyle.height-360));controls.style.bottom=StyleKeyword.Auto;controls.style.width=Mathf.Min(340,viewport.width);controls.style.maxHeight=Mathf.Max(120,root.resolvedStyle.height-controls.style.top.value.value-12);controls.BringToFront();
            if(naming!=null){
                controls.Add(new Label(namingNewDrawer?"New drawer":"Rename drawer"){name="organization-prompt-title",enableRichText=false});
                if(namingNewDrawer)controls.Add(new Label(namingCount+" cards will be added. Drag more cards onto the drawer later."){name="organization-prompt-summary",enableRichText=false});
                naming.label="Name";controls.Add(naming);
                var actions=new VisualElement{name="organization-prompt-actions"};actions.style.flexDirection=FlexDirection.Row;actions.style.justifyContent=Justify.FlexEnd;controls.Add(actions);
                var cancel=Button("Cancel",CancelPrompt);cancel.name="organization-cancel";actions.Add(cancel);
                var accept=Button(namingNewDrawer?"Create drawer":"Save name",ConfirmName);accept.name="organization-confirm";actions.Add(accept);
            }else{
                var inspectable=organization.Groups.FirstOrDefault(g=>g.Id==focused);
                var heading=new VisualElement();heading.style.flexDirection=FlexDirection.Row;controls.Add(heading);var caption=new Label(inspectable?.Name??"Battlefield arrangement"){enableRichText=false};caption.style.flexGrow=1;caption.style.unityFontStyleAndWeight=FontStyle.Bold;heading.Add(caption);
                heading.Add(Button("Close",()=>{addingToGroup=null;menuOpen=false;notice=null;relayout();}));
                if(inspectable!=null)controls.Add(Button("Inspect members",()=>OpenMembers(inspectable.Id)));
                var active=organization.Groups.FirstOrDefault(g=>g.Id==focused && g.Seat==organization.Viewer);
                Foldout advanced=null;
                if(active!=null && !legacy){
                    controls.Add(Button(addingToGroup==active.Id?"Done adding cards":"Add cards",()=>{addingToGroup=addingToGroup==active.Id?null:active.Id;relayout();}));
                    if(addingToGroup==active.Id)controls.Add(new Label("Click your permanents to add them, or drag cards onto this drawer."){enableRichText=false});
                    controls.Add(Button("Rename",()=>Prompt(active.Name,value=>Send(Operation("rename",active.Id,value)))));
                    advanced=new Foldout{text="More options",value=false};controls.Add(advanced);
                    if(host.OrganizationVersion>=3)advanced.Add(Button(active.PresentationMode==BattlefieldGroupPresentationMode.Drawer?"Convert to Panel":"Convert to Drawer",()=>{var operation=Operation("set_mode",active.Id);operation["presentation_mode"]=active.PresentationMode==BattlefieldGroupPresentationMode.Drawer?"panel":"drawer";Send(operation);}));
                    advanced.Add(Button("Delete group",()=>Send(Operation("delete",active.Id))));
                    var remove=Button("Remove selected",()=>Send(Operation("move",null,members:SelectedMembers())));advanced.Add(remove);
                    advanced.Add(Button("Move here",()=>Send(Operation("move",active.Id,members:SelectedMembers()))));
                    int index=organization.Groups.Where(g=>g.Seat==organization.Viewer).ToList().FindIndex(g=>g.Id==active.Id);
                    advanced.Add(Button("Earlier",()=>Send(Operation("reorder",active.Id,index:Math.Max(0,index-1)))));
                    advanced.Add(Button("Later",()=>Send(Operation("reorder",active.Id,index:Math.Min(organization.Groups.Count(g=>g.Seat==organization.Viewer)-1,index+1)))));
                }
                var fallback=new Toggle("Default arrangement"){value=legacy,name="organization-default"};fallback.RegisterValueChangedCallback(ev=>{legacy=ev.newValue;addingToGroup=null;CloseMembers(false,false);CancelDrag();relayout();});if(advanced!=null)advanced.Add(fallback);else controls.Add(fallback);
                if(inspectable==null)controls.Add(new Label("Drag a permanent onto another to create a drawer."){enableRichText=false});
            }
            if(host.OrganizationPending || notice!=null || host.OrganizationError!=null)controls.Add(new Label(host.OrganizationPending?"Saving drawer...":notice??host.OrganizationError){name="organization-status",enableRichText=false});
            }
            RefreshControlAvailability();
            if(legacy){foreach(var binding in groups.Values)binding.Root.style.display=DisplayStyle.None;return false;}
            var seats=frame.PlayerLifeTotals.Keys.OrderBy(id=>id==frame.Context.ViewerId?1:0).ThenBy(id=>id,StringComparer.Ordinal).ToArray();float height=(viewport.height-12)/Math.Max(1,seats.Length);float size=Mathf.Clamp(Mathf.Min(maximumSize,(height-70)/BattlefieldFrame.Aspect),62,110);
            foreach(string seat in seats){
                int ordinal=Array.IndexOf(seats,seat);
                Rect seatLane=new Rect(viewport.x,viewport.y+ordinal*height,viewport.width,height);
                bool hasGroups=organization.Groups.Any(group=>group.Seat==seat);
                // Ungrouped cards and groups use separate horizontal regions. Reserving two
                // vertical card rows in each seat lane overlaps cards at 1280x720.
                float rootSpan=hasGroups?seatLane.width*.34f:seatLane.width;
                Rect groupArea=new Rect(0,0,root.resolvedStyle.width,root.resolvedStyle.height);
                Vector2 dimensions=new Vector2(Mathf.Min(groupArea.width,Mathf.Max(320,2*(size+12)+12)),Mathf.Min(groupArea.height,size*BattlefieldFrame.Aspect+58));
                if(seat==frame.Context.ViewerId){lane=seatLane;area=groupArea;panelSize=dimensions;}
                var roots=(organization.Roots.TryGetValue(seat,out var values)?values:Array.Empty<string>())
                    .Concat(items.Where(i=>i.card.Zone=="battlefield" && i.card.ControllerId==seat && !organization.Handles.ContainsKey(i.card.ObjectId)).Select(i=>i.card.ObjectId)).ToArray();
                Place("root-"+seat,roots.Where(id=>!organization.Placements.ContainsKey(id)).ToArray(),new Rect(seatLane.x,seatLane.y+32,rootSpan,Mathf.Max(20,height-32)),size,items);
                foreach(string id in roots.Where(organization.Placements.ContainsKey))if(cardViews.TryGetValue(id,out var placed)){
                    placed.view.style.display=DisplayStyle.Flex;placed.view.SetPresentation(CardPresentationMode.Compact,size);placed.view.style.rotate=new Rotate(new Angle(placed.card.Tapped==true?90:0));var position=organization.Placements[id];
                    placed.view.style.left=position.x*Mathf.Max(0,groupArea.width-placed.view.style.width.value.value);placed.view.style.top=position.y*Mathf.Max(0,groupArea.height-placed.view.style.height.value.value);
                }
                foreach(var group in organization.Groups.Where(g=>g.Seat==seat)){Rect rect=new Rect(groupArea.x+group.X*Mathf.Max(0,groupArea.width-dimensions.x),groupArea.y+group.Y*Mathf.Max(0,groupArea.height-dimensions.y),dimensions.x,dimensions.y);bounds[group.Id]=rect;
                    if(!groups.TryGetValue(group.Id,out var binding)){string id=group.Id;binding=new BattlefieldGroupBinding(id,seat,chrome,relayout,()=>{if(focused!=id){focused=id;relayout();}},()=>{focused=id;addingToGroup=null;menuOpen=true;menuPoint=bounds.TryGetValue(id,out var box)?box.position:new Vector2(300,100);relayout();},()=>OpenMembers(id),move,up);groups.Add(id,binding);}
                    int untapped=items.Count(i=>group.Objects.Contains(i.card.ObjectId) && i.card.Tapped==false);
                    binding.Update(group,rect,untapped,seat==frame.Context.ViewerId,CanEdit,root.ClassListContains("reduced-motion"),group.Objects.Count(hasChoice),!memberAccessBlocked() && frame.Result==null,items.Count(i=>group.Objects.Contains(i.card.ObjectId) && i.card.Tapped==true));
                    foreach(string member in group.Objects)memberAnchors[member]=binding.IsDrawer?(VisualElement)binding.Drawer.Tab:binding.PanelHeader;
                    if(binding.MembersVisible)
                    Place(group.Id,group.Objects,new Rect(rect.x,rect.y+32,rect.width,Mathf.Max(20,rect.height-32)),Mathf.Min(size,Mathf.Max(62,(rect.height-58)/BattlefieldFrame.Aspect)),items);
                }
            }
            if(chooserGroup!=null){
                var chosen=organization.Groups.FirstOrDefault(g=>g.Id==chooserGroup);
                if(chosen==null)CloseMembers(false,false);
                else{
                    foreach(var item in items)if(item.card.Zone=="battlefield")item.view.style.display=DisplayStyle.None;
                    var chooserBounds=chooser.Present(chosen.Name,viewport);
                    Place("$chooser-"+chosen.Id,chosen.Objects,chooserBounds,Mathf.Min(95,Mathf.Max(40,(chooserBounds.height-24)/Mathf.Max(1,BattlefieldFrame.Aspect))),items,false);
                    // Only admitted member views are promoted, within their existing owner.
                    foreach(var item in items)if(chosen.Objects.Contains(item.card.ObjectId) && item.view.style.display.value!=DisplayStyle.None)item.view.BringToFront();
                }
            }
            ApplyDragPreview();chrome.PlaceBehind(root.Q<VisualElement>("viewer-cards"));CompleteCreation();return true;
        }
        // Continue only after Layout has admitted the matching gameplay frame. Organization
        // snapshots can arrive before Arena presents that frame; never drop membership then.
        private void CompleteCreation()
        {
            if(created==null || !CanEdit || organization.Revision<=createAfterRevision)return;
            var group=organization.Groups.FirstOrDefault(g=>g.Id==created && g.Seat==organization.Viewer);
            if(group==null)return;
            if(createDrawer && group.PresentationMode!=BattlefieldGroupPresentationMode.Drawer){
                createAfterRevision=organization.Revision;var conversion=Operation("set_mode",group.Id);conversion["presentation_mode"]="drawer";Send(conversion);return;
            }
            createDrawer=false;created=null;focused=group.Id;addingToGroup=null;menuOpen=false;
            // Handles identify permanent incarnations. A newer basis is safe only while every
            // original member remains eligible and controlled by this viewer. Never add a subset.
            var owned=organization.Roots[organization.Viewer].Concat(organization.Groups.Where(g=>g.Seat==organization.Viewer).SelectMany(g=>g.Objects))
                .Where(organization.Handles.ContainsKey).Select(id=>organization.Handles[id]).ToHashSet();
            if(createMembers.Length>0 && createMembers.All(owned.Contains))Send(Operation("move",group.Id,members:createMembers));
            else if(createMembers.Length>0){notice="Group created; selection changed. Move cards again.";relayout();}
        }
        private void Place(string id,IReadOnlyList<string> ids,Rect rect,float size,List<(ProjectedCard card,CardView view)> items,bool revealSelected=true)
        {
            var row=ids.Select(value=>items.FirstOrDefault(i=>i.card.ObjectId==value)).Where(i=>i.view!=null).ToList();int capacity=Math.Max(1,Mathf.FloorToInt(rect.width/(size*Mathf.Max(1,BattlefieldFrame.Aspect)+12))),last=Math.Max(0,(row.Count-1)/capacity);int page=pages.TryGetValue(id,out var saved)?Mathf.Clamp(saved,0,last):0;var target=revealSelected?game.Decision?.Options.FirstOrDefault(o=>o.Selected && ids.Contains(o.ObjectId)):null;if(target!=null)page=Math.Max(0,Array.IndexOf(ids.ToArray(),target.ObjectId)/capacity);pages[id]=page;
            for(int i=page*capacity;i<Math.Min(row.Count,(page+1)*capacity);i++){var item=row[i];item.view.style.display=DisplayStyle.Flex;item.view.SetPresentation(CardPresentationMode.Compact,size);item.view.style.left=rect.x+(i-page*capacity)*(size*Mathf.Max(1,BattlefieldFrame.Aspect)+12);item.view.style.top=rect.y;item.view.style.rotate=new Rotate(new Angle(item.card.Tapped==true?90:0));}
            if(last>0){var pager=new VisualElement{name="organization-page-"+id};pager.AddToClassList("organization-pager");pager.style.position=Position.Absolute;pager.style.left=rect.x;pager.style.top=rect.yMax-22;pager.style.flexDirection=FlexDirection.Row;chrome.Add(pager);pager.Add(Button("<",()=>{pages[id]=Math.Max(0,page-1);relayout();}));pager.Add(new Label($"{page+1}/{last+1}"));pager.Add(Button(">",()=>{pages[id]=Math.Min(last,page+1);relayout();}));}
        }
        public bool OpenTools()
        {
            if(disposed || organization==null || game==null || game.Turn==0 || suppressed())return false;
            CloseMembers(false,false);menuOpen=true;focused=null;menuPoint=new Vector2(battlefieldViewport.x,battlefieldViewport.y+20);relayout();return true;
        }
        public void BringToolsToFront(){if(controls.style.display.value==DisplayStyle.Flex)controls.BringToFront();}
        public bool MembersOpen=>chooserGroup!=null;
        public void ObserveOffer(ViewerDecisionOffer offer)
        {
            if(!ReferenceEquals(observedOffer,offer)){observedOffer=offer;CancelDrag();if(MembersOpen)CloseMembers(false);}
            if(MembersOpen && memberAccessBlocked())CloseMembers(false);
        }
        public bool OpenMembers(string id)
        {
            if(disposed || legacy || organization==null || game==null || organization.GameplayRevision!=game.Context.Revision || !host.HasPresentedRevision(game.Context.Revision) || game.Turn==0 || game.Result!=null || memberAccessBlocked() || !organization.Groups.Any(g=>g.Id==id))return false;
            interruptBoard();CancelDrag();selected.Clear();addingToGroup=null;chooserGroup=id;relayout();chooser.Close.Focus();return true;
        }
        public void CloseMembers(bool restoreFocus=true,bool render=true)
        {
            string id=chooserGroup;chooserGroup=null;chooser.Hide();if(id==null)return;
            interruptBoard();CancelDrag();if(render)relayout();
            if(restoreFocus && groups.TryGetValue(id,out var binding) && binding.Root.style.display.value!=DisplayStyle.None)(binding.IsDrawer?(VisualElement)binding.Drawer.Tab:binding.PanelHeader).Focus();
        }
        public VisualElement HiddenMemberAnchor(string objectId)
        {
            if(disposed || legacy || organization==null || game==null || organization.GameplayRevision!=game.Context.Revision || !host.HasPresentedRevision(game.Context.Revision))return null;
            return memberAnchors.TryGetValue(objectId,out var anchor)?anchor:null;
        }
        public Vector2? CardAnchor(string objectId)
        {
            if(objectId==null || disposed || organization==null || game==null || !host.HasPresentedRevision(game.Context.Revision) || !cardViews.TryGetValue(objectId,out var item) || item.card.Hidden)return null;
            return BattlefieldCardAnchorResolver.TryResolve(root,item.view,HiddenMemberAnchor(objectId),out var position)?position:(Vector2?)null;
        }
        private static bool Embedded(VisualElement target){for(var e=target;e!=null;e=e.parent)if(e is Button || e is TextField || e is Toggle)return true;return false;}
        private void Down(PointerDownEvent ev)
        {
            if(ev.button==0)CancelDrag();
            if(ev.button==0 && naming!=null && !controls.Contains(ev.target as VisualElement)){CancelPrompt();ev.StopImmediatePropagation();return;}
            if(ev.button==0 && addingToGroup!=null && !suppressed() && (game?.Decision==null || game.Decision.IsPriority) && !Embedded(ev.target as VisualElement)){
                CardView clicked=null;for(var e=ev.target as VisualElement;e!=null;e=e.parent)if(e is CardView clickedView)clicked=clickedView;
                if(clicked!=null && cards.TryGetValue(clicked,out var permanent) && permanent.Zone=="battlefield" && permanent.ControllerId==game.Context.ViewerId){
                    ev.StopImmediatePropagation();interruptBoard();
                    if(CanEdit && organization.Handles.TryGetValue(permanent.ObjectId,out var handle)){
                        var destination=organization.Groups.FirstOrDefault(g=>g.Id==addingToGroup && g.Seat==organization.Viewer);
                        if(destination!=null && !destination.Objects.Contains(permanent.ObjectId))Send(Operation("move",destination.Id,members:new[]{handle},index:destination.Objects.Count));
                    }
                    return;
                }
            }
            if(ev.button==0 && CanEdit){
                var targetElement=ev.target as VisualElement;var tabGroup=groups.Values.FirstOrDefault(g=>g.Seat==organization.Viewer && g.IsDrawer && (targetElement==g.Drawer.Tab || g.Drawer.Tab.Contains(targetElement)));
                if(tabGroup!=null){moving=focused=tabGroup.Id;groupGrabOffset=root.WorldToLocal(ev.position)-bounds[moving].position;pressed=true;start=ev.position;pointer=ev.pointerId;return;}
            }
            if(ev.button!=0 || !CanEdit || Embedded(ev.target as VisualElement))return;CardView view=null;VisualElement header=null;for(var e=ev.target as VisualElement;e!=null && e!=root;e=e.parent){if(e is CardView card)view=card;if(e.ClassListContains("organization-header"))header=e;}
            moving=null;if(header!=null){var group=organization.Groups.FirstOrDefault(g=>g.Id==(string)header.userData);if(group?.Seat!=organization.Viewer)return;moving=group.Id;focused=group.Id;groupGrabOffset=root.WorldToLocal(ev.position)-bounds[group.Id].position;header.Focus();}
            else if(view!=null && cards.TryGetValue(view,out var card) && card.Zone=="battlefield" && card.ControllerId==organization.Viewer && organization.Handles.TryGetValue(card.ObjectId,out var handle)){
                if(ev.shiftKey){if(!selected.Add(handle))selected.Remove(handle);view.EnableInClassList("organization-selected",selected.Contains(handle));}
                else if(!selected.Contains(handle)){if(host.OrganizationVersion<4)return;selected.Clear();selected.Add(handle);}
                grabbed=view;cardGrabOffset=root.WorldToLocal(ev.position)-new Vector2(view.resolvedStyle.left,view.resolvedStyle.top);draggingMembers=SelectedMembers();
            }else return;
            pressed=true;start=ev.position;pointer=ev.pointerId;if(ev.shiftKey || moving!=null){interruptBoard();root.CapturePointer(pointer);captured=true;ev.StopImmediatePropagation();}
        }
        private void Move(PointerMoveEvent ev)
        {
            if(!pressed || ev.pointerId!=pointer)return;if(!CanEdit){CancelDrag();return;}if(!dragging && Vector2.Distance(start,ev.position)<10)return;
            if(!dragging){
                if(!captured){interruptBoard();if(moving!=null && groups.TryGetValue(moving,out var binding))binding.Drawer.Tab.ReleasePointer(pointer);root.CapturePointer(pointer);captured=true;}
                dragging=true;foreach(var pair in cards)if(organization.Handles.TryGetValue(pair.Value.ObjectId,out var handle) && draggingMembers.Contains(handle))dragOrigins[pair.Key]=new Vector2(pair.Key.resolvedStyle.left,pair.Key.resolvedStyle.top);
            }
            var point=root.WorldToLocal(ev.position);dragDelta=point-root.WorldToLocal(start);ApplyDragPreview();ghost.text=moving==null?$"Move {draggingMembers.Length} permanents":"Move group";ghost.style.display=DisplayStyle.Flex;ghost.style.left=point.x+10;ghost.style.top=point.y+10;ghost.BringToFront();ev.StopImmediatePropagation();
        }
        private void Up(PointerUpEvent ev)
        {
            if(!pressed || ev.pointerId!=pointer)return;bool wasDrag=dragging,consume=captured;string group=moving;var source=grabbed;var members=draggingMembers;var grabOffset=cardGrabOffset;Vector2 point=root.WorldToLocal(ev.position);CancelDrag();if(consume)ev.StopImmediatePropagation();if(!wasDrag){if(consume)relayout();return;}if(!CanEdit)return;
            if(group!=null){Send(Operation("position",group,x:(point.x-groupGrabOffset.x-area.x)/Mathf.Max(1,area.width-panelSize.x),y:(point.y-groupGrabOffset.y-area.y)/Mathf.Max(1,area.height-panelSize.y)));return;}
            if(!area.Contains(point) || members.Length==0){relayout();return;}
            var target=organization.Groups.LastOrDefault(g=>g.Seat==organization.Viewer && bounds.TryGetValue(g.Id,out var rect) && new Rect(rect.x,rect.y,rect.width,groups[g.Id].MembersVisible?rect.height:30).Contains(point));
            if(target!=null){int index=target.Objects.Count(id=>!organization.Handles.TryGetValue(id,out var handle) || !members.Contains(handle));Send(Operation("move",target.Id,members:members,index:index));return;}
            // Restore the dragged views before hit testing stationary permanents.
            var other=cards.Where(pair=>pair.Value.Zone=="battlefield" && pair.Value.ControllerId==organization.Viewer && organization.Handles.TryGetValue(pair.Value.ObjectId,out var handle) && !members.Contains(handle) && pair.Key.style.display.value!=DisplayStyle.None && pair.Key.worldBound.Contains(ev.position)).LastOrDefault();
            if(other.Key!=null){
                string handle=organization.Handles[other.Value.ObjectId];var participants=new[]{handle}.Concat(members).Distinct().ToArray();var anchor=new Vector2(other.Key.resolvedStyle.left,other.Key.resolvedStyle.top);PromptAt(anchor,participants,host.OrganizationVersion>=3);return;
            }
            if(host.OrganizationVersion>=4 && members.Length==1 && source!=null){
                var origin=point-grabOffset;Send(Operation("place",null,members:members,x:origin.x/Mathf.Max(1,area.width-source.resolvedStyle.width),y:origin.y/Mathf.Max(1,area.height-source.resolvedStyle.height)));return;
            }
            relayout();
        }
        private Vector2 dragDelta;
        private void ApplyDragPreview(){if(!dragging)return;foreach(var pair in dragOrigins){pair.Key.style.left=pair.Value.x+dragDelta.x;pair.Key.style.top=pair.Value.y+dragDelta.y;pair.Key.BringToFront();}}
        private void PromptAt(Vector2 anchor,string[] members,bool drawer){
            menuPoint=anchor;Prompt("Drawer "+(organization.Groups.Count(g=>g.Seat==organization.Viewer)+1),value=>Create(value,anchor.x/Mathf.Max(1,area.width-panelSize.x),anchor.y/Mathf.Max(1,area.height-panelSize.y),drawer,members),true,members.Length);
        }
        private void Key(KeyDownEvent ev)
        {
            if(ev.keyCode==KeyCode.Escape && addingToGroup!=null){addingToGroup=null;relayout();ev.StopImmediatePropagation();return;}
            if(ev.keyCode==KeyCode.Escape && MembersOpen){CloseMembers();ev.StopImmediatePropagation();return;}if(ev.keyCode==KeyCode.Escape && naming!=null){CancelPrompt();ev.StopImmediatePropagation();return;}if(suppressed() || game?.Decision!=null && !game.Decision.IsPriority)return;if(naming!=null && (ev.keyCode==KeyCode.Return || ev.keyCode==KeyCode.KeypadEnter)){ConfirmName();ev.StopImmediatePropagation();return;}if(Embedded(ev.target as VisualElement))return;if(ev.keyCode==KeyCode.Escape && (pressed || selected.Count>0 || naming!=null)){Interrupt();ev.StopImmediatePropagation();return;}if(!CanEdit)return;
            for(var element=ev.target as VisualElement;element!=null && element!=root;element=element.parent)if(element is CardView view && ev.shiftKey && ev.keyCode==KeyCode.Space && cards.TryGetValue(view,out var card) && card.ControllerId==organization.Viewer && organization.Handles.TryGetValue(card.ObjectId,out var handle)){if(!selected.Add(handle))selected.Remove(handle);view.EnableInClassList("organization-selected",selected.Contains(handle));ev.StopImmediatePropagation();return;}
            var focus=root.panel?.focusController?.focusedElement as VisualElement;while(focus!=null && !focus.ClassListContains("organization-header"))focus=focus.parent;if(focus==null)return;
            var group=organization.Groups.FirstOrDefault(g=>g.Id==(string)focus.userData && g.Seat==organization.Viewer);if(group==null)return;
            if(ev.keyCode==KeyCode.F2){Prompt(group.Name,value=>Send(Operation("rename",group.Id,value)));ev.StopImmediatePropagation();}else if(ev.keyCode==KeyCode.Delete){Send(Operation("delete",group.Id));ev.StopImmediatePropagation();}
            else if(new[]{KeyCode.LeftArrow,KeyCode.RightArrow,KeyCode.UpArrow,KeyCode.DownArrow}.Contains(ev.keyCode)){Send(Operation("position",group.Id,x:group.X+(ev.keyCode==KeyCode.LeftArrow?-.02f:ev.keyCode==KeyCode.RightArrow?.02f:0),y:group.Y+(ev.keyCode==KeyCode.UpArrow?-.02f:ev.keyCode==KeyCode.DownArrow?.02f:0)));ev.StopImmediatePropagation();}

        }
        // Command ordering follows the admitted organization order, never HashSet iteration.
        private string[] SelectedMembers()=>organization.Roots.Values.SelectMany(ids=>ids)
            .Concat(organization.Groups.SelectMany(group=>group.Objects))
            .Where(id=>organization.Handles.TryGetValue(id,out var handle) && selected.Contains(handle))
            .Select(id=>organization.Handles[id]).ToArray();
        private void CancelDrag(){foreach(var pair in dragOrigins){pair.Key.style.left=pair.Value.x;pair.Key.style.top=pair.Value.y;}dragOrigins.Clear();dragDelta=Vector2.zero;grabbed=null;draggingMembers=Array.Empty<string>();pressed=dragging=false;moving=null;ghost.style.display=DisplayStyle.None;if(captured){captured=false;root.ReleasePointer(pointer);}}
        private void Prompt(string value,Action<string> callback,bool newDrawer=false,int count=0){if(!CanEdit)return;menuOpen=true;if(menuPoint==Vector2.zero)menuPoint=new Vector2(battlefieldViewport.x+20,battlefieldViewport.y+40);namingNewDrawer=newDrawer;namingCount=count;naming=new TextField{value=value,maxLength=64,name="organization-name"};naming.RegisterValueChangedCallback(_=>RefreshControlAvailability());confirm=callback;relayout();naming.Focus();naming.SelectAll();}
        private void RefreshControlAvailability(){
            foreach(var button in controls.Query<Button>().ToList())button.SetEnabled(button.name=="organization-close" || button.name=="organization-cancel" || button.name=="organization-done-adding-cards" || button.name=="organization-inspect-members" && !memberAccessBlocked() || CanEdit && (button.name!="organization-confirm" || !string.IsNullOrWhiteSpace(naming?.value)) && (button.name!="organization-remove-selected" && button.name!="organization-move-here" || selected.Count>0));
        }
        private void ConfirmName(){if(!CanEdit || naming==null || string.IsNullOrWhiteSpace(naming.value))return;string value=naming.value.Trim();var callback=confirm;naming=null;confirm=null;menuOpen=false;callback?.Invoke(value);}
        public bool DismissPrompt(){if(naming==null)return false;CancelPrompt();return true;}
        private void CancelPrompt(){naming=null;confirm=null;addingToGroup=null;menuOpen=false;notice=null;selected.Clear();relayout();root.Focus();}
        private void Create(string value,float x,float y,bool drawer=false,string[] members=null){createDrawer=drawer;created=Guid.NewGuid().ToString("N");createAfterRevision=organization.Revision;createMembers=members??SelectedMembers();Send(Operation("create",created,value,x,y));}
        private void Send(JObject operation){if(!CanEdit)return;if((string)operation["kind"]=="move" && ((JArray)operation["members"]).Count==0){notice="Select permanents first.";return;}notice=null;try{submission=host.OrganizeAsync(organization,operation);}catch{notice="Organization changed. Try again.";created=null;}relayout();}
        internal static JObject Operation(string kind,string group,string name=null,float x=0,float y=0,string[] members=null,int index=0)=>new JObject{["kind"]=kind,["group_id"]=group==null?JValue.CreateNull():new JValue(group),["name"]=name==null?JValue.CreateNull():new JValue(name),["x"]=kind=="create" || kind=="position" || kind=="place"?new JValue((long)Math.Round(Mathf.Clamp01(x)*1000000)):JValue.CreateNull(),["y"]=kind=="create" || kind=="position" || kind=="place"?new JValue((long)Math.Round(Mathf.Clamp01(y)*1000000)):JValue.CreateNull(),["index"]=kind=="move" || kind=="reorder"?new JValue(index):JValue.CreateNull(),["members"]=new JArray(members??Array.Empty<string>())};
        public void Dispose(){if(disposed)return;disposed=true;polling.Pause();Clear();chooser.Dispose();root.UnregisterCallback(down,TrickleDown.TrickleDown);root.UnregisterCallback(move,TrickleDown.TrickleDown);root.UnregisterCallback(up,TrickleDown.TrickleDown);root.UnregisterCallback(key,TrickleDown.TrickleDown);root.UnregisterCallback(lost);root.UnregisterCallback(leave);selected.Clear();cards.Clear();chrome.RemoveFromHierarchy();controls.RemoveFromHierarchy();ghost.RemoveFromHierarchy();}
    }
}

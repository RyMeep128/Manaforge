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
        private readonly EventCallback<PointerDownEvent> down;private readonly EventCallback<PointerMoveEvent> move;private readonly EventCallback<PointerUpEvent> up;private readonly EventCallback<KeyDownEvent> key;private readonly EventCallback<PointerCaptureOutEvent> lost;
        private ProjectedOrganizationFrame organization;private ProjectedDecisionFrame game;private Rect lane,area;private Vector2 panelSize,start,groupGrabOffset;private int pointer;
        private bool pressed,dragging,captured,disposed,legacy;private string moving,focused,notice,created;private long createBasis;private string[] createMembers;
        private bool menuOpen;private Vector2 menuPoint;private Rect battlefieldViewport;
        private string presentationEpoch,presentationViewer;
        private TextField naming;private Action<string> confirm;private Task<bool> submission;
        public BattlefieldOrganizationRenderer(VisualElement root,ViewerSessionHost host,Action relayout,Action interruptBoard,Func<bool> suppressed,Func<string,bool> hasChoice=null,Func<bool> memberAccessBlocked=null)
        {
            this.root=root;this.host=host;this.relayout=relayout;this.interruptBoard=interruptBoard;this.suppressed=suppressed;this.hasChoice=hasChoice??(_=>false);this.memberAccessBlocked=memberAccessBlocked??suppressed;
            chrome=new VisualElement{name="battlefield-organization",pickingMode=PickingMode.Ignore};chrome.style.position=Position.Absolute;chrome.style.left=chrome.style.top=0;chrome.style.right=chrome.style.bottom=0;root.Add(chrome);
            chooser=new BattlefieldMemberChooser(chrome,()=>CloseMembers());
            controls=new VisualElement{name="organization-controls"};controls.style.position=Position.Absolute;controls.style.flexDirection=FlexDirection.Row;controls.style.flexWrap=Wrap.Wrap;controls.style.backgroundColor=new Color(.035f,.055f,.065f,.96f);controls.AddToClassList("organization-context");GameplayTheme.Attach(controls);root.Add(controls);
            ghost=new Label{name="organization-drag-ghost",pickingMode=PickingMode.Ignore};ghost.style.position=Position.Absolute;ghost.style.display=DisplayStyle.None;ghost.style.color=Color.white;ghost.style.backgroundColor=new Color(.035f,.055f,.075f,.98f);root.Add(ghost);
            down=Down;move=Move;up=Up;key=Key;lost=ev=>{if(ev.target==root)CancelDrag();};
            root.RegisterCallback(down,TrickleDown.TrickleDown);root.RegisterCallback(move,TrickleDown.TrickleDown);root.RegisterCallback(up,TrickleDown.TrickleDown);root.RegisterCallback(key,TrickleDown.TrickleDown);root.RegisterCallback(lost);
            polling=root.schedule.Execute(()=>{if(submission==null || !submission.IsCompleted)return;var done=submission;submission=null;if(done.IsFaulted || done.IsCanceled || !done.Result){_ = done.Exception;notice="Organization rejected or changed. Try again.";created=null;}relayout();}).Every(50);
        }
        public void Clear()
        {
            menuOpen=false;CancelDrag();chooserGroup=null;chooser.Hide();observedOffer=null;presentationEpoch=presentationViewer=null;organization=null;game=null;selected.Clear();pages.Clear();focused=created=notice=null;naming=null;confirm=null;
            foreach(var view in cards.Keys)view.RemoveFromClassList("organization-selected");cards.Clear();cardViews.Clear();memberAnchors.Clear();bounds.Clear();foreach(var binding in groups.Values)binding.Dispose();groups.Clear();foreach(var pager in chrome.Query<VisualElement>(className:"organization-pager").ToList())pager.RemoveFromHierarchy();controls.Clear();controls.style.display=DisplayStyle.None;
        }
        public void Observe(ProjectedOrganizationFrame value)
        {
            if(disposed || ReferenceEquals(value,organization))return;CancelDrag();if(value==null || chooserGroup!=null && !value.Groups.Any(g=>g.Id==chooserGroup))CloseMembers(false,false);if(value!=null && presentationEpoch!=null && (value.Epoch!=presentationEpoch || value.Viewer!=presentationViewer))Clear();organization=value;if(value!=null){presentationEpoch=value.Epoch;presentationViewer=value.Viewer;}
            if(value!=null){foreach(string id in groups.Keys.Where(id=>!value.Groups.Any(g=>g.Id==id && g.Seat==groups[id].Seat)).ToArray()){groups[id].Dispose();groups.Remove(id);pages.Remove(id);pages.Remove("$chooser-"+id);}selected.RemoveWhere(h=>!value.Handles.Values.Contains(h));if(created!=null && value.Groups.Any(g=>g.Id==created) && !host.OrganizationPending){string id=created;created=null;if(createMembers.Length>0 && value.Basis==createBasis && createMembers.All(h=>value.Handles.Values.Contains(h)))Send(Operation("move",id,members:createMembers));else if(createMembers.Length>0)notice="Group created; selection changed. Move cards again.";}}relayout();
        }
        private bool CanEdit=>chooserGroup==null && !disposed && !legacy && organization!=null && game!=null && game.Turn!=0 && game.Result==null && organization.GameplayRevision==game.Context.Revision && host.HasPresentedRevision(game.Context.Revision) && !host.OrganizationPending && !suppressed() && (game.Decision==null || game.Decision.IsPriority);
        private Button Button(string text,Action click){var button=new Button(click){text=text,name="organization-"+text.ToLowerInvariant().Replace(" ","-")};GameplayTheme.Button(button);return button;}
        public void Interrupt(){menuOpen=false;CloseMembers(false,false);CancelDrag();selected.Clear();naming=null;confirm=null;relayout();}
        public bool Layout(ProjectedDecisionFrame frame,List<(ProjectedCard card,CardView view)> items,Rect viewport,float maximumSize)
        {
            battlefieldViewport=viewport;game=frame;if(chooserGroup==null)chooser.Hide();if(memberAccessBlocked() || frame.Result!=null)CloseMembers(false,false);foreach(var pager in chrome.Query<VisualElement>(className:"organization-pager").ToList())pager.RemoveFromHierarchy();bool keepDraft=naming!=null && controls.Contains(naming);if(!keepDraft)controls.Clear();cards.Clear();cardViews.Clear();memberAnchors.Clear();bounds.Clear();foreach(var item in items){cards[item.view]=item.card;cardViews[item.card.ObjectId]=(item.card,item.view);item.view.EnableInClassList("organization-selected",!legacy && organization!=null && organization.GameplayRevision==frame.Context.Revision && organization.Handles.TryGetValue(item.card.ObjectId,out var h) && selected.Contains(h));}
            bool valid=organization!=null && organization.GameplayRevision==frame.Context.Revision && organization.Viewer==frame.Context.ViewerId;controls.style.display=(valid || naming!=null) && (menuOpen || naming!=null || notice!=null)?DisplayStyle.Flex:DisplayStyle.None;if(!valid){foreach(var button in controls.Children().OfType<Button>())button.SetEnabled(button.name=="organization-close");foreach(var binding in groups.Values)binding.Root.style.display=DisplayStyle.None;return false;}
            if(!keepDraft){
            controls.style.left=Mathf.Clamp(menuPoint.x,0,Mathf.Max(0,root.resolvedStyle.width-440));controls.style.top=Mathf.Clamp(menuPoint.y,70,Mathf.Max(70,root.resolvedStyle.height-300));controls.style.bottom=StyleKeyword.Auto;controls.style.width=Mathf.Min(440,viewport.width);controls.BringToFront();var fallback=new Toggle("Default arrangement"){value=legacy,name="organization-default"};fallback.RegisterValueChangedCallback(ev=>{legacy=ev.newValue;CloseMembers(false,false);CancelDrag();relayout();});controls.Add(fallback);controls.Add(Button("Close",()=>{menuOpen=false;notice=null;naming=null;confirm=null;relayout();}));if(legacy){foreach(var binding in groups.Values)binding.Root.style.display=DisplayStyle.None;return false;}
            controls.Add(Button("New group",()=>Prompt("Group "+(organization.Groups.Count(g=>g.Seat==organization.Viewer)+1),value=>Create(value,.1f,.1f))));var remove=Button("Remove selected",()=>Send(Operation("move",null,members:SelectedMembers())));controls.Add(remove);controls.Add(new Label(host.OrganizationPending?"Organization pending...":notice??host.OrganizationError??$"{selected.Count} selected"){enableRichText=false});
            if(naming!=null){controls.Add(naming);controls.Add(Button("Confirm",()=>{if(!CanEdit)return;string value=naming.value.Trim();if(value.Length==0)return;var callback=confirm;naming=null;confirm=null;menuOpen=false;callback?.Invoke(value);}));}remove.SetEnabled(CanEdit && selected.Count>0);
            var active=organization.Groups.FirstOrDefault(g=>g.Id==focused && g.Seat==organization.Viewer);if(active!=null){controls.Add(Button("Rename",()=>Prompt(active.Name,value=>Send(Operation("rename",active.Id,value)))));controls.Add(Button("Delete group",()=>Send(Operation("delete",active.Id))));int index=organization.Groups.Where(g=>g.Seat==organization.Viewer).ToList().FindIndex(g=>g.Id==active.Id);controls.Add(Button("Earlier",()=>Send(Operation("reorder",active.Id,index:Math.Max(0,index-1)))));controls.Add(Button("Later",()=>Send(Operation("reorder",active.Id,index:Math.Min(organization.Groups.Count(g=>g.Seat==organization.Viewer)-1,index+1)))));var assign=Button("Move here",()=>Send(Operation("move",active.Id,members:SelectedMembers())));assign.SetEnabled(CanEdit && selected.Count>0);controls.Add(assign);}
            if(active!=null && host.OrganizationVersion==3)controls.Add(Button(active.PresentationMode==BattlefieldGroupPresentationMode.Drawer?"Convert to Panel":"Convert to Drawer",()=>{var operation=Operation("set_mode",active.Id);operation["presentation_mode"]=active.PresentationMode==BattlefieldGroupPresentationMode.Drawer?"panel":"drawer";Send(operation);}));
            }
            foreach(var button in controls.Children().OfType<Button>())button.SetEnabled(button.name=="organization-close" || CanEdit && (button.name!="organization-remove-selected" && button.name!="organization-move-here" || selected.Count>0));
            var seats=frame.PlayerLifeTotals.Keys.OrderBy(id=>id==frame.Context.ViewerId?1:0).ThenBy(id=>id,StringComparer.Ordinal).ToArray();float height=(viewport.height-12)/Math.Max(1,seats.Length);float size=Mathf.Clamp(Mathf.Min(maximumSize,(height-70)/BattlefieldFrame.Aspect),62,110);
            foreach(string seat in seats){
                int ordinal=Array.IndexOf(seats,seat);
                Rect seatLane=new Rect(viewport.x,viewport.y+ordinal*height,viewport.width,height);
                bool hasGroups=organization.Groups.Any(group=>group.Seat==seat);
                // Ungrouped cards and groups use separate horizontal regions. Reserving two
                // vertical card rows in each seat lane overlaps cards at 1280x720.
                float rootSpan=hasGroups?seatLane.width*.34f:seatLane.width;
                Rect groupArea=new Rect(seatLane.x+rootSpan+12,seatLane.y,Mathf.Max(1,seatLane.width-rootSpan-12),seatLane.height);
                Vector2 dimensions=new Vector2(Mathf.Min(groupArea.width,Mathf.Max(320,2*(size+12)+12)),Mathf.Min(groupArea.height,size*BattlefieldFrame.Aspect+58));
                if(seat==frame.Context.ViewerId){lane=seatLane;area=groupArea;panelSize=dimensions;}
                var roots=(organization.Roots.TryGetValue(seat,out var values)?values:Array.Empty<string>())
                    .Concat(items.Where(i=>i.card.Zone=="battlefield" && i.card.ControllerId==seat && !organization.Handles.ContainsKey(i.card.ObjectId)).Select(i=>i.card.ObjectId)).ToArray();
                Place("root-"+seat,roots,new Rect(seatLane.x,seatLane.y+32,rootSpan,Mathf.Max(20,height-32)),size,items);
                foreach(var group in organization.Groups.Where(g=>g.Seat==seat)){Rect rect=new Rect(groupArea.x+group.X*Mathf.Max(0,groupArea.width-dimensions.x),groupArea.y+group.Y*Mathf.Max(0,groupArea.height-dimensions.y),dimensions.x,dimensions.y);bounds[group.Id]=rect;
                    if(!groups.TryGetValue(group.Id,out var binding)){string id=group.Id;binding=new BattlefieldGroupBinding(id,seat,chrome,relayout,()=>{if(focused!=id){focused=id;relayout();}},()=>{focused=id;menuOpen=true;menuPoint=bounds.TryGetValue(id,out var box)?box.position:new Vector2(300,100);relayout();},()=>OpenMembers(id));groups.Add(id,binding);}
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
            chrome.PlaceBehind(root.Q<VisualElement>("viewer-cards"));return true;
        }
        private void Place(string id,IReadOnlyList<string> ids,Rect rect,float size,List<(ProjectedCard card,CardView view)> items,bool revealSelected=true)
        {
            var row=ids.Select(value=>items.FirstOrDefault(i=>i.card.ObjectId==value)).Where(i=>i.view!=null).ToList();int capacity=Math.Max(1,Mathf.FloorToInt(rect.width/(size*Mathf.Max(1,BattlefieldFrame.Aspect)+12))),last=Math.Max(0,(row.Count-1)/capacity);int page=pages.TryGetValue(id,out var saved)?Mathf.Clamp(saved,0,last):0;var target=revealSelected?game.Decision?.Options.FirstOrDefault(o=>o.Selected && ids.Contains(o.ObjectId)):null;if(target!=null)page=Math.Max(0,Array.IndexOf(ids.ToArray(),target.ObjectId)/capacity);pages[id]=page;
            for(int i=page*capacity;i<Math.Min(row.Count,(page+1)*capacity);i++){var item=row[i];item.view.style.display=DisplayStyle.Flex;item.view.SetPresentation(CardPresentationMode.Compact,size);item.view.style.left=rect.x+(i-page*capacity)*(size*Mathf.Max(1,BattlefieldFrame.Aspect)+12);item.view.style.top=rect.y;item.view.style.rotate=new Rotate(new Angle(item.card.Tapped==true?90:0));}
            if(last>0){var pager=new VisualElement{name="organization-page-"+id};pager.AddToClassList("organization-pager");pager.style.position=Position.Absolute;pager.style.left=rect.x;pager.style.top=rect.yMax-22;pager.style.flexDirection=FlexDirection.Row;chrome.Add(pager);pager.Add(Button("<",()=>{pages[id]=Math.Max(0,page-1);relayout();}));pager.Add(new Label($"{page+1}/{last+1}"));pager.Add(Button(">",()=>{pages[id]=Math.Min(last,page+1);relayout();}));}
        }
        public bool MembersOpen=>chooserGroup!=null;
        public void ObserveOffer(ViewerDecisionOffer offer)
        {
            if(!ReferenceEquals(observedOffer,offer)){observedOffer=offer;CancelDrag();if(MembersOpen)CloseMembers(false);}
            if(MembersOpen && memberAccessBlocked())CloseMembers(false);
        }
        public bool OpenMembers(string id)
        {
            if(disposed || legacy || organization==null || game==null || organization.GameplayRevision!=game.Context.Revision || !host.HasPresentedRevision(game.Context.Revision) || game.Turn==0 || game.Result!=null || memberAccessBlocked() || !organization.Groups.Any(g=>g.Id==id))return false;
            interruptBoard();CancelDrag();selected.Clear();chooserGroup=id;relayout();chooser.Close.Focus();return true;
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
            if(ev.button==1 && (CanEdit || legacy && organization!=null && !suppressed()) && !Embedded(ev.target as VisualElement)){
                bool cardTarget=false;for(var e=ev.target as VisualElement;e!=null;e=e.parent)if(e is CardView)cardTarget=true;
                var point=root.WorldToLocal(ev.position);if(!cardTarget && battlefieldViewport.Contains(point)){focused=null;menuPoint=point;menuOpen=true;relayout();ev.StopImmediatePropagation();return;}
            }
            if(ev.button!=0 || !CanEdit || Embedded(ev.target as VisualElement))return;CardView view=null;VisualElement header=null;for(var e=ev.target as VisualElement;e!=null && e!=root;e=e.parent){if(e is CardView card)view=card;if(e.ClassListContains("organization-header"))header=e;}
            moving=null;if(header!=null){var group=organization.Groups.FirstOrDefault(g=>g.Id==(string)header.userData);if(group?.Seat!=organization.Viewer)return;moving=group.Id;focused=group.Id;groupGrabOffset=root.WorldToLocal(ev.position)-bounds[group.Id].position;header.Focus();}
            else if(view!=null && cards.TryGetValue(view,out var card) && card.ControllerId==organization.Viewer && organization.Handles.TryGetValue(card.ObjectId,out var handle)){if(ev.shiftKey){if(!selected.Add(handle))selected.Remove(handle);view.EnableInClassList("organization-selected",selected.Contains(handle));}else if(!selected.Contains(handle))return;}else return;
            pressed=true;start=ev.position;pointer=ev.pointerId;if(ev.shiftKey || moving!=null){interruptBoard();root.CapturePointer(pointer);captured=true;ev.StopImmediatePropagation();}
        }
        private void Move(PointerMoveEvent ev)
        {
            if(!pressed || ev.pointerId!=pointer)return;if(!CanEdit){CancelDrag();return;}if(!dragging && Vector2.Distance(start,ev.position)<10)return;if(!dragging){interruptBoard();root.CapturePointer(pointer);captured=true;dragging=true;}var point=root.WorldToLocal(ev.position);ghost.text=moving==null?$"Move {selected.Count} permanents":"Move group";ghost.style.display=DisplayStyle.Flex;ghost.style.left=point.x+10;ghost.style.top=point.y+10;ghost.BringToFront();ev.StopImmediatePropagation();
        }
        private void Up(PointerUpEvent ev)
        {
            if(!pressed || ev.pointerId!=pointer)return;bool wasDrag=dragging,consume=captured;string group=moving;Vector2 point=root.WorldToLocal(ev.position);CancelDrag();if(consume)ev.StopImmediatePropagation();if(!wasDrag){if(consume)relayout();return;}if(!CanEdit || !lane.Contains(point))return;
            if(group!=null){Send(Operation("position",group,x:(point.x-groupGrabOffset.x-area.x)/Mathf.Max(1,area.width-panelSize.x),y:(point.y-groupGrabOffset.y-area.y)/Mathf.Max(1,area.height-panelSize.y)));return;}
            string target=organization.Groups.LastOrDefault(g=>g.Seat==organization.Viewer && bounds.TryGetValue(g.Id,out var rect) && rect.Contains(point))?.Id;if(target!=null || organization.Groups.Any(g=>g.Seat==organization.Viewer) && !area.Contains(point)){
                var destination=target==null?organization.Roots[organization.Viewer]:organization.Groups.First(g=>g.Id==target).Objects;var remaining=destination.Where(id=>!organization.Handles.TryGetValue(id,out var h) || !selected.Contains(h)).ToList();int index=remaining.Count;
                foreach(var pair in cards)if(remaining.Contains(pair.Value.ObjectId) && pair.Key.style.display.value!=DisplayStyle.None && pair.Key.worldBound.Contains(ev.position)){index=remaining.IndexOf(pair.Value.ObjectId)+(ev.position.x>pair.Key.worldBound.center.x?1:0);break;}
                Send(Operation("move",target,members:SelectedMembers(),index:index));
            }else Prompt("Group "+(organization.Groups.Count(g=>g.Seat==organization.Viewer)+1),value=>Create(value,(point.x-area.x)/Mathf.Max(1,area.width-panelSize.x),(point.y-area.y)/Mathf.Max(1,area.height-panelSize.y)));
        }
        private void Key(KeyDownEvent ev)
        {
            if(ev.keyCode==KeyCode.Escape && MembersOpen){CloseMembers();ev.StopImmediatePropagation();return;}if(suppressed() || game?.Decision!=null && !game.Decision.IsPriority)return;if(ev.keyCode==KeyCode.Escape && naming!=null){Interrupt();ev.StopImmediatePropagation();return;}if(Embedded(ev.target as VisualElement))return;if(ev.keyCode==KeyCode.Escape && (pressed || selected.Count>0 || naming!=null)){Interrupt();ev.StopImmediatePropagation();return;}if(!CanEdit)return;
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
        private void CancelDrag(){pressed=dragging=false;moving=null;ghost.style.display=DisplayStyle.None;if(captured){captured=false;root.ReleasePointer(pointer);}}
        private void Prompt(string value,Action<string> callback){if(!CanEdit)return;menuOpen=true;if(menuPoint==Vector2.zero)menuPoint=new Vector2(battlefieldViewport.x+20,battlefieldViewport.y+40);naming=new TextField{value=value,maxLength=64,name="organization-name"};confirm=callback;relayout();naming.Focus();}
        private void Create(string value,float x,float y){created=Guid.NewGuid().ToString("N");createBasis=organization.Basis;createMembers=SelectedMembers();Send(Operation("create",created,value,x,y));}
        private void Send(JObject operation){if(!CanEdit)return;if((string)operation["kind"]=="move" && ((JArray)operation["members"]).Count==0){notice="Select permanents first.";return;}notice=null;try{submission=host.OrganizeAsync(organization,operation);}catch{notice="Organization changed. Try again.";created=null;}relayout();}
        internal static JObject Operation(string kind,string group,string name=null,float x=0,float y=0,string[] members=null,int index=0)=>new JObject{["kind"]=kind,["group_id"]=group==null?JValue.CreateNull():new JValue(group),["name"]=name==null?JValue.CreateNull():new JValue(name),["x"]=kind=="create" || kind=="position"?new JValue((long)Math.Round(Mathf.Clamp01(x)*1000000)):JValue.CreateNull(),["y"]=kind=="create" || kind=="position"?new JValue((long)Math.Round(Mathf.Clamp01(y)*1000000)):JValue.CreateNull(),["index"]=kind=="move" || kind=="reorder"?new JValue(index):JValue.CreateNull(),["members"]=new JArray(members??Array.Empty<string>())};
        public void Dispose(){if(disposed)return;disposed=true;polling.Pause();Clear();chooser.Dispose();root.UnregisterCallback(down,TrickleDown.TrickleDown);root.UnregisterCallback(move,TrickleDown.TrickleDown);root.UnregisterCallback(up,TrickleDown.TrickleDown);root.UnregisterCallback(key,TrickleDown.TrickleDown);root.UnregisterCallback(lost);selected.Clear();cards.Clear();chrome.RemoveFromHierarchy();controls.RemoveFromHierarchy();ghost.RemoveFromHierarchy();}
    }
}

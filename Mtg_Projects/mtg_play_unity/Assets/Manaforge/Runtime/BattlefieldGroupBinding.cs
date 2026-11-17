using System;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Owns chrome only. Canonical cards remain siblings owned by ViewerCardSurface.
    public sealed class BattlefieldGroupBinding : IDisposable
    {
        public string Id {get;}
        public string Seat {get;}
        public VisualElement Root {get;}
        public GameplayDrawer Drawer {get;}
        public VisualElement PanelHeader {get;}
        public VisualElement DragHandle {get;}
        public Button Edit {get;}
        public Button DrawerEdit {get;}
        private readonly Label title;
        private readonly Action<bool> openChanged;
        private readonly EventCallback<FocusInEvent> focused;
        public bool IsDrawer {get;private set;}
        public bool MembersVisible=>!IsDrawer || Drawer.IsOpen;
        public BattlefieldGroupBinding(string id,string seat,VisualElement parent,Action relayout,Action focus,Action edit)
        {
            Id=id;Seat=seat;
            Root=new VisualElement{name="organization-group-"+id,userData=id,focusable=true,pickingMode=PickingMode.Ignore};Root.AddToClassList("organization-header");Root.style.position=Position.Absolute;parent.Add(Root);
            PanelHeader=new VisualElement{name="organization-header-"+id,userData=id,focusable=true};PanelHeader.AddToClassList("organization-header");PanelHeader.style.height=30;PanelHeader.style.flexDirection=FlexDirection.Row;PanelHeader.style.backgroundColor=new Color(.12f,.17f,.19f,.95f);Root.Add(PanelHeader);
            title=new Label{enableRichText=false,pickingMode=PickingMode.Ignore};title.style.flexGrow=1;title.style.overflow=Overflow.Hidden;PanelHeader.Add(title);
            Edit=new Button(edit){text="...",name="organization-edit-"+id,tooltip="Group actions"};GameplayTheme.Button(Edit);PanelHeader.Add(Edit);
            Drawer=new GameplayDrawer("Group",GameplayDrawerDirection.Down,true){name="organization-drawer-"+id};Drawer.Tab.enableRichText=false;Drawer.style.position=Position.Absolute;Drawer.style.left=Drawer.style.top=0;Drawer.style.height=30;Root.Add(Drawer);
            Drawer.Tab.style.position=Position.Absolute;Drawer.Tab.style.left=30;Drawer.Tab.style.top=0;Drawer.Tab.style.right=0;Drawer.Tab.style.width=StyleKeyword.Auto;Drawer.Tab.style.height=30;
            Drawer.Viewport.style.position=Position.Absolute;Drawer.Viewport.style.left=0;Drawer.Viewport.style.top=32;Drawer.Viewport.style.paddingTop=0;
            DrawerEdit=new Button(edit){name="organization-drawer-edit-"+id,text="...",tooltip="Group actions"};GameplayTheme.Button(DrawerEdit);DrawerEdit.style.position=Position.Absolute;DrawerEdit.style.right=DrawerEdit.style.top=0;DrawerEdit.style.width=28;DrawerEdit.style.height=30;Root.Add(DrawerEdit);
            DragHandle=new Label("↕"){name="organization-drag-"+id,userData=id,focusable=true,tooltip="Drag group; arrows move; F2 renames"};DragHandle.AddToClassList("organization-header");DragHandle.style.position=Position.Absolute;DragHandle.style.left=DragHandle.style.top=0;DragHandle.style.width=28;DragHandle.style.height=30;Root.Add(DragHandle);
            focused=ev=>focus();PanelHeader.RegisterCallback(focused);DragHandle.RegisterCallback(focused);Drawer.Tab.RegisterCallback(focused);Root.RegisterCallback(focused);
            openChanged=_=>relayout();Drawer.OpenChanged+=openChanged;
        }
        public void Update(ProjectedOrganizationGroup group,Rect bounds,int untapped,bool owner,bool canEdit,bool reducedMotion)
        {
            IsDrawer=group.PresentationMode==BattlefieldGroupPresentationMode.Drawer;
            Root.style.display=DisplayStyle.Flex;Root.style.left=bounds.x;Root.style.top=bounds.y;Root.style.width=bounds.width;Root.style.height=bounds.height;
            string summary=group.Name+$" ({group.Objects.Count}, {untapped} untapped)";title.text=summary;title.tooltip=summary;Drawer.SetTitle(summary);Drawer.SetReducedMotion(reducedMotion);
            PanelHeader.style.display=IsDrawer?DisplayStyle.None:DisplayStyle.Flex;Drawer.style.display=IsDrawer?DisplayStyle.Flex:DisplayStyle.None;DragHandle.style.display=IsDrawer && owner?DisplayStyle.Flex:DisplayStyle.None;DragHandle.SetEnabled(canEdit);
            Drawer.Tab.style.left=owner?30:0;Drawer.Tab.style.right=owner?30:0;DrawerEdit.style.display=IsDrawer && owner?DisplayStyle.Flex:DisplayStyle.None;DrawerEdit.SetEnabled(canEdit);
            // No edit button is reparented between modes; drawer actions use header focus.
            Edit.style.display=owner?DisplayStyle.Flex:DisplayStyle.None;Edit.SetEnabled(canEdit);
            Drawer.style.width=bounds.width;Drawer.Viewport.style.width=bounds.width;Drawer.Viewport.style.height=Mathf.Max(0,bounds.height-32);Drawer.Content.style.height=Mathf.Max(0,bounds.height-32);Drawer.Content.style.width=bounds.width;
        }
        public void Dispose(){Drawer.OpenChanged-=openChanged;PanelHeader.UnregisterCallback(focused);DragHandle.UnregisterCallback(focused);Drawer.Tab.UnregisterCallback(focused);Root.UnregisterCallback(focused);Edit.clickable=null;DrawerEdit.clickable=null;Drawer.Dispose();Root.RemoveFromHierarchy();}
    }
}

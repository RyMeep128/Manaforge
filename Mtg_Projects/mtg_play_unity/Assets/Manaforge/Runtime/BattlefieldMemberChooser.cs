using System;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Chrome only: the renderer places the admitted canonical CardViews over this surface.
    public sealed class BattlefieldMemberChooser : IDisposable
    {
        public VisualElement Root {get;}
        public Button Close {get;}
        private readonly Label title;
        public BattlefieldMemberChooser(VisualElement parent,Action close)
        {
            Root=new VisualElement{name="organization-member-chooser"};Root.style.position=Position.Absolute;Root.style.backgroundColor=new Color(.035f,.055f,.075f,.99f);Root.style.display=DisplayStyle.None;parent.Add(Root);
            var header=new VisualElement();header.style.height=30;header.style.flexDirection=FlexDirection.Row;Root.Add(header);
            title=new Label{enableRichText=false};title.style.flexGrow=1;header.Add(title);
            Close=new Button(close){text="Close members",name="organization-members-close"};GameplayTheme.Button(Close);header.Add(Close);
        }
        public Rect Present(string name,Rect viewport)
        {
            float width=Mathf.Min(720,viewport.width),height=Mathf.Min(180,Mathf.Max(100,viewport.height-30));
            var bounds=new Rect(viewport.x+(viewport.width-width)*.5f,viewport.y+12,width,height);
            Root.style.display=DisplayStyle.Flex;Root.style.left=bounds.x;Root.style.top=bounds.y;Root.style.width=bounds.width;Root.style.height=bounds.height;Root.BringToFront();title.text=name+" — individual permanents";
            return new Rect(bounds.x+12,bounds.y+36,Mathf.Max(1,bounds.width-24),Mathf.Max(1,bounds.height-42));
        }
        public void Hide(){Root.style.display=DisplayStyle.None;}
        public void Dispose(){Close.clickable=null;Root.RemoveFromHierarchy();}
    }
}

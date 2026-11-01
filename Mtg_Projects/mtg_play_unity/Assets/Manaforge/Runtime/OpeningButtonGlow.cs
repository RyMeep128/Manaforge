using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    public sealed class OpeningButtonGlow : IDisposable
    {
        private readonly List<Button> buttons=new List<Button>();
        private readonly List<Image> images=new List<Image>();
        private readonly List<VisualElement> holders=new List<VisualElement>();
        private bool disposed;
        public OpeningButtonGlow(VisualElement root,Texture2D texture)
        {
            if(texture==null)return;
            foreach(var button in root.Query<Button>().ToList()){
                if(button.text!="Mulligan" && button.text!="Keep 7")continue;
                var parent=button.parent;int index=parent.IndexOf(button);
                var holder=new VisualElement{name="opening-glow-holder"};holder.style.width=260;holder.style.height=55;holder.style.marginLeft=12;holder.style.marginRight=12;
                var image=new Image{name="opening-button-glow",image=texture,pickingMode=PickingMode.Ignore,scaleMode=ScaleMode.StretchToFill,tintColor=button.text=="Mulligan"?new Color(.4f,.4f,1):new Color(1,.45f,.12f)};
                image.style.position=Position.Absolute;image.style.left=-18;image.style.top=-13;image.style.width=296;image.style.height=81;
                holder.Add(image);parent.Insert(index,holder);holder.Add(button);
                button.style.marginLeft=0;button.style.marginRight=0;
                buttons.Add(button);images.Add(image);holders.Add(holder);
            }
            Refresh();
        }
        public static OpeningButtonGlow AttachLocal(VisualElement root)=>new OpeningButtonGlow(root,Resources.Load<Texture2D>("LocalCardVisuals/Buttons/MainButton_Glow"));
        public int Count=>images.Count;
        public void Refresh()
        {if(disposed)return;for(int i=0;i<buttons.Count;i++)images[i].style.display=buttons[i].enabledInHierarchy?DisplayStyle.Flex:DisplayStyle.None;}
        public void Dispose()
        {
            if(disposed)return;disposed=true;
            for(int i=0;i<buttons.Count;i++){
                var holder=holders[i];var button=buttons[i];var parent=holder.parent;
                if(parent!=null){int index=parent.IndexOf(holder);parent.Insert(index,button);holder.RemoveFromHierarchy();}
                button.style.marginLeft=12;button.style.marginRight=12;images[i].RemoveFromHierarchy();
            }
            buttons.Clear();images.Clear();holders.Clear();
        }
    }
}

using System;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Decorative, borrowed local resource. Never changes the primary button's callback or enabled state.
    public sealed class ArenaPriorityGlow : IDisposable
    {
        private readonly VisualElement root;private readonly Image glow;
        public ArenaPriorityGlow(VisualElement root)
        {
            this.root=root;var texture=Resources.Load<Texture2D>("LocalCardVisuals/Buttons/MainButton_GlowLarge");
            if(texture==null)return;glow=new Image{name="arena-priority-glow",image=texture,scaleMode=ScaleMode.StretchToFill,pickingMode=PickingMode.Ignore,tintColor=new Color(1,.45f,.12f)};
            glow.style.position=Position.Absolute;glow.style.display=DisplayStyle.None;root.Insert(0,glow);
        }
        public void Refresh()
        {
            if(glow==null)return;var primary=root.Q<Button>(className:"arena-primary");
            if(primary==null || !primary.enabledInHierarchy || primary.resolvedStyle.display==DisplayStyle.None || primary.worldBound.width<1){glow.style.display=DisplayStyle.None;return;}
            var bounds=primary.worldBound;var point=root.WorldToLocal(bounds.position);
            glow.style.left=point.x-18;glow.style.top=point.y-10;glow.style.width=bounds.width+36;glow.style.height=bounds.height+20;glow.style.opacity=.7f;glow.style.display=DisplayStyle.Flex;
        }
        public void Dispose(){glow?.RemoveFromHierarchy();}
    }
}

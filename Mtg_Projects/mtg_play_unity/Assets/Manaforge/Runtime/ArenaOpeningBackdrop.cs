using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Public decorative asset only. Never reads game state or owns private card resources.
    public static class ArenaOpeningBackdrop
    {
        public const string ResourceName="LocalCardVisuals/Playmats/ArenaTutorialBattlefield";
        public static Rect BattlefieldViewport=>new Rect(0,0,1,1);
        public static bool Attach(VisualElement root,Texture2D texture)
        {
            if(root==null || texture==null)return false;
            if(root.Q<Image>("arena-opening-backdrop")!=null)return true;
            var image=new Image{name="arena-opening-backdrop",image=texture,uv=BattlefieldViewport,scaleMode=ScaleMode.StretchToFill,pickingMode=PickingMode.Ignore};
            image.style.position=Position.Absolute;image.style.left=0;image.style.right=0;image.style.top=0;image.style.bottom=0;image.style.opacity=.35f;
            root.Insert(0,image);return true;
        }
        public static bool AttachLocal(VisualElement root)=>Attach(root,Resources.Load<Texture2D>(ResourceName));
    }
}

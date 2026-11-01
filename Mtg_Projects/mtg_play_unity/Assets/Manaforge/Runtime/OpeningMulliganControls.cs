using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Presentation only: retain the engine-owned buttons, callbacks, and enabled state.
    public static class OpeningMulliganControls
    {
        public static bool Apply(VisualElement root,int handCount)
        {
            if(root==null || handCount!=7)return false;
            var prompt=root.Q<Label>("decision-prompt");
            var yes=root.Q<Button>("decision-option-0");var no=root.Q<Button>("decision-option-1");
            if(prompt==null || OpeningHandFan.PlainPrompt(prompt.text)!="Mulligan down to 6 cards?" || yes==null || no==null || yes.text!="Yes" || no.text!="No" || root.Query<Button>().ToList().Count!=2)return false;
            Style(yes,"Mulligan",new Color(.22f,.25f,.85f),new Color(.65f,.65f,1));
            Style(no,"Keep 7",new Color(.95f,.36f,.08f),new Color(1,.75f,.35f));
            return true;
        }
        public static bool ApplyLocalSkins(VisualElement root)=>ApplySkins(root,
            Resources.Load<Texture2D>("LocalCardVisuals/Buttons/MainButton_Blue_Up"),
            Resources.Load<Texture2D>("LocalCardVisuals/Buttons/MainButton_Orange_Up"));
        public static bool ApplySkins(VisualElement root,Texture2D blue,Texture2D orange)
        {
            if(root==null || blue==null || orange==null)return false;
            var mulligan=root.Q<Button>("decision-option-0");var keep=root.Q<Button>("decision-option-1");
            if(mulligan==null || keep==null || mulligan.text!="Mulligan" || keep.text!="Keep 7")return false;
            Skin(mulligan,blue);Skin(keep,orange);return true;
        }
        private static void Skin(Button button,Texture2D texture)
        {
            button.style.backgroundImage=new StyleBackground(texture);button.style.backgroundColor=Color.clear;
            button.style.unityBackgroundImageTintColor=Color.white;
            button.style.borderTopWidth=button.style.borderBottomWidth=button.style.borderLeftWidth=button.style.borderRightWidth=0;
        }
        private static void Style(Button button,string label,Color fill,Color edge)
        {
            button.text=label;CardTypography.Apply(button,CardTextRole.Title);button.style.fontSize=30;
            button.style.backgroundColor=fill;
            button.style.borderTopWidth=button.style.borderBottomWidth=button.style.borderLeftWidth=button.style.borderRightWidth=2;
            button.style.borderTopColor=button.style.borderBottomColor=button.style.borderLeftColor=button.style.borderRightColor=edge;
        }
    }
}

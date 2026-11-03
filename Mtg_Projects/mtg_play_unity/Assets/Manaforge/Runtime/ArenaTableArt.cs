using System;
using UnityEngine;
using UnityEngine.UIElements;
namespace Manaforge.Play
{
    // Shared decorative resources only. No card-printing preference or viewer artwork ownership.
    public static class ArenaTableArt
    {
        private static Texture2D orange,blue,nameBacker,backLogo;private static bool loaded;
        private static void Load(){if(loaded)return;loaded=true;orange=Resources.Load<Texture2D>("LocalCardVisuals/Buttons/MainButton_Orange_Up");blue=Resources.Load<Texture2D>("LocalCardVisuals/Buttons/MainButton_Blue_Up");nameBacker=Resources.Load<Texture2D>("LocalCardVisuals/PlayHUD/PlayerNameBacker");backLogo=Resources.Load<Texture2D>("LocalCardVisuals/PlayHUD/CardBackLogo");}
        public static void Player(Label seat,string caption)
        {
            Load();seat.text="";var life=new Label("?"){name="seat-life",enableRichText=false};CardTypography.Apply(life,CardTextRole.Title);seat.Add(life);
            var name=new Label(caption){name="seat-caption",enableRichText=false};CardTypography.Apply(name,CardTextRole.Title);if(nameBacker!=null){name.style.backgroundImage=new StyleBackground(nameBacker);name.style.unityBackgroundImageTintColor=new Color(.75f,.66f,.5f);}seat.Add(name);
        }
        public static bool Back(VisualElement element)
        {
            Load();element.AddToClassList("neutral-card-back");if(backLogo==null)return false;var mark=new Image{image=backLogo,scaleMode=ScaleMode.ScaleToFit,pickingMode=PickingMode.Ignore};mark.AddToClassList("card-back-mark");element.Add(mark);return true;
        }
        public static void Menu(VisualElement menu)
        {Load();foreach(var button in menu.Query<Button>().ToList())StyleButton(button,false);}
        private static void StyleButton(Button button,bool primary)
        {
            button.EnableInClassList("arena-primary",primary);button.AddToClassList("arena-action");button.style.fontSize=primary?24:16;button.style.minHeight=primary?48:32;CardTypography.Apply(button,CardTextRole.Title);
            var texture=primary?orange:blue;
            if(texture!=null){button.style.backgroundImage=new StyleBackground(texture);button.style.backgroundColor=Color.clear;button.style.unityBackgroundImageTintColor=Color.white;button.style.borderTopWidth=button.style.borderBottomWidth=button.style.borderLeftWidth=button.style.borderRightWidth=0;}
            else button.style.backgroundColor=StyleKeyword.Null;
        }
        public static void Decision(ViewerDecisionPanel panel,ProjectedDecisionFrame frame)
        {
            Load();panel.Root.style.backgroundColor=StyleKeyword.Null;
            var prompt=panel.Root.Q<Label>("decision-prompt");prompt.style.fontSize=20;CardTypography.Apply(prompt,CardTextRole.Title);
            foreach(var button in panel.Root.Query<Button>().ToList()){
                bool primary=button.name=="decision-finish" || button.name=="decision-number-submit";
                if(button.name!=null && button.name.StartsWith("decision-action-",StringComparison.Ordinal) && int.TryParse(button.name.Substring(16),out int index) && index>=0 && index<frame.Actions.Count)
                    primary=frame.Actions[index].Kind=="pass" && !(frame.Actions[index].Label??"").StartsWith("Cancel",StringComparison.OrdinalIgnoreCase);
                StyleButton(button,primary);
            }
        }
    }
}

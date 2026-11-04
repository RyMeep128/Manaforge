using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Component appearance only. No scene, player identity, or command ownership.
    public static class GameplayTheme
    {
        public static void Attach(VisualElement root)
        {
            root.AddToClassList("mf-theme");
            var sheet = Resources.Load<StyleSheet>("GameplayTheme");
            if (sheet != null && !root.styleSheets.Contains(sheet)) root.styleSheets.Add(sheet);
        }
        public static void Button(Button button, bool primary = false)
        {
            button.AddToClassList("mf-action");
            button.EnableInClassList("mf-primary", primary);
            button.style.backgroundImage = StyleKeyword.None;
        }
        public static void Back(VisualElement root)
        {
            root.AddToClassList("mf-card-back");
            root.Add(new Label("M"){pickingMode=PickingMode.Ignore, enableRichText=false});
        }
        public static void Menu(VisualElement root)
        {
            root.AddToClassList("mf-menu");
            foreach (var button in root.Query<Button>().ToList()) Button(button);
        }
        public static void Mulligan(VisualElement root,int count)
        {
            if(!OpeningMulliganControls.Apply(root,count))return;
            foreach(var button in root.Query<Button>().ToList()){
                button.style.backgroundColor=StyleKeyword.Null;
                button.style.borderTopColor=button.style.borderBottomColor=button.style.borderLeftColor=button.style.borderRightColor=StyleKeyword.Null;
                Button(button,button.name=="decision-option-1");
            }
        }
        public static void Decision(ViewerDecisionPanel panel, ProjectedDecisionFrame frame)
        {
            panel.Root.AddToClassList("mf-decision");panel.Root.style.backgroundColor=StyleKeyword.Null;
            foreach(string name in new[]{"decision-prompt","decision-status","decision-mana-pool"}){var label=panel.Root.Q<Label>(name);if(label!=null)label.style.color=StyleKeyword.Null;}
            foreach (var button in panel.Root.Query<Button>().ToList()) {
                bool primary = button.name == "decision-finish" || button.name == "decision-number-submit";
                if (button.name != null && button.name.StartsWith("decision-action-", StringComparison.Ordinal)
                    && int.TryParse(button.name.Substring(16), out int i) && i >= 0 && i < frame.Actions.Count)
                    primary = frame.Actions[i].Kind == "pass" && !(frame.Actions[i].Label ?? "").StartsWith("Cancel", StringComparison.OrdinalIgnoreCase);
                Button(button, primary);
            }
        }
    }
}

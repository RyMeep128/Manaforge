using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Presentation only: every row retains the current engine-issued opaque option.
    public sealed class SearchableChoiceMenu
    {
        public VisualElement Root {get;}=new VisualElement{name="searchable-choice-menu"};
        private readonly IReadOnlyList<ProjectedChoiceOption> options;
        private readonly List<ProjectedChoiceOption> visible=new List<ProjectedChoiceOption>();
        private readonly TextField search=new TextField{name="choice-menu-search"};
        private readonly ListView list=new ListView{name="choice-menu-list"};
        private readonly Label empty=new Label{name="choice-menu-empty",enableRichText=false};
        private readonly Label selection=new Label("Select a type"){name="choice-menu-selection",enableRichText=false};
        private readonly Button confirm;
        private readonly Button deck,all;
        private readonly bool creatureTypes;
        private bool allTypes;
        private ProjectedChoiceOption selected;
        public SearchableChoiceMenu(ProjectedDecision decision,Action<ProjectedChoiceOption> submit)
        {
            options=decision.Options;creatureTypes=decision.Menu=="creature_type";allTypes=!creatureTypes;
            Root.AddToClassList("choice-menu");
            if(creatureTypes){
                var tabs=new VisualElement{name="choice-menu-tabs"};tabs.style.flexDirection=FlexDirection.Row;
                deck=new Button(()=>{allTypes=false;Refresh();}){name="choice-menu-deck",text="Your deck"};
                all=new Button(()=>{allTypes=true;Refresh();}){name="choice-menu-all",text="All types"};
                tabs.Add(deck);tabs.Add(all);Root.Add(tabs);
            }
            search.label=creatureTypes?"Search all creature types":"Search choices";
            search.RegisterValueChangedCallback(_=>Refresh());Root.Add(search);
            list.itemsSource=visible;list.fixedItemHeight=36;list.selectionType=SelectionType.Single;
            list.makeItem=()=>{var row=new Label{enableRichText=false};row.AddToClassList("choice-menu-row");return row;};
            list.bindItem=(element,index)=>((Label)element).text=visible[index].Label;
            list.selectionChanged+=values=>{selected=values.OfType<ProjectedChoiceOption>().FirstOrDefault();UpdateSelection();};
            list.style.height=252;list.style.flexShrink=1;Root.Add(list);Root.Add(empty);Root.Add(selection);
            confirm=new Button(()=>{if(selected!=null && options.Contains(selected))submit(selected);}){name="choice-menu-confirm",text="Submit"};
            GameplayTheme.Button(confirm,true);Root.Add(confirm);
            Root.RegisterCallback<KeyDownEvent>(ev=>{
                if(ev.keyCode!=KeyCode.Return && ev.keyCode!=KeyCode.KeypadEnter)return;
                if(selected!=null && confirm.enabledInHierarchy){confirm.Focus();submit(selected);ev.StopPropagation();}
            });
            Refresh();
        }
        private void UpdateSelection(){selection.text=selected?.Label??(creatureTypes?"Select a creature type":"Select an option");confirm?.SetEnabled(selected!=null);}
        private void Refresh()
        {
            string query=(search.value??"").Trim();
            // Searching always reaches every legal type, even from the deck-only default.
            var filtered=options.Where(option=>(allTypes || query.Length>0 || option.Suggested)
                && (query.Length==0 || (option.Label??"").IndexOf(query,StringComparison.OrdinalIgnoreCase)>=0))
                .OrderBy(option=>option.Label,StringComparer.OrdinalIgnoreCase).ToList();
            list.ClearSelection();selected=null;visible.Clear();visible.AddRange(filtered);list.RefreshItems();if(visible.Count>0)list.ScrollToItem(0);
            empty.text=query.Length>0?"No matching choices.":"No creature types from your deck are offered. Choose All types or search.";
            empty.style.display=visible.Count==0?DisplayStyle.Flex:DisplayStyle.None;
            list.style.display=visible.Count==0?DisplayStyle.None:DisplayStyle.Flex;
            list.style.height=Math.Min(252,visible.Count*36);
            deck?.EnableInClassList("choice-menu-tab-selected",!allTypes);all?.EnableInClassList("choice-menu-tab-selected",allTypes);UpdateSelection();
        }
    }
}

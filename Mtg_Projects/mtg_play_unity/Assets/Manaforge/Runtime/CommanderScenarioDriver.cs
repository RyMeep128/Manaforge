using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Explicit public Sidisi fixtures only. Clicks native offered controls in any presentation.
    internal sealed class CommanderScenarioDriver
    {
        public string Scenario {get;}=ArtworkFixtureScene.Argument("-manaforgeCommanderScenario")??"single";
        private bool exploited,firstReturn,effectSelected,effectTarget,activated;
        private string Spell=>Scenario.StartsWith("exile-",StringComparison.Ordinal)?"Baleful Mastery":Scenario.StartsWith("hand-",StringComparison.Ordinal)?"Phyrexian Reclamation":Scenario.StartsWith("library-",StringComparison.Ordinal)?"Forever Young":null;
        public bool Handles(string name)=>name=="Sidisi, Undead Vizier" || name=="Baleful Mastery" || name=="Forever Young" || name=="Phyrexian Reclamation";
        private static Button Find(List<Button> controls,string label)=>controls.Find(button=>button.enabledInHierarchy && button.text==label);
        public Button Choose(ProjectedDecisionFrame frame,List<Button> controls,long mana)
        {
            if(Scenario=="single")return null;
            var commander=frame.Commanders?.FirstOrDefault(value=>value.OwnerId==frame.Context.ViewerId);string prompt=frame.Decision.Prompt??"";
            if(controls.Any(button=>button.text=="Yes") && controls.Any(button=>button.text=="No")){
                if(prompt.IndexOf("mulligan",StringComparison.OrdinalIgnoreCase)>=0)return Find(controls,"No");
                if(prompt.IndexOf("command zone",StringComparison.OrdinalIgnoreCase)>=0){bool accept=!firstReturn?(Scenario=="tax" || Scenario.StartsWith("exile-",StringComparison.Ordinal)):Scenario.EndsWith("accept",StringComparison.Ordinal);firstReturn=true;return Find(controls,accept?"Yes":"No");}
                if(prompt.IndexOf("exploit",StringComparison.OrdinalIgnoreCase)>=0 || prompt.IndexOf("sacrifice a creature",StringComparison.OrdinalIgnoreCase)>=0){bool use=!exploited;exploited=true;return Find(controls,use?"Yes":"No");}
                if(prompt.IndexOf("search",StringComparison.OrdinalIgnoreCase)>=0)return Find(controls,"Yes");
                if(exploited && firstReturn && !effectSelected)return Find(controls,"Yes");
            }
            if(Spell!=null && frame.Decision.Options.Any(option=>option.Label.StartsWith(Spell,StringComparison.Ordinal))){var tutor=controls.Find(button=>button.name!=null && button.name.StartsWith("decision-option-",StringComparison.Ordinal) && button.text.StartsWith(Spell,StringComparison.Ordinal));if(tutor!=null)return tutor;return controls.Find(button=>button.name=="decision-next" && button.enabledInHierarchy);}
            if(effectTarget && frame.Decision.CanFinish){var finish=Find(controls,"Finish selection");if(finish!=null)return finish;}
            var target=controls.Find(button=>button.name!=null && button.name.StartsWith("decision-option-",StringComparison.Ordinal) && button.text.StartsWith("Sidisi, Undead Vizier",StringComparison.Ordinal));
            if(target!=null){if(effectSelected)effectTarget=true;return target;}
            if(commander!=null){
                int extra=0;if(commander.Zone=="command" && !string.IsNullOrEmpty(commander.AdditionalCastCost)){var tax=Regex.Match(commander.AdditionalCastCost,@"^\{([0-9]+)\}$");if(!tax.Success || !int.TryParse(tax.Groups[1].Value,out extra))extra=int.MaxValue-5;}
                if(mana>=5L+extra){var cast=Find(controls,"Cast spell: Sidisi, Undead Vizier")??Find(controls,"Select object: Sidisi, Undead Vizier");if(cast!=null)return cast;}
                if(Spell!=null && !effectSelected && (Scenario.StartsWith("exile-",StringComparison.Ordinal)?commander.Zone=="battlefield" && commander.CommandZonePlays>=2:commander.Zone=="graveyard") && mana>=(Spell=="Baleful Mastery"?4:Spell=="Forever Young"?2:1)){
                    var cast=Find(controls,"Cast spell: "+Spell)??Find(controls,"Select object: "+Spell);if(cast!=null){effectSelected=true;effectTarget=false;return cast;}
                }
                if(Spell=="Phyrexian Reclamation" && commander.Zone=="graveyard" && !activated && mana>=2){var activate=Find(controls,"Activate: Phyrexian Reclamation");if(activate!=null){activated=true;effectSelected=true;effectTarget=false;return activate;}}
                if(Scenario!="tax" || commander.CommandZonePlays<2){var finish=Find(controls,"Finish attacks");if(finish!=null)return finish;}
            }
            return null;
        }
    }
}

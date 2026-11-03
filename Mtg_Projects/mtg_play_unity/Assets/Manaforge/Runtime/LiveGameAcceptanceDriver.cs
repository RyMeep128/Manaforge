using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine.UIElements;

namespace Manaforge.Play
{
    // Explicit public-deck acceptance only, mounted solely by -manaforgeGameAcceptance 1.
    // Uses the actual viewer controls; never submits private/native commands.
    internal sealed class LiveGameAcceptanceDriver
    {
        private long submitted=-1;
        public bool Tick(ViewerSessionHost host,ViewerDecisionPanel panel,ProjectedDecisionFrame frame)
        {
            if(frame.Result!=null)return true;var offer=host.PresentedDecision;if(offer?.CanSubmit!=true || submitted==frame.Context.Revision)return false;
            var controls=panel.Root.Query<Button>().ToList();Button button=null;var decision=frame.Decision;
            if(decision.Family=="number" || decision.Family=="amounts"){
                long remaining=decision.Maximum??0;long[] values=new long[decision.Family=="number"?1:decision.Amounts.Count];
                if(decision.Family=="number")values[0]=Math.Max(decision.Minimum??0,Math.Min(1,decision.Maximum??1));
                else{for(int i=0;i<values.Length;i++){values[i]=decision.Amounts[i].Minimum;remaining-=values[i];}for(int i=0;i<values.Length;i++){long take=Math.Min(remaining,decision.Amounts[i].Maximum-values[i]);values[i]+=take;remaining-=take;}}
                for(int i=0;i<values.Length;i++){var field=panel.Root.Q<TextField>("decision-number-"+i);if(field==null)return false;field.value=values[i].ToString(System.Globalization.CultureInfo.InvariantCulture);}button=controls.Find(value=>value.name=="decision-number-submit");
            }
            button??=controls.Find(value=>value.text.IndexOf("gains flying",StringComparison.OrdinalIgnoreCase)>=0);
            button??=controls.Find(value=>value.text.StartsWith("Use floating mana:",StringComparison.Ordinal));
            if(button==null)for(int i=0;i<frame.Actions.Count;i++)if(frame.Actions[i].Label.StartsWith("Select mana source:",StringComparison.Ordinal) && Array.IndexOf(untappedLandIds,frame.Actions[i].ObjectId)>=0){button=controls.Find(value=>value.name=="decision-action-"+i);break;}
            button??=controls.Find(value=>value.text.StartsWith("Play land:",StringComparison.Ordinal));
            // The public acceptance deck is mono-green. Native availability still supplies every action.
            long mana=frame.ViewerMana?.Values.Sum()??0;
            foreach(var action in frame.Actions)if(action.Label.StartsWith("Cast spell:",StringComparison.Ordinal) || action.Label.StartsWith("Select object:",StringComparison.Ordinal)){
                string name=action.Label.Substring(action.Label.IndexOf(':')+1).Trim();int needed=name=="Memnite"?0:name=="Scryb Sprites"?1:name=="Centaur Courser"?3:2;
                // Ordinary land count is read from mounted action availability below; costly premature
                // casts can be cancelled natively, so never choose a spell without known capacity.
                if(needed>availableLands+mana || name=="Evolution Charm" && availableCreatures==0)continue;button??=controls.Find(value=>value.text==action.Label);
            }
            foreach(var action in frame.Actions)if(action.Label=="Activate: Walking Ballista" && Array.IndexOf(counterBallistaIds,action.ObjectId)>=0){var ability=controls.Find(value=>value.text==action.Label);if(button==null && ability!=null){button=ability;}}
            button??=controls.Find(value=>value.text.IndexOf("Remove a +1/+1 counter",StringComparison.OrdinalIgnoreCase)>=0);
            button??=controls.Find(value=>value.text.StartsWith("Select attacker:",StringComparison.Ordinal) || value.text.StartsWith("Select blocker:",StringComparison.Ordinal));
            button??=controls.Find(value=>value.text.StartsWith("Memnite",StringComparison.Ordinal) || value.text.StartsWith("Centaur Courser",StringComparison.Ordinal));
            button??=controls.Find(value=>value.text.StartsWith("Player ",StringComparison.Ordinal));
            button??=controls.Find(value=>value.text=="You");
            button??=controls.Find(value=>value.text=="No");
            button??=controls.Find(value=>value.text.StartsWith("Finish",StringComparison.Ordinal) || value.text=="Pass priority" || value.text.StartsWith("Discard",StringComparison.Ordinal));
            button??=controls.Find(value=>value.name!=null && value.name.StartsWith("decision-option-",StringComparison.Ordinal));
            if(button==null || !button.enabledInHierarchy)return false;submitted=frame.Context.Revision;using(var input=NavigationSubmitEvent.GetPooled()){input.target=button;button.SendEvent(input);}return false;
        }
        private int availableLands,availableCreatures;
        private string[] untappedLandIds=new string[0],counterBallistaIds=new string[0];
        public void SetAvailableLands(int value,int creatures,string[] lands,string[] ballistas){availableLands=value;availableCreatures=creatures;untappedLandIds=lands;counterBallistaIds=ballistas;}
    }
}

using System.Linq;

namespace Manaforge.Play
{
    // Optional shared formatting; alternative presentations can render the immutable data directly.
    public static class CommanderPresentationText
    {
        public static string Format(ProjectedDecisionFrame frame)
        {
            if(frame.Commanders==null)return "";
            return string.Join("\n",frame.Commanders.Select(commander=>
                (commander.OwnerId==frame.Context.ViewerId?"Your ":"Opponent’s ")+commander.Name+
                " · "+(commander.Zone??"location not visible")+
                " · command casts "+(commander.CommandZonePlays?.ToString()??"unknown")+
                " · additional command-zone cost "+(commander.AdditionalCastCost==null?"unknown":commander.AdditionalCastCost.Length==0?"none":commander.AdditionalCastCost)+
                " · damage "+(commander.DamageDealt==null?"unknown":string.Join(", ",commander.DamageDealt.Select(pair=>(pair.Key==frame.Context.ViewerId?"you ":"opponent ")+pair.Value)))));
        }
    }
}

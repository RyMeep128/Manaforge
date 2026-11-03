package manaforge.payment.xmage;

import java.lang.reflect.Field;
import mage.Mana;
import mage.abilities.mana.*;
import mage.abilities.costs.common.TapSourceCost;
import mage.abilities.effects.mana.BasicManaEffect;
import mage.constants.Zone;

/** Structural exclusion screen ONLY. Never certifies safety, feasibility or equivalence.
 * Game-wide triggers/replacements, source strategy, unpaid cost and native legality require
 * separate review. No activation, game mutation, card-name heuristic or cost solver. */
public final class OrdinaryManaShape {
    public enum Result { ORDINARY_TAP_SHAPE, UNSUPPORTED_ABILITY, ADDITIONAL_COST, NONSTANDARD_EFFECT, CHOICE_OR_ADJUSTER, UNKNOWN }
    private OrdinaryManaShape() {}
    public static Result inspect(ActivatedManaAbilityImpl ability) {
        if(ability==null)return Result.UNKNOWN;
        Class<?> type=ability.getClass();
        if(type!=WhiteManaAbility.class && type!=BlueManaAbility.class && type!=BlackManaAbility.class
                && type!=RedManaAbility.class && type!=GreenManaAbility.class)return Result.UNSUPPORTED_ABILITY;
        try {
            if(ability.getCosts().size()!=1 || ability.getCosts().get(0).getClass()!=TapSourceCost.class
                    || !ability.getManaCosts().isEmpty() || !ability.getManaCostsToPay().isEmpty())return Result.ADDITIONAL_COST;
            if(ability.getZone()!=Zone.BATTLEFIELD || ability.isUsesStack() || ability.isPoolDependant()
                    || ability.getModes().size()!=1 || ability.getModes().getMode()==null
                    || ability.getModes().getMode().getCost()!=null || ability.getModes().isMayChooseNone()
                    || ability.getModes().getMinModes()!=1 || !ability.getTargets().isEmpty()
                    || !ability.getSubAbilities().isEmpty() || !ability.getWatchers().isEmpty()
                    || ability.getTargetAdjuster()!=null || ability.getCostAdjuster()!=null
                    || (ability.getCostsTagMap()!=null && !ability.getCostsTagMap().isEmpty()))return Result.CHOICE_OR_ADJUSTER;
            if(ability.getEffects().size()!=1 || ability.getAllEffects().size()!=1
                    || ability.getEffects().get(0).getClass()!=BasicManaEffect.class)return Result.NONSTANDARD_EFFECT;
            BasicManaEffect effect=(BasicManaEffect)ability.getEffects().get(0);
            // Pinned BasicManaEffect also supports dynamic and conditional mana: reject both.
            Field amount=BasicManaEffect.class.getDeclaredField("netAmount");amount.setAccessible(true);
            Mana template=effect.getManaTemplate();
            if(amount.get(effect)!=null || template==null || template.getClass()!=Mana.class)return Result.NONSTANDARD_EFFECT;
            Mana expected=type==WhiteManaAbility.class?Mana.WhiteMana(1):type==BlueManaAbility.class?Mana.BlueMana(1)
                :type==BlackManaAbility.class?Mana.BlackMana(1):type==RedManaAbility.class?Mana.RedMana(1):Mana.GreenMana(1);
            if(!expected.equals(template))return Result.NONSTANDARD_EFFECT;
            return Result.ORDINARY_TAP_SHAPE;
        } catch(ReflectiveOperationException | RuntimeException unavailable) {return Result.UNKNOWN;}
    }
}

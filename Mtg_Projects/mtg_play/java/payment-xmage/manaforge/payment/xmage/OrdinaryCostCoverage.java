package manaforge.payment.xmage;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import mage.Mana;
import mage.abilities.costs.mana.*;

/** Native arithmetic check for an already-proposed plain mana total, NOT a source plan.
 * Does not model restrictions, replacement/trigger effects, source utility or equivalence.
 * Never sufficient to issue VERIFIED_ORDINARY_EQUIVALENT, activate or declare payment complete. */
public final class OrdinaryCostCoverage {
    public enum Result { COVERS, INSUFFICIENT, NO_UNPAID_COST, UNSUPPORTED, UNKNOWN }
    private OrdinaryCostCoverage() {}
    private static boolean plain(Mana mana,boolean production) {
        if(mana==null || mana.getClass()!=Mana.class || mana.getFlag() || mana.getAny()!=0)return false;
        int[] amounts={mana.getWhite(),mana.getBlue(),mana.getBlack(),mana.getRed(),mana.getGreen(),mana.getColorless(),mana.getGeneric()};
        for(int value:amounts)if(value<0 || value>128)return false;
        return mana.count()<=128 && (!production || mana.getGeneric()==0);
    }
    private static boolean supported(ManaCost cost,int depth,int[] nodes,Set<ManaCost> seen) {
        if(cost==null || depth>8 || ++nodes[0]>128 || !seen.add(cost))return false;
        Class<?> type=cost.getClass();
        if(type!=ManaCostsImpl.class && type!=GenericManaCost.class && type!=ColoredManaCost.class && type!=ColorlessManaCost.class)return false;
        if(type==ManaCostsImpl.class) {
            ManaCostsImpl<?> list=(ManaCostsImpl<?>)cost;
            if(list.size()>128)return false;
            for(ManaCost part:list)if(!supported(part,depth+1,nodes,seen))return false;
        }
        if(cost.isPhyrexian() || cost.getSourceFilter()!=null || !cost.getTargets().isEmpty())return false;
        return plain(cost.getMana(),false);
    }
    private static boolean supported(ManaCost cost) {
        return supported(cost,0,new int[]{0},Collections.newSetFromMap(new IdentityHashMap<ManaCost,Boolean>()));
    }
    public static Result inspect(ManaCost cost,Mana proposedProduction) {
        if(cost==null || proposedProduction==null)return Result.UNKNOWN;
        try {
            // Validate before and after native copying/unpaid projection: special costs must not
            // disappear into a simple aggregate and accidentally receive a positive result.
            if(!supported(cost) || !plain(proposedProduction,true))return Result.UNSUPPORTED;
            ManaCost unpaid=cost.copy().getUnpaid();
            if(!supported(unpaid))return Result.UNSUPPORTED;
            Mana required=unpaid.getMana();
            if(required.count()==0)return Result.NO_UNPAID_COST;
            // Pinned native ManaOptions.enough uses this exact direction: COST.enough(AVAILABLE).
            // Mana.enough copies its argument; both caller-owned inputs remain unchanged.
            return required.enough(proposedProduction.copy())?Result.COVERS:Result.INSUFFICIENT;
        }catch(RuntimeException unknown){return Result.UNKNOWN;}
    }
}

package manaforge.payment.xmage;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import mage.abilities.costs.mana.ManaCost;
import mage.abilities.mana.ActivatedManaAbilityImpl;
import mage.util.ManaUtil;

/** Adapter-side native delegation for ONE already-selected source, on the engine owner.
 * Not an eligibility check, cost solver, source planner or permission to auto-activate.
 * Copies the input map because pinned ManaUtil can clear/replace its entries.
 * Ability objects remain native borrowed objects; no deep-copy/privacy guarantee. */
public final class SelectedSourceMana {
    private SelectedSourceMana() {}
    public static Map<UUID,ActivatedManaAbilityImpl> narrow(ManaCost unpaid,Map<UUID,ActivatedManaAbilityImpl> engineAbilities) {
        if(unpaid==null || engineAbilities==null || engineAbilities.size()>128)throw new IllegalArgumentException("PAYMENT_NATIVE_CONTEXT");
        Map<UUID,ActivatedManaAbilityImpl> scratch=new LinkedHashMap<>();
        for(Map.Entry<UUID,ActivatedManaAbilityImpl> entry:engineAbilities.entrySet()) {
            if(entry.getKey()==null || entry.getValue()==null || !entry.getKey().equals(entry.getValue().getId()))throw new IllegalArgumentException("PAYMENT_NATIVE_CONTEXT");
            scratch.put(entry.getKey(),entry.getValue());
        }
        return Collections.unmodifiableMap(new LinkedHashMap<>(ManaUtil.tryToAutoPay(unpaid,scratch)));
    }
}

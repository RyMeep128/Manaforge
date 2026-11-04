package manaforge.payment.xmage;

import java.util.*;
import mage.Mana;
import mage.ConditionalMana;
import mage.abilities.Ability;
import mage.abilities.costs.mana.ManaCost;
import mage.game.Game;
import mage.players.ManaPoolItem;

/** Bounded server-only search over native legal productions. Never activates anything.
 * Conditions are evaluated by XMage for this paying ability, not by the renderer. */
public final class NativePaymentPlan {
    public static final class Step {
        public final UUID source,ability;public final int incarnation;public final Mana production;
        public final ContextHumanPlayer.SourceTicket ticket;
        public Step(UUID source,UUID ability,int incarnation,Mana production,ContextHumanPlayer.SourceTicket ticket){this.source=source;this.ability=ability;this.incarnation=incarnation;this.production=production;this.ticket=ticket;}
    }
    public static final class Source {
        public final List<Step> alternatives=new ArrayList<>();
    }
    private static final class Candidate {
        final Mana total;final List<Step> steps;
        Candidate(Mana total,List<Step> steps){this.total=total;this.steps=steps;}
    }
    private NativePaymentPlan() {}
    public static Mana eligible(Mana mana,UUID producer,Ability paying,ManaCost cost,Game game){
        if(mana==null || mana.getFlag() || mana.getGeneric()!=0 || mana.getAny()!=0 || mana.count()<1 || mana.count()>128)return null;
        try{if(mana instanceof ConditionalMana && !((ConditionalMana)mana).apply(paying,game,producer,cost))return null;}catch(RuntimeException unsupported){return null;}
        Mana plain=new Mana();plain.setWhite(mana.getWhite());plain.setBlue(mana.getBlue());plain.setBlack(mana.getBlack());plain.setRed(mana.getRed());plain.setGreen(mana.getGreen());plain.setColorless(mana.getColorless());return plain;
    }
    public static Mana pool(ContextHumanPlayer player,Ability paying,ManaCost cost,Game game){
        Mana total=new Mana();for(ManaPoolItem item:player.getManaPool().getManaItems()){
            if(cost.getSourceFilter()!=null && !cost.getSourceFilter().match(item.getSourceObject(),game))continue;
            Mana value=eligible(item.isConditional()?item.getConditionalMana():item.getMana(),item.getSourceId(),paying,cost,game);if(value!=null)total.add(value);
        }return total;
    }
    public static List<Step> select(ManaCost unpaid,Mana floating,List<Source> sources){
        if(OrdinaryCostCoverage.inspect(unpaid,floating)==OrdinaryCostCoverage.Result.UNSUPPORTED)return null;
        LinkedHashMap<Mana,Candidate> frontier=new LinkedHashMap<>();frontier.put(floating,new Candidate(floating,new ArrayList<>()));
        Candidate best=OrdinaryCostCoverage.inspect(unpaid,floating)==OrdinaryCostCoverage.Result.COVERS?frontier.get(floating):null;
        int examined=0;
        for(Source source:sources){
            List<Candidate> previous=new ArrayList<>(frontier.values());
            for(Candidate before:previous)for(Step step:source.alternatives){
                if(++examined>16384 || frontier.size()>4096)return null;
                if(best!=null && before.steps.size()+1>=best.steps.size())continue;
                Mana sum=before.total.copy();sum.add(step.production);if(sum.count()>128)continue;
                List<Step> steps=new ArrayList<>(before.steps);steps.add(step);Candidate candidate=new Candidate(sum,steps);
                Candidate old=frontier.get(sum);if(old==null || old.steps.size()>steps.size())frontier.put(sum,candidate);
                if(OrdinaryCostCoverage.inspect(unpaid,sum)==OrdinaryCostCoverage.Result.COVERS){best=candidate;if(steps.size()==1)return steps;}
            }
        }
        return best==null?null:best.steps;
    }
}

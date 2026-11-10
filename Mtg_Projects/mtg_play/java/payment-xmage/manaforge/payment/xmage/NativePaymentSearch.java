package manaforge.payment.xmage;

import java.util.*;
import mage.Mana;
import mage.abilities.Ability;
import mage.abilities.ActivatedAbility;
import mage.abilities.costs.Cost;
import mage.abilities.costs.common.TapSourceCost;
import mage.abilities.costs.mana.ManaCost;
import mage.abilities.mana.ActivatedManaAbilityImpl;
import mage.constants.*;
import mage.game.Game;
import mage.game.permanent.Permanent;
import mage.players.Player;

/** Server-only native payment search. Every activation and pool allocation runs on
 * an isolated simulation, with private response objects and fail-on-choice players.
 * No aggregate Mana value is used to prove coverage or restricted mana eligibility. */
public final class NativePaymentSearch {
    public enum Outcome { READY, INSUFFICIENT_MANA, CONSEQUENTIAL_CHOICE_REQUIRED, UNSUPPORTED_INTERACTION, SEARCH_LIMIT_REACHED }
    public static final int MAX_NODES=100000;
    public static final long MAX_NANOS=250000000L;
    public static final class Step {
        public final UUID source,ability;public final ManaType color;public final List<String> choices;
        Step(UUID source,UUID ability,ManaType color,List<String> choices){this.source=source;this.ability=ability;this.color=color;this.choices=Collections.unmodifiableList(new ArrayList<>(choices));}
    }
    public static final class Result {
        public final Outcome outcome;public final List<Step> steps;public final int examined;
        Result(Outcome outcome,List<Step> steps,int examined){this.outcome=outcome;this.steps=Collections.unmodifiableList(new ArrayList<>(steps));this.examined=examined;}
    }
    private static final class Node {
        final Game game;final ManaCost cost;final List<Step> steps;
        Node(Game game,ManaCost cost,List<Step> steps){this.game=game;this.cost=cost;this.steps=steps;}
    }
    private NativePaymentSearch(){}
    static Game isolated(Game live) {
        Game copy=live.createSimulationForAI();
        if(copy==live || copy.getState()==live.getState() || !copy.isSimulation())throw new IllegalStateException("PAYMENT_COPY_NOT_ISOLATED");
        for(Player player:new ArrayList<>(copy.getState().getPlayers().values()))
            copy.getState().getPlayers().put(player.getId(),new PaymentSimulationPlayer(player));
        return copy;
    }
    static boolean safeCosts(ActivatedManaAbilityImpl ability) {
        if(ability.isUsesStack() || !ability.getTargets().isEmpty() || !ability.getSubAbilities().isEmpty()
            || ability.getModes().size()!=1 || ability.getModes().isMayChooseNone())return false;
        // Filters may spend mana, but no life, sacrifice, discard or counter costs.
        for(Cost cost:ability.getCosts())if(cost.getClass()!=TapSourceCost.class)return false;
        return true;
    }
    static boolean deterministicEffects(Ability ability) {
        if(ability.getEffects().isEmpty())return false;
        for(mage.abilities.effects.Effect effect:ability.getEffects()) {
            Class<?> type=effect.getClass();
            // Core dynamic values are native read-only calculations. Card-specific
            // executable calculators are not admitted merely because their outer
            // effect is a standard mana effect.
            for(Class<?> owner=type;owner!=null && owner!=Object.class;owner=owner.getSuperclass())for(java.lang.reflect.Field field:owner.getDeclaredFields())
                if(mage.abilities.dynamicvalue.DynamicValue.class.isAssignableFrom(field.getType()))try {
                    field.setAccessible(true);Object value=field.get(effect);
                    if(value!=null && !value.getClass().getName().startsWith("mage.abilities.dynamicvalue."))return false;
                }catch(ReflectiveOperationException unavailable){return false;}
            boolean coreManaHelper=effect instanceof mage.abilities.effects.mana.ManaEffect && type.getPackage().getName().equals("mage.abilities.mana");
            if(!coreManaHelper && type!=mage.abilities.effects.mana.BasicManaEffect.class
                && type!=mage.abilities.effects.mana.AddManaOfAnyColorEffect.class
                && type!=mage.abilities.effects.mana.DynamicManaEffect.class
                && type!=mage.abilities.effects.mana.AddManaOfAnyTypeProducedEffect.class
                && type!=mage.abilities.effects.mana.AddConditionalManaEffect.class
                && type!=mage.abilities.effects.mana.AddConditionalColorlessManaEffect.class
                && type!=mage.abilities.effects.mana.AddConditionalManaOfAnyColorEffect.class
                && type!=mage.abilities.effects.mana.AddManaChosenColorEffect.class
                && type!=mage.abilities.effects.mana.AddConditionalManaChosenColorEffect.class
                && type!=mage.abilities.effects.mana.AddManaFromColorChoicesEffect.class)return false;
        }
        return true;
    }
    static int unpaid(ManaCost cost){return cost.getUnpaid().manaValue();}
    private static void allocate(Game game,UUID payer,Ability paying,ManaCost cost) {
        Player player=game.getPlayer(payer);player.getManaPool().setAutoPayment(true);player.getManaPool().setAutoPaymentRestricted(false);
        cost.assignPayment(game,paying,player.getManaPool(),paying.getManaCostsToPay().isEmpty()?cost:paying.getManaCostsToPay());
    }
    private static boolean unchangedResources(Game before,Game after,UUID activated) {
        if(before.getStack().size()!=after.getStack().size())return false;
        for(Player old:before.getPlayers().values()) {
            Player now=after.getPlayer(old.getId());
            if(now==null || old.getLife()!=now.getLife() || !old.getHand().equals(now.getHand())
                || !old.getGraveyard().equals(now.getGraveyard()) || old.getLibrary().size()!=now.getLibrary().size()
                || !old.getCountersAsCopy().equals(now.getCountersAsCopy()))return false;
            if(!after.getState().getTriggered(old.getId()).isEmpty())return false;
        }
        Collection<Permanent> first=before.getBattlefield().getAllActivePermanents(),last=after.getBattlefield().getAllActivePermanents();
        if(first.size()!=last.size())return false;
        for(Permanent old:first) {
            Permanent now=after.getPermanent(old.getId());
            if(now==null || !old.getControllerId().equals(now.getControllerId())
                || !old.getCounters(before).equals(now.getCounters(after))
                || !old.getId().equals(activated) && old.isTapped()!=now.isTapped())return false;
        }
        return true;
    }
    private static Node greedy(Node start,UUID payer,Ability paying,Set<UUID> permitted,long deadline,int[] examined,int maxNodes) {
        Node current=start;
        List<UUID> ids=new ArrayList<>(permitted);
        ids.sort(Comparator.comparingInt((UUID id)->{
            Permanent source=start.game.getPermanent(id);if(source==null)return 0;
            int maximum=0;PaymentSimulationPlayer player=(PaymentSimulationPlayer)start.game.getPlayer(payer);
            for(ActivatedManaAbilityImpl ability:player.usable(source,start.game).values())if(safeCosts(ability) && deterministicEffects(ability))
                for(Mana amount:ability.getNetMana(start.game))maximum=Math.max(maximum,amount.count());
            return -maximum;
        }).thenComparingInt(id->{Permanent source=start.game.getPermanent(id);return source==null?3:source.isLand(start.game)?0:source.isCreature(start.game)?2:1;})
            .thenComparingInt(id->{Permanent source=start.game.getPermanent(id);if(source==null)return 99;Set<ManaType> types=new HashSet<>();for(ActivatedManaAbilityImpl ability:((PaymentSimulationPlayer)start.game.getPlayer(payer)).usable(source,start.game).values())if(deterministicEffects(ability))types.addAll(ability.getProducableManaTypes(start.game));return types.size();})
            .thenComparing(UUID::toString));
        for(UUID id:ids) {
            Permanent permanent=current.game.getPermanent(id);if(permanent==null || !payer.equals(permanent.getControllerId()))continue;
            List<ActivatedManaAbilityImpl> abilities=new ArrayList<>(((PaymentSimulationPlayer)current.game.getPlayer(payer)).usable(permanent,current.game).values());
            abilities.sort(Comparator.comparing(ability->ability.getId().toString()));
            boolean used=false;
            for(ActivatedManaAbilityImpl ability:abilities) {
                if(!safeCosts(ability) || !deterministicEffects(ability))continue;
                List<ManaType> colors=new ArrayList<>(ability.getProducableManaTypes(current.game));colors.remove(ManaType.GENERIC);
                final ManaCost remainingCost=current.cost;
                colors.sort(Comparator.comparingInt((ManaType color)->-remainingCost.getUnpaid().getMana().get(color)).thenComparing(ManaType::name));
                for(ManaType color:colors) {
                    if(++examined[0]>maxNodes || System.nanoTime()>deadline)return null;
                    try {
                        Game trial=isolated(current.game);PaymentSimulationPlayer player=(PaymentSimulationPlayer)trial.getPlayer(payer);player.begin(color);
                        ActivatedManaAbilityImpl candidate=player.usable(trial.getPermanent(id),trial).get(ability.getId());
                        if(candidate==null || !player.activate(candidate,trial) || !unchangedResources(current.game,trial,id))continue;
                        ManaCost cost=current.cost.copy();allocate(trial,payer,paying,cost);
                        if(unpaid(cost)>=unpaid(current.cost))continue;
                        List<Step> steps=new ArrayList<>(current.steps);steps.add(new Step(id,ability.getId(),color,player.recorded()));
                        current=new Node(trial,cost,steps);used=true;if(cost.isPaid())return current;break;
                    }catch(RuntimeException unsupported){ /* Try a different native candidate on another copy. */ }
                }
                if(used)break;
            }
        }
        return null;
    }
    public static Result search(Game live,UUID payer,Ability paying,ManaCost unpaid,UUID[] visibleSources) {
        return search(live,payer,paying,unpaid,visibleSources,MAX_NODES,MAX_NANOS);
    }
    static Result search(Game live,UUID payer,Ability paying,ManaCost unpaid,UUID[] visibleSources,int maxNodes,long maxNanos) {
        if(!(live instanceof mage.game.GameImpl))return new Result(Outcome.UNSUPPORTED_INTERACTION,Collections.emptyList(),0);
        Game root;
        try{root=isolated(live);}catch(RuntimeException unavailable){return new Result(Outcome.UNSUPPORTED_INTERACTION,Collections.emptyList(),0);}
        Ability payment=paying.copy();ManaCost initial=unpaid.copy();
        long deadline=System.nanoTime()+maxNanos;int nodes=0;boolean consequential=false,unsupported=false;
        try{allocate(root,payer,payment,initial);}catch(PaymentSimulationPlayer.ChoiceRequired choice){return new Result(Outcome.CONSEQUENTIAL_CHOICE_REQUIRED,Collections.emptyList(),nodes);}
        if(initial.isPaid())return new Result(Outcome.READY,Collections.emptyList(),nodes);
        Set<UUID> permitted=new HashSet<>(Arrays.asList(visibleSources));
        PriorityQueue<Node> queue=new PriorityQueue<>(Comparator.comparingInt((Node n)->n.steps.size()+unpaid(n.cost)).thenComparingInt(n->unpaid(n.cost)).thenComparing(n->n.steps.isEmpty()?"":n.steps.get(n.steps.size()-1).source.toString()));
        Node start=new Node(root,initial,Collections.emptyList());queue.add(start);
        int[] greedyNodes={0};Node best=greedy(start,payer,payment,permitted,deadline,greedyNodes,maxNodes);nodes=greedyNodes[0];
        while(!queue.isEmpty()) {
            Node node=queue.remove();if(best!=null && node.steps.size()+1>best.steps.size())continue;PaymentSimulationPlayer player=(PaymentSimulationPlayer)node.game.getPlayer(payer);
            List<Permanent> sources=new ArrayList<>();for(UUID id:permitted){Permanent source=node.game.getPermanent(id);if(source!=null && payer.equals(source.getControllerId()))sources.add(source);}
            sources.sort(Comparator.comparingInt((Permanent source)->source.isLand(node.game)?0:source.isCreature(node.game)?2:1).thenComparing(source->source.getId().toString()));
            List<Node> solved=new ArrayList<>();
            for(Permanent source:sources) {
                Map<UUID,ActivatedManaAbilityImpl> usable=player.usable(source,node.game);
                List<ActivatedManaAbilityImpl> abilities=new ArrayList<>(usable.values());abilities.sort(Comparator.comparing(ability->ability.getId().toString()));
                for(ActivatedManaAbilityImpl ability:abilities) {
                    if(!safeCosts(ability)){consequential=true;continue;}
                    if(!deterministicEffects(ability)){unsupported=true;continue;}
                    Set<ManaType> produced=ability.getProducableManaTypes(node.game);
                    EnumSet<ManaType> colors=produced.isEmpty()?EnumSet.allOf(ManaType.class):EnumSet.copyOf(produced);colors.remove(ManaType.GENERIC);
                    for(ManaType color:colors) {
                        if(++nodes>maxNodes || System.nanoTime()>deadline)return best==null?new Result(Outcome.SEARCH_LIMIT_REACHED,Collections.emptyList(),nodes):new Result(Outcome.READY,best.steps,nodes);
                        try {
                            Game trial=isolated(node.game);PaymentSimulationPlayer actor=(PaymentSimulationPlayer)trial.getPlayer(payer);actor.begin(color);
                            ActivatedManaAbilityImpl candidate=actor.usable(trial.getPermanent(source.getId()),trial).get(ability.getId());
                            if(candidate==null || !safeCosts(candidate) || !actor.activate(candidate,trial))continue;
                            if(!unchangedResources(node.game,trial,source.getId())){consequential=true;continue;}
                            ManaCost remaining=node.cost.copy();allocate(trial,payer,payment,remaining);
                            // Repeatable no-tap sources/filters must make progress; bounded search also stops cycles.
                            if(!candidate.hasTapCost() && unpaid(remaining)>=unpaid(node.cost)){unsupported=true;continue;}
                            List<Step> steps=new ArrayList<>(node.steps);steps.add(new Step(source.getId(),ability.getId(),color,actor.recorded()));
                            Node next=new Node(trial,remaining,steps);
                            if(remaining.isPaid()) {
                                solved.add(next);
                                if(best==null || steps.size()<best.steps.size() || steps.size()==best.steps.size() && trial.getPlayer(payer).getManaPool().count()<best.game.getPlayer(payer).getManaPool().count())best=next;
                            }else queue.add(next);
                        }catch(PaymentSimulationPlayer.ChoiceRequired choice){consequential=true;}
                        catch(RuntimeException unavailable){unsupported=true;}
                    }
                }
            }
            if(!solved.isEmpty()) {
                solved.sort(Comparator.comparingInt((Node solution)->solution.game.getPlayer(payer).getManaPool().count()));
                if(best.steps.size()==1)return new Result(Outcome.READY,best.steps,nodes);
            }
        }
        if(best!=null)return new Result(Outcome.READY,best.steps,nodes);
        return new Result(consequential?Outcome.CONSEQUENTIAL_CHOICE_REQUIRED:unsupported?Outcome.UNSUPPORTED_INTERACTION:Outcome.INSUFFICIENT_MANA,Collections.emptyList(),nodes);
    }
}

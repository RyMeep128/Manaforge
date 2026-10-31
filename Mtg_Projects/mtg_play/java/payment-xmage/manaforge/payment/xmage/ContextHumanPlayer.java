package manaforge.payment.xmage;

import com.google.gson.JsonObject;
import java.lang.reflect.Field;
import java.util.UUID;
import java.util.Map;
import java.util.Collections;
import java.util.LinkedHashMap;
import mage.Mana;
import mage.abilities.effects.mana.BasicManaEffect;
import mage.abilities.mana.ActivatedManaAbilityImpl;
import mage.constants.Zone;
import mage.game.permanent.Permanent;
import mage.abilities.Ability;
import mage.abilities.costs.mana.ManaCost;
import mage.constants.RangeOfInfluence;
import mage.game.Game;
import mage.player.human.HumanPlayer;

/** Opt-in owned runtime extension: observes native parameters, delegates ALL payment to XMage.
 * Never installed into the pinned distribution. No source selection, cost solver or auto response. */
public final class ContextHumanPlayer extends HumanPlayer {
    private static final long serialVersionUID=1L;
    private static final Field RESPONSE=field("response"),OPEN=field("responseOpenedForAnswer");
    private static Field field(String name) {
        try{Field value=HumanPlayer.class.getDeclaredField(name);value.setAccessible(true);return value;}
        catch(ReflectiveOperationException failure){throw new ExceptionInInitializerError("PINNED_PAYMENT_CONTEXT_CHANGED");}
    }
    private static final class Frame {
        Game game;Ability ability;ManaCost unpaid;final long sequence;
        Frame(Game game,Ability ability,ManaCost unpaid,long sequence){this.game=game;this.ability=ability;this.unpaid=unpaid;this.sequence=sequence;}
        void clear(){game=null;ability=null;unpaid=null;}
    }
    private transient volatile Frame payment;
    private transient long sequence;
    public ContextHumanPlayer(String name,RangeOfInfluence range,int skill){super(name,range,skill);}
    private ContextHumanPlayer(ContextHumanPlayer original){super(original); /* No borrowed context copied into bookmarks. */}
    @Override public ContextHumanPlayer copy(){return new ContextHumanPlayer(this);}
    @Override protected boolean playManaHandling(Ability ability,ManaCost unpaid,String message,Game game) {
        Frame previous=payment,current=new Frame(game,ability,unpaid,++sequence);payment=current;
        try{return super.playManaHandling(ability,unpaid,message,game);}
        finally{payment=previous;current.clear();}
    }
    /** Trusted server-only read callback. Caller MUST hold this player's native response monitor.
     * No IO, mutation, retained native references or client serialization inside the callback. */
    public interface Inspector<T>{T read(Ability ability,ManaCost unpaid);}
    public <T> T inspectPayment(Game game,UUID payer,int cycle,Inspector<T> inspector) throws ReflectiveOperationException {
        Object response=RESPONSE.get(this);Frame captured=payment;
        if(inspector==null || captured==null || game==null || !Thread.holdsLock(response)
                || !Boolean.TRUE.equals(OPEN.get(this)) || !isInPayManaMode() || !getId().equals(payer)
                || captured.game!=game || game.hasEnded() || game.getPlayer(payer)!=this
                || game.getState().getApplyEffectsCounter()!=cycle || captured.ability==null || captured.unpaid==null)return null;
        T result=inspector.read(captured.ability,captured.unpaid);
        return payment==captured && captured.game==game && Boolean.TRUE.equals(OPEN.get(this))
            && isInPayManaMode() && !game.hasEnded() && game.getPlayer(payer)==this
            && game.getState().getApplyEffectsCounter()==cycle?result:null;
    }
    /** Borrowed engine candidates, not a safety certificate or a complete payment plan.
     * Same no-IO/no-mutation/no-retention contract as Inspector. Never expose this to a client. */
    public interface SourceInspector<T>{T read(Ability ability,ManaCost unpaid,Map<UUID,ActivatedManaAbilityImpl> candidates);}
    public <T> T inspectBattlefieldSource(Game game,UUID payer,int cycle,UUID source,SourceInspector<T> inspector)
            throws ReflectiveOperationException {
        if(source==null || inspector==null)return null;
        return inspectPayment(game,payer,cycle,(ability,unpaid)->{
            Permanent permanent=game.getPermanent(source);
            if(permanent==null || !source.equals(permanent.getId()) || !payer.equals(permanent.getControllerId()))return null;
            // Delegate legality to the exact pinned method used by HumanPlayer.playManaAbilities.
            Map<UUID,ActivatedManaAbilityImpl> nativeAbilities=getUseableManaAbilities(permanent,Zone.BATTLEFIELD,game);
            if(nativeAbilities==null || nativeAbilities.size()>128)return null;
            Map<UUID,ActivatedManaAbilityImpl> snapshot=new LinkedHashMap<>();
            for(Map.Entry<UUID,ActivatedManaAbilityImpl> entry:nativeAbilities.entrySet()) {
                if(entry.getKey()==null || entry.getValue()==null || !entry.getKey().equals(entry.getValue().getId()))return null;
                snapshot.put(entry.getKey(),entry.getValue());
            }
            T result=inspector.read(ability,unpaid,Collections.unmodifiableMap(snapshot));
            // A native object leaving/reentering under the same ID must not validate this observation.
            return game.getPermanent(source)==permanent && payer.equals(permanent.getControllerId())?result:null;
        });
    }
    private static final class SourceEvidence {
        int candidates,ordinary;Mana base;
    }
    /** Bounded diagnostic evidence only. Never exports cost text, names, IDs, abilities or Game. */
    public JsonObject paymentProbe(Game game,UUID payer,int cycle) throws ReflectiveOperationException {
        return paymentProbe(game,payer,cycle,new UUID[0]);
    }
    /** Source IDs must already be visible to this payer; diagnostics export aggregate counts only. */
    public JsonObject paymentProbe(Game game,UUID payer,int cycle,UUID[] visibleSources) throws ReflectiveOperationException {
        if(visibleSources==null || visibleSources.length>128)return null;
        final int[] counts={0,0,0};
        final Mana baseTotal=new Mana();
        for(UUID source:new java.util.LinkedHashSet<>(java.util.Arrays.asList(visibleSources))) {
            SourceEvidence count=inspectBattlefieldSource(game,payer,cycle,source,(ability,unpaid,candidates)->{
                SourceEvidence evidence=new SourceEvidence();evidence.candidates=candidates.size();
                for(ActivatedManaAbilityImpl candidate:candidates.values()) {
                    if(OrdinaryManaShape.inspect(candidate)==OrdinaryManaShape.Result.ORDINARY_TAP_SHAPE) {
                        evidence.ordinary++;
                        if(candidates.size()==1)evidence.base=((BasicManaEffect)candidate.getEffects().get(0)).getManaTemplate().copy();
                    }
                }
                return evidence;
            });
            if(count!=null && count.candidates>0){counts[0]++;counts[1]+=count.candidates;counts[2]+=count.ordinary;if(count.base!=null)baseTotal.add(count.base);}
        }
        return inspectPayment(game,payer,cycle,(ability,unpaid)->{
            JsonObject result=new JsonObject();result.addProperty("available",true);
            result.addProperty("unpaid_mana_count",unpaid.getUnpaid().getMana().count());
            result.addProperty("sequence",payment.sequence);
            result.addProperty("candidate_sources",counts[0]);
            result.addProperty("candidate_abilities",counts[1]);
            result.addProperty("ordinary_shape_abilities",counts[2]);
            // BASE templates only: replacement effects, restrictions, floating mana and strategy
            // have not been reviewed. This does NOT authorize selection or activation.
            result.addProperty("base_cost_coverage",OrdinaryCostCoverage.inspect(unpaid,baseTotal).name());return result;
        });
    }
}

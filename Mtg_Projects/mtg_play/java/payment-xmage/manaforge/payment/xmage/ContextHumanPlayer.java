package manaforge.payment.xmage;

import com.google.gson.*;
import java.lang.reflect.Field;
import java.lang.ref.WeakReference;
import mage.game.GameState;
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

/** Owned server-side payment integration. Native simulations plan payment; native
 * game-thread activation and allocation remain the sole live rules authority. */
public final class ContextHumanPlayer extends HumanPlayer {
    private static final long serialVersionUID=1L;
    private static final Field RESPONSE=field("response"),OPEN=field("responseOpenedForAnswer");
    private static Field field(String name) {
        try{Field value=HumanPlayer.class.getDeclaredField(name);value.setAccessible(true);return value;}
        catch(ReflectiveOperationException failure){throw new ExceptionInInitializerError("PINNED_PAYMENT_CONTEXT_CHANGED");}
    }
    private static final class Frame {
        Game game;Ability ability;ManaCost unpaid;final long sequence;
        JsonObject assessment;GameState assessedState;int assessedCycle;UUID[] assessedSources;
        NativePaymentSearch.Step step;SourceTicket ticket;String token=UUID.randomUUID().toString(),costFingerprint;
        Frame(Game game,Ability ability,ManaCost unpaid,long sequence){this.game=game;this.ability=ability;this.unpaid=unpaid;this.sequence=sequence;}
        void clear(){game=null;ability=null;unpaid=null;assessment=null;assessedState=null;assessedSources=null;step=null;ticket=null;}
    }
    private transient volatile Frame payment;
    private transient long sequence;
    private transient Object ticketOwner=new Object();
    public ContextHumanPlayer(String name,RangeOfInfluence range,int skill){super(name,range,skill);}
    private ContextHumanPlayer(ContextHumanPlayer original){super(original); /* No borrowed context copied into bookmarks. */}
    @Override public ContextHumanPlayer copy(){return new ContextHumanPlayer(this);}
    @Override protected boolean playManaHandling(Ability ability,ManaCost unpaid,String message,Game game) {
        if(ticketOwner==null)ticketOwner=new Object();
        Frame previous=payment,current=new Frame(game,ability,unpaid,++sequence);payment=current;
        try {
            boolean accepted=super.playManaHandling(ability,unpaid,message,game);
            if(accepted && current.assessment!=null && current.assessment.has("steps")) {
                JsonObject step=current.assessment.getAsJsonArray("steps").get(0).getAsJsonObject();
                if("mana_type".equals(step.get("kind").getAsString())) {
                    JsonObject receipt=new JsonObject();receipt.addProperty("sequence",current.sequence);receipt.addProperty("plan_token",current.token);
                    receipt.add("source",step.get("source"));receipt.addProperty("activated",true);receipt.addProperty("completed",false);
                    receipt.addProperty("paying_source",ability.getSourceId().toString());paymentExecution=receipt;
                }
            }
            return accepted;
        } finally{payment=previous;current.clear();}
    }
    private transient volatile JsonObject paymentExecution;
    private void finishPayment(boolean success,Ability ability,long started) {
        JsonObject old=paymentExecution;
        if(old!=null && sequence>started && old.get("sequence").getAsLong()==sequence) {
            JsonObject receipt=old.deepCopy();receipt.addProperty("completed",success);receipt.addProperty("paying_source",ability.getSourceId().toString());paymentExecution=receipt;
        }
    }
    @Override public boolean cast(mage.abilities.SpellAbility ability,Game game,boolean noMana,mage.ApprovingObject approving) {
        long started=sequence;boolean success=super.cast(ability,game,noMana,approving);finishPayment(success,ability,started);return success;
    }
    @Override public boolean activateAbility(mage.abilities.ActivatedAbility ability,Game game) {
        long started=sequence;boolean success=super.activateAbility(ability,game);finishPayment(success,ability,started);return success;
    }
    public JsonObject paymentExecution(Game game,UUID payer,int cycle) {
        if(!getId().equals(payer) || game.getPlayer(payer)!=this || game.getState().getApplyEffectsCounter()!=cycle)return null;
        JsonObject receipt=paymentExecution;return receipt==null?null:receipt.deepCopy();
    }
    private static final class TargetFrame {
        final Game game;final Ability source;final mage.target.Target target;
        TargetFrame(Game game,Ability source,mage.target.Target target){this.game=game;this.source=source;this.target=target;}
    }
    private transient volatile TargetFrame targeting;
    @Override public boolean chooseTarget(mage.constants.Outcome outcome,mage.target.Target target,Ability source,Game game){
        TargetFrame previous=targeting;targeting=new TargetFrame(game,source,target);
        try{return super.chooseTarget(outcome,target,source,game);}finally{targeting=previous;}
    }
    @Override public boolean chooseTarget(mage.constants.Outcome outcome,mage.cards.Cards cards,mage.target.TargetCard target,Ability source,Game game){
        TargetFrame previous=targeting;targeting=new TargetFrame(game,source,target);
        try{return super.chooseTarget(outcome,cards,target,source,game);}finally{targeting=previous;}
    }
    @Override public boolean chooseTargetAmount(mage.constants.Outcome outcome,mage.target.TargetAmount target,Ability source,Game game){
        TargetFrame previous=targeting;targeting=new TargetFrame(game,source,target);
        try{return super.chooseTargetAmount(outcome,target,source,game);}finally{targeting=previous;}
    }
    public JsonObject targetingProbe(Game game,UUID payer,int cycle) throws ReflectiveOperationException {
        TargetFrame frame=targeting;
        if(frame==null || frame.game!=game || frame.target==null || frame.target.isNotTarget() || game.hasEnded()
            || !getId().equals(payer) || game.getPlayer(payer)!=this || !Thread.holdsLock(RESPONSE.get(this))
            || !Boolean.TRUE.equals(OPEN.get(this)) || game.getState().getApplyEffectsCounter()!=cycle)return null;
        JsonObject result=new JsonObject();if(frame.source!=null && frame.source.getSourceId()!=null)result.addProperty("source",frame.source.getSourceId().toString());
        result.addProperty("minimum",frame.target.getMinNumberOfTargets());result.addProperty("maximum",frame.target.getMaxNumberOfTargets());
        JsonArray selected=new JsonArray();if(frame.target.getTargets().size()>256)return null;
        for(UUID id:frame.target.getTargets()){JsonObject row=new JsonObject();row.addProperty("id",id.toString());if(frame.target instanceof mage.target.TargetAmount){int amount=frame.target.getTargetAmount(id);if(amount>=0)row.addProperty("amount",amount);}selected.add(row);}result.add("selected",selected);return targeting==frame && Boolean.TRUE.equals(OPEN.get(this)) && !game.hasEnded() && game.getPlayer(payer)==this && game.getState().getApplyEffectsCounter()==cycle?result:null;
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
    /** Opaque SERVER-ONLY observation identity, never a legal action or permission to pay.
     * Weak native references cannot keep a closed private game/frame/source alive. */
    public static final class SourceTicket {
        private final Object issuer;
        private final WeakReference<Frame> frame;
        private final WeakReference<GameState> state;
        private final WeakReference<Permanent> permanent;
        private final WeakReference<ActivatedManaAbilityImpl> ability;
        private final UUID payer,source,abilityId;
        private final int cycle,incarnation,transforms;
        private final boolean tapped,phased,flipped;
        private SourceTicket(Object issuer,Frame frame,GameState state,Permanent source,ActivatedManaAbilityImpl ability,UUID payer,int cycle) {
            this.issuer=issuer;this.frame=new WeakReference<>(frame);this.state=new WeakReference<>(state);
            permanent=new WeakReference<>(source);this.ability=new WeakReference<>(ability);
            this.payer=payer;this.source=source.getId();abilityId=ability.getId();this.cycle=cycle;
            incarnation=state.getZoneChangeCounter(this.source);transforms=source.getTransformCount();
            tapped=source.isTapped();phased=source.isPhasedIn();flipped=source.isFlipped();
        }
        @Override public String toString(){return "NativeSourceTicket(private)";}
    }
    private boolean ticketCurrent(Game game,UUID payer,int cycle,SourceTicket ticket,Map<UUID,ActivatedManaAbilityImpl> candidates) {
        Frame frame=ticket.frame.get();GameState state=game.getState();Permanent permanent=game.getPermanent(ticket.source);
        ActivatedManaAbilityImpl ability=ticket.ability.get();
        return ticket.issuer==ticketOwner && frame!=null && frame==payment && ticket.payer.equals(payer) && ticket.cycle==cycle
            && ticket.state.get()==state && state.getApplyEffectsCounter()==cycle
            && permanent!=null && ticket.permanent.get()==permanent && payer.equals(permanent.getControllerId())
            && state.getZoneChangeCounter(ticket.source)==ticket.incarnation && permanent.getTransformCount()==ticket.transforms
            && permanent.isTapped()==ticket.tapped && permanent.isPhasedIn()==ticket.phased && permanent.isFlipped()==ticket.flipped
            && ability!=null && candidates.get(ticket.abilityId)==ability
            && ticket.source.equals(ability.getSourceId()) && payer.equals(ability.getControllerId());
    }
    public SourceTicket captureSourceTicket(Game game,UUID payer,int cycle,UUID source,UUID abilityId) throws ReflectiveOperationException {
        if(abilityId==null || ticketOwner==null)return null;
        return inspectBattlefieldSource(game,payer,cycle,source,(paying,unpaid,candidates)->{
            ActivatedManaAbilityImpl ability=candidates.get(abilityId);Permanent permanent=game.getPermanent(source);
            if(ability==null || permanent==null || !source.equals(ability.getSourceId()) || !payer.equals(ability.getControllerId()))return null;
            SourceTicket ticket=new SourceTicket(ticketOwner,payment,game.getState(),permanent,ability,payer,cycle);
            return ticketCurrent(game,payer,cycle,ticket,candidates)?ticket:null;
        });
    }
    /** Fresh native legality query before and after a trusted no-IO/no-mutation read.
     * Session/revision/decision admission, single-use plan claims and safety remain external. */
    public <T> T inspectSourceTicket(Game game,UUID payer,int cycle,SourceTicket ticket,SourceInspector<T> inspector) throws ReflectiveOperationException {
        if(ticket==null || inspector==null || ticket.issuer!=ticketOwner)return null;
        return inspectBattlefieldSource(game,payer,cycle,ticket.source,(paying,unpaid,candidates)->{
            if(!ticketCurrent(game,payer,cycle,ticket,candidates))return null;
            T result=inspector.read(paying,unpaid,candidates);
            Permanent permanent=game.getPermanent(ticket.source);
            if(permanent==null || permanent!=ticket.permanent.get() || game.getState()!=ticket.state.get())return null;
            Map<UUID,ActivatedManaAbilityImpl> fresh=getUseableManaAbilities(permanent,Zone.BATTLEFIELD,game);
            return fresh!=null && ticketCurrent(game,payer,cycle,ticket,fresh)?result:null;
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
    /** Conservative private assessment. Caller supplies all counter-free visible own permanents
     * from the same guarded native view. No activation, IO or client serialization here. */
    private transient NativePaymentSearch.Step executingSource;
    private transient int executionChoice;
    @Override protected void playManaAbilities(UUID source,Ability paying,ManaCost unpaid,Game game){
        Frame frame=payment;NativePaymentSearch.Step planned=frame==null?null:frame.step;
        if(!getManaPool().isAutoPayment() || planned==null || !source.equals(planned.source)){super.playManaAbilities(source,paying,unpaid,game);return;}
        frame.step=null;
        Map<UUID,ActivatedManaAbilityImpl> abilities=getUseableManaAbilities(game.getObject(source),Zone.BATTLEFIELD,game);
        if(abilities==null || !ticketCurrent(game,getId(),game.getState().getApplyEffectsCounter(),frame.ticket,abilities)
            || frame.costFingerprint==null || !frame.costFingerprint.equals(paymentCostFingerprint(paying,unpaid))){recordExecution(frame,paying,planned,false);return;}
        ActivatedManaAbilityImpl ability=abilities.get(planned.ability);if(ability==null){recordExecution(frame,paying,planned,false);return;}
        currentlyUnpaidMana=unpaid;executingSource=planned;executionChoice=0;
        try {
            boolean success=super.activateAbility(ability,game);
            recordExecution(frame,paying,planned,success);
        }
        finally{executingSource=null;executionChoice=0;currentlyUnpaidMana=null;frame.assessment=null;}
    }
    private void recordExecution(Frame frame,Ability paying,NativePaymentSearch.Step planned,boolean success) {
        JsonObject receipt=new JsonObject();receipt.addProperty("sequence",frame.sequence);receipt.addProperty("plan_token",frame.token);
        receipt.addProperty("source",planned.source.toString());receipt.addProperty("ability",planned.ability.toString());receipt.addProperty("activated",success);
        receipt.addProperty("completed",false);receipt.addProperty("paying_source",paying.getSourceId().toString());paymentExecution=receipt;
    }
    @Override public boolean choose(mage.constants.Outcome outcome,mage.choices.Choice choice,Game game){
        if(executingSource!=null && outcome==mage.constants.Outcome.PutManaInPool && choice.isManaColorChoice()
            && executionChoice<executingSource.choices.size()
            && PaymentSimulationPlayer.apply(choice,executingSource.choices.get(executionChoice))){executionChoice++;return true;}
        return super.choose(outcome,choice,game);
    }
    private static String paymentCostFingerprint(Ability ability,ManaCost unpaid) {
        try {
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
            try(java.io.ObjectOutputStream out=new java.io.ObjectOutputStream(bytes)){out.writeObject(unpaid);out.writeObject(ability.getManaCostsToPay());}
            byte[] hash=java.security.MessageDigest.getInstance("SHA-256").digest(bytes.toByteArray());StringBuilder result=new StringBuilder();for(byte value:hash)result.append(String.format("%02x",value & 255));return result.toString();
        }catch(java.io.IOException | java.security.NoSuchAlgorithmException unavailable){return null;}
    }
    public JsonObject ordinaryPayment(Game game,UUID payer,int cycle,UUID[] sources) throws ReflectiveOperationException {
        if(sources==null || sources.length>512)return null;
        return inspectPayment(game,payer,cycle,(paying,unpaid)->{
            Frame frame=payment;String costFingerprint=paymentCostFingerprint(paying,unpaid);
            if(costFingerprint==null){JsonObject unknown=new JsonObject();unknown.addProperty("safety","UNKNOWN");unknown.addProperty("reason","UNSUPPORTED_INTERACTION");unknown.addProperty("outcome","UNSUPPORTED_INTERACTION");return unknown;}
            if(frame.assessment!=null && frame.assessedState==game.getState() && frame.assessedCycle==cycle
                && java.util.Arrays.equals(frame.assessedSources,sources) && costFingerprint.equals(frame.costFingerprint)) {
                if(frame.step!=null) {
                    try{if(!Boolean.TRUE.equals(inspectSourceTicket(game,payer,cycle,frame.ticket,(a,c,abilities)->true))){frame.assessment=null;frame.step=null;JsonObject stale=new JsonObject();stale.addProperty("safety","UNKNOWN");stale.addProperty("reason","STALE_CONTEXT");stale.addProperty("outcome","STALE_CONTEXT");return stale;}}
                    catch(ReflectiveOperationException changed){frame.assessment=null;frame.step=null;return null;}
                }
                return frame.assessment.deepCopy();
            }
            frame.step=null;frame.ticket=null;frame.token=UUID.randomUUID().toString();frame.costFingerprint=costFingerprint;JsonObject result=new JsonObject();result.addProperty("safety","UNKNOWN");
            result.addProperty("reason","UNSUPPORTED_INTERACTION");result.addProperty("outcome","UNSUPPORTED_INTERACTION");
            NativePaymentHazards.Assessment hazard=NativePaymentHazards.assessSimulation(game,paying);
            if(hazard.result!=NativePaymentHazards.Result.NO_REGISTERED_HAZARD){result.addProperty("reason",hazard.reason);result.addProperty("outcome","CONSEQUENTIAL_CHOICE_REQUIRED");return result;}
            NativePaymentSearch.Result search;
            try{search=NativePaymentSearch.search(game,payer,paying,unpaid,sources);}catch(RuntimeException unavailable){return result;}
            result.addProperty("outcome",search.outcome.name());result.addProperty("reason",search.outcome.name());
            result.addProperty("examined",search.examined);
            if(search.outcome!=NativePaymentSearch.Outcome.READY)return result;
            JsonArray steps=new JsonArray();JsonObject step=new JsonObject();
            if(search.steps.isEmpty()) {
                // A native allocation on the copied pool proved full coverage. Unlock a
                // present pool type; the real native allocator retains all restrictions.
                mage.constants.ManaType type=null;
                for(mage.players.ManaPoolItem item:getManaPool().getManaItems())for(mage.constants.ManaType candidate:mage.constants.ManaType.values())
                    if(type==null && candidate!=mage.constants.ManaType.GENERIC && (item.isConditional()?item.getConditionalMana():item.getMana()).get(candidate)>0)type=candidate;
                if(type==null){result.addProperty("reason","NO_UNPAID_COST");return result;}
                step.addProperty("source","pool:"+type.name());step.addProperty("kind","mana_type");
            } else {
                NativePaymentSearch.Step first=search.steps.get(0);SourceTicket ticket;
                try{ticket=captureSourceTicket(game,payer,cycle,first.source,first.ability);}catch(ReflectiveOperationException missing){result.addProperty("reason","STALE_CONTEXT");return result;}
                if(ticket==null){result.addProperty("reason","STALE_CONTEXT");return result;}
                frame.step=first;frame.ticket=ticket;
                step.addProperty("source",first.source.toString());step.addProperty("ability",first.ability.toString());step.addProperty("incarnation",game.getState().getZoneChangeCounter(first.source));step.addProperty("kind","object");
            }
            steps.add(step);result.add("steps",steps);result.addProperty("safety","VERIFIED_ORDINARY_EQUIVALENT");
            result.addProperty("reason","VERIFIED_ORDINARY_EQUIVALENT");result.addProperty("sequence",frame.sequence);
            result.addProperty("plan_token",frame.token);result.addProperty("cost_fingerprint",costFingerprint);result.addProperty("paying_source",paying.getSourceId().toString());
            result.addProperty("unpaid_count",NativePaymentSearch.unpaid(unpaid));
            frame.assessment=result.deepCopy();frame.assessedState=game.getState();frame.assessedCycle=cycle;frame.assessedSources=sources.clone();
            return result;
        });
    }

    public JsonObject paymentProbe(Game game,UUID payer,int cycle,UUID[] visibleSources) throws ReflectiveOperationException {
        if(visibleSources==null || visibleSources.length>512)return null;
        final int[] counts={0,0,0};
        int tickets=0;
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
            UUID candidate=inspectBattlefieldSource(game,payer,cycle,source,(paying,unpaid,abilities)->abilities.size()==1?abilities.keySet().iterator().next():null);
            SourceTicket ticket=captureSourceTicket(game,payer,cycle,source,candidate);
            if(ticket!=null && Boolean.TRUE.equals(inspectSourceTicket(game,payer,cycle,ticket,(paying,unpaid,abilities)->true)))tickets++;
        }
        final int revalidated=tickets;
        return inspectPayment(game,payer,cycle,(ability,unpaid)->{
            JsonObject result=new JsonObject();result.addProperty("available",true);
            result.addProperty("unpaid_mana_count",unpaid.getUnpaid().getMana().count());
            result.addProperty("sequence",payment.sequence);
            result.addProperty("candidate_sources",counts[0]);
            result.addProperty("candidate_abilities",counts[1]);
            result.addProperty("ordinary_shape_abilities",counts[2]);
            // BASE templates only: replacement effects, restrictions, floating mana and strategy
            // have not been reviewed. This does NOT authorize selection or activation.
            result.addProperty("base_cost_coverage",OrdinaryCostCoverage.inspect(unpaid,baseTotal).name());
            result.addProperty("registered_hazards",NativePaymentHazards.inspect(game,ability).name());
            result.addProperty("source_tickets_revalidated",revalidated);return result;
        });
    }
}

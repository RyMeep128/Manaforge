package manaforge.payment.xmage;

import java.util.UUID;
import mage.abilities.Ability;
import mage.cards.Card;
import mage.cards.CardImpl;
import mage.constants.AbilityType;
import mage.game.Game;
import mage.game.GameState;
import mage.players.Player;

/** Private, read-only exclusion screen inside a paused native payment context.
 * NO_REGISTERED_HAZARD is not safety, equivalence, legality or permission to activate.
 * Never exports registered effect/trigger names, identities or hidden-zone information. */
public final class NativePaymentHazards {
    public enum Result { REQUIRES_MANUAL, NO_REGISTERED_HAZARD, UNKNOWN }
    public static final class Assessment {
        public final Result result;public final String reason;
        private Assessment(Result result,String reason){this.result=result;this.reason=reason;}
    }
    private static Assessment unknown(){return new Assessment(Result.UNKNOWN,"UNKNOWN_HAZARD_CONTEXT");}
    private static Assessment manual(String reason){return new Assessment(Result.REQUIRES_MANUAL,reason);}
    private static Assessment clear(){return new Assessment(Result.NO_REGISTERED_HAZARD,"NO_REGISTERED_HAZARD");}
    private NativePaymentHazards() {}
    public static Result inspect(Game game,Ability payingAbility) {return assess(game,payingAbility,false).result;}
    /** Screens only events emitted by ordinary counter-free tap mana sources.
     * The caller still validates costs, native legality, production and source tickets. */
    public static Result inspectOrdinaryTap(Game game,Ability payingAbility){return assessOrdinaryTap(game,payingAbility).result;}
    public static Assessment assessOrdinaryTap(Game game,Ability payingAbility){return assess(game,payingAbility,true);}
    // Read only the native event-type prefilter. Never call applies/checkTrigger or
    // replacement execution: those methods can change the game or ask a choice.
    private static final mage.game.events.GameEvent.EventType[] PAYMENT_EVENTS={
        mage.game.events.GameEvent.EventType.TAP,mage.game.events.GameEvent.EventType.TAPPED,
        mage.game.events.GameEvent.EventType.TAPPED_FOR_MANA,mage.game.events.GameEvent.EventType.TAPPED_BATCH,
        mage.game.events.GameEvent.EventType.ACTIVATE_ABILITY,mage.game.events.GameEvent.EventType.ACTIVATED_ABILITY,
        mage.game.events.GameEvent.EventType.ADD_MANA,mage.game.events.GameEvent.EventType.MANA_ADDED,
        mage.game.events.GameEvent.EventType.MANA_PAID};
    private static boolean inactiveBattlefieldSource(Ability ability,Game game){
        if(ability.getZone()!=mage.constants.Zone.BATTLEFIELD || ability.getSourceId()==null)return false;
        mage.constants.Zone zone=game.getState().getZone(ability.getSourceId());
        // Only exclude sources proven to be in a different stable zone. Unknown
        // identities, delayed abilities and pending triggers remain conservative.
        return (zone==mage.constants.Zone.LIBRARY || zone==mage.constants.Zone.HAND
            || zone==mage.constants.Zone.GRAVEYARD || zone==mage.constants.Zone.EXILED)
            && game.getPermanent(ability.getSourceId())==null && game.getCard(ability.getSourceId())!=null;
    }
    private static String paymentTriggers(Iterable<? extends mage.abilities.TriggeredAbility> triggers,Game game,Ability paying,boolean registered){
        int scanned=0,active=0;for(mage.abilities.TriggeredAbility trigger:triggers){
            if(++scanned>4096 || trigger==null)return "TRIGGER_SCAN_UNAVAILABLE";
            if(registered && inactiveBattlefieldSource(trigger,game))continue;
            if(++active>128)return "ACTIVE_HAZARD_SCAN_LIMIT";
            for(mage.game.events.GameEvent.EventType type:PAYMENT_EVENTS)
                if(trigger.checkEventType(mage.game.events.GameEvent.getEvent(type,paying.getSourceId(),paying,paying.getControllerId()),game))return "MANA_TRIGGER_EVENT";
        }return null;
    }
    private static String paymentEffects(mage.abilities.effects.ContinuousEffects effects,Game game,Ability paying){
        int count=0,active=0;for(mage.abilities.effects.ContinuousEffectsList<?> list:effects.allEffectsLists)for(mage.abilities.effects.ContinuousEffect effect:list){
            if(++count>4096 || effect==null)return "EFFECT_SCAN_UNAVAILABLE";
            java.util.Set<Ability> origins=list.getAbility(effect.getId());
            if(origins!=null && !origins.isEmpty()){
                boolean inactive=true;
                for(Ability origin:origins)if(origin==null || origin.getAbilityType()!=AbilityType.STATIC
                    || !inactiveBattlefieldSource(origin,game)){inactive=false;break;}
                if(inactive)continue;
            }
            if(++active>128)return "ACTIVE_HAZARD_SCAN_LIMIT";
            if(effect instanceof mage.abilities.effects.ReplacementEffect){
                for(mage.game.events.GameEvent.EventType type:PAYMENT_EVENTS)
                    if(((mage.abilities.effects.ReplacementEffect)effect).checksEventType(mage.game.events.GameEvent.getEvent(type,paying.getSourceId(),paying,paying.getControllerId()),game))return "MANA_REPLACEMENT_EVENT";
            }else if(effect instanceof mage.abilities.effects.ContinuousRuleModifyingEffect){
                for(mage.game.events.GameEvent.EventType type:PAYMENT_EVENTS)
                    if(((mage.abilities.effects.ContinuousRuleModifyingEffect)effect).checksEventType(mage.game.events.GameEvent.getEvent(type,paying.getSourceId(),paying,paying.getControllerId()),game))return "MANA_RULE_EVENT";
            }else if(effect instanceof mage.abilities.effects.CostModificationEffect){
                // The spell's unpaid cost is already finalized. A cost reduction
                // cannot add a cost to the zero-mana, tap-only source candidates
                // that ordinaryPayment separately verifies. Increases and sets can.
                if(((mage.abilities.effects.CostModificationEffect)effect).getModificationType()!=mage.constants.CostModificationType.REDUCE_COST)return "MANA_COST_MODIFIER";
            }else if(effect.getEffectType()!=mage.constants.EffectType.CONTINUOUS || !derivedCharacteristics(effect))return "UNSUPPORTED_CONTINUOUS_EFFECT";
        }return count!=effects.getTotalEffectsCount()?"EFFECT_REGISTRY_CHANGED":null;
    }
    // These layers have already been applied to the native objects. Inspect the
    // resulting controller, legal mana abilities, costs and productions instead
    // of treating lifelink, creature types or lord abilities as payment events.
    private static boolean derivedCharacteristics(mage.abilities.effects.ContinuousEffect effect){
        mage.constants.Layer layer=effect.getLayer();
        return layer==mage.constants.Layer.CopyEffects_1 || layer==mage.constants.Layer.ControlChangingEffects_2
            || layer==mage.constants.Layer.TextChangingEffects_3 || layer==mage.constants.Layer.TypeChangingEffects_4
            || layer==mage.constants.Layer.ColorChangingEffects_5 || layer==mage.constants.Layer.AbilityAddingRemovingEffects_6
            || layer==mage.constants.Layer.PTChangingEffects_7;
    }
    private static Assessment assess(Game game,Ability payingAbility,boolean ordinaryTap) {
        if(game==null || payingAbility==null)return unknown();
        try {
            if(game.hasEnded())return unknown();
            GameState state=game.getState();if(state==null)return unknown();
            int cycle=state.getApplyEffectsCounter();
            if(state.getContinuousEffects()==null || state.getTriggers()==null || state.getDelayed()==null || state.getPlayers()==null)return unknown();
            int effects=state.getContinuousEffects().getTotalEffectsCount();
            if(effects<0 || state.getPlayers().size()>128)return unknown();
            if(state.isManaBurn())return manual("MANA_BURN");
            if(ordinaryTap){
                String reason=paymentEffects(state.getContinuousEffects(),game,payingAbility);
                if(reason==null)reason=paymentTriggers(state.getTriggers().values(),game,payingAbility,true);
                if(reason==null)reason=paymentTriggers(state.getDelayed(),game,payingAbility,false);
                if(reason!=null)return manual(reason);
            }else if(effects>0 || !state.getTriggers().isEmpty() || !state.getDelayed().isEmpty())return manual("REGISTERED_HAZARDS");
            // No two-seat/five-seat rule: this is only a bounded internal read budget.
            for(UUID id:state.getPlayers().keySet()) {
                Player player=state.getPlayers().get(id);
                if(id==null || player==null || !id.equals(player.getId()))return unknown();
                if(!state.getTriggered(id).isEmpty())return manual("PENDING_TRIGGER");
            }
            // Spell and activated-ability payments use the same guarded source context.
            UUID source=payingAbility.getSourceId();
            if((payingAbility.getAbilityType()!=AbilityType.SPELL && !payingAbility.getAbilityType().isActivatedAbility()) || source==null)return unknown();
            Card card=game.getCard(source);
            if(payingAbility.getAbilityType().isActivatedAbility()){
                mage.MageObject object=game.getObject(source);
                return object!=null && source.equals(object.getId()) && game.getState()==state && state.getApplyEffectsCounter()==cycle?clear():unknown();
            }
            if(!(card instanceof CardImpl) || !source.equals(card.getId()))return unknown();
            // Same native check used by HumanPlayer before narrowing selected-source abilities.
            if(((CardImpl)card).caresAboutManaColor(game))return manual("MANA_COLOR_DEPENDENT");
            return !game.hasEnded() && game.getState()==state && state.getApplyEffectsCounter()==cycle
                && source.equals(payingAbility.getSourceId()) && game.getCard(source)==card
                ?clear():unknown();
        }catch(RuntimeException unavailable){return unknown();}
    }
}

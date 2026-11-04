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
    private NativePaymentHazards() {}
    public static Result inspect(Game game,Ability payingAbility) {return inspect(game,payingAbility,false);}
    /** Screens only events emitted by ordinary counter-free tap mana sources.
     * The caller still validates costs, native legality, production and source tickets. */
    public static Result inspectOrdinaryTap(Game game,Ability payingAbility){return inspect(game,payingAbility,true);}
    // Read only the native event-type prefilter. Never call applies/checkTrigger or
    // replacement execution: those methods can change the game or ask a choice.
    private static final mage.game.events.GameEvent.EventType[] PAYMENT_EVENTS={
        mage.game.events.GameEvent.EventType.TAP,mage.game.events.GameEvent.EventType.TAPPED,
        mage.game.events.GameEvent.EventType.TAPPED_FOR_MANA,mage.game.events.GameEvent.EventType.TAPPED_BATCH,
        mage.game.events.GameEvent.EventType.ACTIVATE_ABILITY,mage.game.events.GameEvent.EventType.ACTIVATED_ABILITY,
        mage.game.events.GameEvent.EventType.ADD_MANA,mage.game.events.GameEvent.EventType.MANA_ADDED,
        mage.game.events.GameEvent.EventType.MANA_PAID};
    private static boolean paymentTriggers(Iterable<? extends mage.abilities.TriggeredAbility> triggers,Game game,Ability paying){
        int count=0;for(mage.abilities.TriggeredAbility trigger:triggers){
            if(++count>128 || trigger==null)return true;
            for(mage.game.events.GameEvent.EventType type:PAYMENT_EVENTS)
                if(trigger.checkEventType(mage.game.events.GameEvent.getEvent(type,paying.getSourceId(),paying,paying.getControllerId()),game))return true;
        }return false;
    }
    private static boolean paymentEffects(mage.abilities.effects.ContinuousEffects effects,Game game,Ability paying){
        int count=0;for(mage.abilities.effects.ContinuousEffectsList<?> list:effects.allEffectsLists)for(mage.abilities.effects.ContinuousEffect effect:list){
            if(++count>128 || effect==null)return true;
            if(effect instanceof mage.abilities.effects.ReplacementEffect){
                for(mage.game.events.GameEvent.EventType type:PAYMENT_EVENTS)
                    if(((mage.abilities.effects.ReplacementEffect)effect).checksEventType(mage.game.events.GameEvent.getEvent(type,paying.getSourceId(),paying,paying.getControllerId()),game))return true;
            }else if(effect.getLayer()!=mage.constants.Layer.PTChangingEffects_7 && effect.getLayer()!=mage.constants.Layer.ColorChangingEffects_5)return true;
        }return count!=effects.getTotalEffectsCount();
    }
    private static Result inspect(Game game,Ability payingAbility,boolean ordinaryTap) {
        if(game==null || payingAbility==null)return Result.UNKNOWN;
        try {
            if(game.hasEnded())return Result.UNKNOWN;
            GameState state=game.getState();if(state==null)return Result.UNKNOWN;
            int cycle=state.getApplyEffectsCounter();
            if(state.getContinuousEffects()==null || state.getTriggers()==null || state.getDelayed()==null || state.getPlayers()==null)return Result.UNKNOWN;
            int effects=state.getContinuousEffects().getTotalEffectsCount();
            if(effects<0 || state.getPlayers().size()>128)return Result.UNKNOWN;
            if(state.isManaBurn() || (ordinaryTap?paymentEffects(state.getContinuousEffects(),game,payingAbility) || paymentTriggers(state.getTriggers().values(),game,payingAbility) || paymentTriggers(state.getDelayed(),game,payingAbility):effects>0 || !state.getTriggers().isEmpty() || !state.getDelayed().isEmpty()))return Result.REQUIRES_MANUAL;
            // No two-seat/five-seat rule: this is only a bounded internal read budget.
            for(UUID id:state.getPlayers().keySet()) {
                Player player=state.getPlayers().get(id);
                if(id==null || player==null || !id.equals(player.getId()))return Result.UNKNOWN;
                if(!state.getTriggered(id).isEmpty())return Result.REQUIRES_MANUAL;
            }
            // Spell and activated-ability payments use the same guarded source context.
            UUID source=payingAbility.getSourceId();
            if((payingAbility.getAbilityType()!=AbilityType.SPELL && !payingAbility.getAbilityType().isActivatedAbility()) || source==null)return Result.UNKNOWN;
            Card card=game.getCard(source);
            if(payingAbility.getAbilityType().isActivatedAbility()){
                mage.MageObject object=game.getObject(source);
                return object!=null && source.equals(object.getId()) && game.getState()==state && state.getApplyEffectsCounter()==cycle?Result.NO_REGISTERED_HAZARD:Result.UNKNOWN;
            }
            if(!(card instanceof CardImpl) || !source.equals(card.getId()))return Result.UNKNOWN;
            // Same native check used by HumanPlayer before narrowing selected-source abilities.
            if(((CardImpl)card).caresAboutManaColor(game))return Result.REQUIRES_MANUAL;
            return !game.hasEnded() && game.getState()==state && state.getApplyEffectsCounter()==cycle
                && source.equals(payingAbility.getSourceId()) && game.getCard(source)==card
                ?Result.NO_REGISTERED_HAZARD:Result.UNKNOWN;
        }catch(RuntimeException unavailable){return Result.UNKNOWN;}
    }
}

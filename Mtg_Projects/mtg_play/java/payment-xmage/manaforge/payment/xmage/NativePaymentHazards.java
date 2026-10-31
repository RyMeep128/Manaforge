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
    public static Result inspect(Game game,Ability payingAbility) {
        if(game==null || payingAbility==null)return Result.UNKNOWN;
        try {
            if(game.hasEnded())return Result.UNKNOWN;
            GameState state=game.getState();if(state==null)return Result.UNKNOWN;
            int cycle=state.getApplyEffectsCounter();
            if(state.getContinuousEffects()==null || state.getTriggers()==null || state.getDelayed()==null || state.getPlayers()==null)return Result.UNKNOWN;
            int effects=state.getContinuousEffects().getTotalEffectsCount();
            if(effects<0 || state.getPlayers().size()>128)return Result.UNKNOWN;
            if(state.isManaBurn() || effects>0 || !state.getTriggers().isEmpty() || !state.getDelayed().isEmpty())return Result.REQUIRES_MANUAL;
            // No two-seat/five-seat rule: this is only a bounded internal read budget.
            for(UUID id:state.getPlayers().keySet()) {
                Player player=state.getPlayers().get(id);
                if(id==null || player==null || !id.equals(player.getId()))return Result.UNKNOWN;
                if(!state.getTriggered(id).isEmpty())return Result.REQUIRES_MANUAL;
            }
            // Initial scope is spell payments. Activated/other payment families need review.
            UUID source=payingAbility.getSourceId();
            if(payingAbility.getAbilityType()!=AbilityType.SPELL || source==null)return Result.UNKNOWN;
            Card card=game.getCard(source);
            if(!(card instanceof CardImpl) || !source.equals(card.getId()))return Result.UNKNOWN;
            // Same native check used by HumanPlayer before narrowing selected-source abilities.
            if(((CardImpl)card).caresAboutManaColor(game))return Result.REQUIRES_MANUAL;
            return !game.hasEnded() && game.getState()==state && state.getApplyEffectsCounter()==cycle
                && source.equals(payingAbility.getSourceId()) && game.getCard(source)==card
                ?Result.NO_REGISTERED_HAZARD:Result.UNKNOWN;
        }catch(RuntimeException unavailable){return Result.UNKNOWN;}
    }
}

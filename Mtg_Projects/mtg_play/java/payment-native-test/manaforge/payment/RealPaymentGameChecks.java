package manaforge.payment;

import com.google.gson.*;
import java.lang.reflect.Field;
import java.util.*;
import java.util.concurrent.*;
import mage.cards.Card;
import mage.cards.CardSetInfo;
import mage.constants.*;
import mage.game.TwoPlayerDuel;
import mage.game.events.PlayerQueryEvent;
import mage.game.permanent.PermanentCard;
import mage.player.human.HumanPlayer;
import manaforge.payment.xmage.ContextHumanPlayer;

/** Real native game/cast/payment regression. No proxy game, simulated sources or manual mana responses. */
public final class RealPaymentGameChecks {
    private static void require(boolean value,String code){if(!value)throw new AssertionError(code);}
    private static CardSetInfo info(String name){return new CardSetInfo(name,"TST","1",Rarity.COMMON);}
    private static void load(TwoPlayerDuel game,Card card,Zone zone){
        game.loadCards(Collections.singleton(card),card.getOwnerId());game.setZone(card.getId(),zone);
        if(zone==Zone.BATTLEFIELD){
            PermanentCard permanent=new PermanentCard(card,card.getOwnerId(),game);game.addPermanent(permanent,0);
            for(mage.abilities.Ability ability:permanent.getAbilities())game.getState().addAbility(ability,permanent);
        }else if(zone==Zone.HAND)game.getPlayer(card.getOwnerId()).getHand().add(card);
    }
    private static void scenario(boolean doubleRed) throws Exception {
        TwoPlayerDuel game=new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),20,7,7);
        ContextHumanPlayer payer=new ContextHumanPlayer("Public payer",RangeOfInfluence.ALL,0);
        ContextHumanPlayer opponent=new ContextHumanPlayer("Public opponent",RangeOfInfluence.ALL,0);
        game.addPlayer(payer,new mage.cards.decks.Deck());game.addPlayer(opponent,new mage.cards.decks.Deck());
        game.getState().setActivePlayerId(payer.getId());game.getState().setPriorityPlayerId(payer.getId());
        game.getState().setTurnNum(4);game.getTurn().setPhase(new mage.game.turn.PreCombatMainPhase());
        payer.init(game);opponent.init(game);payer.getManaPool().setAutoPayment(true);
        // GameImpl.init normally installs these after pregame. Include them in
        // the focused board fixture rather than testing an unrealistically empty rules registry.
        for(mage.abilities.effects.Effect rule:new mage.abilities.effects.Effect[]{
            new mage.abilities.effects.keyword.ShieldCounterEffect(),new mage.abilities.effects.keyword.StunCounterEffect(),
            new mage.abilities.effects.keyword.FinalityCounterEffect()})
            game.getState().addAbility(new mage.abilities.common.SimpleStaticAbility(Zone.ALL,rule),(Card)null);
        game.initGameDefaultWatchers();
        game.getState().addHelperEmblem(new mage.game.command.emblems.RadiationEmblem(),payer.getId());
        game.getState().addHelperEmblem(new mage.game.command.emblems.RadiationEmblem(),opponent.getId());
        Card first=new mage.cards.basiclands.Mountain(payer.getId(),info("Mountain"));
        Card second=new mage.cards.basiclands.Mountain(payer.getId(),info("Mountain"));
        load(game,first,Zone.BATTLEFIELD);load(game,second,Zone.BATTLEFIELD);
        Card herald=new mage.cards.w.WirewoodHerald(opponent.getId(),info("Wirewood Herald"));
        Card elves=new mage.cards.l.LlanowarElves(opponent.getId(),info("Llanowar Elves"));
        load(game,herald,Zone.BATTLEFIELD);load(game,elves,Zone.BATTLEFIELD);
        Card spell=doubleRed?new mage.cards.e.EmberHauler(payer.getId(),info("Ember Hauler")):
            new mage.cards.f.FoundryStreetDenizen(payer.getId(),info("Foundry Street Denizen"));
        load(game,spell,Zone.HAND);game.applyEffects();game.saveState(false);
        require(!game.getState().getTriggers().isEmpty(),"REAL_OPPONENT_TRIGGER_NOT_REGISTERED");
        UUID[] sources={first.getId(),second.getId()};
        BlockingQueue<PlayerQueryEvent> queries=new LinkedBlockingQueue<>();game.addPlayerQueryEventListener(queries::add);
        Field responseField=HumanPlayer.class.getDeclaredField("response");responseField.setAccessible(true);
        Object response=responseField.get(payer);
        ExecutorService executor=Executors.newSingleThreadExecutor(task->{Thread thread=new Thread(task,"GAME-real-payment");thread.setDaemon(true);return thread;});
        Future<Boolean> cast=executor.submit(()->payer.cast(spell.getSpellAbility(),game,false,null));
        int automaticSources=0,poolResponses=0;long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(20);
        try {
            while(!cast.isDone() && System.nanoTime()<deadline){
                PlayerQueryEvent event=queries.poll(50,TimeUnit.MILLISECONDS);if(event==null)continue;
                require(event.getPlayerId().equals(payer.getId()) && event.getQueryType()==PlayerQueryEvent.QueryType.PLAY_MANA,"UNEXPECTED_REAL_PAYMENT_CHOICE_"+event.getQueryType());
                JsonObject assessment=null;
                while(assessment==null && !cast.isDone() && System.nanoTime()<deadline){
                    synchronized(response){assessment=payer.ordinaryPayment(game,payer.getId(),game.getState().getApplyEffectsCounter(),sources);}
                    if(assessment==null)Thread.sleep(1);
                }
                require(assessment!=null,"REAL_PAYMENT_CONTEXT_MISSING");
                require("VERIFIED_ORDINARY_EQUIVALENT".equals(assessment.get("safety").getAsString()),"REAL_PAYMENT_FALLBACK_"+assessment.get("reason").getAsString());
                JsonObject step=assessment.getAsJsonArray("steps").get(0).getAsJsonObject();
                if("mana_type".equals(step.get("kind").getAsString())){
                    require(++poolResponses<=2,"REAL_PAYMENT_POOL_LOOP");
                    payer.setResponseManaType(payer.getId(),ManaType.valueOf(step.get("source").getAsString().substring(5)));
                }else{
                    require(++automaticSources<=2,"REAL_PAYMENT_SOURCE_LOOP");
                    payer.setResponseUUID(UUID.fromString(step.get("source").getAsString()));
                }
            }
            require(cast.get(1,TimeUnit.SECONDS),"REAL_CAST_FAILED");
            require(game.getStack().size()==1 && game.getStack().getFirst().getSourceId().equals(spell.getId()),"REAL_SPELL_NOT_ON_STACK");
            int tapped=(game.getPermanent(first.getId()).isTapped()?1:0)+(game.getPermanent(second.getId()).isTapped()?1:0);
            require(tapped==(doubleRed?2:1) && automaticSources==tapped,"REAL_PAYMENT_WRONG_MOUNTAINS");
            require(!game.getPermanent(elves.getId()).isTapped(),"REAL_PAYMENT_USED_OPPONENT_SOURCE");
            game.getStack().resolve(game);
            require(game.getStack().isEmpty() && game.getPermanent(spell.getId())!=null,"REAL_SPELL_NOT_RESOLVED");
            JsonObject proof=new JsonObject();proof.addProperty("scenario",doubleRed?"two-red-mountains":"foundry-street-opponent-triggers");
            proof.addProperty("real_engine",true);proof.addProperty("mountains_tapped",tapped);proof.addProperty("manual_payment_inputs",0);
            proof.addProperty("spell_stacked_and_resolved",true);System.out.println(proof);
        }finally{payer.abort();opponent.abort();cast.cancel(true);executor.shutdownNow();executor.awaitTermination(2,TimeUnit.SECONDS);}
    }
    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("GAME-real-payment-setup");scenario(false);scenario(true);
    }
}

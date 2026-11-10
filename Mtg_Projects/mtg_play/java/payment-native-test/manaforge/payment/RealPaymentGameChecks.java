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
    private static void scenario(String name,boolean doubleRed,boolean activeHazard) throws Exception {
        boolean green=name.equals("green") || name.equals("generic-green");
        boolean blue=name.equals("mixed-blue");
        boolean generic=name.equals("generic-green");
        boolean poolOnly=name.equals("floating-only");
        boolean poolMixed=name.equals("floating-and-source");
        boolean poolGeneric=name.equals("floating-generic");
        boolean insufficient=name.equals("insufficient");
        int expectedTaps=poolOnly?0:poolMixed || poolGeneric?1:generic?3:blue || doubleRed?2:1;
        TwoPlayerDuel game=new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),20,7,7);
        ContextHumanPlayer payer=new ContextHumanPlayer("Public payer",RangeOfInfluence.ALL,0);
        ContextHumanPlayer opponent=new ContextHumanPlayer("Public opponent",RangeOfInfluence.ALL,0);
        payer.setUserData(mage.players.net.UserData.getDefaultUserDataView());
        opponent.setUserData(mage.players.net.UserData.getDefaultUserDataView());
        game.addPlayer(payer,new mage.cards.decks.Deck());game.addPlayer(opponent,new mage.cards.decks.Deck());
        // GameImpl.init normally binds this transient turn-order cursor. Failed
        // casts restore the saved state and need the same cursor as a live game.
        Field playerList= mage.game.GameImpl.class.getDeclaredField("playerList");playerList.setAccessible(true);
        game.getState().getPlayerList().add(payer.getId());game.getState().getPlayerList().add(opponent.getId());
        game.getState().getPlayerList().setCurrent(payer.getId());playerList.set(game,game.getState().getPlayerList());
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
        Card first=green?new mage.cards.basiclands.Forest(payer.getId(),info("Forest")):
            blue?new mage.cards.basiclands.Island(payer.getId(),info("Island")):new mage.cards.basiclands.Mountain(payer.getId(),info("Mountain"));
        Card second=new mage.cards.basiclands.Mountain(payer.getId(),info("Mountain"));
        load(game,first,Zone.BATTLEFIELD);load(game,second,Zone.BATTLEFIELD);
        Card third=generic?new mage.cards.basiclands.Mountain(payer.getId(),info("Mountain")):null;
        if(third!=null)load(game,third,Zone.BATTLEFIELD);
        Card herald=new mage.cards.w.WirewoodHerald(opponent.getId(),info("Wirewood Herald"));
        Card elves=new mage.cards.l.LlanowarElves(opponent.getId(),info("Llanowar Elves"));
        load(game,herald,Zone.BATTLEFIELD);load(game,elves,Zone.BATTLEFIELD);
        // A registered battlefield ability in a library must not affect this board.
        // Real games register abilities for the whole deck, unlike a five-card fixture.
        Card inactive=new mage.cards.m.Manabarbs(opponent.getId(),info("Manabarbs"));
        load(game,inactive,activeHazard?Zone.BATTLEFIELD:Zone.LIBRARY);
        Card inactiveReplacement=new mage.cards.m.ManaFlare(opponent.getId(),info("Mana Flare"));
        load(game,inactiveReplacement,Zone.LIBRARY);
        if(name.equals("registered-decks"))for(int i=0;i<140;i++){
            UUID owner=i%2==0?payer.getId():opponent.getId();
            load(game,new mage.cards.m.Manabarbs(owner,info("Manabarbs")),Zone.LIBRARY);
            load(game,new mage.cards.m.ManaFlare(owner,info("Mana Flare")),Zone.LIBRARY);
        }
        Card spell=generic?new mage.cards.c.CentaurCourser(payer.getId(),info("Centaur Courser")):
            green?new mage.cards.s.SedgeScorpion(payer.getId(),info("Sedge Scorpion")):
            blue || poolGeneric?new mage.cards.c.CoralMerfolk(payer.getId(),info("Coral Merfolk")):doubleRed?new mage.cards.e.EmberHauler(payer.getId(),info("Ember Hauler")):
            new mage.cards.f.FoundryStreetDenizen(payer.getId(),info("Foundry Street Denizen"));
        load(game,spell,Zone.HAND);
        if(poolOnly || poolMixed)payer.getManaPool().addMana(mage.Mana.RedMana(1),game,first.getAbilities().get(0));
        if(poolGeneric)payer.getManaPool().addMana(mage.Mana.BlueMana(1),game,first.getAbilities().get(0));
        if(insufficient)game.getPermanent(second.getId()).setTapped(true);
        game.applyEffects();game.saveState(false);
        require(!game.getState().getTriggers().isEmpty(),"REAL_OPPONENT_TRIGGER_NOT_REGISTERED");
        UUID[] sources=third==null?new UUID[]{first.getId(),second.getId()}:new UUID[]{first.getId(),second.getId(),third.getId()};
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
                if(activeHazard || insufficient){
                    require((activeHazard?"REQUIRES_MANUAL":"INSUFFICIENT_OR_UNSUPPORTED_SOURCES").equals(assessment.get("reason").getAsString()),"REAL_UNSAFE_PAYMENT_NOT_REJECTED");
                    require(automaticSources==0 && !game.getPermanent(first.getId()).isTapped() && game.getPermanent(second.getId()).isTapped()==insufficient,"REAL_HAZARD_TAPPED_SOURCE");
                    payer.setResponseBoolean(false);
                    require(!cast.get(2,TimeUnit.SECONDS),"REAL_HAZARD_CAST_NOT_CANCELLED");
                    System.out.println("{\"scenario\":\""+name+"\",\"real_engine\":true,\"manual_required\":true,\"automatic_sources\":0}");
                    return;
                }
                require("VERIFIED_ORDINARY_EQUIVALENT".equals(assessment.get("safety").getAsString()),"REAL_PAYMENT_FALLBACK_"+assessment.get("reason").getAsString());
                JsonObject step=assessment.getAsJsonArray("steps").get(0).getAsJsonObject();
                if("mana_type".equals(step.get("kind").getAsString())){
                    require(++poolResponses<=2,"REAL_PAYMENT_POOL_LOOP");
                    payer.setResponseManaType(payer.getId(),ManaType.valueOf(step.get("source").getAsString().substring(5)));
                }else{
                    require(++automaticSources<=sources.length,"REAL_PAYMENT_SOURCE_LOOP");
                    payer.setResponseUUID(UUID.fromString(step.get("source").getAsString()));
                }
            }
            require(cast.get(1,TimeUnit.SECONDS),"REAL_CAST_FAILED");
            require(game.getStack().size()==1 && game.getStack().getFirst().getSourceId().equals(spell.getId()),"REAL_SPELL_NOT_ON_STACK");
            int tapped=0;for(UUID id:sources)if(game.getPermanent(id).isTapped())tapped++;
            require(tapped==expectedTaps && automaticSources==tapped,"REAL_PAYMENT_WRONG_MOUNTAINS");
            require(!game.getPermanent(elves.getId()).isTapped(),"REAL_PAYMENT_USED_OPPONENT_SOURCE");
            game.getStack().resolve(game);
            require(game.getStack().isEmpty() && game.getPermanent(spell.getId())!=null,"REAL_SPELL_NOT_RESOLVED");
            JsonObject proof=new JsonObject();proof.addProperty("scenario",name);
            proof.addProperty("real_engine",true);proof.addProperty("mountains_tapped",tapped);proof.addProperty("manual_payment_inputs",0);
            proof.addProperty("spell_stacked_and_resolved",true);System.out.println(proof);
        }finally{payer.abort();opponent.abort();cast.cancel(true);executor.shutdownNow();executor.awaitTermination(2,TimeUnit.SECONDS);}
    }
    private static void nativeSessionRequests() throws Exception {
        Class<?> bridgeType=Class.forName("ManaforgeBridge"),transportType=Class.forName("ManaforgeBridge$RequestTransport");
        UUID game=UUID.randomUUID(),related=UUID.randomUUID();List<Object[]> sends=new ArrayList<>();List<JsonObject> events=new ArrayList<>();
        Object transport=java.lang.reflect.Proxy.newProxyInstance(bridgeType.getClassLoader(),new Class<?>[]{transportType},(proxy,method,args)->{sends.add(args);return true;});
        java.lang.reflect.Constructor<?> constructor=bridgeType.getDeclaredConstructor(java.util.function.Consumer.class,transportType);constructor.setAccessible(true);
        Object bridge=constructor.newInstance((java.util.function.Consumer<JsonObject>)events::add,transport);
        Field gameField=bridgeType.getDeclaredField("gameId");gameField.setAccessible(true);gameField.set(bridge,game);
        java.lang.reflect.Method receive=bridgeType.getDeclaredMethod("sessionRequest",mage.view.UserRequestMessage.class,int.class),poll=bridgeType.getDeclaredMethod("pollSessionRequest"),current=bridgeType.getDeclaredMethod("sessionRequestCurrent",String.class),execute=bridgeType.getDeclaredMethod("execute",JsonObject.class);
        for(java.lang.reflect.Method method:new java.lang.reflect.Method[]{receive,poll,current,execute})method.setAccessible(true);
        int decision=10;
        for(boolean rollback:new boolean[]{false,true})for(int option=0;option<2;option++){
            mage.view.UserRequestMessage message=new mage.view.UserRequestMessage("Permission","Allow this request?");message.setGameId(game);message.setRelatedUser(related,"Public requester");
            mage.constants.PlayerAction accept=rollback?mage.constants.PlayerAction.ADD_PERMISSION_TO_ROLLBACK_TURN:mage.constants.PlayerAction.ADD_PERMISSION_TO_SEE_HAND_CARDS;
            mage.constants.PlayerAction decline=rollback?mage.constants.PlayerAction.DENY_PERMISSION_TO_ROLLBACK_TURN:null;
            message.setButton1("Accept",accept);message.setButton2("Deny",decline);receive.invoke(bridge,message,decision++);
            JsonObject request=(JsonObject)poll.invoke(bridge);require(request!=null,"NATIVE_REQUEST_NOT_CAPTURED");int previous=sends.size();
            JsonObject reply=new JsonObject();reply.addProperty("protocol",1);reply.addProperty("request_id","explicit-request-reply");reply.addProperty("command","respond_request");reply.addProperty("game_id",game.toString());reply.add("decision_id",request.get("decision_id"));reply.add("session_request_id",request.get("session_request_id"));reply.addProperty("value",Integer.toString(option));execute.invoke(bridge,reply);
            require(!((Boolean)current.invoke(bridge,request.get("session_request_id").getAsString())),"NATIVE_REQUEST_NOT_CONSUMED");
            require(sends.size()==previous+(option==1 && !rollback?0:1),"NATIVE_REQUEST_UNEXPECTED_IO");
            if(sends.size()>previous){Object[] sent=sends.get(previous);require(sent[0]==(option==0?accept:decline) && game.equals(sent[1]) && related.equals(sent[2]),"NATIVE_REQUEST_WRONG_AUTHORITY");}
            execute.invoke(bridge,reply);require(sends.size()==previous+(option==1 && !rollback?0:1),"NATIVE_REQUEST_REPLAYED");
            receive.invoke(bridge,message,decision++);JsonObject old=(JsonObject)poll.invoke(bridge);receive.invoke(bridge,message,decision++);require(!((Boolean)current.invoke(bridge,old.get("session_request_id").getAsString())),"NATIVE_DUPLICATE_REQUEST_RETAINED");
            Field pending=bridgeType.getDeclaredField("requests");pending.setAccessible(true);Map<?,?> map=(Map<?,?>)pending.get(bridge);Object entry=map.values().iterator().next();Field created=entry.getClass().getDeclaredField("created");created.setAccessible(true);created.setLong(entry,System.nanoTime()-TimeUnit.MINUTES.toNanos(3));require(poll.invoke(bridge)==null,"NATIVE_REQUEST_DID_NOT_EXPIRE");
        }
        System.out.println("Native permission adapter: accept/decline, authority, duplicates, expiry and no replay passed; transport fixture only");
    }
    private static void nativePileChoice(boolean firstPile) throws Exception {
        TwoPlayerDuel game=new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),20,7,7);
        ContextHumanPlayer payer=new ContextHumanPlayer("Pile chooser",RangeOfInfluence.ALL,0);payer.setUserData(mage.players.net.UserData.getDefaultUserDataView());
        ContextHumanPlayer other=new ContextHumanPlayer("Other player",RangeOfInfluence.ALL,0);other.setUserData(mage.players.net.UserData.getDefaultUserDataView());
        game.addPlayer(payer,new mage.cards.decks.Deck());game.addPlayer(other,new mage.cards.decks.Deck());payer.init(game);other.init(game);
        Card card=new mage.cards.basiclands.Mountain(payer.getId(),info("Mountain"));load(game,card,Zone.LIBRARY);
        BlockingQueue<PlayerQueryEvent> queries=new LinkedBlockingQueue<>();game.addPlayerQueryEventListener(queries::add);
        // HumanPlayer requires its feedback calls to run on an engine game thread.
        ExecutorService executor=Executors.newSingleThreadExecutor(task->{Thread thread=new Thread(task,"GAME-real-pile");thread.setDaemon(true);return thread;});Future<Boolean> result=executor.submit(()->payer.choosePile(Outcome.Benefit,"Choose a pile",Collections.singletonList(card),Collections.emptyList(),game));
        try{PlayerQueryEvent query=queries.poll(2,TimeUnit.SECONDS);require(query!=null && query.getQueryType()==PlayerQueryEvent.QueryType.CHOOSE_PILE,"REAL_PILE_QUERY_MISSING");payer.setResponseBoolean(firstPile);require(result.get(2,TimeUnit.SECONDS)==firstPile,"REAL_PILE_RESPONSE_CHANGED");System.out.println("Native pile response: "+firstPile+"; choice completed");}
        finally{payer.abort();other.abort();result.cancel(true);executor.shutdownNow();executor.awaitTermination(2,TimeUnit.SECONDS);}
    }
    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("GAME-real-payment-setup");nativeSessionRequests();nativePileChoice(true);nativePileChoice(false);
        scenario("foundry-street-opponent-triggers",false,false);
        scenario("two-red-mountains",true,false);
        scenario("active-mana-hazard",false,true);
        scenario("green",false,false);scenario("mixed-blue",false,false);scenario("generic-green",false,false);
        scenario("floating-only",false,false);scenario("floating-and-source",true,false);scenario("floating-generic",false,false);
        scenario("registered-decks",false,false);
        scenario("insufficient",true,false);
    }
}

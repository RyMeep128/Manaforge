import com.google.gson.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import mage.cards.*;
import mage.constants.*;
import mage.game.GameState;
import mage.game.events.PlayerQueryEvent;
import mage.interfaces.callback.*;
import mage.view.*;

/** One real pinned native Game, two authenticated loopback clients, no Unity. */
public final class NativeMultiViewerChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static PlayerQueryEvent priority(NativePaymentAcceptanceChecks.Engine e,Runnable change) throws Exception {
        check(e.running==null || e.running.isDone(),"NATIVE_PREVIOUS_PRIORITY_ACTIVE");check(e.queries.isEmpty(),"NATIVE_PENDING_QUERY");
        e.running=e.thread.submit(()->{change.run();e.game.applyEffects();e.game.saveState(false);e.payer.resetPassed();e.payer.resetPlayerPassedActions();e.payer.priority(e.game);});
        long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);PlayerQueryEvent query=null;
        while(query==null && System.nanoTime()<end){if(e.running.isDone())e.running.get();query=e.queries.poll(20,TimeUnit.MILLISECONDS);}
        check(query!=null && query.getQueryType().name().equals("SELECT") && query.getPlayerId().equals(e.payer.getId()),"NATIVE_PRIORITY_QUERY");
        while(System.nanoTime()<end){if(e.running.isDone())e.running.get();synchronized(e.response.get(e.payer)){if(Boolean.TRUE.equals(e.opened.get(e.payer))){
            JsonObject request=new JsonObject();request.add("object_ids",new JsonArray());request.add("identified_ids",new JsonArray());
            JsonObject guard=ManaforgeGameMetadata.readPaused(e.game,e.payer.getId(),e.game.getState().getApplyEffectsCounter(),request,()->new GameView(e.game.getState(),e.game,e.payer.getId(),null));
            check(new JsonPrimitive("ok").equals(guard.get("status")) && new JsonPrimitive(true).equals(guard.get("priority_open")),"RECOVERY_WRAPPED_NATIVE_PRIORITY_UNPROVEN");
            return query;
        }}Thread.yield();}
        throw new AssertionError("NATIVE_PRIORITY_NOT_PAUSED");
    }
    static void resume(NativePaymentAcceptanceChecks.Engine e) throws Exception {e.payer.setResponseBoolean(false);e.running.get(5,TimeUnit.SECONDS);check(e.queries.isEmpty(),"NATIVE_PRIORITY_NOT_CONSUMED");}
    static void waitingViewerMetadata(NativePaymentAcceptanceChecks.Engine e,Card card) throws Exception {
        JsonObject request=new JsonObject();JsonArray ids=new JsonArray();ids.add(card.getId().toString());request.add("object_ids",ids);request.add("identified_ids",ids.deepCopy());
        int cycle=e.game.getState().getApplyEffectsCounter();
        JsonObject guard=ManaforgeGameMetadata.readPaused(e.game,e.opponent.getId(),cycle,request,()->new GameView(e.game.getState(),e.game,e.opponent.getId(),null));
        check(new JsonPrimitive("ok").equals(guard.get("status")),"WAITING_VIEWER_METADATA_UNAVAILABLE");
        check(guard.get("cycle").getAsInt()==cycle && guard.getAsJsonObject("objects").has(card.getId().toString()),"WAITING_VIEWER_ORGANIZATION_BASIS_MISSING");
        check(!guard.getAsJsonObject("objects").getAsJsonObject(card.getId().toString()).get("controller").isJsonNull(),"WAITING_VIEWER_CONTROLLER_MISSING");
        check(!e.running.isDone() && cycle==e.game.getState().getApplyEffectsCounter(),"WAITING_METADATA_ADVANCED_ENGINE");
    }
    static JsonArray smartFacts(NativePaymentAcceptanceChecks.Engine e,UUID viewer) {
        GameView view=new GameView(e.game.getState(),e.game,viewer,null);Set<UUID> known=new HashSet<>(view.getStack().keySet());known.addAll(view.getMyHand().keySet());
        for(PlayerView seat:view.getPlayers())known.addAll(seat.getBattlefield().keySet());
        int cycle=e.game.getState().getApplyEffectsCounter(),stack=e.game.getStack().size();
        JsonArray hints=ManaforgeGameMetadata.priorityHints(e.game,viewer,view,known);
        check(cycle==e.game.getState().getApplyEffectsCounter() && stack==e.game.getStack().size(),"SMART_PRIORITY_MUTATED_NATIVE_STATE");return hints;
    }
    static void smartPriorityMechanics() throws Exception {
        // Native ability inspection probes. These do not submit game decisions.
        try(NativePaymentAcceptanceChecks.Engine e=new NativePaymentAcceptanceChecks.Engine()){
            Card probe=e.load(new NativePaymentAcceptanceChecks.Probe(e.payer.getId(),"{1}"),Zone.BATTLEFIELD);
            mage.abilities.Ability sacrifice=new mage.abilities.common.EntersBattlefieldTriggeredAbility(new mage.abilities.effects.common.SacrificeSourceEffect());
            sacrifice.setSourceId(probe.getId());sacrifice.setControllerId(e.payer.getId());e.game.getStack().push(new mage.game.stack.StackAbility(sacrifice,e.payer.getId()));
            check(smartFacts(e,e.payer.getId()).contains(new JsonPrimitive("self_leaves")),"GENERIC_SACRIFICE_SMART_HOLD_MISSING");e.game.getStack().clear();
            for(String type:new String[]{"mage.cards.u.UrzasSaga","mage.cards.w.WildernessReclamation","mage.cards.u.UroTitanOfNaturesWrath"}){
                Card card=e.load(NativePaymentAcceptanceChecks.card(type,e.payer.getId()),Zone.BATTLEFIELD);mage.abilities.Ability selected=null;
                for(mage.abilities.Ability ability:e.game.getPermanent(card.getId()).getAbilities(e.game))if(ability.isTriggeredAbility()){
                    String rule=ability.getRule("{this}").toLowerCase(Locale.ROOT);
                    if(type.contains("Saga")?mage.abilities.common.SagaAbility.isFinalAbility(ability,3):type.contains("Reclamation")?rule.contains("untap"):rule.contains("sacrifice")){selected=ability.copy();break;}
                }
                check(selected!=null,"SMART_FIXTURE_NATIVE_TRIGGER_MISSING_"+type);selected.setSourceId(card.getId());selected.setControllerId(e.payer.getId());e.game.getStack().push(new mage.game.stack.StackAbility(selected,e.payer.getId()));
                String expected=type.contains("Saga")?"final_saga":type.contains("Reclamation")?"untap_resources":"self_leaves";
                check(smartFacts(e,e.payer.getId()).contains(new JsonPrimitive(expected)),"NATIVE_SMART_MECHANIC_MISSING_"+expected);e.game.getStack().clear();
            }
            e.load(NativePaymentAcceptanceChecks.card("mage.cards.s.SheoldredTheApocalypse",e.opponent.getId()),Zone.BATTLEFIELD);
            check(smartFacts(e,e.payer.getId()).contains(new JsonPrimitive("draw_hazard")),"DRAW_HAZARD_SMART_HOLD_MISSING");
            e.load(NativePaymentAcceptanceChecks.card("mage.cards.l.LutriTheSpellchaser",e.payer.getId()),Zone.HAND);
            Card bolt=e.load(NativePaymentAcceptanceChecks.card("mage.cards.l.LightningBolt",e.payer.getId()),Zone.HAND);e.payer.getHand().remove(bolt.getId());e.game.setZone(bolt.getId(),Zone.STACK);
            e.game.getStack().push(new mage.game.stack.Spell(bolt,bolt.getSpellAbility(),e.payer.getId(),Zone.HAND,e.game));
            check(smartFacts(e,e.payer.getId()).contains(new JsonPrimitive("copy_spell")),"OWN_SPELL_COPY_SMART_HOLD_MISSING");
            check(!smartFacts(e,e.opponent.getId()).contains(new JsonPrimitive("copy_spell")),"SMART_PRIORITY_LEAKED_OPPONENT_HAND");
        }
    }
    static Map<String,ManaforgeMatchCoordinator.Observation> observations(NativePaymentAcceptanceChecks.Engine e,PlayerQueryEvent query,AtomicInteger submissions) throws Exception {return observations(e,query,submissions,null);}
    static Map<String,ManaforgeMatchCoordinator.Observation> observations(NativePaymentAcceptanceChecks.Engine e,PlayerQueryEvent query,AtomicInteger submissions,Map<UUID,GameView> views) throws Exception {
        synchronized(e.response.get(e.payer)){
            check(Boolean.TRUE.equals(e.opened.get(e.payer)),"NATIVE_UNSAFE_READ");GameState state=e.game.getState();int cycle=state.getApplyEffectsCounter();Map<String,ManaforgeMatchCoordinator.Observation> result=new HashMap<>();
            for(UUID viewer:Arrays.asList(e.payer.getId(),e.opponent.getId())){
                GameView view=views==null?new GameView(state,e.game,viewer,null):views.get(viewer);check(view!=null && view.getGameCycle()==cycle,"NATIVE_CAPTURED_VIEW");
                ManaforgeBridge bridge=new ManaforgeBridge(value->{},null,new ManaforgeBridge.ResponseTransport(){
                    public boolean object(UUID game,UUID source){submissions.incrementAndGet();throw new AssertionError("READ_ONLY_NATIVE_OBJECT_SUBMISSION");}
                    public boolean mana(UUID game,UUID player,ManaType type){submissions.incrementAndGet();throw new AssertionError("READ_ONLY_NATIVE_MANA_SUBMISSION");}
                    public boolean bool(UUID game,boolean value){submissions.incrementAndGet();throw new AssertionError("READ_ONLY_NATIVE_BOOLEAN_SUBMISSION");}
                });
                ClientCallback callback=new ClientCallback(ClientCallbackMethod.GAME_SELECT,e.game.getId(),new GameClientMessage(view,query.getOptions(),query.getMessage()));callback.setMessageId(1);bridge.onCallback(callback);
                check(bridge.currentState()!=null && bridge.currentDecision().get("is_priority").getAsBoolean(),"NATIVE_PRIORITY_PROJECTION_CONTEXT");
                result.put(viewer.equals(e.payer.getId())?"a":"b",new ManaforgeMatchCoordinator.Observation(bridge.currentState(),bridge.currentDecision()));
            }
            check(e.game.getState()==state && state.getApplyEffectsCounter()==cycle,"NATIVE_MIXED_BASIS");return result;
        }
    }
    static JsonObject snapshot(JsonObject envelope){return envelope.getAsJsonObject("body").getAsJsonObject("snapshot");}
    static void privacy(JsonObject envelope,String own,String other){
        JsonObject snapshot=snapshot(envelope);check(snapshot.get("decision").isJsonNull() && snapshot.getAsJsonArray("actions").size()==0,"READ_ONLY_OFFER_LEAK");
        Set<String> hand=new HashSet<>();for(JsonElement value:snapshot.getAsJsonArray("objects")){JsonObject card=value.getAsJsonObject();if(card.get("zone").getAsString().equals("hand") && !card.get("characteristics").isJsonNull())hand.add(card.getAsJsonObject("characteristics").get("name").getAsString());}
        check(hand.contains(own) && !envelope.toString().contains(other),"PRIVATE_HAND_CROSSED_VIEWERS");
    }
    static int tappedForests(JsonObject envelope){int count=0;for(JsonElement value:snapshot(envelope).getAsJsonArray("objects")){JsonObject card=value.getAsJsonObject();if(card.get("zone").getAsString().equals("battlefield") && !card.get("characteristics").isJsonNull() && card.getAsJsonObject("characteristics").get("name").getAsString().equals("Forest") && card.get("tapped").getAsBoolean())count++;}return count;}
    /** Exercise the live queue reader used both when idle and inside advance(). */
    static void waitingStatePublication() throws Exception {
        ManaforgeLiveOpening live=new ManaforgeLiveOpening();
        java.lang.reflect.Field queueField=ManaforgeLiveOpening.class.getDeclaredField("events"),publicationField=ManaforgeLiveOpening.class.getDeclaredField("multiplayerStatePublication"),waitingField=ManaforgeLiveOpening.class.getDeclaredField("multiplayerAwaitingDecision");
        queueField.setAccessible(true);publicationField.setAccessible(true);waitingField.setAccessible(true);
        @SuppressWarnings("unchecked") BlockingQueue<JsonObject> queue=(BlockingQueue<JsonObject>)queueField.get(live);
        List<JsonObject> published=new ArrayList<>();
        Object publication=java.lang.reflect.Proxy.newProxyInstance(ManaforgeLiveOpening.class.getClassLoader(),new Class<?>[]{publicationField.getType()},(proxy,method,values)->{published.add(((JsonObject)values[0]).deepCopy());return null;});
        publicationField.set(live,publication);waitingField.setBoolean(live,true);
        java.lang.reflect.Method next=ManaforgeLiveOpening.class.getDeclaredMethod("next");next.setAccessible(true);
        JsonObject update=new JsonObject();update.addProperty("event","game_state");update.addProperty("cycle",10);
        queue.add(update);next.invoke(live);
        update=update.deepCopy();update.addProperty("cycle",11);queue.add(update);next.invoke(live);
        check(published.size()==2 && published.get(1).get("cycle").getAsInt()==11,"BOARD_WAITED_FOR_PRIORITY_DECISION");
        // An existing interactive offer must retain its command authority.
        waitingField.setBoolean(live,false);queue.add(update);next.invoke(live);
        check(published.size()==2,"BOARD_UPDATE_REPLACED_ACTIVE_OFFER");
        waitingField.setBoolean(live,true);
        JsonObject decision=new JsonObject();decision.addProperty("event","decision");decision.addProperty("decision_id",12);queue.add(decision);next.invoke(live);
        check(published.size()==2,"DECISION_PUBLISHED_AS_WAITING_BOARD");
    }
    public static void main(String[] args) throws Exception {
        waitingStatePublication();

        Thread.currentThread().setName("GAME-multiview-fixture-owner");smartPriorityMechanics();NativePaymentAcceptanceChecks.Engine e=new NativePaymentAcceptanceChecks.Engine();AtomicInteger disposed=new AtomicInteger(),submissions=new AtomicInteger();AtomicBoolean cancel=new AtomicBoolean();byte[] keyA=MatchCoordinatorChecks.key(11),keyB=MatchCoordinatorChecks.key(22);
        try{
            Card forest=e.load(new mage.cards.basiclands.Forest(e.payer.getId(),NativePaymentAcceptanceChecks.info("Forest")),Zone.BATTLEFIELD);
            e.load(new mage.cards.basiclands.Forest(e.payer.getId(),NativePaymentAcceptanceChecks.info("Forest")),Zone.BATTLEFIELD);e.load(new mage.cards.basiclands.Mountain(e.opponent.getId(),NativePaymentAcceptanceChecks.info("Mountain")),Zone.BATTLEFIELD);
            e.load(new mage.cards.l.LlanowarElves(e.payer.getId(),NativePaymentAcceptanceChecks.info("Llanowar Elves")),Zone.HAND);e.load(new mage.cards.g.GoblinGuide(e.opponent.getId(),NativePaymentAcceptanceChecks.info("Goblin Guide")),Zone.HAND);
            try(ManaforgeMatchCoordinator coordinator=new ManaforgeMatchCoordinator(e.game.getId().toString(),MatchCoordinatorChecks.ENGINE,MatchCoordinatorChecks.HASH,()->{disposed.incrementAndGet();e.close();},cancel::get)){
                ManaforgeMatchCoordinator.Viewer a=coordinator.register("a",e.payer.getId().toString(),"native-session-a","viewer-a",keyA),b=coordinator.register("b",e.opponent.getId().toString(),"native-session-b","viewer-b",keyB);coordinator.start();
                try(MatchCoordinatorChecks.Client clientA=new MatchCoordinatorChecks.Client(a,keyA,false);MatchCoordinatorChecks.Client clientB=new MatchCoordinatorChecks.Client(b,keyB,false)){
                    PlayerQueryEvent query=priority(e,()->{});waitingViewerMetadata(e,forest);coordinator.publishNative(observations(e,query,submissions));JsonObject firstA=clientA.read(),firstB=clientB.read();privacy(firstA,"Llanowar Elves","Goblin Guide");privacy(firstB,"Goblin Guide","Llanowar Elves");check(tappedForests(firstA)==0 && tappedForests(firstB)==0,"INITIAL_NATIVE_BOARD");resume(e);
                    query=priority(e,()->check(e.game.getPermanent(forest.getId()).tap(forest.getSpellAbility(),e.game),"NATIVE_PUBLIC_TAP"));coordinator.publishNative(observations(e,query,submissions));JsonObject secondA=clientA.read(),secondB=clientB.read();privacy(secondA,"Llanowar Elves","Goblin Guide");privacy(secondB,"Goblin Guide","Llanowar Elves");check(tappedForests(secondA)==1 && tappedForests(secondB)==1,"PUBLIC_UPDATE_NOT_SHARED");
                    int cycle=e.game.getState().getApplyEffectsCounter();clientA.send("{\"wire_version\":1,\"message_type\":\"command\",\"message_id\":\"forged\",\"body\":{}}");MatchCoordinatorChecks.await(()->"READ_ONLY_TRAFFIC".equals(coordinator.status("a").reason),"NATIVE_COMMAND_TRAFFIC_ADMITTED");
                    check(submissions.get()==0 && !e.running.isDone() && cycle==e.game.getState().getApplyEffectsCounter() && disposed.get()==0,"VIEWER_TRAFFIC_MUTATED_NATIVE_MATCH");resume(e);
                    query=priority(e,()->check(e.game.getPermanent(forest.getId()).untap(e.game),"NATIVE_PUBLIC_UNTAP"));coordinator.publishNative(observations(e,query,submissions));JsonObject thirdB=clientB.read();privacy(thirdB,"Goblin Guide","Llanowar Elves");check(tappedForests(thirdB)==0 && coordinator.status("b").status==ManaforgeMatchCoordinator.Status.CONNECTED && !e.game.hasEnded() && disposed.get()==0,"A_DISCONNECT_STOPPED_B_OR_MATCH");
                    cancel.set(true);MatchCoordinatorChecks.await(coordinator::isClosed,"NATIVE_PARENT_CANCEL");coordinator.close();check(disposed.get()==1 && submissions.get()==0,"NATIVE_CLEANUP_OR_SUBMISSION");
                }
            }
            check(disposed.get()==1,"NATIVE_MATCH_DISPOSED_TWICE");System.out.println("Native two-viewer proof passed: one game, two authenticated private views, shared tap/untap, disconnect isolation, zero client submissions, owner cleanup");
        }finally{Arrays.fill(keyA,(byte)0);Arrays.fill(keyB,(byte)0);if(disposed.get()==0)e.close();}
    }
}

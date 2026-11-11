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
        while(System.nanoTime()<end){if(e.running.isDone())e.running.get();synchronized(e.response.get(e.payer)){if(Boolean.TRUE.equals(e.opened.get(e.payer)))return query;}Thread.yield();}
        throw new AssertionError("NATIVE_PRIORITY_NOT_PAUSED");
    }
    static void resume(NativePaymentAcceptanceChecks.Engine e) throws Exception {e.payer.setResponseBoolean(false);e.running.get(5,TimeUnit.SECONDS);check(e.queries.isEmpty(),"NATIVE_PRIORITY_NOT_CONSUMED");}
    static Map<String,ManaforgeMatchCoordinator.Observation> observations(NativePaymentAcceptanceChecks.Engine e,PlayerQueryEvent query,AtomicInteger submissions) throws Exception {
        synchronized(e.response.get(e.payer)){
            check(Boolean.TRUE.equals(e.opened.get(e.payer)),"NATIVE_UNSAFE_READ");GameState state=e.game.getState();int cycle=state.getApplyEffectsCounter();Map<String,ManaforgeMatchCoordinator.Observation> result=new HashMap<>();
            for(UUID viewer:Arrays.asList(e.payer.getId(),e.opponent.getId())){
                GameView view=new GameView(state,e.game,viewer,null);
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
    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("GAME-multiview-fixture-owner");NativePaymentAcceptanceChecks.Engine e=new NativePaymentAcceptanceChecks.Engine();AtomicInteger disposed=new AtomicInteger(),submissions=new AtomicInteger();AtomicBoolean cancel=new AtomicBoolean();byte[] keyA=MatchCoordinatorChecks.key(11),keyB=MatchCoordinatorChecks.key(22);
        try{
            Card forest=e.load(new mage.cards.basiclands.Forest(e.payer.getId(),NativePaymentAcceptanceChecks.info("Forest")),Zone.BATTLEFIELD);
            e.load(new mage.cards.basiclands.Forest(e.payer.getId(),NativePaymentAcceptanceChecks.info("Forest")),Zone.BATTLEFIELD);e.load(new mage.cards.basiclands.Mountain(e.opponent.getId(),NativePaymentAcceptanceChecks.info("Mountain")),Zone.BATTLEFIELD);
            e.load(new mage.cards.l.LlanowarElves(e.payer.getId(),NativePaymentAcceptanceChecks.info("Llanowar Elves")),Zone.HAND);e.load(new mage.cards.g.GoblinGuide(e.opponent.getId(),NativePaymentAcceptanceChecks.info("Goblin Guide")),Zone.HAND);
            try(ManaforgeMatchCoordinator coordinator=new ManaforgeMatchCoordinator(e.game.getId().toString(),MatchCoordinatorChecks.ENGINE,MatchCoordinatorChecks.HASH,()->{disposed.incrementAndGet();e.close();},cancel::get)){
                ManaforgeMatchCoordinator.Viewer a=coordinator.register("a",e.payer.getId().toString(),"native-session-a","viewer-a",keyA),b=coordinator.register("b",e.opponent.getId().toString(),"native-session-b","viewer-b",keyB);coordinator.start();
                try(MatchCoordinatorChecks.Client clientA=new MatchCoordinatorChecks.Client(a,keyA,false);MatchCoordinatorChecks.Client clientB=new MatchCoordinatorChecks.Client(b,keyB,false)){
                    PlayerQueryEvent query=priority(e,()->{});coordinator.publishNative(observations(e,query,submissions));JsonObject firstA=clientA.read(),firstB=clientB.read();privacy(firstA,"Llanowar Elves","Goblin Guide");privacy(firstB,"Goblin Guide","Llanowar Elves");check(tappedForests(firstA)==0 && tappedForests(firstB)==0,"INITIAL_NATIVE_BOARD");resume(e);
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

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import mage.game.events.PlayerQueryEvent;
import manaforge.payment.xmage.NativeMatchRecovery;

/** Hosted-only acceptance against a real pinned Game and native human/MAD policies. */
public final class NativeRecoveryChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static void awaitParked(NativePaymentAcceptanceChecks.Engine engine) throws Exception {
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);
        while(!NativeMatchRecovery.control(engine.game.getId(),"pause",null).get("ready").getAsBoolean()){
            if(System.nanoTime()>deadline)throw new AssertionError("RECOVERY_PAUSE_TIMEOUT");Thread.sleep(10);
        }
    }
    public static void main(String[] args) throws Exception {
        try(NativePaymentAcceptanceChecks.Engine engine=new NativePaymentAcceptanceChecks.Engine()){
            UUID id=engine.payer.getId();int life=engine.payer.getLife();Set<UUID> hand=new HashSet<>(engine.payer.getHand());
            AtomicInteger amount=new AtomicInteger(-1);
            engine.running=engine.thread.submit(()->amount.set(engine.payer.getAmount(1,3,"Choose an amount",null,engine.game)));
            PlayerQueryEvent query=engine.queries.poll(10,TimeUnit.SECONDS);check(query!=null,"HUMAN_QUERY_MISSING");
            awaitParked(engine);Thread.sleep(50);check(!engine.running.isDone(),"PAUSE_ADVANCED_GAME");
            NativeMatchRecovery.control(engine.game.getId(),"ai",id);
            check(!engine.running.isDone(),"AI_ASSIGNMENT_RESUMED_GAME");
            NativeMatchRecovery.control(engine.game.getId(),"resume",null);engine.running.get(40,TimeUnit.SECONDS);
            check(amount.get()>=1 && amount.get()<=3,"MAD_CHOICE_INVALID");
            check(engine.game.getPlayer(id)==engine.payer && engine.payer.getId().equals(id),"SEAT_IDENTITY_CHANGED");
            check(engine.payer.getLife()==life && new HashSet<>(engine.payer.getHand()).equals(hand),"SEAT_STATE_LOST");
            NativeMatchRecovery.control(engine.game.getId(),"pause",null);
            engine.running=engine.thread.submit(()->amount.set(engine.payer.getAmount(1,3,"Human again",null,engine.game)));
            awaitParked(engine);NativeMatchRecovery.control(engine.game.getId(),"human",id);
            check(!engine.running.isDone(),"HUMAN_ASSIGNMENT_RESUMED_GAME");
            NativeMatchRecovery.control(engine.game.getId(),"resume",null);
            check(engine.queries.poll(10,TimeUnit.SECONDS)!=null,"HUMAN_TAKEOVER_QUERY_MISSING");
            engine.payer.setResponseInteger(2);engine.running.get(10,TimeUnit.SECONDS);
            check(amount.get()==2 && engine.game.getPlayer(id)==engine.payer,"HUMAN_TAKEOVER_FAILED");
        }
        System.out.println("Native recovery pause, explicit resume, MAD handoff and human return preserved seat state");
    }
}

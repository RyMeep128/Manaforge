package manaforge.payment;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import manaforge.payment.xmage.ManaResponseExecutor;
import manaforge.payment.xmage.ManaResponseExecutor.Outcome;

/** Guard/transport tests, not a game or native payment planner. */
public final class NativeManaResponseChecks {
    private static int checks;
    private static void check(boolean value){checks++;if(!value)throw new AssertionError("NATIVE_RESPONSE_"+checks);}
    private static final UUID GAME=UUID.fromString("00000000-0000-0000-0000-000000000001"),SOURCE=UUID.fromString("00000000-0000-0000-0000-000000000002");
    private static final class Window implements ManaResponseExecutor.Authority {
        int decision=7;boolean open=true;int claims;
        public synchronized boolean claim(UUID game,int expected,UUID source){if(!open || !GAME.equals(game) || !SOURCE.equals(source) || expected!=decision)return false;claims++;open=false;return true;}
        synchronized void next(){decision++;open=true;}
    }
    public static void main(String[] args) throws Exception {
        Window window=new Window();AtomicInteger sends=new AtomicInteger();ManaResponseExecutor executor=new ManaResponseExecutor(window,(game,source)->{sends.incrementAndGet();return true;});
        check(executor.submit(null,7,SOURCE)==Outcome.STALE);check(executor.submit(GAME,-1,SOURCE)==Outcome.STALE);check(executor.submit(GAME,7,null)==Outcome.STALE);
        check(executor.submit(SOURCE,7,SOURCE)==Outcome.STALE);check(executor.submit(GAME,6,SOURCE)==Outcome.STALE);check(executor.submit(GAME,7,GAME)==Outcome.STALE);check(sends.get()==0 && window.claims==0);
        check(executor.submit(GAME,7,SOURCE)==Outcome.SUBMITTED);check(executor.submit(GAME,7,SOURCE)==Outcome.STALE);check(sends.get()==1 && window.claims==1);
        for(int kind=0;kind<4;kind++) {
            Window current=new Window();AtomicInteger calls=new AtomicInteger();final int behavior=kind;AssertionError fatal=new AssertionError("native fixture fatal");
            ManaResponseExecutor failing=new ManaResponseExecutor(current,(game,source)->{calls.incrementAndGet();if(behavior==1)throw new IOException("private fixture detail");if(behavior==2)throw new InterruptedException("private fixture detail");if(behavior==3)throw fatal;return false;});
            if(kind==3){boolean escaped=false;try{failing.submit(GAME,7,SOURCE);}catch(AssertionError actual){check(actual==fatal);escaped=true;}check(escaped);}
            else check(failing.submit(GAME,7,SOURCE)==Outcome.UNCERTAIN);
            if(kind==2){try{check(Thread.currentThread().isInterrupted());}finally{Thread.interrupted();}}
            check(failing.submit(GAME,7,SOURCE)==Outcome.STALE);check(calls.get()==1 && current.claims==1);
        }
        Window changing=new Window();AtomicInteger calls=new AtomicInteger();ManaResponseExecutor callback=new ManaResponseExecutor(changing,(game,source)->{calls.incrementAndGet();changing.next();return true;});
        check(callback.submit(GAME,7,SOURCE)==Outcome.SUBMITTED);check(callback.submit(GAME,7,SOURCE)==Outcome.STALE);check(callback.submit(GAME,8,SOURCE)==Outcome.SUBMITTED);check(calls.get()==2);
        ExecutorService workers=Executors.newFixedThreadPool(2);
        try{for(int round=0;round<16;round++) {
            Window current=new Window();AtomicInteger effects=new AtomicInteger();ManaResponseExecutor shared=new ManaResponseExecutor(current,(game,source)->{effects.incrementAndGet();return true;});CountDownLatch ready=new CountDownLatch(2),go=new CountDownLatch(1);
            Callable<Outcome> run=()->{ready.countDown();if(!go.await(2,TimeUnit.SECONDS))throw new AssertionError();return shared.submit(GAME,7,SOURCE);};Future<Outcome> first=workers.submit(run),second=workers.submit(run);check(ready.await(2,TimeUnit.SECONDS));go.countDown();Outcome a=first.get(2,TimeUnit.SECONDS),b=second.get(2,TimeUnit.SECONDS);check((a==Outcome.SUBMITTED && b==Outcome.STALE) || (b==Outcome.SUBMITTED && a==Outcome.STALE));check(effects.get()==1 && current.claims==1);
        }}finally{workers.shutdownNow();check(workers.awaitTermination(3,TimeUnit.SECONDS));}
        System.out.println("Native mana response guard: "+checks+" synthetic claim/transport checks passed; native gameplay not simulated");
    }
}

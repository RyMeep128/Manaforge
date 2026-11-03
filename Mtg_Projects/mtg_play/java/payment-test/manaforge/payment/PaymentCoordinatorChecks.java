package manaforge.payment;

import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import manaforge.payment.PaymentCoordinator.*;

/** Synthetic lifecycle/policy checks, NOT XMage payment acceptance or a fake mana solver. */
public final class PaymentCoordinatorChecks {
    private static int checks;
    private static void check(boolean condition){checks++;if(!condition)throw new AssertionError("PAYMENT_CHECK_"+checks);}
    private static Context context(long revision){return new Context("session","human","payment","decision-"+revision,revision);}
    private static final class Port implements EnginePort {
        boolean current=true,replaceDuringInspection,throwInspect,throwEnqueue;int inspections,enqueues;
        Safety safety=Safety.VERIFIED_ORDINARY_EQUIVALENT;Submission result=Submission.ENQUEUED;
        List<String> tokens=new ArrayList<>(Arrays.asList("engine-step-b","engine-step-a"));
        Runnable onInspect=()->{},onEnqueue=()->{};
        public boolean isCurrent(Context context){return current;}
        public Assessment inspect(Context context){inspections++;onInspect.run();if(throwInspect)throw new IllegalStateException();if(replaceDuringInspection)current=false;return new Assessment(safety,tokens);}
        public Submission enqueue(Attempt attempt){enqueues++;onEnqueue.run();if(throwEnqueue)throw new IllegalStateException();return result;}
    }
    public static void main(String[] args) throws Exception {
        Port p=new Port();PaymentCoordinator c=new PaymentCoordinator("session","human",true,p);
        check(c.mode()==Mode.AUTO);check(c.consider()==null);check(c.offer(context(7)));Attempt a=c.consider();
        check(a!=null && a.engineStepToken.equals("engine-step-a"));check(c.state()==State.SUBMITTED);check(c.consider()==null && p.enqueues==1);
        check(!c.claimManual(a.context));check(!c.offer(context(8)));check(c.state()==State.UNCERTAIN);check(c.consider()==null);
        check(c.observe(a,Observation.PROGRESS));check(c.state()==State.PROGRESSED);check(c.consider()==null);
        check(c.offer(context(8)));Attempt b=c.consider();check(b!=null && b!=a && p.enqueues==2);
        check(!c.observe(a,Observation.COMPLETE));check(c.observe(b,Observation.COMPLETE));check(c.state()==State.COMPLETED);
        check(!c.offer(b.context));check(!c.offer(context(6)));c.close();check(c.stopped() && c.state()==State.STOPPED);check(!c.offer(context(9)));
        for(Mode mode:Arrays.asList(Mode.MANUAL,Mode.FULL_CONTROL)) {
            p=new Port();c=new PaymentCoordinator("session","human",true,mode,p);c.offer(context(7));check(c.consider()==null);check(p.inspections==0 && p.enqueues==0);check(c.claimManual(context(7)));c.close();
        }
        p=new Port();c=new PaymentCoordinator("session","human",false,p);c.offer(context(7));check(c.consider()==null && p.enqueues==0);
        for(Safety safety:Arrays.asList(Safety.UNKNOWN,Safety.STRATEGIC,Safety.UNSUPPORTED)) {
            p=new Port();p.safety=safety;c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));check(c.consider()==null && c.state()==State.MANUAL_REQUIRED && p.enqueues==0);check(c.claimManual(context(7)));
        }
        p=new Port();p.tokens.clear();c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));check(c.consider()==null && p.enqueues==0);
        p=new Port();p.current=false;c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));check(c.consider()==null && p.inspections==0);
        p=new Port();p.replaceDuringInspection=true;c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));check(c.consider()==null && p.enqueues==0);
        p=new Port();p.throwInspect=true;c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));check(c.consider()==null && p.enqueues==0);
        p=new Port();c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));check(c.claimManual(context(7)));check(c.consider()==null && p.enqueues==0);
        check(!c.offer(new Context("other","human","payment","decision",8)));check(!c.offer(new Context("session","other","payment","decision",8)));
        p=new Port();c=new PaymentCoordinator("session","human",true,p);Context original=context(7);c.offer(original);check(!c.offer(context(7)));a=c.consider();
        c.setMode(Mode.MANUAL);check(c.consider()==null && p.enqueues==1);check(c.observe(a,Observation.PROGRESS));c.offer(context(8));check(c.consider()==null && p.enqueues==1);
        for(Submission result:Arrays.asList(Submission.REJECTED,Submission.UNCERTAIN)) {
            p=new Port();p.result=result;c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));a=c.consider();check(c.state()==(result==Submission.REJECTED?State.REJECTED:State.UNCERTAIN));check(c.consider()==null && p.enqueues==1);
            if(result==Submission.REJECTED)check(c.claimManual(context(7)));else {check(!c.claimManual(context(7)));check(!c.offer(context(8)));check(c.observe(a,Observation.REJECTED));check(c.claimManual(context(7)));}
        }
        p=new Port();p.throwEnqueue=true;c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));a=c.consider();check(c.state()==State.UNCERTAIN);c.close();check(c.stopped() && c.state()==State.UNCERTAIN);check(!c.observe(a,Observation.COMPLETE));check(c.consider()==null && p.enqueues==1);
        p=new Port();c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));final PaymentCoordinator owned=c;
        AtomicReference<Throwable> failure=new AtomicReference<>();Thread thread=new Thread(()->{try{owned.consider();}catch(Throwable error){failure.set(error);}});thread.start();thread.join();check(failure.get() instanceof IllegalStateException && p.enqueues==0);
        p.onInspect=()->owned.setMode(Mode.MANUAL);check(c.consider()==null && p.enqueues==0);
        p=new Port();c=new PaymentCoordinator("session","human",true,p);c.offer(context(7));final PaymentCoordinator enqueueOwner=c;p.onEnqueue=()->enqueueOwner.close();c.consider();check(c.state()==State.UNCERTAIN && p.enqueues==1);
        p=new Port();PaymentCoordinator first=new PaymentCoordinator("session","human",true,Mode.MANUAL,p);PaymentCoordinator second=new PaymentCoordinator("session","human-2",true,new Port());check(first.mode()==Mode.MANUAL && second.mode()==Mode.AUTO);
        boolean invalid=false;try{new Assessment(Safety.VERIFIED_ORDINARY_EQUIVALENT,Arrays.asList("same","same"));}catch(IllegalArgumentException expected){invalid=true;}check(invalid);
        System.out.println("Java payment coordinator: "+checks+" synthetic safety/lifecycle checks passed; production integration disabled");
    }
}

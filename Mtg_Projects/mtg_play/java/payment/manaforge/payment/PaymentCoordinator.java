package manaforge.payment;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/** Trusted Java engine-owner policy. Not a rules solver, wire command or client receipt authority.
 * All calls, including manual admission and observations, belong on ONE serialized engine owner.
 * No production EnginePort exists yet. A view's object list is NOT a safe payment assessment. */
public final class PaymentCoordinator implements AutoCloseable {
    public enum Mode { AUTO, MANUAL, FULL_CONTROL }
    public enum State { IDLE, MANUAL_REQUIRED, SUBMITTED, PROGRESSED, COMPLETED, REJECTED, UNCERTAIN, STOPPED }
    public enum Safety { VERIFIED_ORDINARY_EQUIVALENT, UNKNOWN, STRATEGIC, UNSUPPORTED }
    public enum Submission { ENQUEUED, REJECTED, UNCERTAIN }
    public enum Observation { PROGRESS, COMPLETE, REJECTED, UNCERTAIN }
    public static final class Context {
        public final String session, viewer, payment, decision;
        public final long revision;
        public Context(String session,String viewer,String payment,String decision,long revision) {
            this.session=id(session);this.viewer=id(viewer);this.payment=id(payment);this.decision=id(decision);
            if(revision<0)throw new IllegalArgumentException("PAYMENT_CONTEXT");this.revision=revision;
        }
        private boolean same(Context other) {return other!=null && session.equals(other.session) && viewer.equals(other.viewer)
            && payment.equals(other.payment) && decision.equals(other.decision) && revision==other.revision;}
    }
    /** All tokens must describe already verified, equivalent, safe NEXT steps for this exact cost.
     * Engine integration must reject unknown restrictions/effects, costly abilities, unchosen X and
     * unsupported payment mechanics BEFORE issuing this assessment. No speculative activation. */
    public static final class Assessment {
        public final Safety safety;
        private final List<String> steps;
        public Assessment(Safety safety,List<String> equivalentStepTokens) {
            this.safety=Objects.requireNonNull(safety);
            if(equivalentStepTokens==null || equivalentStepTokens.size()>128)throw new IllegalArgumentException("PAYMENT_ASSESSMENT");
            List<String> copy=new ArrayList<>();for(String token:equivalentStepTokens){id(token);if(copy.contains(token))throw new IllegalArgumentException("PAYMENT_ASSESSMENT");copy.add(token);}
            Collections.sort(copy);steps=Collections.unmodifiableList(copy);
        }
    }
    /** Internal automation correlation, never a fabricated Unity command/ACK. Identity matters. */
    public static final class Attempt {
        public final Context context;
        public final String engineStepToken;
        private Attempt(Context context,String token){this.context=context;engineStepToken=token;}
    }
    public interface EnginePort {
        boolean isCurrent(Context context);
        Assessment inspect(Context context);
        // Prompt enqueue on this same serialized engine owner, revalidating context and source.
        // No waiting, IO, reentry or outcome callbacks until after this call returns.
        Submission enqueue(Attempt attempt) throws Exception;
    }
    private final Thread owner=Thread.currentThread();
    private final String session,viewer;private final boolean human;private final EnginePort engine;
    private Mode mode;private State state=State.IDLE;private Context current;private Attempt pending;
    private boolean attempted,stopped,calling;private long minimumRevision=-1;
    public PaymentCoordinator(String session,String viewer,boolean human,EnginePort engine) {this(session,viewer,human,Mode.AUTO,engine);}
    public PaymentCoordinator(String session,String viewer,boolean human,Mode mode,EnginePort engine) {
        this.session=id(session);this.viewer=id(viewer);this.human=human;this.mode=Objects.requireNonNull(mode);this.engine=Objects.requireNonNull(engine);
    }
    private static String id(String value){if(value==null || !value.matches("[A-Za-z0-9_.:-]{1,128}"))throw new IllegalArgumentException("PAYMENT_CONTEXT");return value;}
    private void owner(){if(Thread.currentThread()!=owner || calling)throw new IllegalStateException("PAYMENT_OWNER");}
    public Mode mode(){owner();return mode;}
    public State state(){owner();return state;}
    public boolean stopped(){owner();return stopped;}
    public void setMode(Mode next){owner();if(stopped)return;mode=Objects.requireNonNull(next);}
    /** Trusted engine observation only. Replacement during unconfirmed work fails closed. */
    public boolean offer(Context context) {
        owner();if(stopped || state==State.UNCERTAIN)return false;
        if(context==null || !session.equals(context.session) || !viewer.equals(context.viewer) || context.revision<minimumRevision)return false;
        if(current!=null && current.same(context))return false;
        if(pending!=null){uncertain();return false;}
        current=context;minimumRevision=context.revision;attempted=false;state=State.IDLE;return true;
    }
    /** Called AFTER authenticated manual admission, BEFORE any manual engine enqueue on this owner.
     * A false return means automation already owns an unresolved submission. Never bypass the gate. */
    public boolean claimManual(Context context) {
        owner();if(stopped || state==State.UNCERTAIN || current==null || !current.same(context) || pending!=null)return false;
        attempted=true;state=State.MANUAL_REQUIRED;return true;
    }
    /** At most one attempt per offered context. Progress needs a fresh engine offer and reassessment. */
    public Attempt consider() {
        owner();if(stopped || state==State.UNCERTAIN || current==null || attempted || pending!=null)return null;
        attempted=true;state=State.MANUAL_REQUIRED;
        if(!human || mode!=Mode.AUTO)return null;
        Assessment assessment;
        calling=true;
        try {if(!engine.isCurrent(current))return null;assessment=engine.inspect(current);
            if(assessment==null || assessment.safety!=Safety.VERIFIED_ORDINARY_EQUIVALENT || assessment.steps.isEmpty() || !engine.isCurrent(current))return null;
        }catch(Exception failure){return null;}finally{calling=false;}
        Attempt attempt=new Attempt(current,assessment.steps.get(0));pending=attempt;
        calling=true;
        try {
            Submission result=engine.enqueue(attempt);
            if(result==Submission.ENQUEUED){state=State.SUBMITTED;return attempt;}
            if(result==Submission.REJECTED){pending=null;state=State.REJECTED;return null;}
            uncertain();return attempt;
        }catch(Exception failure){uncertain();return attempt;}finally{calling=false;}
    }
    /** Only engine-correlated semantic observations, not queue ACKs or changed client revisions. */
    public boolean observe(Attempt attempt,Observation result) {
        owner();if(stopped || attempt==null || attempt!=pending || result==null || current!=attempt.context)return false;
        if(result==Observation.UNCERTAIN){uncertain();return true;}
        pending=null;
        state=result==Observation.PROGRESS?State.PROGRESSED:result==Observation.COMPLETE?State.COMPLETED:State.REJECTED;
        return true;
    }
    private void uncertain(){state=State.UNCERTAIN;}
    /** Owner shutdown/disconnect/cancel: release private references, retain bounded outcome only. */
    public void close(){owner();if(stopped)return;stopped=true;state=pending!=null || state==State.UNCERTAIN?State.UNCERTAIN:State.STOPPED;current=null;pending=null;}
}

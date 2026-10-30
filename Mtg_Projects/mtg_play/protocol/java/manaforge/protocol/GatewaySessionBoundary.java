package manaforge.protocol;

import com.google.gson.JsonObject;
import java.io.IOException;

/** Owned viewer admission plus receipt reservation. No sockets, engine calls or reconnect. */
public final class GatewaySessionBoundary implements AutoCloseable {
    /** Trusted, prompt enqueue only: no socket IO, engine waiting or calls back into this owner. */
    public interface Submission {void enqueue(JsonObject request) throws Exception;}
    public enum State { ACTIVE, DISCONNECTED, FAULTED, CLOSED }
    private final GatewayCommandGate gate;
    private final SubmissionLedger ledger;
    private State state=State.ACTIVE;
    private boolean dispatching;
    public GatewaySessionBoundary(GatewayHandshake.ViewerContext context,boolean fixtureMode,int capacity) {
        if(context==null)throw new IllegalArgumentException("SESSION_CONTEXT");
        // Both constituents use the same validated capacity and authenticated ownership.
        gate=new GatewayCommandGate(context,fixtureMode,capacity);
        ledger=new SubmissionLedger(context.sessionId,context.viewerId,capacity);
    }
    public synchronized State state(){return state;}
    private void active() throws WireEnvelope.EnvelopeException {
        notDispatching();
        if(state!=State.ACTIVE)throw new WireEnvelope.EnvelopeException("SESSION_CLOSED");
    }
    private void retained() throws WireEnvelope.EnvelopeException {
        notDispatching();
        if(state==State.CLOSED)throw new WireEnvelope.EnvelopeException("SESSION_CLOSED");
    }
    private void notDispatching() throws WireEnvelope.EnvelopeException {
        if(dispatching)throw new WireEnvelope.EnvelopeException("SESSION_REENTRANT");
    }
    private void stop(State reason) throws IOException {
        state=reason;gate.close();ledger.disconnected();
    }
    public synchronized void observe(String text) throws IOException {
        active();try{gate.observe(text);}catch(IOException | RuntimeException error){stop(State.FAULTED);throw error;}
    }
    /** Admission and one-time reservation share this monitor. shouldSubmit is not an engine outcome. */
    public synchronized SubmissionLedger.Prepared prepare(String text) throws IOException {
        active();try{return ledger.prepare(text,gate.check(text));}
        catch(IOException | RuntimeException error){stop(State.FAULTED);throw error;}
    }
    /** Reserve and invoke the trusted enqueue once under the owner monitor. Never confirms execution. */
    public synchronized SubmissionLedger.Prepared dispatch(String text,Submission submission) throws IOException {
        if(submission==null)throw new IllegalArgumentException("SESSION_SUBMISSION");
        SubmissionLedger.Prepared prepared=prepare(text);
        if(!prepared.shouldSubmit)return prepared;
        dispatching=true;
        try {
            submission.enqueue(WireMessages.parse(text));
            return prepared;
        }catch(Exception error) {
            if(error instanceof InterruptedException)Thread.currentThread().interrupt();
            stop(State.FAULTED);
            // Enqueue may have taken effect before throwing. Never retry or expose callback details.
            throw new WireEnvelope.EnvelopeException("SESSION_DISPATCH_FAILED");
        }catch(Error error) {
            // Preserve JVM/programming failures, but do not leave an apparently retryable reservation.
            stop(State.FAULTED);throw error;
        }finally{dispatching=false;}
    }
    /** Trusted engine-correlated outcomes only. Late outcomes may resolve uncertainty after disconnect. */
    public synchronized JsonObject recordOutcome(String id,String outcome,String code) throws IOException {
        retained();try{return ledger.recordOutcome(id,outcome,code);}
        catch(IOException | RuntimeException error){if(state==State.ACTIVE)stop(State.FAULTED);throw error;}
    }
    /** Private owner diagnostic/reconciliation API; never send to another viewer. */
    public synchronized JsonObject receiptFor(String id) throws IOException {retained();return ledger.receiptFor(id);}
    public synchronized void disconnected() throws IOException {notDispatching();if(state==State.ACTIVE)stop(State.DISCONNECTED);}
    public synchronized void close(){if(dispatching)throw new IllegalStateException("SESSION_REENTRANT");if(state==State.CLOSED)return;state=State.CLOSED;gate.close();ledger.close();}
}

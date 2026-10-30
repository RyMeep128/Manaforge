package manaforge.protocol;

import com.google.gson.JsonObject;
import java.io.IOException;

/** Owned viewer admission plus receipt reservation. No sockets, engine calls or reconnect. */
public final class GatewaySessionBoundary implements AutoCloseable {
    public enum State { ACTIVE, DISCONNECTED, FAULTED, CLOSED }
    private final GatewayCommandGate gate;
    private final SubmissionLedger ledger;
    private State state=State.ACTIVE;
    public GatewaySessionBoundary(GatewayHandshake.ViewerContext context,boolean fixtureMode,int capacity) {
        if(context==null)throw new IllegalArgumentException("SESSION_CONTEXT");
        // Both constituents use the same validated capacity and authenticated ownership.
        gate=new GatewayCommandGate(context,fixtureMode,capacity);
        ledger=new SubmissionLedger(context.sessionId,context.viewerId,capacity);
    }
    public synchronized State state(){return state;}
    private void active() throws WireEnvelope.EnvelopeException {
        if(state!=State.ACTIVE)throw new WireEnvelope.EnvelopeException("SESSION_CLOSED");
    }
    private void retained() throws WireEnvelope.EnvelopeException {
        if(state==State.CLOSED)throw new WireEnvelope.EnvelopeException("SESSION_CLOSED");
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
    /** Trusted engine-correlated outcomes only. Late outcomes may resolve uncertainty after disconnect. */
    public synchronized JsonObject recordOutcome(String id,String outcome,String code) throws IOException {
        retained();try{return ledger.recordOutcome(id,outcome,code);}
        catch(IOException | RuntimeException error){if(state==State.ACTIVE)stop(State.FAULTED);throw error;}
    }
    /** Private owner diagnostic/reconciliation API; never send to another viewer. */
    public synchronized JsonObject receiptFor(String id) throws IOException {retained();return ledger.receiptFor(id);}
    public synchronized void disconnected() throws IOException {if(state==State.ACTIVE)stop(State.DISCONNECTED);}
    public synchronized void close(){if(state==State.CLOSED)return;state=State.CLOSED;gate.close();ledger.close();}
}

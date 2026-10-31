package manaforge.payment.gateway;

import java.io.IOException;
import java.util.*;
import manaforge.payment.PaymentCoordinator;
import manaforge.payment.PaymentCoordinator.*;
import manaforge.protocol.GatewaySessionBoundary;

/** Shared session reservation around a trusted native port. No production native port exists yet.
 * Construct/call on the coordinator's serialized engine owner. Boundary is borrowed, never closed here. */
public final class GatewayPaymentPort implements EnginePort,AutoCloseable {
    private final Thread owner=Thread.currentThread();
    private final GatewaySessionBoundary boundary;private final EnginePort nativePort;
    private final Set<Attempt> seen=Collections.newSetFromMap(new IdentityHashMap<Attempt,Boolean>());
    private GatewaySessionBoundary.InternalReservation reservation;private Attempt pending;private boolean closed,calling;
    public GatewayPaymentPort(GatewaySessionBoundary boundary,EnginePort nativePort) {
        this.boundary=Objects.requireNonNull(boundary);this.nativePort=Objects.requireNonNull(nativePort);
    }
    private void owner(){if(Thread.currentThread()!=owner || calling)throw new IllegalStateException("PAYMENT_OWNER");}
    private boolean nativeCurrent(Context context){calling=true;try{return nativePort.isCurrent(context);}finally{calling=false;}}
    public boolean isCurrent(Context context) {
        owner();return !closed && context!=null && boundary.matchesInternalDecision(context.session,context.viewer,context.revision,context.decision) && nativeCurrent(context);
    }
    public Assessment inspect(Context context) {owner();if(!isCurrent(context))return null;calling=true;try{return nativePort.inspect(context);}finally{calling=false;}}
    public Submission enqueue(Attempt attempt) throws Exception {
        owner();if(closed || attempt==null)return Submission.REJECTED;
        if(seen.contains(attempt))return Submission.UNCERTAIN;
        if(pending!=null || seen.size()>=4096)return Submission.REJECTED;
        seen.add(attempt);Context context=attempt.context;
        reservation=boundary.reserveInternal(context.session,context.viewer,context.revision,context.decision);
        if(reservation==null)return Submission.REJECTED;
        pending=attempt;
        // A failed read-only preflight is definite nonexecution, so manual input remains possible.
        boolean current;
        try{current=boundary.internalCurrent(reservation) && nativeCurrent(context);}
        catch(Exception failure){settle(attempt,true);return Submission.REJECTED;}
        if(!current){settle(attempt,true);return Submission.REJECTED;}
        try {
            // Recheck after reserving, before handing off. Native enqueue must validate atomically too.
            calling=true;
            Submission result=nativePort.enqueue(attempt);
            if(result==Submission.REJECTED)settle(attempt,true);
            else if(result!=Submission.ENQUEUED){settle(attempt,false);return Submission.UNCERTAIN;}
            return result;
        }catch(Exception failure){settle(attempt,false);throw failure;}
        catch(Error failure){try{settle(attempt,false);}catch(Exception cleanup){failure.addSuppressed(cleanup);}throw failure;}
        finally{calling=false;}
    }
    /** Semantic native observation only, not a client ACK. Owner must also notify its coordinator. */
    public boolean observe(Attempt attempt,Observation observation) throws IOException {
        owner();if(closed || observation==null)return false;
        return settle(attempt,observation!=Observation.UNCERTAIN);
    }
    private boolean settle(Attempt attempt,boolean resolved) throws IOException {
        if(attempt==null || attempt!=pending || reservation==null)return false;
        boolean accepted=boundary.settleInternal(reservation,resolved);
        if(accepted && resolved){pending=null;reservation=null;}return accepted;
    }
    public void close() throws IOException {
        owner();if(closed)return;closed=true;
        try{if(pending!=null && boundary.state()!=GatewaySessionBoundary.State.CLOSED)settle(pending,false);}
        finally{pending=null;reservation=null;seen.clear();}
    }
}

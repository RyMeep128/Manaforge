import com.google.gson.JsonObject;
import manaforge.protocol.*;
import java.io.IOException;
import java.util.concurrent.ArrayBlockingQueue;

/** Serialized trusted session-worker composition. No socket/engine IO inside admission. */
public final class ManaforgeOpeningSession implements AutoCloseable {
    private final GatewayHandshake.ViewerContext context;
    private final ManaforgeOpeningProjection projection;
    private final GatewaySessionBoundary boundary;
    private final ArrayBlockingQueue<JsonObject> nativeQueue=new ArrayBlockingQueue<>(1);
    private JsonObject submittedNative;
    public ManaforgeOpeningSession(GatewayHandshake.ViewerContext context,ManaforgeOpeningProjection projection,String snapshot) throws IOException {
        if(context==null || projection==null)throw new IllegalArgumentException("OPENING_SESSION_CONTEXT");
        // Bounded history covers the opening plus up to 512 continuation decisions.
        this.context=context;this.projection=projection;boundary=new GatewaySessionBoundary(context,false,Boolean.getBoolean("manaforge.liveGame")?4096:1024);
        try{boundary.observe(snapshot);}catch(IOException | RuntimeException failure){close();throw failure;}
    }
    public SubmissionLedger.Prepared dispatch(String wire,String game,String engineViewer,long decision,long cycle) throws IOException {
        return boundary.dispatch(wire,request->{
            JsonObject nativeCommand=projection.claimOperation(request.toString(),context.sessionId,context.viewerId,game,engineViewer,decision,cycle);
            if(!nativeQueue.offer(nativeCommand))throw new IOException("OPENING_QUEUE_FULL");
            submittedNative=nativeCommand.deepCopy();
        });
    }
    /** Trusted engine worker only. Ownership of the fresh private command transfers here. */
    public JsonObject pollNative(){return nativeQueue.poll();}
    public JsonObject receiptFor(String commandId) throws IOException{return boundary.receiptFor(commandId);}
    public void observe(String snapshot) throws IOException{boundary.observe(snapshot);}
    public JsonObject uncertain(String id) throws IOException{return boundary.recordOutcome(id,"uncertain","COMMAND_UNCERTAIN");}
    public JsonObject confirmAbility(String id,NativeCastCorrelation.AbilityEvidence evidence) throws IOException {
        if(evidence==null || submittedNative==null || !id.equals(submittedNative.get("request_id").getAsString())
            || !evidence.matchesCommand(submittedNative))throw new IOException("CAST_EVIDENCE_MISMATCH");
        return boundary.recordOutcome(id,"confirmed",null);
    }
    public JsonObject confirmPriority(String id,NativeCastCorrelation.PriorityEvidence evidence) throws IOException {
        if(evidence==null || submittedNative==null || !id.equals(submittedNative.get("request_id").getAsString())
            || !evidence.matchesCommand(submittedNative))throw new IOException("PRIORITY_EVIDENCE_MISMATCH");
        return boundary.recordOutcome(id,"confirmed",null);
    }
    public JsonObject confirmAttackFinish(String id,NativeCastCorrelation.AttackFinishEvidence evidence) throws IOException {
        if(evidence==null || submittedNative==null || !id.equals(submittedNative.get("request_id").getAsString())
            || !evidence.matchesCommand(submittedNative))throw new IOException("ATTACK_EVIDENCE_MISMATCH");
        return boundary.recordOutcome(id,"confirmed",null);
    }
    public JsonObject confirmAttackerSelection(String id,NativeCastCorrelation.AttackerSelectionEvidence evidence) throws IOException {
        if(evidence==null || submittedNative==null || !id.equals(submittedNative.get("request_id").getAsString())
            || !evidence.matchesCommand(submittedNative))throw new IOException("ATTACKER_EVIDENCE_MISMATCH");
        return boundary.recordOutcome(id,"confirmed",null);
    }
    public JsonObject confirmDeclaredAttack(String id,NativeCastCorrelation.DeclaredAttackEvidence evidence) throws IOException {
        if(evidence==null || submittedNative==null || !id.equals(submittedNative.get("request_id").getAsString()) || !evidence.matchesCommand(submittedNative))throw new IOException("DECLARED_ATTACK_EVIDENCE_MISMATCH");
        return boundary.recordOutcome(id,"confirmed",null);
    }
    public JsonObject confirmTurnDecision(String id,NativeCastCorrelation.TurnDecisionEvidence evidence) throws IOException {
        if(evidence==null || submittedNative==null || !id.equals(submittedNative.get("request_id").getAsString()) || !evidence.matchesCommand(submittedNative))throw new IOException("TURN_EVIDENCE_MISMATCH");return boundary.recordOutcome(id,"confirmed",null);
    }
    public void disconnected() throws IOException {
        try{boundary.disconnected();}finally{projection.invalidateDecision();nativeQueue.clear();}
    }
    public void close(){try{boundary.close();}finally{projection.invalidateDecision();nativeQueue.clear();submittedNative=null;}}
}

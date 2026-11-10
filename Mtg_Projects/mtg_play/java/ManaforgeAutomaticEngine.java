import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Shared manual/native response authority with conservative internal payment between
 * viewer windows. The outstanding manual dispatch stays reserved until advance returns. */
public final class ManaforgeAutomaticEngine implements ManaforgeGameplaySession.Engine {
    private final ManaforgeGameplaySession.Engine nativeEngine;private final NativeAutomaticPayment payment;private final java.util.function.BooleanSupplier cancelled;
    public ManaforgeAutomaticEngine(ManaforgeGameplaySession.Engine nativeEngine,NativeAutomaticPayment payment,java.util.function.BooleanSupplier cancelled){this.cancelled=Objects.requireNonNull(cancelled);this.nativeEngine=Objects.requireNonNull(nativeEngine);this.payment=Objects.requireNonNull(payment);}
    public JsonObject metadata(JsonObject state,String... ids) throws Exception{return nativeEngine.metadata(state,ids);}
    public JsonObject submit(JsonObject command) throws Exception{return nativeEngine.submit(command);}
    public JsonObject terminalMetadata(JsonObject before) throws Exception{return nativeEngine.terminalMetadata(before);}
    public String sessionNotice() throws Exception{return nativeEngine.sessionNotice();}
    public JsonObject pollRequest() throws Exception{return nativeEngine.pollRequest();}
    public boolean requestCurrent(String id) throws Exception{return nativeEngine.requestCurrent(id);}
    public ManaforgeGameplaySession.Advance refresh() throws Exception{return nativeEngine.refresh();}
    public ManaforgeGameplaySession.Advance advance(long previous) throws Exception {return automate(nativeEngine.advance(previous));}
    public ManaforgeGameplaySession.Advance resume(ManaforgeGameplaySession.Advance fresh) throws Exception {return automate(nativeEngine.resume(fresh));}
    private ManaforgeGameplaySession.Advance automate(ManaforgeGameplaySession.Advance next) throws Exception {
        for(int step=0;next.prompt!=null && next.terminal==null && step<128;step++) {
            if(nativeEngine.pollRequest()!=null)break;
            if(cancelled.getAsBoolean() || Thread.currentThread().isInterrupted()){payment.uncertain();throw new IOException("AUTO_PAYMENT_CANCELLED");}
            JsonObject before=next.state.deepCopy(),prompt=next.prompt.deepCopy(),guard=metadata(before);
            JsonObject command=payment.prepare(before,prompt,guard);if(command==null){
                if("GAME_PLAY_MANA".equals(prompt.get("kind").getAsString()))next.state.addProperty("payment_reason",payment.reason());break;
            }
            if(!payment.revalidate(metadata(before))){payment.rejectedBeforeSubmission();ManaforgeGameplaySession.Advance fresh=nativeEngine.refresh();if(fresh==null){next.state.addProperty("payment_reason","STALE_CONTEXT");return next;}next=fresh;continue;}
            JsonObject accepted;
            try{accepted=submit(command);next=nativeEngine.advance(prompt.get("decision_id").getAsLong());}
            catch(Exception failure){payment.uncertain();throw failure;}
            if(next.terminal!=null){payment.observedTerminal(command,accepted,nativeEngine.terminalMetadata(before));return next;}
            if(next.prompt==null){payment.uncertain();throw new IOException("AUTO_PAYMENT_INTERRUPTED");}
            List<String> ids=new ArrayList<>();if("object".equals(command.get("kind").getAsString()))ids.add(command.get("value").getAsString());
            for(JsonElement stacked:next.state.getAsJsonArray("stack"))ids.add(stacked.getAsJsonObject().get("id").getAsString());
            payment.observed(before,prompt,command,guard,accepted,next.state,next.prompt,metadata(next.state,ids.toArray(new String[0])));
        }
        return next;
    }
}

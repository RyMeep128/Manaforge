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
    public ManaforgeOpeningSession(GatewayHandshake.ViewerContext context,ManaforgeOpeningProjection projection,String snapshot) throws IOException {
        if(context==null || projection==null)throw new IllegalArgumentException("OPENING_SESSION_CONTEXT");
        this.context=context;this.projection=projection;boundary=new GatewaySessionBoundary(context,false,16);
        try{boundary.observe(snapshot);}catch(IOException | RuntimeException failure){close();throw failure;}
    }
    public SubmissionLedger.Prepared dispatch(String wire,String game,String engineViewer,long decision,long cycle) throws IOException {
        return boundary.dispatch(wire,request->{
            JsonObject nativeCommand=projection.claimBoolean(request.toString(),context.sessionId,context.viewerId,game,engineViewer,decision,cycle);
            if(!nativeQueue.offer(nativeCommand))throw new IOException("OPENING_QUEUE_FULL");
        });
    }
    /** Trusted engine worker only. Ownership of the fresh private command transfers here. */
    public JsonObject pollNative(){return nativeQueue.poll();}
    public JsonObject receiptFor(String commandId) throws IOException{return boundary.receiptFor(commandId);}
    public void disconnected() throws IOException {
        try{boundary.disconnected();}finally{projection.invalidateDecision();nativeQueue.clear();}
    }
    public void close(){try{boundary.close();}finally{projection.invalidateDecision();nativeQueue.clear();}}
}

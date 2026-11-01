import com.google.gson.*;
import manaforge.protocol.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.function.BooleanSupplier;

/** Opt-in public-fixture live opening endpoint; no product launch or broad gameplay support. */
public final class ManaforgeUnityOpening {
    public interface VerifiedAbilitySubmit {NativeCastCorrelation.AbilityEvidence submit(JsonObject command) throws Exception;}
    public interface NextPriority {PriorityOffer next() throws Exception;}
    public interface Observation {ObservedSnapshot read() throws Exception;}
    public static final class ObservedSnapshot {
        private final JsonObject snapshot;private final NativeCastCorrelation.PriorityEvidence evidence;
        public ObservedSnapshot(JsonObject snapshot,NativeCastCorrelation.PriorityEvidence evidence){this.snapshot=snapshot.deepCopy();this.evidence=evidence;}
    }
    public static final class PriorityOffer {
        private final JsonObject snapshot;private final long decision,cycle;private final ManaforgeOpeningLoopback.NativeSubmit submit;private final Observation observation;
        public PriorityOffer(JsonObject snapshot,long decision,long cycle,ManaforgeOpeningLoopback.NativeSubmit submit){this(snapshot,decision,cycle,submit,null);}
        public PriorityOffer(JsonObject snapshot,long decision,long cycle,ManaforgeOpeningLoopback.NativeSubmit submit,Observation observation){this.snapshot=snapshot.deepCopy();this.decision=decision;this.cycle=cycle;this.submit=submit;this.observation=observation;}
    }
    public static byte[] readBootstrap(InputStream input) throws IOException {
        try {
            JsonObject boot=WireEnvelope.parseObject(TextFrame.read(input));
            if(boot.size()!=2 || !boot.has("live_opening_bootstrap_version") || !boot.get("live_opening_bootstrap_version").toString().equals("1")
                || !boot.has("viewer_key_hex") || !boot.get("viewer_key_hex").isJsonPrimitive() || !boot.getAsJsonPrimitive("viewer_key_hex").isString()
                || !boot.get("viewer_key_hex").getAsString().matches("[0-9a-f]{64}"))throw new IOException();
            String hex=boot.get("viewer_key_hex").getAsString();byte[] key=new byte[32];for(int i=0;i<32;i++)key[i]=(byte)Integer.parseInt(hex.substring(i*2,i*2+2),16);return key;
        }catch(IOException | RuntimeException failure){throw new IOException("LIVE_OPENING_BOOTSTRAP_FAILED");}
    }
    public static void serve(JsonObject snapshot,ManaforgeOpeningProjection projection,String game,String engineViewer,long decision,long cycle,
            String engine,String hash,byte[] key,Path ready,ManaforgeOpeningLoopback.NativeSubmit submit,BooleanSupplier cancelled) throws Exception {
        serveVerifiedAbility(snapshot,projection,game,engineViewer,decision,cycle,engine,hash,key,ready,command->{submit.submit(command);return null;},cancelled);
    }
    public static void serveVerifiedAbility(JsonObject snapshot,ManaforgeOpeningProjection projection,String game,String engineViewer,long decision,long cycle,
            String engine,String hash,byte[] key,Path ready,VerifiedAbilitySubmit submit,BooleanSupplier cancelled) throws Exception {
        serveVerifiedAbility(snapshot,projection,game,engineViewer,decision,cycle,engine,hash,key,ready,submit,cancelled,null);
    }
    public static void serveVerifiedAbility(JsonObject snapshot,ManaforgeOpeningProjection projection,String game,String engineViewer,long decision,long cycle,
            String engine,String hash,byte[] key,Path ready,VerifiedAbilitySubmit submit,BooleanSupplier cancelled,NextPriority continuation) throws Exception {
        try(ServerSocket listener=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(500);
            JsonObject address=new JsonObject();address.addProperty("host","127.0.0.1");address.addProperty("port",listener.getLocalPort());
            Path temporary=Paths.get(ready.toString()+".tmp");Files.write(temporary,address.toString().getBytes(StandardCharsets.UTF_8));Files.move(temporary,ready,StandardCopyOption.ATOMIC_MOVE);
            long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(continuation==null?120:180);Socket socket=null;
            while(socket==null && !cancelled.getAsBoolean() && System.nanoTime()<deadline)try{socket=listener.accept();}catch(SocketTimeoutException waiting){}
            if(socket==null)throw new IOException("LIVE_UNITY_ACCEPT_FAILED");
            try(LoopbackFrameReader frames=new LoopbackFrameReader(socket)) {
                JsonObject client=ManaforgeOpeningLoopback.hello("live-opening","human",engine,hash,"client"),gateway=ManaforgeOpeningLoopback.hello("live-opening","human",engine,hash,"gateway");
                GatewayHandshake.ViewerContext context=ViewerChallengeHandshake.accept(frames,client.toString(),gateway.toString(),key,5000,cancelled);
                try(ManaforgeOpeningSession owner=new ManaforgeOpeningSession(context,projection,snapshot.toString())) {
                    frames.write(snapshot.toString(),5000,cancelled);
                    String wire=frames.read(60000,cancelled);SubmissionLedger.Prepared prepared=owner.dispatch(wire,game,engineViewer,decision,cycle);
                    frames.write(prepared.receipt().toString(),5000,cancelled);
                    if(!prepared.shouldSubmit)throw new IOException("LIVE_UNITY_CHOICE_REJECTED");
                    JsonObject command=owner.pollNative();if(command==null || owner.pollNative()!=null)throw new IOException("LIVE_UNITY_QUEUE_FAILED");
                    if(cancelled.getAsBoolean())throw new IOException("LIVE_UNITY_CANCELLED");
                    NativeCastCorrelation.AbilityEvidence evidence=submit.submit(command);
                    // Advancement alone remains uncertain. Only exact native ability evidence may settle.
                    JsonObject request=WireMessages.parse(wire);String id=request.get("message_id").getAsString();
                    frames.write((evidence==null?owner.uncertain(id):owner.confirmAbility(id,evidence)).toString(),5000,cancelled);
                    if(continuation!=null) {
                        if(evidence==null)throw new IOException("LIVE_UNITY_CONTINUATION_UNCONFIRMED");
                        PriorityOffer next=continuation.next();owner.observe(next.snapshot.toString());frames.write(next.snapshot.toString(),5000,cancelled);
                        boolean sent=false;
                        for(int retries=0;retries<8 && !sent;retries++) {
                            long remaining=java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(deadline-System.nanoTime());
                            if(remaining<=0)throw new IOException("LIVE_UNITY_PRIORITY_TIMEOUT");
                            String follow=frames.read((int)Math.min(60000,remaining),cancelled);
                            SubmissionLedger.Prepared admitted=owner.dispatch(follow,game,engineViewer,next.decision,next.cycle);
                            frames.write(admitted.receipt().toString(),5000,cancelled);
                            if(!admitted.shouldSubmit)continue;
                            JsonObject pass=owner.pollNative();if(pass==null || owner.pollNative()!=null)throw new IOException("LIVE_UNITY_QUEUE_FAILED");
                            if(cancelled.getAsBoolean())throw new IOException("LIVE_UNITY_CANCELLED");
                            next.submit.submit(pass);String passId=WireMessages.parse(follow).get("message_id").getAsString();
                            if(next.observation==null)frames.write(owner.uncertain(passId).toString(),5000,cancelled);
                            else {
                                ObservedSnapshot observed=next.observation.read();
                                frames.write(owner.confirmPriority(passId,observed.evidence).toString(),5000,cancelled);
                                owner.observe(observed.snapshot.toString());frames.write(observed.snapshot.toString(),5000,cancelled);
                            }
                            sent=true;
                        }
                        if(!sent)throw new IOException("LIVE_UNITY_PRIORITY_RETRY_LIMIT");
                    }
                    while(!cancelled.getAsBoolean() && System.nanoTime()<deadline)Thread.sleep(10);
                    owner.disconnected();
                }
            }
        }finally{projection.invalidateDecision();}
    }
}

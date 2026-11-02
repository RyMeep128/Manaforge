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
    public interface VerifiedAttackSubmit {VerifiedAttackResult submit(JsonObject command) throws Exception;}
    public static final class VerifiedAttackResult {
        private final NativeCastCorrelation.AttackFinishEvidence evidence;private final JsonObject snapshot;private final PriorityOffer followup;
        public VerifiedAttackResult(NativeCastCorrelation.AttackFinishEvidence evidence,JsonObject snapshot) {
            if(evidence==null || snapshot==null || !"snapshot".equals(snapshot.get("message_type").getAsString())
                || !snapshot.getAsJsonObject("body").getAsJsonObject("snapshot").get("decision").isJsonNull()
                || snapshot.getAsJsonObject("body").getAsJsonObject("snapshot").getAsJsonArray("actions").size()!=0)
                throw new IllegalArgumentException("COMBAT_RESULT_NOT_READ_ONLY");
            this.evidence=evidence;this.snapshot=snapshot.deepCopy();this.followup=null;
        }
        public VerifiedAttackResult(NativeCastCorrelation.AttackFinishEvidence evidence,PriorityOffer followup) {
            if(followup==null)throw new IllegalArgumentException("COMBAT_RESULT_NOT_PASS_ONLY");
            JsonObject view=followup.snapshot.getAsJsonObject("body").getAsJsonObject("snapshot");
            if(evidence==null || view.get("decision").isJsonNull() || !new JsonPrimitive(true).equals(view.getAsJsonObject("decision").get("is_priority"))
                || view.getAsJsonArray("actions").size()!=1 || !"pass".equals(view.getAsJsonArray("actions").get(0).getAsJsonObject().get("kind").getAsString()))
                throw new IllegalArgumentException("COMBAT_RESULT_NOT_PASS_ONLY");
            this.evidence=evidence;this.snapshot=followup.snapshot.deepCopy();this.followup=followup;
        }
    }
    private interface ChoiceSubmit {ChoiceEvidence submit(JsonObject command) throws Exception;}
    private static final class ChoiceEvidence {
        final NativeCastCorrelation.AbilityEvidence ability;final NativeCastCorrelation.AttackFinishEvidence attack;final JsonObject snapshot;final PriorityOffer followup;
        ChoiceEvidence(NativeCastCorrelation.AbilityEvidence ability,NativeCastCorrelation.AttackFinishEvidence attack){this(ability,attack,null,null);}
        ChoiceEvidence(NativeCastCorrelation.AbilityEvidence ability,NativeCastCorrelation.AttackFinishEvidence attack,JsonObject snapshot,PriorityOffer followup){this.ability=ability;this.attack=attack;this.snapshot=snapshot;this.followup=followup;}
        JsonObject confirm(ManaforgeOpeningSession owner,String id) throws IOException{return ability!=null?owner.confirmAbility(id,ability):owner.confirmAttackFinish(id,attack);}
    }
    public interface NextPriority {PriorityOffer next() throws Exception;}
    public interface Observation {ObservedSnapshot read() throws Exception;}
    public static final class ObservedSnapshot {
        private final JsonObject snapshot;private final NativeCastCorrelation.PriorityEvidence evidence;private final PriorityOffer followup;
        public ObservedSnapshot(JsonObject snapshot,NativeCastCorrelation.PriorityEvidence evidence){this(snapshot,evidence,null);}
        public ObservedSnapshot(JsonObject snapshot,NativeCastCorrelation.PriorityEvidence evidence,PriorityOffer followup){this.snapshot=snapshot.deepCopy();this.evidence=evidence;this.followup=followup;}
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
        serveChoice(snapshot,projection,game,engineViewer,decision,cycle,engine,hash,key,ready,command->{NativeCastCorrelation.AbilityEvidence proof=submit.submit(command);return proof==null?null:new ChoiceEvidence(proof,null);},cancelled,continuation);
    }
    public static void serveVerifiedAttackFinish(JsonObject snapshot,ManaforgeOpeningProjection projection,String game,String engineViewer,long decision,long cycle,
            String engine,String hash,byte[] key,Path ready,VerifiedAttackSubmit submit,BooleanSupplier cancelled) throws Exception {
        serveChoice(snapshot,projection,game,engineViewer,decision,cycle,engine,hash,key,ready,command->{VerifiedAttackResult result=submit.submit(command);return result==null?null:new ChoiceEvidence(null,result.evidence,result.snapshot,result.followup);},cancelled,null);
    }
    private static void serveChoice(JsonObject snapshot,ManaforgeOpeningProjection projection,String game,String engineViewer,long decision,long cycle,
            String engine,String hash,byte[] key,Path ready,ChoiceSubmit submit,BooleanSupplier cancelled,NextPriority continuation) throws Exception {
        try(ServerSocket listener=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(500);
            JsonObject address=new JsonObject();address.addProperty("host","127.0.0.1");address.addProperty("port",listener.getLocalPort());
            Path temporary=Paths.get(ready.toString()+".tmp");Files.write(temporary,address.toString().getBytes(StandardCharsets.UTF_8));Files.move(temporary,ready,StandardCopyOption.ATOMIC_MOVE);
            long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(continuation==null?180:240);Socket socket=null;
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
                    ChoiceEvidence evidence=submit.submit(command);
                    // Advancement alone remains uncertain. Only exact typed native evidence may settle.
                    JsonObject request=WireMessages.parse(wire);String id=request.get("message_id").getAsString();
                    frames.write((evidence==null?owner.uncertain(id):evidence.confirm(owner,id)).toString(),5000,cancelled);
                    if(evidence!=null && evidence.snapshot!=null){owner.observe(evidence.snapshot.toString());frames.write(evidence.snapshot.toString(),5000,cancelled);}
                    PriorityOffer next=evidence==null?null:evidence.followup;
                    if(continuation!=null) {
                        if(evidence==null || evidence.ability==null)throw new IOException("LIVE_UNITY_CONTINUATION_UNCONFIRMED");
                        next=continuation.next();owner.observe(next.snapshot.toString());frames.write(next.snapshot.toString(),5000,cancelled);
                    }
                    if(next!=null) {
                        for(int stage=0;stage<2 && next!=null;stage++) {
                            PriorityOffer following=null;
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
                                    following=observed.followup;
                                }
                                sent=true;
                            }
                            if(!sent)throw new IOException("LIVE_UNITY_PRIORITY_RETRY_LIMIT");
                            next=following;
                        }
                        if(next!=null)throw new IOException("LIVE_UNITY_PRIORITY_STAGE_LIMIT");
                    }
                    while(!cancelled.getAsBoolean() && System.nanoTime()<deadline)Thread.sleep(10);
                    owner.disconnected();
                }
            }
        }finally{projection.invalidateDecision();}
    }
}

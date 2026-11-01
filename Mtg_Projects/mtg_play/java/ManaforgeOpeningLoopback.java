import com.google.gson.*;
import manaforge.protocol.*;
import java.io.*;
import java.net.*;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.BooleanSupplier;

/** Public diagnostic client ONLY, not a product listener or credential-delivery API. */
public final class ManaforgeOpeningLoopback {
    public interface NativeSubmit {void submit(JsonObject command) throws Exception;}
    private static void require(boolean condition) throws IOException {if(!condition)throw new IOException("OPENING_LOOPBACK_FAILED");}
    private static String fresh(){byte[] bytes=new byte[32];new SecureRandom().nextBytes(bytes);StringBuilder out=new StringBuilder();for(byte value:bytes)out.append(String.format(Locale.ROOT,"%02x",value&255));return out.toString();}
    private static JsonObject hello(String session,String viewer,String engine,String hash,String role) {
        JsonObject out=new JsonObject(),body=new JsonObject();out.addProperty("wire_version",1);out.addProperty("message_type","hello");out.addProperty("message_id","auth-"+role);
        body.addProperty("protocol_version",1);body.addProperty("engine_version",engine);body.addProperty("artifact_manifest_sha256",hash);
        body.addProperty("session_id",session);body.addProperty("viewer_id",viewer);body.addProperty("role",role);
        for(String field:new String[]{"client_nonce","server_nonce","proof"})body.addProperty(field,String.join("",Collections.nCopies(64,"0")));
        out.add("body",body);return out;
    }
    private static void send(Socket peer,JsonObject value) throws IOException{TextFrame.write(peer.getOutputStream(),value.toString());peer.getOutputStream().flush();}
    private static JsonObject answer(JsonObject snapshot) {
        JsonObject envelope=new JsonObject(),body=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","command");envelope.addProperty("message_id","opening-choice");
        for(String field:new String[]{"session_id","viewer_id","revision"})body.add(field,snapshot.get(field));body.addProperty("operation","choose");
        body.add("decision_id",snapshot.getAsJsonObject("decision").get("decision_id"));
        body.add("option_id",snapshot.getAsJsonObject("decision").getAsJsonArray("options").get(0).getAsJsonObject().get("option_id"));envelope.add("body",body);return envelope;
    }
    public static void exchange(JsonObject snapshotEnvelope,ManaforgeOpeningProjection projection,String game,String engineViewer,long decision,long cycle,
            String engine,String hash,NativeSubmit submit,BooleanSupplier cancelled) throws Exception {
        JsonObject snapshot=snapshotEnvelope.getAsJsonObject("body").getAsJsonObject("snapshot");
        String session=snapshot.get("session_id").getAsString(),viewer=snapshot.get("viewer_id").getAsString();
        JsonObject client=hello(session,viewer,engine,hash,"client"),gateway=hello(session,viewer,engine,hash,"gateway");
        byte[] key=new byte[32];new SecureRandom().nextBytes(key);
        ExecutorService worker=Executors.newSingleThreadExecutor();Future<?> peerTask=null;
        try(ServerSocket listener=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));Socket peer=new Socket()) {
            listener.setSoTimeout(5000);peer.connect(new InetSocketAddress("127.0.0.1",listener.getLocalPort()),5000);peer.setSoTimeout(15000);
            try(LoopbackFrameReader owned=new LoopbackFrameReader(listener.accept())) {
                peerTask=worker.submit(()->{
                    JsonObject localClient=client.deepCopy(),localGateway=gateway.deepCopy();
                    String server=ViewerChallengeHandshake.readChallenge(TextFrame.read(peer.getInputStream())),nonce=fresh();
                    TextFrame.write(peer.getOutputStream(),ViewerChallengeHandshake.response(server,nonce));peer.getOutputStream().flush();
                    for(JsonObject value:new JsonObject[]{localClient,localGateway}){value.getAsJsonObject("body").addProperty("server_nonce",server);value.getAsJsonObject("body").addProperty("client_nonce",nonce);}
                    localClient.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(localClient.toString(),key));send(peer,localClient);
                    try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(localGateway.toString(),key)){require(verifier.verify(TextFrame.read(peer.getInputStream())));}
                    JsonObject received=ReceiveMessages.parse(TextFrame.read(peer.getInputStream()),session,viewer,1,false);
                    JsonObject command=answer(received.getAsJsonObject("body").getAsJsonObject("snapshot"));send(peer,command);
                    JsonObject first=WireMessages.parse(TextFrame.read(peer.getInputStream()));require(first.getAsJsonObject("body").get("outcome").getAsString().equals("submitted"));
                    send(peer,command);JsonObject duplicate=WireMessages.parse(TextFrame.read(peer.getInputStream()));require(first.equals(duplicate));return null;
                });
                GatewayHandshake.ViewerContext context=ViewerChallengeHandshake.accept(owned,client.toString(),gateway.toString(),key,5000,cancelled);
                try(ManaforgeOpeningSession owner=new ManaforgeOpeningSession(context,projection,snapshotEnvelope.toString())) {
                    owned.write(snapshotEnvelope.toString(),5000,cancelled);String wire=owned.read(5000,cancelled);
                    SubmissionLedger.Prepared first=owner.dispatch(wire,game,engineViewer,decision,cycle);require(first.shouldSubmit);
                    owned.write(first.receipt().toString(),5000,cancelled);
                    String retry=owned.read(5000,cancelled);require(wire.equals(retry));
                    SubmissionLedger.Prepared duplicate=owner.dispatch(retry,game,engineViewer,decision,cycle);require(!duplicate.shouldSubmit && duplicate.receipt().equals(first.receipt()));
                    JsonObject nativeCommand=owner.pollNative();require(nativeCommand!=null && owner.pollNative()==null);
                    // Native IO happens on the serialized worker AFTER admission returned.
                    if(cancelled.getAsBoolean())throw new IOException("OPENING_CANCELLED");submit.submit(nativeCommand);
                    owned.write(duplicate.receipt().toString(),5000,cancelled);peerTask.get(5,TimeUnit.SECONDS);
                    owner.disconnected();require(owner.receiptFor("opening-choice").getAsJsonObject("body").get("outcome").getAsString().equals("uncertain"));
                }
            }
        } finally {
            if(peerTask!=null)peerTask.cancel(true);worker.shutdownNow();projection.invalidateDecision();
            try {if(!worker.awaitTermination(5,TimeUnit.SECONDS))throw new IOException("OPENING_WORKER_CLEANUP_FAILED");}
            finally{Arrays.fill(key,(byte)0);}
        }
    }
}

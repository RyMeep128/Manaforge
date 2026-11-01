import com.google.gson.*;
import manaforge.protocol.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.function.BooleanSupplier;

/** Opt-in public-fixture live opening endpoint; no product launch or broad gameplay support. */
public final class ManaforgeUnityOpening {
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
        try(ServerSocket listener=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(500);
            JsonObject address=new JsonObject();address.addProperty("host","127.0.0.1");address.addProperty("port",listener.getLocalPort());
            Path temporary=Paths.get(ready.toString()+".tmp");Files.write(temporary,address.toString().getBytes(StandardCharsets.UTF_8));Files.move(temporary,ready,StandardCopyOption.ATOMIC_MOVE);
            long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(120);Socket socket=null;
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
                    submit.submit(command);
                    // Advancement alone is not semantic reconciliation. Never fabricate confirmed.
                    JsonObject request=WireMessages.parse(wire);frames.write(owner.uncertain(request.get("message_id").getAsString()).toString(),5000,cancelled);
                    while(!cancelled.getAsBoolean() && System.nanoTime()<deadline)Thread.sleep(10);
                    owner.disconnected();
                }
            }
        }finally{projection.invalidateDecision();}
    }
}

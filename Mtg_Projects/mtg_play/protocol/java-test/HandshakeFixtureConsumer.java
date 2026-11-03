package manaforge.protocol;
import com.google.gson.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class HandshakeFixtureConsumer {
    private static final ExecutorService POOL=Executors.newFixedThreadPool(4);
    private static JsonObject client,gateway;
    private interface Attempt {GatewayHandshake.ViewerContext get() throws IOException;}
    private static void require(boolean value){if(!value)throw new AssertionError("Gateway handshake fixture failed");}
    private static byte[] key(){byte[] value=new byte[32];for(int i=0;i<32;i++)value[i]=(byte)i;return value;}
    private static String failure(Attempt attempt) throws IOException {
        try{attempt.get();throw new AssertionError("Accepted failed handshake");}
        catch(WireEnvelope.EnvelopeException error){require(error.getMessage().equals(error.code));return error.code;}
    }
    private static final class Pair implements AutoCloseable {
        final Socket peer;final LoopbackFrameReader frames;
        Pair() throws IOException {
            Socket socket=new Socket();Socket accepted=null;
            try(ServerSocket listener=new ServerSocket()) {
                listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0));listener.setSoTimeout(2000);
                socket.connect(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),listener.getLocalPort()),2000);socket.setSoTimeout(2000);
                accepted=listener.accept();frames=new LoopbackFrameReader(accepted);peer=socket;
            }catch(IOException | RuntimeException error){socket.close();if(accepted!=null)accepted.close();throw error;}
        }
        public void close() throws IOException{try{frames.close();}finally{peer.close();}}
    }
    private static Future<?> validPeer(Pair p) {
        return POOL.submit(()->{
            TextFrame.write(p.peer.getOutputStream(),client.toString());
            try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(gateway.toString(),key())){require(verifier.verify(TextFrame.read(p.peer.getInputStream())));}
            return null;
        });
    }
    private static void started(LoopbackFrameReader frames) throws InterruptedException {
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(1);while(!frames.readInProgress() && System.nanoTime()<until)Thread.sleep(1);require(frames.readInProgress());
    }
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        client=corpus.getAsJsonArray("positive").get(0).getAsJsonObject().getAsJsonObject("envelope");gateway=corpus.getAsJsonArray("positive").get(1).getAsJsonObject().getAsJsonObject("envelope");int passed=0;
        try {
            try(Pair p=new Pair()) {
                byte[] callerKey=key();Future<?> peer=validPeer(p);GatewayHandshake.ViewerContext context=GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),callerKey,2000);
                CommandGateFixtureConsumer.run(context,Paths.get(args[0]).resolveSibling("dummy-session-v1.json"));
                SessionBoundaryFixtureConsumer.run(context,Paths.get(args[0]).resolveSibling("dummy-session-v1.json"));
                peer.get(2,TimeUnit.SECONDS);require(context.sessionId.equals("fixture-session") && context.viewerId.equals("seat-one") && Arrays.equals(callerKey,key()) && !p.frames.isClosed());passed++;
            }
            for(String defect:new String[]{"proof","pin","viewer","reflection","data"})try(Pair p=new Pair()) {
                JsonObject response=client.deepCopy();
                if(defect.equals("proof"))response.getAsJsonObject("body").addProperty("proof",String.join("",java.util.Collections.nCopies(64,"0")));
                if(defect.equals("pin") || defect.equals("viewer")) {
                    response.getAsJsonObject("body").addProperty(defect.equals("pin")?"artifact_manifest_sha256":"viewer_id",defect.equals("pin")?String.join("",java.util.Collections.nCopies(64,"b")):"other");
                    response.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(response.toString(),key()));
                }
                if(defect.equals("reflection"))response=gateway.deepCopy();if(defect.equals("data"))response.addProperty("message_type","snapshot");
                final String text=response.toString();Future<?> peer=POOL.submit(()->{TextFrame.write(p.peer.getOutputStream(),text);require(TextFrame.read(p.peer.getInputStream())==null);return null;});
                require("AUTH_FAILED".equals(failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),1000))) && p.frames.isClosed());peer.get(2,TimeUnit.SECONDS);passed++;
            }
            try(Pair p=new Pair()) {
                JsonObject inconsistent=gateway.deepCopy();inconsistent.getAsJsonObject("body").addProperty("session_id","other");
                require("AUTH_FAILED".equals(failure(()->GatewayHandshake.accept(p.frames,client.toString(),inconsistent.toString(),key(),1000))));require(TextFrame.read(p.peer.getInputStream())==null);passed++;
            }
            try(Pair p=new Pair()) {require("AUTH_TIMEOUT".equals(failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),120))) && p.frames.isClosed());passed++;}
            try(Pair p=new Pair()) {
                AtomicBoolean cancel=new AtomicBoolean();Future<String> attempt=POOL.submit(()->failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),5000,cancel::get)));
                started(p.frames);cancel.set(true);require(attempt.get(2,TimeUnit.SECONDS).equals("AUTH_CANCELLED") && p.frames.isClosed());passed++;
            }
            try(Pair p=new Pair()) {
                AtomicReference<Thread> worker=new AtomicReference<>();Future<String> attempt=POOL.submit(()->{worker.set(Thread.currentThread());try{return failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),5000));}finally{Thread.interrupted();}});
                started(p.frames);worker.get().interrupt();require(attempt.get(2,TimeUnit.SECONDS).equals("AUTH_CANCELLED"));passed++;
            }
            for(int length:new int[]{0,31})try(Pair p=new Pair()) {require("AUTH_FAILED".equals(failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),length==0?null:new byte[length],1000))) && p.frames.isClosed());passed++;}
            try(Pair p=new Pair()) {
                Future<?> peer=validPeer(p);GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),2000);peer.get(2,TimeUnit.SECONDS);
                require("AUTH_FAILED".equals(failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),1000))) && p.frames.isClosed());passed++;
            }
            for(int budget:new int[]{0,60001})try(Pair p=new Pair()) {
                try{GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),budget);throw new AssertionError("Accepted budget");}catch(IllegalArgumentException expected){}require(!p.frames.isClosed());passed++;
            }
            try(Pair p=new Pair()) {require("AUTH_CANCELLED".equals(failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),1000,()->true))) && p.frames.isClosed());passed++;}
            // Exercise the public authentication boundary, not only the frame primitive.
            byte[][] fragments={new byte[]{0,0},new byte[]{0,0,0,8,123},new byte[]{0,16,0,1},new byte[]{0,0,0,1,(byte)0xff},new byte[]{0,0,0,8,123},new byte[]{}};
            for(int i=0;i<fragments.length;i++)try(Pair p=new Pair()) {
                p.peer.getOutputStream().write(fragments[i]);p.peer.getOutputStream().flush();
                if(i>=4)p.peer.shutdownOutput();
                String expected=i<2?"AUTH_TIMEOUT":"AUTH_FAILED";
                require(failure(()->GatewayHandshake.accept(p.frames,client.toString(),gateway.toString(),key(),150)).equals(expected));
                require(p.frames.isClosed() && TextFrame.read(p.peer.getInputStream())==null);passed++;
            }
            require(passed==22);System.out.println("Java gateway handshake: 22 real loopback cases passed");
        }finally{POOL.shutdownNow();require(POOL.awaitTermination(3,TimeUnit.SECONDS));}
    }
}

import com.google.gson.*;
import manaforge.protocol.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Dormant private transport foundation. One authenticated owner, one bound game/viewer, read-only callback. */
public final class ManaforgeMetadataChannel implements AutoCloseable {
    public interface Reader {JsonObject read(JsonObject request) throws Exception;}
    private final ServerSocket listener;
    private final byte[] key;
    private final String game,viewer,engine,hash,session="metadata-"+UUID.randomUUID();
    private final Reader reader;
    private final AtomicBoolean cancelled=new AtomicBoolean();
    private final Thread worker;
    private volatile Socket peer;
    private volatile LoopbackFrameReader frames;
    public int port(){return listener.getLocalPort();}
    public String session(){return session;}
    private static JsonObject hello(String session,String viewer,String engine,String hash,String role) {
        JsonObject out=new JsonObject(),body=new JsonObject();out.addProperty("wire_version",1);out.addProperty("message_type","hello");out.addProperty("message_id","auth-"+role);
        body.addProperty("protocol_version",1);body.addProperty("session_id",session);body.addProperty("viewer_id",viewer);body.addProperty("engine_version",engine);body.addProperty("artifact_manifest_sha256",hash);body.addProperty("role",role);
        for(String field:new String[]{"server_nonce","client_nonce","proof"})body.addProperty(field,String.join("",Collections.nCopies(64,"0")));out.add("body",body);return out;
    }
    public static final class Client implements AutoCloseable {
        private final LoopbackFrameReader frames;
        private final String game,viewer;
        private Client(LoopbackFrameReader frames,String game,String viewer){this.frames=frames;this.game=game;this.viewer=viewer;}
        public synchronized JsonObject read(JsonObject request) throws IOException {
            JsonObject checked=validate(request.toString(),game,viewer);
            try{frames.write(checked.toString(),3000);String response=frames.read(3000);if(response==null)throw new IOException();return WireEnvelope.parseObject(response);}
            catch(IOException | RuntimeException failure){close();throw new IOException("METADATA_IO_FAILED");}
        }
        public void close() throws IOException{frames.close();}
    }
    public static Client connect(int port,String session,byte[] ownerKey,String game,String viewer,String engine,String hash) throws IOException {
        if(port<1 || port>65535 || ownerKey==null || ownerKey.length!=32)throw new IOException("METADATA_CONTEXT");
        try{uuid(new JsonPrimitive(game));uuid(new JsonPrimitive(viewer));}catch(RuntimeException invalid){throw new IOException("METADATA_CONTEXT");}
        byte[] privateKey=ownerKey.clone();Socket socket=new Socket();LoopbackFrameReader frames=null;
        try {
            socket.connect(new InetSocketAddress("127.0.0.1",port),3000);frames=new LoopbackFrameReader(socket);
            String serverNonce=ViewerChallengeHandshake.readChallenge(frames.read(3000));byte[] random=new byte[32];new java.security.SecureRandom().nextBytes(random);StringBuilder nonce=new StringBuilder();for(byte value:random)nonce.append(String.format("%02x",value&255));Arrays.fill(random,(byte)0);
            frames.write(ViewerChallengeHandshake.response(serverNonce,nonce.toString()),3000);
            JsonObject client=hello(session,viewer,engine,hash,"client"),gateway=hello(session,viewer,engine,hash,"gateway");
            for(JsonObject value:new JsonObject[]{client,gateway}){value.getAsJsonObject("body").addProperty("server_nonce",serverNonce);value.getAsJsonObject("body").addProperty("client_nonce",nonce.toString());}
            client.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(client.toString(),privateKey));frames.write(client.toString(),3000);
            try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(gateway.toString(),privateKey)){if(!verifier.verify(frames.read(3000)))throw new IOException();}
            return new Client(frames,game,viewer);
        }catch(IOException | RuntimeException failure){if(frames!=null)try{frames.close();}catch(IOException ignored){}try{socket.close();}catch(IOException ignored){}throw new IOException("METADATA_AUTH_FAILED");}
        finally{Arrays.fill(privateKey,(byte)0);}
    }
    private static String uuid(JsonElement value) {
        if(value==null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString())throw new IllegalArgumentException();
        String id=value.getAsString();if(!UUID.fromString(id).toString().equals(id))throw new IllegalArgumentException();return id;
    }
    private static Set<String> ids(JsonElement value) {
        if(value==null || !value.isJsonArray() || value.getAsJsonArray().size()>256)throw new IllegalArgumentException();
        Set<String> result=new HashSet<>();for(JsonElement item:value.getAsJsonArray())if(!result.add(uuid(item)))throw new IllegalArgumentException();return result;
    }
    /** No caller-provided paths, mutation commands, arbitrary seats or unrestricted object exports. */
    public static JsonObject validate(String text,String trustedGame,String trustedViewer) throws IOException {
        try {
            if(text==null || text.length()>65536)throw new IllegalArgumentException();
            JsonObject request=WireEnvelope.parseObject(text);
            if(request.size()!=6 || !new JsonPrimitive("metadata").equals(request.get("command"))
                || !trustedGame.equals(uuid(request.get("game"))) || !trustedViewer.equals(uuid(request.get("player"))))throw new IllegalArgumentException();
            JsonElement cycle=request.get("cycle");
            if(cycle==null || !cycle.isJsonPrimitive() || !cycle.getAsJsonPrimitive().isNumber() || !cycle.getAsString().matches("[0-9]+")
                || Long.parseLong(cycle.getAsString())>Integer.MAX_VALUE)throw new IllegalArgumentException();
            Set<String> objects=ids(request.get("object_ids")),identified=ids(request.get("identified_ids"));
            if(!objects.containsAll(identified))throw new IllegalArgumentException();
            return request;
        }catch(IOException | RuntimeException invalid){throw new IOException("METADATA_REQUEST_INVALID");}
    }
    public ManaforgeMetadataChannel(byte[] ownerKey,String game,String viewer,String engine,String hash,Reader reader) throws IOException {
        if(ownerKey==null || ownerKey.length!=32 || reader==null || engine==null || engine.isEmpty() || hash==null || !hash.matches("[0-9a-f]{64}"))throw new IllegalArgumentException("METADATA_CONTEXT");
        try{uuid(new JsonPrimitive(game));uuid(new JsonPrimitive(viewer));}catch(RuntimeException invalid){throw new IllegalArgumentException("METADATA_CONTEXT");}
        this.key=ownerKey.clone();this.game=game;this.viewer=viewer;this.engine=engine;this.hash=hash;this.reader=reader;
        ServerSocket bound=null;
        try{bound=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));bound.setSoTimeout(5000);}
        catch(IOException failure){Arrays.fill(key,(byte)0);if(bound!=null)try{bound.close();}catch(IOException ignored){}throw failure;}
        listener=bound;
        worker=new Thread(this::serve,"manaforge-private-metadata");worker.setDaemon(true);worker.start();
    }
    private void serve() {
        try {
            peer=listener.accept();
            if(cancelled.get())return;
            frames=new LoopbackFrameReader(peer);
            JsonObject client=hello(session,viewer,engine,hash,"client"),gateway=hello(session,viewer,engine,hash,"gateway");
            ViewerChallengeHandshake.accept(frames,client.toString(),gateway.toString(),key,5000,cancelled::get);
            Arrays.fill(key,(byte)0);
            for(int count=0;count<16384 && !cancelled.get();count++) {
                JsonObject request=validate(frames.readWhenAvailable(60000,cancelled::get),game,viewer);
                if(cancelled.get())return;
                JsonObject response;
                try{response=reader.read(request.deepCopy());if(response==null)throw new IOException();}
                catch(Exception failure){if(failure instanceof InterruptedException)Thread.currentThread().interrupt();response=new JsonObject();response.addProperty("status","error");response.addProperty("code","METADATA_READ_FAILED");}
                if(cancelled.get())return;
                frames.write(response.toString(),5000,cancelled::get);
            }
        }catch(IOException | RuntimeException failed){/* Fail closed; native or peer details never enter public logs. */}
        finally{cancelled.set(true);Arrays.fill(key,(byte)0);release();}
    }
    private void release() {
        try{if(frames!=null)frames.close();}catch(IOException ignored){}
        try{if(peer!=null)peer.close();}catch(IOException ignored){}
        try{listener.close();}catch(IOException ignored){}
    }
    public void close() throws IOException {
        cancelled.set(true);Arrays.fill(key,(byte)0);release();worker.interrupt();
        try{worker.join(2000);}catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new IOException("METADATA_CLEANUP_UNCERTAIN");}
        if(worker.isAlive())throw new IOException("METADATA_CLEANUP_UNCERTAIN");
    }
}

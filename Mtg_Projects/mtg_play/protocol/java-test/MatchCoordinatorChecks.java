import com.google.gson.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
import manaforge.protocol.*;

/** Real loopback/authentication checks. Synthetic snapshots are explicitly fixture-only. */
public final class MatchCoordinatorChecks {
    public static final String ENGINE="coordinator-fixture",HASH=String.join("",Collections.nCopies(64,"a"));
    public static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    interface Checked {void run() throws Exception;}
    static void rejects(Checked action,String code) throws Exception {try{action.run();}catch(IOException | IllegalArgumentException expected){return;}throw new AssertionError(code);}
    public static void await(BooleanSupplier condition,String code) throws Exception {long end=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(8);while(!condition.getAsBoolean() && System.nanoTime()<end)Thread.sleep(10);check(condition.getAsBoolean(),code);}
    public static byte[] key(int value){byte[] key=new byte[32];Arrays.fill(key,(byte)value);return key;}
    public static final class Client implements AutoCloseable {
        public final Socket socket;final ManaforgeMatchCoordinator.Viewer viewer;final boolean fixture;long revision=-1;
        public Client(ManaforgeMatchCoordinator.Viewer viewer,byte[] key,boolean fixture) throws Exception {this(viewer,key,fixture,viewer.viewer,ENGINE,HASH);}
        Client(ManaforgeMatchCoordinator.Viewer viewer,byte[] key,boolean fixture,String claimedViewer,String engine,String hash) throws Exception {
            this.viewer=viewer;this.fixture=fixture;socket=new Socket();socket.setReceiveBufferSize(1024);socket.connect(new InetSocketAddress("127.0.0.1",viewer.port),3000);socket.setSoTimeout(5000);
            try{
                String server=ViewerChallengeHandshake.readChallenge(TextFrame.read(socket.getInputStream())),nonce=String.join("",Collections.nCopies(64,"b"));
                TextFrame.write(socket.getOutputStream(),ViewerChallengeHandshake.response(server,nonce));
                JsonObject client=hello(viewer.session,claimedViewer,engine,hash,server,nonce,"client"),gateway=hello(viewer.session,claimedViewer,engine,hash,server,nonce,"gateway");
                client.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(client.toString(),key));TextFrame.write(socket.getOutputStream(),client.toString());socket.getOutputStream().flush();
                try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(gateway.toString(),key)){if(!verifier.verify(TextFrame.read(socket.getInputStream())))throw new IOException("CLIENT_AUTH_FAILED");}
            }catch(Exception failure){socket.close();throw failure;}
        }
        public JsonObject read() throws Exception {String raw=TextFrame.read(socket.getInputStream());if(raw==null)throw new IOException("CLIENT_EOF");JsonObject message=ReceiveMessages.parse(raw,viewer.session,viewer.viewer,revision<0?0:revision+1,fixture);revision=message.getAsJsonObject("body").getAsJsonObject("snapshot").get("revision").getAsLong();return message;}
        public void send(String raw) throws IOException {TextFrame.write(socket.getOutputStream(),raw);socket.getOutputStream().flush();}
        public void close() throws IOException {socket.close();}
    }
    static JsonObject hello(String session,String viewer,String engine,String hash,String server,String nonce,String role){
        JsonObject message=new JsonObject(),body=new JsonObject();message.addProperty("wire_version",1);message.addProperty("message_type","hello");message.addProperty("message_id","auth-"+(role.equals("client")?"client":"gateway"));
        body.addProperty("protocol_version",1);body.addProperty("session_id",session);body.addProperty("viewer_id",viewer);body.addProperty("engine_version",engine);body.addProperty("artifact_manifest_sha256",hash);body.addProperty("server_nonce",server);body.addProperty("client_nonce",nonce);body.addProperty("role",role);body.addProperty("proof",String.join("",Collections.nCopies(64,"0")));message.add("body",body);return message;
    }
    static JsonElement remap(JsonElement value,String viewer){
        if(value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()){String text=value.getAsString();return new JsonPrimitive(text.equals("one")?viewer:text.equals("two")?"other-"+viewer:text);}
        if(value.isJsonObject()){JsonObject next=new JsonObject();for(Map.Entry<String,JsonElement> field:value.getAsJsonObject().entrySet())next.add(field.getKey(),remap(field.getValue(),viewer));return next;}
        if(value.isJsonArray()){JsonArray next=new JsonArray();for(JsonElement item:value.getAsJsonArray())next.add(remap(item,viewer));return next;}return value.deepCopy();
    }
    static JsonObject snapshot(JsonObject template,ManaforgeMatchCoordinator.Viewer viewer,long revision,boolean large){
        JsonObject message=remap(template,viewer.viewer).getAsJsonObject(),snapshot=message.getAsJsonObject("body").getAsJsonObject("snapshot");snapshot.addProperty("session_id",viewer.session);snapshot.addProperty("viewer_id",viewer.viewer);snapshot.addProperty("revision",revision);snapshot.add("decision",JsonNull.INSTANCE);snapshot.add("actions",new JsonArray());
        if(large){JsonArray padding=new JsonArray();char[] chars=new char[800000];Arrays.fill(chars,'x');padding.add(new String(chars));snapshot.add("unsupported_fields",padding);}return message;
    }
    static Map<String,JsonObject> batch(JsonObject template,ManaforgeMatchCoordinator.Viewer a,ManaforgeMatchCoordinator.Viewer b,long revision,boolean large){Map<String,JsonObject> batch=new HashMap<>();batch.put(a.seat,snapshot(template,a,revision,large));batch.put(b.seat,snapshot(template,b,revision,false));return batch;}
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();JsonObject template=corpus.getAsJsonArray("cases").get(0).getAsJsonObject().getAsJsonArray("steps").get(0).getAsJsonObject().getAsJsonObject("envelope");
        AtomicInteger disposed=new AtomicInteger();AtomicBoolean cancel=new AtomicBoolean();byte[] keyA=key(1),keyB=key(2);
        try(ManaforgeMatchCoordinator coordinator=new ManaforgeMatchCoordinator("native-game",ENGINE,HASH,disposed::incrementAndGet,cancel::get,10000,300,true)){
            ManaforgeMatchCoordinator.Viewer a=coordinator.register("a","native-a","session-a","viewer-a",keyA);
            rejects(()->coordinator.register("a","other","other","other",keyB),"DUPLICATE_SEAT");rejects(()->coordinator.register("other","native-a","other","other",keyB),"DUPLICATE_NATIVE_PLAYER");rejects(()->coordinator.register("other","other","other","other",keyA),"DUPLICATE_KEY");
            ManaforgeMatchCoordinator.Viewer b=coordinator.register("b","native-b","session-b","viewer-b",keyB);coordinator.start();
            rejects(()->new Client(a,keyB,true),"WRONG_KEY");await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"WRONG_KEY_CLEANUP");
            rejects(()->new Client(a,keyA,true,"viewer-b",ENGINE,HASH),"SEAT_IMPERSONATION");await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"IMPERSONATION_CLEANUP");
            rejects(()->new Client(a,keyA,true,a.viewer,"wrong-engine",HASH),"WRONG_ENGINE_PIN");await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"PIN_CLEANUP");
            rejects(()->new Client(a,keyA,true,a.viewer,ENGINE,String.join("",Collections.nCopies(64,"c"))),"WRONG_ARTIFACT_PIN");await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"HASH_CLEANUP");
            try(Socket stalled=new Socket("127.0.0.1",a.port)){
                stalled.setSoTimeout(5000);ViewerChallengeHandshake.readChallenge(TextFrame.read(stalled.getInputStream()));
                try(Client clientB=new Client(b,keyB,true)){
                    await(()->coordinator.status("b").status==ManaforgeMatchCoordinator.Status.CONNECTED,"B_BLOCKED_BY_A_AUTH");check(coordinator.status("a").status==ManaforgeMatchCoordinator.Status.AUTHENTICATING,"A_AUTH_NOT_INDEPENDENT");stalled.close();await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"A_AUTH_CLOSE");
                    try(Client clientA=new Client(a,keyA,true)){
                        await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.CONNECTED,"A_CONNECT");
                        try(Socket duplicate=new Socket("127.0.0.1",a.port)){duplicate.setSoTimeout(5000);check(duplicate.getInputStream().read()==-1,"DUPLICATE_ACTIVE_ATTACHMENT");}
                        Map<String,JsonObject> first=batch(template,a,b,1,false);coordinator.publishSnapshots(first);first.clear();check(clientA.read()!=null && clientB.read()!=null,"TWO_VIEWER_PUBLICATION");await(()->coordinator.status("a").sentRevision==1 && coordinator.status("b").sentRevision==1,"INITIAL_WRITES_COMPLETE");
                        Map<String,JsonObject> bad=batch(template,a,b,2,false);bad.get("b").getAsJsonObject("body").getAsJsonObject("snapshot").addProperty("viewer_id","viewer-a");rejects(()->coordinator.publishSnapshots(bad),"FOREIGN_PUBLICATION");
                        check(coordinator.status("a").sentRevision==1 && coordinator.status("b").sentRevision==1,"PARTIAL_PUBLICATION");
                        clientA.close();await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"A_DISCONNECT");coordinator.publishSnapshots(batch(template,a,b,2,false));check(clientB.read()!=null && disposed.get()==0,"A_DISCONNECT_OWNED_MATCH");
                    }
                    try(Client slowA=new Client(a,keyA,true)){
                        await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.CONNECTED,"SLOW_A_CONNECT");
                        for(int revision=3;revision<35 && coordinator.status("a").status==ManaforgeMatchCoordinator.Status.CONNECTED;revision++){
                            coordinator.publishSnapshots(batch(template,a,b,revision,true));check(clientB.read()!=null && coordinator.status("a").pendingSnapshots<=1,"SLOW_A_BLOCKED_B");
                        }
                        await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"STALLED_WRITER_NOT_DISCONNECTED");check(disposed.get()==0,"WRITE_FAILURE_OWNED_MATCH");
                    }
                    clientB.send("{\"wire_version\":1,\"message_type\":\"command\",\"message_id\":\"forged\",\"body\":{}}");await(()->"READ_ONLY_TRAFFIC".equals(coordinator.status("b").reason),"UNEXPECTED_COMMAND_NOT_REJECTED");check(disposed.get()==0,"COMMAND_CLOSED_MATCH");
                }
            }
            cancel.set(true);await(coordinator::isClosed,"PARENT_CANCELLATION");coordinator.close();check(disposed.get()==1 && coordinator.status("a").status==ManaforgeMatchCoordinator.Status.CLOSED && coordinator.status("b").status==ManaforgeMatchCoordinator.Status.CLOSED,"OWNER_CLEANUP");
            rejects(()->coordinator.publishSnapshots(batch(template,a,b,99,false)),"PUBLISH_AFTER_CLOSE");
        }
        check(disposed.get()==1,"MATCH_DISPOSED_TWICE");Arrays.fill(keyA,(byte)0);Arrays.fill(keyB,(byte)0);
        System.out.println("Two-viewer coordinator authentication, bounded publication, disconnect isolation, read-only rejection and parent cleanup passed");
    }
}

import com.google.gson.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
import manaforge.protocol.*;

/** Opt-in read-only local match owner. No production launch or command routing. */
public final class ManaforgeMatchCoordinator implements AutoCloseable {
    public enum Status { REGISTERED, WAITING, AUTHENTICATING, CONNECTED, DISCONNECTED, CLOSED }
    public static final class Viewer {
        public final String seat,nativePlayer,session,viewer;public final int port;
        private Viewer(String seat,String nativePlayer,String session,String viewer,int port){this.seat=seat;this.nativePlayer=nativePlayer;this.session=session;this.viewer=viewer;this.port=port;}
    }
    public static final class ConnectionStatus {
        public final Status status;public final String reason;public final long sentRevision;public final int pendingSnapshots,pendingOrganizationSnapshots,queuedReceipts,pendingInputs;
        private ConnectionStatus(Status status,String reason,long sentRevision,int pending,int organization,int receipts,int inputs){this.status=status;this.reason=reason;this.sentRevision=sentRevision;pendingSnapshots=pending;pendingOrganizationSnapshots=organization;queuedReceipts=receipts;pendingInputs=inputs;}
    }
    public static final class Observation {
        private final JsonObject state,prompt;
        public Observation(JsonObject state,JsonObject prompt){this.state=state.deepCopy();this.prompt=prompt.deepCopy();}
    }
    /** Host-only projection bindings. Never serialized or accepted from a socket. */
    public static final class ProjectedObservation {
        public final Viewer viewer;public final long cycle;
        public final Map<String,String> objects,seats;
        private final JsonObject snapshot;
        private ProjectedObservation(Viewer viewer,long cycle,ManaforgeOpeningProjection.ObserverResult result){this.viewer=viewer;this.cycle=cycle;objects=result.objects;seats=result.seats;snapshot=result.snapshot();}
        public JsonObject snapshot(){return snapshot.deepCopy();}
    }
    public interface PreparedPublication {void commit() throws Exception;}
    public interface PublicationHook {PreparedPublication prepare(Map<String,ProjectedObservation> projected) throws Exception;}
    private static final class Connection {
        final LoopbackFrameReader frames;volatile boolean active;
        Connection(Socket socket) throws IOException {frames=new LoopbackFrameReader(socket);}
    }
    private final class Channel {
        final Viewer viewer;final ServerSocket listener;final byte[] key;final String client,gateway;
        ManaforgeOpeningProjection projection;
        final boolean extensionAllowed;final ArrayDeque<String> receipts=new ArrayDeque<>();final AtomicInteger incoming=new AtomicInteger();String control,organization;boolean extensionReady;
        Connection connection;Status status=Status.REGISTERED;String reason,pending,latest;long revision=-1,sent=-1;
        Channel(Viewer viewer,ServerSocket listener,byte[] key,boolean extensionAllowed){this.extensionAllowed=extensionAllowed;this.viewer=viewer;this.listener=listener;this.key=key.clone();client=hello(viewer,"client");gateway=hello(viewer,"gateway");projection=new ManaforgeOpeningProjection(viewer.session,viewer.viewer,viewer.nativePlayer,Collections.emptyMap());}
    }
    private final String nativeGame,engine,hash;private final AutoCloseable ownedMatch;private final BooleanSupplier parentCancelled;
    private final int authMilliseconds,writeMilliseconds;private final boolean fixtureMode;
    private final ConcurrentMap<String,Channel> channels=new ConcurrentHashMap<>();
    private final AtomicReference<Thread> ownerThread=new AtomicReference<>();
    private final ExecutorService owner=Executors.newSingleThreadExecutor(task->{Thread thread=new Thread(task,"match-coordinator-owner");thread.setDaemon(true);ownerThread.set(thread);return thread;});
    private final AtomicInteger workerSerial=new AtomicInteger();
    private final ThreadPoolExecutor workers=new ThreadPoolExecutor(7,7,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(16),task->{Thread thread=new Thread(task,"match-viewer-"+workerSerial.incrementAndGet());thread.setDaemon(true);return thread;},new ThreadPoolExecutor.AbortPolicy());
    private final AtomicBoolean stopping=new AtomicBoolean();private final CompletableFuture<Void> closed=new CompletableFuture<>();private boolean started;private ViewerChannelExtension extension;
    public ManaforgeMatchCoordinator(String nativeGame,String engine,String hash,AutoCloseable ownedMatch,BooleanSupplier parentCancelled){this(nativeGame,engine,hash,ownedMatch,parentCancelled,5000,5000,false);}
    ManaforgeMatchCoordinator(String nativeGame,String engine,String hash,AutoCloseable ownedMatch,BooleanSupplier parentCancelled,int authMilliseconds,int writeMilliseconds,boolean fixtureMode){
        if(!id(nativeGame) || !id(engine) || hash==null || !hash.matches("[0-9a-f]{64}") || authMilliseconds<1 || authMilliseconds>60000 || writeMilliseconds<1 || writeMilliseconds>60000)throw new IllegalArgumentException("COORDINATOR_CONTEXT");
        this.nativeGame=nativeGame;this.engine=engine;this.hash=hash;this.ownedMatch=Objects.requireNonNull(ownedMatch);this.parentCancelled=Objects.requireNonNull(parentCancelled);this.authMilliseconds=authMilliseconds;this.writeMilliseconds=writeMilliseconds;this.fixtureMode=fixtureMode;
    }
    private static boolean id(String value){return value!=null && value.matches("[A-Za-z0-9_.:-]{1,128}");}
    private static void require(boolean value,String code) throws IOException {if(!value)throw new IOException(code);}
    private <T>T invoke(Callable<T> action) throws Exception {
        require(!stopping.get(),"COORDINATOR_CLOSED");
        if(Thread.currentThread()==ownerThread.get())return action.call();
        try{return owner.submit(()->{require(!stopping.get(),"COORDINATOR_CLOSED");return action.call();}).get(15,TimeUnit.SECONDS);}catch(ExecutionException failure){Throwable cause=failure.getCause();if(cause instanceof Exception)throw (Exception)cause;throw new IOException("COORDINATOR_OWNER_FAILED");}catch(RejectedExecutionException failure){throw new IOException("COORDINATOR_CLOSED");}
    }
    public Viewer register(String seat,String nativePlayer,String session,String viewer,byte[] key) throws Exception {
        return register(seat,nativePlayer,session,viewer,key,false);
    }
    public Viewer register(String seat,String nativePlayer,String session,String viewer,byte[] key,boolean extensionAllowed) throws Exception {
        if(!id(seat) || !id(nativePlayer) || !id(session) || !id(viewer) || key==null || key.length!=32)throw new IllegalArgumentException("COORDINATOR_VIEWER");
        byte[] copy=key.clone();try{return invoke(()->{
            require(!started && channels.size()<2 && !channels.containsKey(seat),"COORDINATOR_REGISTRATION");
            for(Channel other:channels.values())require(!other.viewer.nativePlayer.equals(nativePlayer) && !other.viewer.session.equals(session) && !other.viewer.viewer.equals(viewer) && !Arrays.equals(other.key,copy),"COORDINATOR_DUPLICATE_IDENTITY");
            ServerSocket listener=new ServerSocket(0,4,InetAddress.getByName("127.0.0.1"));listener.setSoTimeout(100);
            Viewer registration=new Viewer(seat,nativePlayer,session,viewer,listener.getLocalPort());channels.put(seat,new Channel(registration,listener,copy,extensionAllowed));return registration;
        });}finally{Arrays.fill(copy,(byte)0);}
    }
    public void installExtension(ViewerChannelExtension.Factory factory) throws Exception {
        invoke(()->{require(!started && extension==null,"COORDINATOR_EXTENSION");extension=Objects.requireNonNull(factory.create(this::sendExtension));return null;});
    }
    public void updateExtension(ViewerChannelExtension.OwnerAction action) throws Exception {
        invoke(()->{require(extension!=null,"COORDINATOR_EXTENSION");action.run(extension);return null;});
    }
    private boolean sendExtension(String seat,ViewerChannelExtension.Kind kind,String raw) throws Exception {
        require(Thread.currentThread()==ownerThread.get(),"EXTENSION_OWNER_THREAD");
        require(raw!=null && raw.length()<=ViewerChannelExtension.MAX_BYTES && raw.getBytes(StandardCharsets.UTF_8).length<=ViewerChannelExtension.MAX_BYTES,"EXTENSION_SIZE");
        Channel channel=channels.get(seat);require(channel!=null && channel.extensionAllowed,"EXTENSION_SEAT");Connection overflow=null;
        synchronized(channel){
            if(channel.connection==null || !channel.connection.active || stopping.get())return false;
            if(kind==ViewerChannelExtension.Kind.CONTROL){if(channel.control!=null)overflow=channel.connection;else channel.control=raw;}
            else if(kind==ViewerChannelExtension.Kind.RECEIPT){if(channel.receipts.size()>=32)overflow=channel.connection;else channel.receipts.addLast(raw);}
            else if(kind==ViewerChannelExtension.Kind.SNAPSHOT)channel.organization=raw;
            else throw new IOException("EXTENSION_KIND");
            channel.notifyAll();
        }
        if(overflow!=null){disconnect(channel,overflow,"EXTENSION_OUTPUT_OVERFLOW");return false;}return true;
    }
    private void extensionConnected(Channel channel,Connection connection){
        owner.execute(()->{if(stopping.get())return;synchronized(channel){if(channel.connection!=connection || !connection.active)return;}
            try{extension.connected(channel.viewer.seat);synchronized(channel){if(channel.connection==connection && connection.active){channel.extensionReady=true;channel.notifyAll();}}}catch(Exception failure){disconnect(channel,connection,"EXTENSION_FAILED");}
        });
    }
    private String hello(Viewer viewer,String role){
        JsonObject message=new JsonObject(),body=new JsonObject();message.addProperty("wire_version",1);message.addProperty("message_type","hello");message.addProperty("message_id","auth-"+(role.equals("client")?"client":"gateway"));
        body.addProperty("protocol_version",1);body.addProperty("engine_version",engine);body.addProperty("artifact_manifest_sha256",hash);body.addProperty("session_id",viewer.session);body.addProperty("viewer_id",viewer.viewer);body.addProperty("role",role);
        for(String field:new String[]{"server_nonce","client_nonce","proof"})body.addProperty(field,String.join("",Collections.nCopies(64,"0")));message.add("body",body);return message.toString();
    }
    public void start() throws Exception {invoke(()->{require(!started && !channels.isEmpty(),"COORDINATOR_START");for(Channel channel:channels.values())require(!channel.extensionAllowed || extension!=null,"COORDINATOR_EXTENSION");started=true;for(Channel channel:channels.values()){synchronized(channel){channel.status=Status.WAITING;}workers.execute(()->accept(channel));}workers.execute(this::watchParent);return null;});}
    private void watchParent(){try{while(!stopping.get()){if(parentCancelled.getAsBoolean()){requestStop();return;}Thread.sleep(25);}}catch(InterruptedException interrupted){Thread.currentThread().interrupt();}catch(RuntimeException failure){requestStop();}}
    private void accept(Channel channel){
        while(!stopping.get()){
            Connection connection=null;
            try{
                Socket socket;try{socket=channel.listener.accept();}catch(SocketTimeoutException waiting){continue;}
                synchronized(channel){if(stopping.get() || channel.connection!=null){socket.close();continue;}connection=new Connection(socket);channel.connection=connection;channel.status=Status.AUTHENTICATING;channel.reason=null;}
                Connection current=connection;
                GatewayHandshake.ViewerContext verified=ViewerChallengeHandshake.accept(current.frames,channel.client,channel.gateway,channel.key,authMilliseconds,stopping::get);
                require(verified.sessionId.equals(channel.viewer.session) && verified.viewerId.equals(channel.viewer.viewer),"COORDINATOR_AUTH_CONTEXT");
                synchronized(channel){require(!stopping.get() && channel.connection==current,"COORDINATOR_CLOSED");current.active=true;channel.status=Status.CONNECTED;channel.pending=channel.latest;channel.notifyAll();}
                if(channel.extensionAllowed)extensionConnected(channel,current);
                workers.execute(()->read(channel,current));workers.execute(()->write(channel,current));
            }catch(IOException | RuntimeException failure){if(connection!=null)disconnect(channel,connection,connection.active?"CHANNEL_FAILED":"AUTH_FAILED");if(stopping.get())return;}
        }
    }
    private void read(Channel channel,Connection connection){
        try{while(!stopping.get() && connection.active){
            String incoming=connection.frames.readWhenAvailable(5000,()->stopping.get() || !connection.active);
            if(incoming==null){disconnect(channel,connection,"PEER_CLOSED");return;}
            if(!channel.extensionAllowed){disconnect(channel,connection,"READ_ONLY_TRAFFIC");return;}
            if(incoming.length()>ViewerChannelExtension.MAX_BYTES || incoming.getBytes(StandardCharsets.UTF_8).length>ViewerChannelExtension.MAX_BYTES){disconnect(channel,connection,"EXTENSION_SIZE");return;}
            if(channel.incoming.incrementAndGet()>32){channel.incoming.decrementAndGet();disconnect(channel,connection,"EXTENSION_INPUT_OVERFLOW");return;}
            try{owner.execute(()->{try{
                if(stopping.get())return;synchronized(channel){if(channel.connection!=connection || !connection.active)return;}
                extension.receive(channel.viewer.seat,incoming);
            }catch(Exception failure){disconnect(channel,connection,"EXTENSION_REJECTED");}finally{channel.incoming.decrementAndGet();}});}
            catch(RejectedExecutionException failure){channel.incoming.decrementAndGet();disconnect(channel,connection,"OWNER_CLOSED");return;}
        }}catch(IOException failure){disconnect(channel,connection,"PEER_CLOSED");}
    }
    private void write(Channel channel,Connection connection){
        try{while(!stopping.get()){
            String pending;long revision;boolean gameplay;
            synchronized(channel){while((channel.extensionAllowed && !channel.extensionReady || channel.pending==null && channel.control==null && channel.organization==null && channel.receipts.isEmpty()) && channel.connection==connection && connection.active && !stopping.get())channel.wait(100);
                if(channel.connection!=connection || !connection.active || stopping.get())return;
                revision=channel.revision;gameplay=false;
                if(channel.control!=null){pending=channel.control;channel.control=null;}
                else if(channel.pending!=null){pending=channel.pending;channel.pending=null;gameplay=true;}
                else if(!channel.receipts.isEmpty())pending=channel.receipts.removeFirst();
                else{pending=channel.organization;channel.organization=null;}
            }
            connection.frames.write(pending,writeMilliseconds,()->stopping.get() || !connection.active);
            synchronized(channel){if(gameplay && channel.connection==connection)channel.sent=Math.max(channel.sent,revision);}
        }}catch(InterruptedException interrupted){Thread.currentThread().interrupt();}catch(IOException failure){disconnect(channel,connection,"WRITE_FAILED");}
    }
    private void disconnect(Channel channel,Connection connection,String reason){
        boolean wasActive=connection.active;connection.active=false;try{connection.frames.close();}catch(IOException ignored){}
        boolean notify=false;
        synchronized(channel){if(channel.connection==connection){channel.connection=null;channel.status=stopping.get()?Status.CLOSED:Status.DISCONNECTED;channel.reason=reason;channel.pending=null;channel.control=channel.organization=null;channel.extensionReady=false;channel.receipts.clear();notify=wasActive && channel.extensionAllowed && !stopping.get();channel.notifyAll();}}
        if(notify)try{owner.execute(()->{if(stopping.get())return;synchronized(channel){if(channel.connection!=null)return;}extension.disconnected(channel.viewer.seat);});}catch(RejectedExecutionException ignored){}
    }
    /** Trusted preprojected fixture port, not a client-facing publication endpoint. */
    void publishSnapshots(Map<String,JsonObject> snapshots) throws Exception {
        Map<String,JsonObject> copy=new HashMap<>();for(Map.Entry<String,JsonObject> entry:snapshots.entrySet())copy.put(entry.getKey(),entry.getValue().deepCopy());
        invoke(()->{publishOwned(copy);return null;});
    }
    private void publishOwned(Map<String,JsonObject> snapshots) throws Exception {
        require(started && snapshots.keySet().equals(channels.keySet()),"COORDINATOR_PUBLICATION");Map<String,String> payloads=new HashMap<>();Map<String,Long> revisions=new HashMap<>();
        // Validate the entire batch before any channel becomes eligible to send it.
        for(Channel channel:channels.values()){
            long minimum; synchronized(channel){require(channel.revision<Long.MAX_VALUE,"COORDINATOR_REVISION_EXHAUSTED");minimum=channel.revision<0?0:channel.revision+1;}
            String raw=snapshots.get(channel.viewer.seat).toString();JsonObject envelope=ReceiveMessages.parse(raw,channel.viewer.session,channel.viewer.viewer,minimum,fixtureMode);
            require(envelope.get("message_type").getAsString().equals("snapshot"),"COORDINATOR_READ_ONLY");JsonObject snapshot=envelope.getAsJsonObject("body").getAsJsonObject("snapshot");
            require(snapshot.get("decision").isJsonNull() && snapshot.getAsJsonArray("actions").size()==0,"COORDINATOR_READ_ONLY");payloads.put(channel.viewer.seat,raw);revisions.put(channel.viewer.seat,snapshot.get("revision").getAsLong());
        }
        for(Channel channel:channels.values())synchronized(channel){channel.latest=payloads.get(channel.viewer.seat);channel.revision=revisions.get(channel.viewer.seat);channel.pending=channel.latest;channel.notifyAll();}
    }
    public void publishNative(Map<String,Observation> observations) throws Exception {publishNative(observations,null);}
    public void publishNative(Map<String,Observation> observations,PublicationHook hook) throws Exception {
        Map<String,Observation> copy=new HashMap<>(observations);
        invoke(()->{
            require(copy.keySet().equals(channels.keySet()),"COORDINATOR_PUBLICATION");Long cycle=null;Map<String,JsonObject> snapshots=new HashMap<>();Map<String,ProjectedObservation> projected=new HashMap<>();
            for(Channel channel:channels.values()){
                Observation observation=copy.get(channel.viewer.seat);require(observation!=null && nativeGame.equals(observation.state.get("game_id").getAsString()) && channel.viewer.nativePlayer.equals(observation.state.get("viewer").getAsString()),"COORDINATOR_NATIVE_CONTEXT");
                long next=observation.state.get("cycle").getAsLong();require(cycle==null || cycle==next,"COORDINATOR_NATIVE_BASIS");cycle=next;
                ManaforgeOpeningProjection.ObserverResult result=channel.projection.projectObserverWithBindings(observation.state,observation.prompt);
                projected.put(channel.viewer.seat,new ProjectedObservation(channel.viewer,next,result));
                JsonObject snapshot=result.snapshot(),envelope=new JsonObject(),body=new JsonObject();
                envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","match-view-"+snapshot.get("revision").getAsLong());body.addProperty("fixture_only",fixtureMode);body.add("snapshot",snapshot);envelope.add("body",body);snapshots.put(channel.viewer.seat,envelope);
            }
            PreparedPublication prepared=hook==null?null:Objects.requireNonNull(hook.prepare(Collections.unmodifiableMap(projected)));
            publishOwned(snapshots);if(prepared!=null)prepared.commit();return null;
        });
    }
    public ConnectionStatus status(String seat){Channel channel=channels.get(seat);if(channel==null)throw new IllegalArgumentException("COORDINATOR_SEAT");synchronized(channel){return new ConnectionStatus(channel.status,channel.reason,channel.sent,channel.pending==null?0:1,channel.organization==null?0:1,channel.receipts.size(),channel.incoming.get());}}
    private void requestStop(){if(stopping.compareAndSet(false,true))owner.execute(this::stopOwned);}
    private void stopOwned(){
        boolean failed=false;
        try{
            for(Channel channel:channels.values()){
                try{channel.listener.close();}catch(IOException failure){failed=true;}
                synchronized(channel){if(channel.connection!=null)disconnect(channel,channel.connection,"OWNER_CLOSED");channel.status=Status.CLOSED;channel.pending=channel.latest=channel.control=channel.organization=null;channel.extensionReady=false;channel.receipts.clear();channel.projection.invalidateDecision();channel.projection=null;Arrays.fill(channel.key,(byte)0);channel.notifyAll();}
            }
            workers.shutdownNow();try{if(!workers.awaitTermination(5,TimeUnit.SECONDS))failed=true;}catch(InterruptedException interrupted){Thread.currentThread().interrupt();failed=true;}
        }finally{
            if(extension!=null){try{extension.close();}catch(Exception failure){failed=true;}extension=null;}
            try{ownedMatch.close();}catch(Exception failure){failed=true;}
            if(failed)closed.completeExceptionally(new IOException("COORDINATOR_CLEANUP_FAILED"));else closed.complete(null);owner.shutdown();
        }
    }
    public boolean isClosed(){return closed.isDone();}
    public void close() throws Exception {requestStop();if(Thread.currentThread()!=ownerThread.get()){try{closed.get(10,TimeUnit.SECONDS);}catch(ExecutionException failure){throw new IOException("COORDINATOR_CLEANUP_FAILED");}require(owner.awaitTermination(5,TimeUnit.SECONDS),"COORDINATOR_OWNER_CLEANUP_FAILED");}}
}

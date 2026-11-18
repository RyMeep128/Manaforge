import java.io.IOException;
import java.util.*;
import com.google.gson.*;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Host-owned layout bridge. Organization commands never enter the native rules transport. */
final class NativeOrganizationBridge implements ViewerChannelExtension {
    /** Reuses trusted reads only. Never performs IO or accepts client-supplied metadata. */
    static final class MetadataCache {
        private JsonObject view,metadata;
        static String[] includeBattlefield(JsonObject view,String... sources){
            Set<String> ids=new LinkedHashSet<>(Arrays.asList(sources));
            for(JsonElement seat:view.getAsJsonArray("players"))for(JsonElement card:seat.getAsJsonObject().getAsJsonArray("battlefield"))ids.add(card.getAsJsonObject().get("id").getAsString());
            return ids.size()<=256?ids.toArray(new String[0]):sources;
        }
        void observe(JsonObject view,JsonObject metadata){
            if(!new JsonPrimitive("ok").equals(metadata.get("status")) || !view.get("cycle").equals(metadata.get("cycle")))return;
            if(!complete(view,metadata.getAsJsonObject("objects")))return;
            this.view=new JsonObject();for(String key:new String[]{"game_id","viewer","cycle"})this.view.add(key,view.get(key).deepCopy());this.metadata=metadata.deepCopy();
        }
        private static boolean complete(JsonObject requested,JsonObject objects){
            for(JsonElement seat:requested.getAsJsonArray("players"))for(JsonElement card:seat.getAsJsonObject().getAsJsonArray("battlefield"))if(!objects.has(card.getAsJsonObject().get("id").getAsString()))return false;
            return true;
        }
        boolean matches(JsonObject requested){
            for(String key:new String[]{"game_id","viewer","cycle"})if(view==null || !Objects.equals(view.get(key),requested.get(key)))return false;
            return complete(requested,metadata.getAsJsonObject("objects"));
        }
        JsonObject objects(JsonObject requested) throws IOException {
            if(!matches(requested))throw new IOException("ORGANIZATION_BASIS_UNAVAILABLE");
            return metadata.getAsJsonObject("objects").deepCopy();
        }
    }
    private final Thread owner=Thread.currentThread();
    private final UUID game;private final Map<String,ManaforgeMatchCoordinator.Viewer> registrations;
    private final Map<UUID,String> actors=new HashMap<>();
    private final BattlefieldIdentityRegistry identities;private final OrganizationChannel channel;
    private long revision;private boolean closed;private final boolean version2;private final int version;private final Map<String,Long> gameplay=new HashMap<>();
    private final Map<String,InteractiveView> interactive=new TreeMap<>();
    private final Map<String,Map<String,String>> initialReferences=new TreeMap<>();
    private final Set<String> unavailable=new HashSet<>();
    private BattlefieldIdentityRegistry.Snapshot latestNative;
    private static final class InteractiveView {
        final BattlefieldIdentityRegistry.Snapshot nativeView;
        final ManaforgeOpeningProjection.ObserverResult projected;
        final Map<UUID,BattlefieldIdentityRegistry.Observation> objects=new HashMap<>();
        InteractiveView(BattlefieldIdentityRegistry.Snapshot nativeView,ManaforgeOpeningProjection.ObserverResult projected){this.nativeView=nativeView;this.projected=projected;for(BattlefieldIdentityRegistry.Observation object:nativeView.permanents)objects.put(object.nativeId,object);}
    }
    NativeOrganizationBridge(UUID game,Map<String,ManaforgeMatchCoordinator.Viewer> registrations,Sender sender) throws Exception {
        this(game,registrations,sender,false);
    }
    NativeOrganizationBridge(UUID game,Map<String,ManaforgeMatchCoordinator.Viewer> registrations,Sender sender,boolean version2) throws Exception {
        this(game,registrations,sender,version2?2:1);
    }
    NativeOrganizationBridge(UUID game,Map<String,ManaforgeMatchCoordinator.Viewer> registrations,Sender sender,int version) throws Exception {
        if(version<1 || version>4)throw new IllegalArgumentException("ORGANIZATION_VERSION");this.version=version;this.version2=version==2;this.game=Objects.requireNonNull(game);this.registrations=Collections.unmodifiableMap(new TreeMap<>(registrations));
        for(Map.Entry<String,ManaforgeMatchCoordinator.Viewer> entry:this.registrations.entrySet()){
            ManaforgeMatchCoordinator.Viewer viewer=entry.getValue();if(!entry.getKey().equals(viewer.seat) || actors.put(UUID.fromString(viewer.nativePlayer),viewer.seat)!=null)throw new IllegalArgumentException("NATIVE_ORGANIZATION_REGISTRATION");
        }
        identities=new BattlefieldIdentityRegistry(game);Map<String,OrganizationCodec.HostContext> contexts=new TreeMap<>();
        for(ManaforgeMatchCoordinator.Viewer viewer:this.registrations.values()){
            Map<String,String> refs=new TreeMap<>();for(String seat:this.registrations.keySet())refs.put(seat,seat.equals(viewer.seat)?viewer.viewer:UUID.randomUUID().toString());
            initialReferences.put(viewer.seat,Collections.unmodifiableMap(new TreeMap<>(refs)));
            OrganizationMessages.Context context=new OrganizationMessages.Context(identities.matchEpoch,viewer.viewer,0,Collections.emptyMap(),Collections.emptyMap(),Collections.emptyList(),refs.values());
            contexts.put(viewer.seat,new OrganizationCodec.HostContext(context,Collections.emptyMap(),refs));
        }
        try{channel=new OrganizationChannel((seat,kind,wire)->sender.send(seat,kind,version>=3?correlate(wire,gameplay.getOrDefault(seat,0L)):version2?OrganizationV2Messages.upgrade(wire,gameplay.getOrDefault(seat,0L)):wire),new Basis(identities.matchEpoch,this.registrations.keySet(),Collections.emptyList()),0,contexts,version>=3?version:1,()->0);}catch(Exception failure){identities.close();throw failure;}
    }
    private String correlate(String raw,long gameplay) throws IOException {
        com.google.gson.JsonObject wire=version==4?OrganizationV4Messages.parseContract(raw):OrganizationV3Messages.parseContract(raw);if(wire.get("message_type").getAsString().equals("organization_snapshot"))wire.getAsJsonObject("body").addProperty("gameplay_revision",gameplay);return wire.toString();
    }
    private void owned(){if(Thread.currentThread()!=owner || closed)throw new IllegalStateException("NATIVE_ORGANIZATION_OWNER");}
    private static void require(boolean value) throws IOException {if(!value)throw new IOException("NATIVE_ORGANIZATION_BASIS");}
    void unavailable(String seat){owned();unavailable.add(seat);}
    /** Interactive viewers advance independently. Share one reducer while retaining each
     * recipient's own gameplay revision and currently admitted public references. */
    void observeInteractive(String seat,BattlefieldIdentityRegistry.Snapshot nativeView,ManaforgeOpeningProjection.ObserverResult projected) throws Exception {
        owned();require(version==4 && registrations.containsKey(seat) && revision<Long.MAX_VALUE);
        ManaforgeMatchCoordinator.Viewer registration=registrations.get(seat);
        JsonObject snapshot=projected.snapshot();
        require(game.equals(nativeView.game) && nativeView.viewer.toString().equals(registration.nativePlayer)
            && nativeView.seats.equals(actors.keySet()) && snapshot.get("session_id").getAsString().equals(registration.session)
            && snapshot.get("viewer_id").getAsString().equals(registration.viewer) && snapshot.get("status").getAsString().equals("active"));
        InteractiveView previous=interactive.get(seat);
        require(previous==null || snapshot.get("revision").getAsLong()>previous.projected.snapshot().get("revision").getAsLong());
        Map<String,InteractiveView> nextViews=new TreeMap<>(interactive);nextViews.put(seat,new InteractiveView(nativeView,projected));
        BattlefieldIdentityRegistry.Snapshot current=latestNative==null || nativeView.cycle>latestNative.cycle?nativeView:latestNative;
        BattlefieldIdentityRegistry.Prepared identity=identities.prepare();long nextRevision=revision+1;
        Map<UUID,BattlefieldIdentityRegistry.Observation> currentObjects=new HashMap<>();
        for(BattlefieldIdentityRegistry.Observation object:current.permanents){require(actors.containsKey(object.controller));currentObjects.put(object.nativeId,object);}
        Map<String,List<BattlefieldIdentityRegistry.Member>> members=new TreeMap<>();
        Map<String,Map<UUID,String>> admissions=new TreeMap<>();
        for(Map.Entry<String,InteractiveView> entry:nextViews.entrySet()){
            InteractiveView view=entry.getValue();Map<UUID,String> admitted=new HashMap<>();
            for(Map.Entry<UUID,String> item:view.nativeView.admitted.entrySet()){
                BattlefieldIdentityRegistry.Observation now=currentObjects.get(item.getKey()),before=view.objects.get(item.getKey());
                if(now!=null && before!=null && now.eligible && before.eligible && now.generation==before.generation && now.controller.equals(before.controller))admitted.put(item.getKey(),item.getValue());
            }
            admissions.put(entry.getKey(),admitted);
            members.put(entry.getKey(),identity.candidate.project(new BattlefieldIdentityRegistry.Snapshot(game,view.nativeView.viewer,current.cycle,current.seats,current.permanents,admitted)));
        }
        List<Member> basisMembers=new ArrayList<>();
        for(BattlefieldIdentityRegistry.Observation object:current.permanents)basisMembers.add(new Member(identity.candidate.incarnation(object.nativeId),actors.get(object.controller),object.eligible));
        Basis basis=new Basis(identities.matchEpoch,registrations.keySet(),basisMembers);
        Map<String,OrganizationCodec.HostContext> contexts=new TreeMap<>();Map<String,Long> nextGameplay=new HashMap<>();
        for(ManaforgeMatchCoordinator.Viewer recipient:registrations.values()){
            InteractiveView view=nextViews.get(recipient.seat);Map<String,String> refs=new TreeMap<>(),objects=new TreeMap<>(),owners=new TreeMap<>();Map<String,OrganizationCodec.Binding> bindings=new TreeMap<>();
            if(view==null){refs.putAll(initialReferences.get(recipient.seat));nextGameplay.put(recipient.seat,0L);}
            else{
                for(Map.Entry<UUID,String> actor:actors.entrySet()){String reference=view.projected.seats.get(actor.getKey().toString());require(reference!=null);refs.put(actor.getValue(),reference);}
                Map<String,UUID> nativeByReference=new HashMap<>();for(Map.Entry<UUID,String> item:admissions.get(recipient.seat).entrySet())nativeByReference.put(item.getValue(),item.getKey());
                for(BattlefieldIdentityRegistry.Member member:members.get(recipient.seat)){
                    UUID nativeId=nativeByReference.get(member.objectReference);BattlefieldIdentityRegistry.Observation object=currentObjects.get(nativeId);require(object!=null);
                    String actor=actors.get(object.controller);objects.put(member.handle,member.objectReference);owners.put(member.handle,refs.get(actor));bindings.put(member.handle,new OrganizationCodec.Binding(identity.candidate.incarnation(nativeId),actor));
                }
                nextGameplay.put(recipient.seat,view.projected.snapshot().get("revision").getAsLong());
            }
            OrganizationMessages.Context wire=new OrganizationMessages.Context(identities.matchEpoch,recipient.viewer,nextRevision,objects,owners,objects.values(),refs.values());
            contexts.put(recipient.seat,new OrganizationCodec.HostContext(wire,bindings,refs));
        }
        OrganizationChannel.PreparedBasis organization=channel.prepareBasis(basis,nextRevision,contexts);
        identity.commit();interactive.clear();interactive.putAll(nextViews);latestNative=current;gameplay.clear();gameplay.putAll(nextGameplay);revision=nextRevision;unavailable.remove(seat);organization.commit();
    }
    ManaforgeMatchCoordinator.PublicationHook publication(Map<String,BattlefieldIdentityRegistry.Snapshot> snapshots){
        Map<String,BattlefieldIdentityRegistry.Snapshot> copy=Collections.unmodifiableMap(new TreeMap<>(snapshots));return projected->prepare(copy,projected);
    }
    private ManaforgeMatchCoordinator.PreparedPublication prepare(Map<String,BattlefieldIdentityRegistry.Snapshot> snapshots,Map<String,ManaforgeMatchCoordinator.ProjectedObservation> projected) throws Exception {
        owned();require(snapshots.keySet().equals(registrations.keySet()) && projected.keySet().equals(registrations.keySet()) && revision<Long.MAX_VALUE);
        BattlefieldIdentityRegistry.Prepared identity=identities.prepare();long nextRevision=revision+1;
        Map<String,List<BattlefieldIdentityRegistry.Member>> members=new TreeMap<>();
        for(String seat:registrations.keySet()){
            BattlefieldIdentityRegistry.Snapshot nativeView=snapshots.get(seat);ManaforgeMatchCoordinator.ProjectedObservation view=projected.get(seat);ManaforgeMatchCoordinator.Viewer registration=registrations.get(seat);
            require(nativeView!=null && view!=null && game.equals(nativeView.game) && nativeView.viewer.toString().equals(registration.nativePlayer) && view.viewer==registration && nativeView.cycle==view.cycle && nativeView.seats.equals(actors.keySet()));
            require(view.seats.keySet().equals(stringIds(actors.keySet())) && view.objects.keySet().equals(stringIds(nativeView.admitted.keySet())));
            Map<UUID,String> admitted=new HashMap<>();for(Map.Entry<String,String> object:view.objects.entrySet())admitted.put(UUID.fromString(object.getKey()),object.getValue());
            BattlefieldIdentityRegistry.Snapshot mapped=new BattlefieldIdentityRegistry.Snapshot(game,nativeView.viewer,nativeView.cycle,nativeView.seats,nativeView.permanents,admitted);
            members.put(seat,identity.candidate.project(mapped));
        }
        BattlefieldIdentityRegistry.Snapshot first=snapshots.values().iterator().next();List<Member> basisMembers=new ArrayList<>();
        for(BattlefieldIdentityRegistry.Observation object:first.permanents)basisMembers.add(new Member(identity.candidate.incarnation(object.nativeId),actors.get(object.controller),object.eligible));
        Basis basis=new Basis(identities.matchEpoch,registrations.keySet(),basisMembers);Map<String,OrganizationCodec.HostContext> contexts=new TreeMap<>();
        for(String seat:registrations.keySet()){
            ManaforgeMatchCoordinator.ProjectedObservation view=projected.get(seat);Map<String,String> refs=new TreeMap<>(),objects=new TreeMap<>(),seats=new TreeMap<>();Map<String,OrganizationCodec.Binding> bindings=new TreeMap<>();
            for(Map.Entry<UUID,String> actor:actors.entrySet())refs.put(actor.getValue(),view.seats.get(actor.getKey().toString()));
            Map<String,BattlefieldIdentityRegistry.Member> byReference=new HashMap<>();for(BattlefieldIdentityRegistry.Member member:members.get(seat))byReference.put(member.objectReference,member);
            for(BattlefieldIdentityRegistry.Observation object:first.permanents){
                String reference=view.objects.get(object.nativeId.toString());if(reference==null || !object.eligible)continue;BattlefieldIdentityRegistry.Member member=byReference.get(reference);require(member!=null);
                String actor=actors.get(object.controller);objects.put(member.handle,reference);seats.put(member.handle,refs.get(actor));bindings.put(member.handle,new OrganizationCodec.Binding(identity.candidate.incarnation(object.nativeId),actor));
            }
            OrganizationMessages.Context wire=new OrganizationMessages.Context(identities.matchEpoch,view.viewer.viewer,nextRevision,objects,seats,objects.values(),refs.values());contexts.put(seat,new OrganizationCodec.HostContext(wire,bindings,refs));
        }
        Map<String,Long> nextGameplay=new HashMap<>();for(String seat:registrations.keySet())nextGameplay.put(seat,projected.get(seat).snapshot().get("revision").getAsLong());
        if(version>=2){BattlefieldOrganizationSession.Snapshot before=channel.snapshot();State candidate=BattlefieldOrganizationService.reconcile(before.state,basis);long next=before.organizationRevision+(candidate.seats.equals(before.state.seats)?0:1);for(String seat:registrations.keySet()){if(version>=3)OrganizationCodec.snapshotState("preflight",candidate,next,nextRevision,contexts.get(seat),version,nextGameplay.get(seat));else OrganizationV2Messages.upgrade(OrganizationCodec.snapshotState("preflight",candidate,next,nextRevision,contexts.get(seat)),nextGameplay.get(seat));}}
        OrganizationChannel.PreparedBasis organization=channel.prepareBasis(basis,nextRevision,contexts);
        return ()->{owned();require(revision+1==nextRevision);identity.commit();gameplay.clear();gameplay.putAll(nextGameplay);organization.commit();revision=nextRevision;};
    }
    private static Set<String> stringIds(Collection<UUID> ids){Set<String> result=new HashSet<>();for(UUID id:ids)result.add(id.toString());return result;}
    BattlefieldOrganizationSession.Snapshot snapshot(){return channel.snapshot();}
    public void connected(String seat) throws Exception {owned();channel.connected(seat);}
    public void receive(String seat,String raw) throws Exception {owned();if(version==4 && unavailable.contains(seat) && "organization_command".equals(WireEnvelope.parseObject(raw).get("message_type").getAsString())){channel.rejectUnready(seat,raw);return;}if(version2){com.google.gson.JsonObject message=OrganizationV2Messages.parseContract(raw);com.google.gson.JsonObject legacy=OrganizationV2Messages.legacy(message);if(message.get("message_type").getAsString().equals("organization_capabilities")){boolean found=false;for(com.google.gson.JsonElement version:message.getAsJsonObject("body").getAsJsonArray("versions"))found|=version.getAsInt()==2;require(found);com.google.gson.JsonArray versions=new com.google.gson.JsonArray();versions.add(1);legacy.getAsJsonObject("body").add("versions",versions);}raw=legacy.toString();}channel.receive(seat,raw);}
    public void disconnected(String seat){owned();channel.disconnected(seat);}
    public void close(){owned();try{channel.close();}finally{identities.close();closed=true;}}
}

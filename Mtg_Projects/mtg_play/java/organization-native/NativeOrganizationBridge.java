import java.io.IOException;
import java.util.*;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Explicitly installed host bridge. No production launcher or native response transport. */
final class NativeOrganizationBridge implements ViewerChannelExtension {
    private final Thread owner=Thread.currentThread();
    private final UUID game;private final Map<String,ManaforgeMatchCoordinator.Viewer> registrations;
    private final Map<UUID,String> actors=new HashMap<>();
    private final BattlefieldIdentityRegistry identities;private final OrganizationChannel channel;
    private long revision;private boolean closed;
    NativeOrganizationBridge(UUID game,Map<String,ManaforgeMatchCoordinator.Viewer> registrations,Sender sender) throws Exception {
        this.game=Objects.requireNonNull(game);this.registrations=Collections.unmodifiableMap(new TreeMap<>(registrations));
        for(Map.Entry<String,ManaforgeMatchCoordinator.Viewer> entry:this.registrations.entrySet()){
            ManaforgeMatchCoordinator.Viewer viewer=entry.getValue();if(!entry.getKey().equals(viewer.seat) || actors.put(UUID.fromString(viewer.nativePlayer),viewer.seat)!=null)throw new IllegalArgumentException("NATIVE_ORGANIZATION_REGISTRATION");
        }
        identities=new BattlefieldIdentityRegistry(game);Map<String,OrganizationCodec.HostContext> contexts=new TreeMap<>();
        for(ManaforgeMatchCoordinator.Viewer viewer:this.registrations.values()){
            Map<String,String> refs=new TreeMap<>();for(String seat:this.registrations.keySet())refs.put(seat,seat.equals(viewer.seat)?viewer.viewer:UUID.randomUUID().toString());
            OrganizationMessages.Context context=new OrganizationMessages.Context(identities.matchEpoch,viewer.viewer,0,Collections.emptyMap(),Collections.emptyMap(),Collections.emptyList(),refs.values());
            contexts.put(viewer.seat,new OrganizationCodec.HostContext(context,Collections.emptyMap(),refs));
        }
        try{channel=new OrganizationChannel(sender,new Basis(identities.matchEpoch,this.registrations.keySet(),Collections.emptyList()),0,contexts);}catch(Exception failure){identities.close();throw failure;}
    }
    private void owned(){if(Thread.currentThread()!=owner || closed)throw new IllegalStateException("NATIVE_ORGANIZATION_OWNER");}
    private static void require(boolean value) throws IOException {if(!value)throw new IOException("NATIVE_ORGANIZATION_BASIS");}
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
        OrganizationChannel.PreparedBasis organization=channel.prepareBasis(basis,nextRevision,contexts);
        return ()->{owned();require(revision+1==nextRevision);identity.commit();organization.commit();revision=nextRevision;};
    }
    private static Set<String> stringIds(Collection<UUID> ids){Set<String> result=new HashSet<>();for(UUID id:ids)result.add(id.toString());return result;}
    BattlefieldOrganizationSession.Snapshot snapshot(){return channel.snapshot();}
    public void connected(String seat) throws Exception {owned();channel.connected(seat);}
    public void receive(String seat,String raw) throws Exception {owned();channel.receive(seat,raw);}
    public void disconnected(String seat){owned();channel.disconnected(seat);}
    public void close(){owned();try{channel.close();}finally{identities.close();closed=true;}}
}

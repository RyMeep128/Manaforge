import com.google.gson.*;
import java.io.IOException;
import java.util.*;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Normal game's single authenticated recipient; AI seats are roster entries, not sockets. */
final class NormalOrganizationEndpoint implements OrganizationEndpoint {
    interface Metadata {JsonObject read(JsonObject state,String... ids) throws Exception;}
    interface Writer {void write(String packet) throws Exception;}
    private final ManaforgeOpeningProjection projection;private final String actor,viewer;private final Metadata metadata;private final Writer writer;
    private final BattlefieldIdentityRegistry identities;private CorrelatedOrganizationChannel channel;private final int version;private long revision,gameplay=-1;private boolean negotiated,available;
    NormalOrganizationEndpoint(ManaforgeOpeningProjection projection,String game,String actor,String viewer,Metadata metadata,Writer writer){this(projection,game,actor,viewer,metadata,writer,2);}
    NormalOrganizationEndpoint(ManaforgeOpeningProjection projection,String game,String actor,String viewer,Metadata metadata,Writer writer,int version){if(version!=2 && version!=3)throw new IllegalArgumentException("ORGANIZATION_VERSION");this.version=version;this.projection=projection;this.actor=actor;this.viewer=viewer;this.metadata=metadata;this.writer=writer;identities=new BattlefieldIdentityRegistry(UUID.fromString(game));}
    public void observe(String packet) throws Exception {
        JsonObject envelope=WireEnvelope.parseObject(packet);String type=envelope.get("message_type").getAsString();if(!type.equals("snapshot") && !type.equals("result"))return;
        JsonObject snapshot=envelope.getAsJsonObject("body").getAsJsonObject("snapshot");long next=snapshot.get("revision").getAsLong();if(next<=gameplay)return;available=false;
        ManaforgeOpeningProjection.ObserverResult bindings=projection.organizationBindings();JsonObject raw=projection.organizationRaw();if(bindings==null || raw==null || bindings.snapshot().get("revision").getAsLong()!=next || !snapshot.get("status").getAsString().equals("active"))return;
        // Each bounded request is verified by the owned server at the exact paused cycle.
        List<String> ids=new ArrayList<>();Set<UUID> roster=new HashSet<>();Map<String,Boolean> eligible=new HashMap<>();
        for(JsonElement seat:raw.getAsJsonArray("players")){JsonObject row=seat.getAsJsonObject();roster.add(UUID.fromString(row.get("id").getAsString()));for(JsonElement item:row.getAsJsonArray("battlefield")){JsonObject card=item.getAsJsonObject();String id=card.get("id").getAsString();ids.add(id);eligible.put(id,bindings.objects.containsKey(id));}}
        if(ids.size()>1024)return;JsonObject objects=new JsonObject();
        for(int start=0;start<Math.max(1,ids.size());start+=256){JsonObject result=metadata.read(raw,ids.subList(start,Math.min(start+256,ids.size())).toArray(new String[0]));if(!new JsonPrimitive("ok").equals(result.get("status")) || !raw.get("cycle").equals(result.get("cycle")))return;for(Map.Entry<String,JsonElement> entry:result.getAsJsonObject("objects").entrySet())objects.add(entry.getKey(),entry.getValue());}
        List<BattlefieldIdentityRegistry.Observation> observations=new ArrayList<>();Map<UUID,String> admitted=new HashMap<>();
        for(String id:ids){JsonObject object=objects.getAsJsonObject(id);if(object==null || !object.has("controller") || object.get("controller").isJsonNull())return;observations.add(new BattlefieldIdentityRegistry.Observation(UUID.fromString(id),object.get("incarnation").getAsInt(),UUID.fromString(object.get("controller").getAsString()),eligible.get(id)));if(eligible.get(id))admitted.put(UUID.fromString(id),bindings.objects.get(id));}
        BattlefieldIdentityRegistry.Prepared prepared=identities.prepare();BattlefieldIdentityRegistry.Snapshot captured=new BattlefieldIdentityRegistry.Snapshot(UUID.fromString(raw.get("game_id").getAsString()),UUID.fromString(actor),raw.get("cycle").getAsInt(),roster,observations,admitted);
        List<BattlefieldIdentityRegistry.Member> members=prepared.candidate.project(captured);List<Member> basisMembers=new ArrayList<>();for(BattlefieldIdentityRegistry.Observation object:observations)basisMembers.add(new Member(prepared.candidate.incarnation(object.nativeId),object.controller.toString(),object.eligible));
        List<String> seats=new ArrayList<>();for(UUID seat:roster)seats.add(seat.toString());Basis basis=new Basis(identities.matchEpoch,seats,basisMembers);Map<String,String> refs=new HashMap<>(),handles=new HashMap<>(),owners=new HashMap<>();Map<String,OrganizationCodec.Binding> resolved=new HashMap<>();
        refs.putAll(bindings.seats);Map<String,String> nativeByReference=new HashMap<>();for(Map.Entry<String,String> entry:bindings.objects.entrySet())nativeByReference.put(entry.getValue(),entry.getKey());
        for(BattlefieldIdentityRegistry.Member member:members){String id=nativeByReference.get(member.objectReference);BattlefieldIdentityRegistry.Observation object=observations.stream().filter(o->o.nativeId.toString().equals(id)).findFirst().get();String owner=object.controller.toString();handles.put(member.handle,member.objectReference);owners.put(member.handle,refs.get(owner));resolved.put(member.handle,new OrganizationCodec.Binding(prepared.candidate.incarnation(object.nativeId),owner));}
        OrganizationMessages.Context context=new OrganizationMessages.Context(identities.matchEpoch,viewer,revision+1,handles,owners,handles.values(),refs.values());Map<String,OrganizationCodec.HostContext> contexts=Collections.singletonMap(actor,new OrganizationCodec.HostContext(context,resolved,refs));
        boolean first=channel==null;
        if(channel==null){ViewerChannelExtension.Sender sender=(seat,kind,wire)->{if(negotiated || kind==ViewerChannelExtension.Kind.CONTROL)writer.write(wire);return true;};channel=version==3?new OrganizationV3Channel(sender,basis,revision+1,next,contexts):new OrganizationV2Channel(sender,basis,revision+1,next,contexts);}else channel.update(basis,revision+1,next,contexts);
        prepared.commit();revision++;gameplay=next;available=true;if(first)channel.connected(actor);
    }
    public boolean receive(String raw) throws Exception {
        JsonObject packet=WireEnvelope.parseObject(raw);String type=packet.has("message_type")?packet.get("message_type").getAsString():"";if(!type.startsWith("organization_"))return false;
        if(version==3)OrganizationV3Messages.parseContract(raw);else OrganizationV2Messages.parseContract(raw);if(channel==null || !available){if(type.equals("organization_command") && channel!=null && negotiated)channel.rejectUnready(actor,raw);return true;}
        if(!negotiated){if(!type.equals("organization_capabilities"))throw new IOException("ORGANIZATION_NOT_NEGOTIATED");negotiated=true;}channel.receive(actor,raw);return true;
    }
    public void close(){try{if(channel!=null)channel.close();}finally{identities.close();}}
}

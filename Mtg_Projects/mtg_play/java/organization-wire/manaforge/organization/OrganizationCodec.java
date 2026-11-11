package manaforge.organization;

import com.google.gson.*;
import java.io.IOException;
import java.util.*;
import manaforge.protocol.OrganizationMessages;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Explicit host-to-viewer translation. Host State is never a serialized DTO. */
public final class OrganizationCodec {
    private OrganizationCodec(){}
    public static final class Binding {
        public final String incarnation,hostSeat;
        public Binding(String incarnation,String hostSeat){this.incarnation=Objects.requireNonNull(incarnation);this.hostSeat=Objects.requireNonNull(hostSeat);}
    }
    public static final class HostContext {
        public final OrganizationMessages.Context viewer;
        public final Map<String,Binding> bindings;
        public final Map<String,String> seatReferences;
        public HostContext(OrganizationMessages.Context viewer,Map<String,Binding> bindings,Map<String,String> seatReferences){
            if(!bindings.keySet().equals(viewer.objects.keySet()) || !new HashSet<>(seatReferences.values()).equals(viewer.visibleSeats) || new HashSet<>(seatReferences.values()).size()!=seatReferences.size())throw new IllegalArgumentException("ORGANIZATION_CONTEXT");
            Set<String> incarnations=new HashSet<>();
            for(Map.Entry<String,Binding> entry:bindings.entrySet()){
                Binding b=entry.getValue();if(b==null || b.incarnation.isEmpty() || b.incarnation.equals(entry.getKey()) || b.incarnation.equals(viewer.objects.get(entry.getKey())) || !incarnations.add(b.incarnation) || !Objects.equals(seatReferences.get(b.hostSeat),viewer.seats.get(entry.getKey())))throw new IllegalArgumentException("ORGANIZATION_CONTEXT");
            }
            if(!Collections.disjoint(incarnations,viewer.objects.keySet()) || !Collections.disjoint(incarnations,viewer.objects.values()) || !Collections.disjoint(incarnations,seatReferences.values()))throw new IllegalArgumentException("ORGANIZATION_CONTEXT");
            this.viewer=viewer;this.bindings=Collections.unmodifiableMap(new HashMap<>(bindings));this.seatReferences=Collections.unmodifiableMap(new TreeMap<>(seatReferences));
        }
    }
    public static final class DecodedCommand {
        public final String commandId;
        public final long expectedOrganizationRevision,basisRevision;
        public final Operation operation;
        private DecodedCommand(JsonObject body,Operation operation){commandId=body.get("command_id").getAsString();expectedOrganizationRevision=body.get("expected_organization_revision").getAsLong();basisRevision=body.get("basis_revision").getAsLong();this.operation=operation;}
    }
    private static void require(boolean value) throws IOException {if(!value)throw new IOException("ORGANIZATION_CONTEXT");}
    private static String nullable(JsonObject object,String name){return object.get(name).isJsonNull()?null:object.get(name).getAsString();}
    public static DecodedCommand command(String raw,HostContext context,String trustedActorSeat) throws IOException {
        JsonObject message=OrganizationMessages.parse(raw,context.viewer);require(message.get("message_type").getAsString().equals("organization_command") && trustedActorSeat!=null && context.seatReferences.containsKey(trustedActorSeat));
        JsonObject body=message.getAsJsonObject("body"),op=body.getAsJsonObject("operation");String group=nullable(op,"group_id");Operation operation;
        switch(op.get("kind").getAsString()){
            case "create":operation=Operation.create(group,nullable(op,"name"),op.get("x").getAsLong()/1000000.0,op.get("y").getAsLong()/1000000.0);break;
            case "rename":operation=Operation.rename(group,nullable(op,"name"));break;
            case "delete":operation=Operation.delete(group);break;
            case "position":operation=Operation.position(group,op.get("x").getAsLong()/1000000.0,op.get("y").getAsLong()/1000000.0);break;
            case "reorder":operation=Operation.reorder(group,op.get("index").getAsInt());break;
            case "move":
                List<String> incarnations=new ArrayList<>();for(JsonElement token:op.getAsJsonArray("members")){Binding binding=context.bindings.get(token.getAsString());require(binding!=null && binding.hostSeat.equals(trustedActorSeat));incarnations.add(binding.incarnation);}
                operation=Operation.move(incarnations,group,op.get("index").getAsInt());break;
            default:throw new IOException("ORGANIZATION_INVALID");
        }
        return new DecodedCommand(body,operation);
    }
    private static JsonObject envelope(String type,String messageId,JsonObject body){JsonObject message=new JsonObject();message.addProperty("wire_version",1);message.addProperty("organization_version",1);message.addProperty("message_type","organization_"+type);message.addProperty("message_id",messageId);message.add("body",body);return message;}
    private static JsonObject body(BattlefieldOrganizationSession.Snapshot snapshot){JsonObject body=new JsonObject();body.addProperty("match_epoch",snapshot.matchEpoch);body.addProperty("organization_revision",snapshot.organizationRevision);body.addProperty("basis_revision",snapshot.basisRevision);return body;}
    private static void basis(BattlefieldOrganizationSession.Snapshot snapshot,HostContext context) throws IOException {require(snapshot.matchEpoch.equals(context.viewer.matchEpoch) && snapshot.basisRevision==context.viewer.basisRevision);}
    public static String receipt(String messageId,String commandId,BattlefieldOrganizationSession.Result result,HostContext context) throws IOException {
        basis(result.snapshot,context);JsonObject body=body(result.snapshot);body.addProperty("command_id",commandId);body.addProperty("outcome",result.outcome==BattlefieldOrganizationSession.Outcome.APPLIED?"applied":"rejected");body.add("reason_code",result.reasonCode==null?JsonNull.INSTANCE:new JsonPrimitive(result.reasonCode));return OrganizationMessages.serialize(envelope("receipt",messageId,body),context.viewer);
    }
    public static String snapshot(String messageId,BattlefieldOrganizationSession.Snapshot snapshot,HostContext context) throws IOException {
        basis(snapshot,context);snapshot.state.validate();Map<String,String> handles=new HashMap<>();
        require(Collections.disjoint(snapshot.state.basis.members.keySet(),context.viewer.objects.keySet()) && Collections.disjoint(snapshot.state.basis.members.keySet(),context.viewer.objects.values()) && Collections.disjoint(snapshot.state.basis.members.keySet(),context.seatReferences.values()));
        for(Map.Entry<String,Binding> entry:context.bindings.entrySet()){
            Binding binding=entry.getValue();Member member=snapshot.state.basis.members.get(binding.incarnation);require(member!=null && member.controller.equals(binding.hostSeat));
            if(member.eligible)handles.put(binding.incarnation,entry.getKey());
        }
        JsonArray seats=new JsonArray(),mappings=new JsonArray();
        for(Map.Entry<String,String> seatRef:context.seatReferences.entrySet()){
            Seat state=snapshot.state.seats.get(seatRef.getKey());require(state!=null);JsonObject seat=new JsonObject();seat.addProperty("seat_id",seatRef.getValue());
            seat.add("root",members(state.root,handles,context,seatRef.getValue(),mappings));JsonArray groups=new JsonArray();
            for(Group group:state.groups){JsonObject entry=new JsonObject();entry.addProperty("group_id",group.id);entry.addProperty("name",group.name);entry.addProperty("x",Math.round(group.x*1000000));entry.addProperty("y",Math.round(group.y*1000000));entry.add("members",members(group.members,handles,context,seatRef.getValue(),mappings));groups.add(entry);}
            seat.add("groups",groups);seats.add(seat);
        }
        JsonObject body=body(snapshot);body.addProperty("viewer_id",context.viewer.viewerId);body.add("seats",seats);body.add("mappings",mappings);
        return OrganizationMessages.serialize(envelope("snapshot",messageId,body),context.viewer);
    }
    private static JsonArray members(List<String> members,Map<String,String> handles,HostContext context,String seat,JsonArray mappings){
        JsonArray result=new JsonArray();for(String incarnation:members){String handle=handles.get(incarnation);if(handle==null)continue;result.add(handle);JsonObject mapping=new JsonObject();mapping.addProperty("handle",handle);mapping.addProperty("object_reference",context.viewer.objects.get(handle));mapping.addProperty("seat_id",seat);mappings.add(mapping);}return result;
    }
}

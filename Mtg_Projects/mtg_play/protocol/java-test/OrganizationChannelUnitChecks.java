import com.google.gson.*;
import java.io.IOException;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Synthetic contexts only. Authentication is proved by the separate socket harness. */
public final class OrganizationChannelUnitChecks {
    static final class Packet {final String seat,raw;final ViewerChannelExtension.Kind kind;Packet(String seat,ViewerChannelExtension.Kind kind,String raw){this.seat=seat;this.kind=kind;this.raw=raw;}}
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static Basis basis(){return new Basis("match",Arrays.asList("a","b"),Arrays.asList(new Member("p1","a",true),new Member("p3","a",true),new Member("p2","b",true),new Member("SECRET-HIDDEN","a",false),new Member("SECRET-UNADMITTED","a",true)));}
    static Map<String,OrganizationCodec.HostContext> contexts(Basis basis,long revision){
        Map<String,OrganizationCodec.HostContext> result=new TreeMap<>();
        for(String viewer:Arrays.asList("a","b")){
            Map<String,String> references=new TreeMap<>(),objects=new TreeMap<>(),seats=new TreeMap<>();Map<String,OrganizationCodec.Binding> bindings=new TreeMap<>();
            references.put("a",viewer+"-seat-a");references.put("b",viewer+"-seat-b");
            for(Member member:basis.members.values())if(member.eligible && !member.incarnation.startsWith("SECRET")){
                String handle=handle(viewer,member.incarnation,revision);objects.put(handle,viewer+"-object-"+member.incarnation+"-"+revision);seats.put(handle,references.get(member.controller));bindings.put(handle,new OrganizationCodec.Binding(member.incarnation,member.controller));
            }
            OrganizationMessages.Context wire=new OrganizationMessages.Context("match","viewer-"+viewer,revision,objects,seats,objects.values(),references.values());result.put(viewer,new OrganizationCodec.HostContext(wire,bindings,references));
        }
        return result;
    }
    static String handle(String viewer,String member,long revision){return viewer+"-h-"+member+"-"+revision;}
    static String capabilities(){JsonObject message=header("capabilities","capabilities"),body=new JsonObject();JsonArray versions=new JsonArray();versions.add(1);body.add("versions",versions);message.add("body",body);return message.toString();}
    static JsonObject header(String kind,String id){JsonObject message=new JsonObject();message.addProperty("wire_version",1);message.addProperty("organization_version",1);message.addProperty("message_type","organization_"+kind);message.addProperty("message_id","packet-"+id);return message;}
    static String command(String id,long organization,long basis,Operation operation){
        JsonObject message=header("command",id),body=new JsonObject(),op=new JsonObject();body.addProperty("match_epoch","match");body.addProperty("command_id",id);body.addProperty("expected_organization_revision",organization);body.addProperty("basis_revision",basis);
        op.addProperty("kind",operation.kind.name().toLowerCase(Locale.ROOT));for(String field:new String[]{"group_id","name","x","y","index"})op.add(field,JsonNull.INSTANCE);JsonArray members=new JsonArray();op.add("members",members);
        if(operation.groupId!=null)op.addProperty("group_id",operation.groupId);
        switch(operation.kind){case CREATE:case POSITION:op.addProperty("x",Math.round(operation.x*1000000));op.addProperty("y",Math.round(operation.y*1000000));break;default:break;}
        if(operation.kind==Kind.CREATE || operation.kind==Kind.RENAME)op.addProperty("name",operation.name);
        if(operation.kind==Kind.MOVE || operation.kind==Kind.REORDER)op.addProperty("index",operation.index);
        for(String member:operation.members)members.add(member);body.add("operation",op);message.add("body",body);return message.toString();
    }
    static Packet receipt(List<Packet> packets){return packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.RECEIPT).findFirst().orElseThrow(()->new AssertionError("RECEIPT_MISSING"));}
    static String reason(Packet packet){JsonElement code=JsonParser.parseString(packet.raw).getAsJsonObject().getAsJsonObject("body").get("reason_code");return code.isJsonNull()?null:code.getAsString();}
    static void admission() throws Exception {
        List<Packet> packets=new ArrayList<>();Map<String,OrganizationCodec.HostContext> contexts=contexts(basis(),7);
        try(OrganizationChannel channel=new OrganizationChannel((seat,kind,raw)->{packets.add(new Packet(seat,kind,raw));return true;},basis(),7,contexts)){
            channel.connected("a");channel.connected("b");channel.receive("a",capabilities());channel.receive("b",capabilities());packets.clear();
            String create=command("create",0,7,Operation.create("g1","Mana Rocks",.2,.3));channel.receive("a",create);String original=receipt(packets).raw;
            check(reason(receipt(packets))==null && channel.snapshot().organizationRevision==1 && packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT).count()==2,"APPLY_AND_FANOUT");packets.clear();
            try{channel.updateBasis(basis(),8,contexts);throw new AssertionError("INVALID_CONTEXT_MUTATED_BASIS");}catch(IOException expected){}
            check(channel.snapshot().basisRevision==7 && channel.snapshot().organizationRevision==1,"PARTIAL_BASIS_COMMIT");
            channel.updateBasis(basis(),8,contexts(basis(),8));check(channel.snapshot().organizationRevision==1 && channel.snapshot().basisRevision==8,"BASIS_ONLY_UPDATE");packets.clear();
            JsonObject retry=JsonParser.parseString(create).getAsJsonObject();retry.addProperty("message_id","new-transport-id");channel.receive("a",retry.toString());
            check(packets.size()==1 && receipt(packets).raw.equals(original) && channel.snapshot().organizationRevision==1,"HISTORICAL_RETRY_APPLIED_TWICE");
            OrganizationMessages.parseReceipt(original,"match",Collections.singletonList("create"));
            try{OrganizationMessages.parse(original,contexts(basis(),8).get("a").viewer);throw new AssertionError("OLD_RECEIPT_ACCEPTED_AS_CURRENT_CONTEXT");}catch(IOException expected){}
            try{OrganizationMessages.parseReceipt(original,"match",Collections.singletonList("unknown"));throw new AssertionError("UNKNOWN_RECEIPT_ACCEPTED");}catch(IOException expected){}
            packets.clear();channel.receive("a",command("create",1,8,Operation.create("other","Conflict",0,0)));check(reason(receipt(packets)).equals("COMMAND_CONFLICT"),"CONFLICTING_RETRY");packets.clear();channel.receive("a",create);check(receipt(packets).raw.equals(original),"CONFLICT_OVERWROTE_LEDGER");
            List<String> codes=Arrays.asList("STALE_ORGANIZATION_REVISION","STALE_BASIS_REVISION","UNKNOWN_MEMBER_HANDLE","DUPLICATE_SELECTION","MEMBER_NOT_OWNED_OR_ELIGIBLE","GROUP_NOT_OWNED");
            List<String> commands=Arrays.asList(command("stale-org",0,8,Operation.delete("g1")),command("stale-basis",1,7,Operation.delete("g1")),command("unknown",1,8,Operation.move(Collections.singletonList("unknown"),"g1",0)),command("duplicates",1,8,Operation.move(Arrays.asList(handle("a","p1",8),handle("a","p1",8)),"g1",0)),command("foreign-member",1,8,Operation.move(Collections.singletonList(handle("a","p2",8)),"g1",0)),command("foreign-group",1,8,Operation.rename("g1","Stolen")));
            for(int i=0;i<commands.size();i++){packets.clear();channel.receive(i==5?"b":"a",commands.get(i));check(reason(receipt(packets)).equals(codes.get(i)) && channel.snapshot().organizationRevision==1,"ATOMIC_REJECTION_"+codes.get(i));check(packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT).count()==1,"REJECTION_BROADCAST_TO_OPPONENT");}
            packets.clear();JsonObject foreign=JsonParser.parseString(command("foreign-match",1,8,Operation.delete("g1"))).getAsJsonObject();foreign.getAsJsonObject("body").addProperty("match_epoch","foreign");channel.receive("a",foreign.toString());check(reason(receipt(packets)).equals("FOREIGN_MATCH"),"FOREIGN_MATCH");
            for(int i=2;i<=32;i++){packets.clear();channel.receive("a",command("group-"+i,channel.snapshot().organizationRevision,8,Operation.create("g"+i,"Group",0,0)));check(reason(receipt(packets))==null,"VALID_GROUP_LIMIT");}
            long before=channel.snapshot().organizationRevision;packets.clear();channel.receive("a",command("group-33",before,8,Operation.create("g33","Overflow",0,0)));check(reason(receipt(packets)).equals("ORGANIZATION_LIMIT_REACHED") && channel.snapshot().organizationRevision==before && channel.snapshot().state.seats.get("a").groups.size()==32,"PREFLIGHT_LIMIT_MUTATED_STATE");
        }
    }
    static void ledgerLimit() throws Exception {
        AtomicReference<Packet> last=new AtomicReference<>();
        try(OrganizationChannel channel=new OrganizationChannel((seat,kind,raw)->{if(kind==ViewerChannelExtension.Kind.RECEIPT)last.set(new Packet(seat,kind,raw));return true;},basis(),7,contexts(basis(),7))){
            channel.connected("a");channel.connected("b");channel.receive("a",capabilities());channel.receive("b",capabilities());
            String first=command("limit-0",0,7,Operation.create("g","G",0,0));channel.receive("a",first);String stored=last.get().raw;
            for(int i=1;i<OrganizationChannel.COMMAND_LIMIT;i++)channel.receive("a",command("limit-"+i,1,7,Operation.rename("g","G")));
            channel.receive("a",command("over-limit",1,7,Operation.rename("g","Changed")));check(reason(last.get()).equals("COMMAND_LIMIT_REACHED") && channel.snapshot().organizationRevision==1,"COMMAND_LIMIT_MUTATED_STATE");
            channel.receive("a",first);check(last.get().raw.equals(stored),"LEDGER_EVICTED_FIRST_RECORD");
            channel.receive("b",command("limit-0",1,7,Operation.create("b-group","Other",0,0)));check(reason(last.get())==null && channel.snapshot().organizationRevision==2,"LEDGER_NOT_SEAT_SCOPED");
        }
    }
    static void preparedBasis() throws Exception {
        List<Packet> packets=new ArrayList<>();
        try(OrganizationChannel channel=new OrganizationChannel((seat,kind,raw)->{packets.add(new Packet(seat,kind,raw));return true;},basis(),7,contexts(basis(),7))){
            channel.connected("a");channel.receive("a",capabilities());packets.clear();
            OrganizationChannel.PreparedBasis prepared=channel.prepareBasis(basis(),8,contexts(basis(),8));
            check(packets.isEmpty() && channel.snapshot().basisRevision==7,"PREPARE_PUBLISHED_OR_MUTATED");
            prepared.commit();check(channel.snapshot().basisRevision==8 && packets.size()==1,"PREPARED_BASIS_COMMIT");
            try{prepared.commit();throw new AssertionError("PREPARED_DOUBLE_COMMIT");}catch(IllegalStateException expected){}
            prepared=channel.prepareBasis(basis(),9,contexts(basis(),9));channel.receive("a",command("intervening",0,8,Operation.create("g","G",0,0)));
            try{prepared.commit();throw new AssertionError("PREPARED_STALE_COMMIT");}catch(IllegalStateException expected){}
            check(channel.snapshot().basisRevision==8 && channel.snapshot().organizationRevision==1,"STALE_PREPARATION_MUTATED_STATE");
        }
    }
    public static void main(String[] args) throws Exception {admission();ledgerLimit();preparedBasis();System.out.println("Organization owner admission, contextual preflight, historical retry, conflict and per-seat command bounds passed");}
}

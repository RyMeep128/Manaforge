import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Actual authenticated sockets, synthetic basis and read-only game projections. No native-game proof. */
public final class OrganizationChannelChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static final class Peer implements AutoCloseable {
        final String seat;final MatchCoordinatorChecks.Client client;final Set<String> pending=new HashSet<>();
        OrganizationMessages.Context context;JsonObject state;long revision;
        Peer(String seat,ManaforgeMatchCoordinator.Viewer viewer,byte[] key,Basis basis,long basisRevision) throws Exception {
            this.seat=seat;context=OrganizationChannelUnitChecks.contexts(basis,basisRevision).get(seat).viewer;
            client=new MatchCoordinatorChecks.Client(viewer,key,true);
            JsonObject cap=OrganizationMessages.parseContract(raw());check(cap.get("message_type").getAsString().equals("organization_capabilities"),"CAPABILITIES_NOT_FIRST");
            client.send(OrganizationChannelUnitChecks.capabilities());
        }
        String raw() throws IOException {String raw=TextFrame.read(client.socket.getInputStream());check(raw!=null,"UNEXPECTED_EOF");return raw;}
        void snapshot() throws Exception {
            String raw=raw();JsonObject message=OrganizationMessages.parse(raw,context);check(message.get("message_type").getAsString().equals("organization_snapshot"),"EXPECTED_ORGANIZATION_SNAPSHOT");
            check(!raw.contains("SECRET") && !raw.contains("incarnation") && !raw.contains("host_seat"),"PRIVATE_METADATA_LEAK");
            state=message.getAsJsonObject("body");revision=state.get("organization_revision").getAsLong();
        }
        void send(String id,long basisRevision,Operation operation) throws Exception {pending.add(id);client.send(OrganizationChannelUnitChecks.command(id,revision,basisRevision,operation));}
        String receipt(String id,String reason) throws Exception {
            String raw=raw();JsonObject body=OrganizationMessages.parseReceipt(raw,"match",pending).getAsJsonObject("body");check(body.get("command_id").getAsString().equals(id),"WRONG_RECEIPT");
            check(reason==null?body.get("reason_code").isJsonNull():reason.equals(body.get("reason_code").getAsString()),"WRONG_RECEIPT_REASON_"+reason);pending.remove(id);return raw;
        }
        JsonObject seat(String owner){for(JsonElement item:state.getAsJsonArray("seats"))if(item.getAsJsonObject().get("seat_id").getAsString().equals(seat+"-seat-"+owner))return item.getAsJsonObject();throw new AssertionError("SEAT_MISSING");}
        JsonObject group(String owner,String id){for(JsonElement item:seat(owner).getAsJsonArray("groups"))if(item.getAsJsonObject().get("group_id").getAsString().equals(id))return item.getAsJsonObject();throw new AssertionError("GROUP_MISSING");}
        void members(String owner,String group,String... ids){JsonArray actual=group==null?seat(owner).getAsJsonArray("root"):group(owner,group).getAsJsonArray("members");List<String> expected=new ArrayList<>();for(String id:ids)expected.add(OrganizationChannelUnitChecks.handle(seat,id,context.basisRevision));List<String> found=new ArrayList<>();for(JsonElement id:actual)found.add(id.getAsString());check(found.equals(expected),"MEMBER_ORDER_"+seat+"_"+owner+"_"+group);}
        public void close() throws IOException {client.close();}
    }
    static String apply(Peer actor,Peer other,String id,Operation operation) throws Exception {
        long before=actor.revision;actor.send(id,actor.context.basisRevision,operation);String receipt=actor.receipt(id,null);actor.snapshot();other.snapshot();check(actor.revision==before+1 && other.revision==actor.revision,"REVISION_FANOUT");return receipt;
    }
    static void rejected(Peer actor,String id,Operation operation,String reason) throws Exception {
        long before=actor.revision;actor.send(id,actor.context.basisRevision,operation);actor.receipt(id,reason);actor.snapshot();check(actor.revision==before,"REJECTION_MUTATED_STATE");
    }
    static JsonObject template(String path) throws IOException {return JsonParser.parseString(new String(Files.readAllBytes(Paths.get(path)),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonArray("cases").get(0).getAsJsonObject().getAsJsonArray("steps").get(0).getAsJsonObject().getAsJsonObject("envelope");}
    public static void main(String[] args) throws Exception {
        Basis basis=OrganizationChannelUnitChecks.basis();JsonObject template=template(args[0]);AtomicInteger disposed=new AtomicInteger();AtomicBoolean cancel=new AtomicBoolean();AtomicReference<OrganizationChannel> host=new AtomicReference<>();byte[] keyA=MatchCoordinatorChecks.key(11),keyB=MatchCoordinatorChecks.key(12);
        try(ManaforgeMatchCoordinator coordinator=new ManaforgeMatchCoordinator("synthetic-organization",MatchCoordinatorChecks.ENGINE,MatchCoordinatorChecks.HASH,disposed::incrementAndGet,cancel::get,10000,300,true)){
            ManaforgeMatchCoordinator.Viewer a=coordinator.register("a","native-a","session-a","viewer-a",keyA,true),b=coordinator.register("b","native-b","session-b","viewer-b",keyB,true);
            coordinator.installExtension(sender->{OrganizationChannel channel=new OrganizationChannel(sender,basis,7,OrganizationChannelUnitChecks.contexts(basis,7));host.set(channel);return channel;});coordinator.start();
            try(Peer clientA=new Peer("a",a,keyA,basis,7);Peer clientB=new Peer("b",b,keyB,basis,7)){
                clientA.snapshot();clientB.snapshot();clientA.members("a",null,"p1","p3");clientB.members("b",null,"p2");
                coordinator.publishSnapshots(MatchCoordinatorChecks.batch(template,a,b,1,false));clientA.client.read();clientB.client.read();
                String originalCommand=OrganizationChannelUnitChecks.command("create",0,7,Operation.create("g1","Mana Rocks",.2,.3));
                String originalReceipt=apply(clientA,clientB,"create",Operation.create("g1","Mana Rocks",.2,.3));
                apply(clientA,clientB,"move",Operation.move(Arrays.asList(OrganizationChannelUnitChecks.handle("a","p3",7),OrganizationChannelUnitChecks.handle("a","p1",7)),"g1",0));clientA.members("a","g1","p3","p1");clientB.members("a","g1","p3","p1");
                apply(clientA,clientB,"rename",Operation.rename("g1","Engine"));check(clientB.group("a","g1").get("name").getAsString().equals("Engine"),"RENAME_NOT_SHARED");
                apply(clientA,clientB,"position",Operation.position("g1",.7,.1));check(clientB.group("a","g1").get("x").getAsLong()==700000,"POSITION_NOT_SHARED");
                apply(clientA,clientB,"second",Operation.create("g2","Empty",0,0));apply(clientA,clientB,"reorder",Operation.reorder("g2",0));check(clientB.seat("a").getAsJsonArray("groups").get(0).getAsJsonObject().get("group_id").getAsString().equals("g2"),"GROUP_ORDER_NOT_SHARED");
                apply(clientA,clientB,"delete",Operation.delete("g2"));check(clientB.seat("a").getAsJsonArray("groups").size()==1,"EMPTY_GROUP_DELETE");
                apply(clientA,clientB,"unassign",Operation.move(Collections.singletonList(OrganizationChannelUnitChecks.handle("a","p1",7)),null,0));clientB.members("a",null,"p1");clientB.members("a","g1","p3");
                apply(clientA,clientB,"reassign",Operation.move(Collections.singletonList(OrganizationChannelUnitChecks.handle("a","p1",7)),"g1",1));
                rejected(clientB,"foreign-group",Operation.rename("g1","Stolen"),"GROUP_NOT_OWNED");
                rejected(clientB,"foreign-member",Operation.move(Collections.singletonList(OrganizationChannelUnitChecks.handle("b","p1",7)),null,0),"MEMBER_NOT_OWNED_OR_ELIGIBLE");
                rejected(clientA,"unknown",Operation.move(Collections.singletonList("unknown"),"g1",0),"UNKNOWN_MEMBER_HANDLE");
                rejected(clientA,"duplicate",Operation.move(Arrays.asList(OrganizationChannelUnitChecks.handle("a","p1",7),OrganizationChannelUnitChecks.handle("a","p1",7)),"g1",0),"DUPLICATE_SELECTION");
                clientA.pending.add("stale");clientA.client.send(OrganizationChannelUnitChecks.command("stale",0,7,Operation.delete("g1")));clientA.receipt("stale","STALE_ORGANIZATION_REVISION");clientA.snapshot();
                // Retries ignore transport IDs and never advance either revision.
                JsonObject retry=JsonParser.parseString(originalCommand).getAsJsonObject();retry.addProperty("message_id","another-transport");clientA.pending.add("create");clientA.client.send(retry.toString());check(clientA.receipt("create",null).equals(originalReceipt),"RETRY_NOT_EXACT");
                rejected(clientA,"create",Operation.create("conflicting","Conflict",0,0),"COMMAND_CONFLICT");
                coordinator.publishSnapshots(MatchCoordinatorChecks.batch(template,a,b,2,false));clientA.client.read();clientB.client.read();
                MatchCoordinatorChecks.await(()->coordinator.status("a").sentRevision==2 && coordinator.status("b").sentRevision==2,"GAMEPLAY_WRITES_COMPLETE");check(host.get().snapshot().organizationRevision==9,"ORGANIZATION_ADVANCED_GAMEPLAY");
                // Trusted lifecycle changes: p1 leaves, p3 changes controller, p2 becomes ineligible.
                Basis next=new Basis("match",Arrays.asList("a","b"),Arrays.asList(new Member("p3","b",true),new Member("p2","b",false),new Member("SECRET-HIDDEN","a",false),new Member("SECRET-UNADMITTED","a",true)));
                coordinator.updateExtension(extension->((OrganizationChannel)extension).updateBasis(next,8,OrganizationChannelUnitChecks.contexts(next,8)));
                clientA.context=OrganizationChannelUnitChecks.contexts(next,8).get("a").viewer;clientB.context=OrganizationChannelUnitChecks.contexts(next,8).get("b").viewer;clientA.snapshot();clientB.snapshot();
                check(clientA.revision==10 && clientB.revision==10,"LIFECYCLE_REVISION");clientA.members("a","g1");clientB.members("b",null,"p3");check(clientB.state.getAsJsonArray("mappings").size()==1,"INELIGIBLE_MAPPING_LEAK");
                clientA.pending.add("create");clientA.client.send(originalCommand);check(clientA.receipt("create",null).equals(originalReceipt),"BASIS_RETRY_NOT_HISTORICAL");
                // Slow A does not block B's read-only gameplay traffic or organization edits.
                for(int revision=3;revision<35 && coordinator.status("a").status==ManaforgeMatchCoordinator.Status.CONNECTED;revision++){
                    coordinator.publishSnapshots(MatchCoordinatorChecks.batch(template,a,b,revision,true));clientB.client.read();check(coordinator.status("a").pendingSnapshots<=1 && coordinator.status("a").pendingOrganizationSnapshots<=1 && coordinator.status("a").queuedReceipts<=32,"UNBOUNDED_QUEUES");
                }
                MatchCoordinatorChecks.await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"SLOW_A_NOT_DISCONNECTED");
                clientB.send("b-create",8,Operation.create("b-group","Independent",0,0));clientB.receipt("b-create",null);clientB.snapshot();check(clientB.revision==11 && disposed.get()==0,"DISCONNECT_STOPPED_SIBLING");
                coordinator.publishSnapshots(MatchCoordinatorChecks.batch(template,a,b,clientB.client.revision+1,false));clientB.client.read();
                // Reattach the same authenticated registration: full current organization, old ledger retained.
                try(Peer reconnected=new Peer("a",a,keyA,next,8)){
                    reconnected.client.read();reconnected.snapshot();check(reconnected.revision==11 && reconnected.group("b","b-group").get("name").getAsString().equals("Independent"),"REATTACH_MISSED_STATE");
                    reconnected.pending.add("create");reconnected.client.send(originalCommand);check(reconnected.receipt("create",null).equals(originalReceipt),"REATTACH_LOST_LEDGER");
                    // Gameplay commands cannot use the organization route.
                    reconnected.client.send("{\"wire_version\":1,\"message_type\":\"command\",\"message_id\":\"forged\",\"body\":{}}");MatchCoordinatorChecks.await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"GAME_COMMAND_ADMITTED");check(disposed.get()==0,"FOREIGN_TRAFFIC_DISPOSED_MATCH");
                }
                cancel.set(true);MatchCoordinatorChecks.await(coordinator::isClosed,"PARENT_CANCELLATION");
            }
            coordinator.close();check(disposed.get()==1,"MATCH_NOT_DISPOSED_ONCE");
            try{host.get().snapshot();throw new AssertionError("ORGANIZATION_SESSION_LEAK");}catch(IllegalStateException expected){}
        }finally{Arrays.fill(keyA,(byte)0);Arrays.fill(keyB,(byte)0);}
        check(disposed.get()==1,"MATCH_DISPOSED_TWICE");System.out.println("Authenticated two-client synthetic organization edits, privacy, retry, lifecycle, stalled-viewer isolation, reattach and cleanup passed; native gameplay remains a separate gate");
    }
}

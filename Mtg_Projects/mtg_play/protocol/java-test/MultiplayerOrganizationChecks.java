import com.google.gson.*;
import java.util.*;
import manaforge.protocol.*;

/** Two independently advancing human views share placement state, never private/native IDs. */
public final class MultiplayerOrganizationChecks {
    static final UUID GAME=UUID.randomUUID(),A=UUID.randomUUID(),B=UUID.randomUUID(),P1=UUID.randomUUID(),P2=UUID.randomUUID(),SECRET=UUID.randomUUID();
    static final class Packet {
        final String seat;final ViewerChannelExtension.Kind kind;final String raw;
        Packet(String seat,ViewerChannelExtension.Kind kind,String raw){this.seat=seat;this.kind=kind;this.raw=raw;}
    }
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static BattlefieldIdentityRegistry.Snapshot nativeView(UUID viewer,int cycle,boolean transferred,String prefix){
        List<BattlefieldIdentityRegistry.Observation> cards=Arrays.asList(
            new BattlefieldIdentityRegistry.Observation(P1,0,transferred?B:A,true),
            new BattlefieldIdentityRegistry.Observation(P2,0,B,true),
            new BattlefieldIdentityRegistry.Observation(SECRET,0,A,false));
        Map<UUID,String> admitted=new HashMap<>();admitted.put(P1,prefix+"-one");admitted.put(P2,prefix+"-two");
        return new BattlefieldIdentityRegistry.Snapshot(GAME,viewer,cycle,Arrays.asList(A,B),cards,admitted);
    }
    static ManaforgeOpeningProjection.ObserverResult projection(ManaforgeMatchCoordinator.Viewer viewer,long revision,String prefix){
        JsonObject snapshot=new JsonObject();snapshot.addProperty("session_id",viewer.session);snapshot.addProperty("viewer_id",viewer.viewer);snapshot.addProperty("revision",revision);snapshot.addProperty("status","active");
        Map<String,String> objects=new HashMap<>(),seats=new HashMap<>();objects.put(P1.toString(),prefix+"-one");objects.put(P2.toString(),prefix+"-two");
        seats.put(A.toString(),viewer.nativePlayer.equals(A.toString())?viewer.viewer:"other-"+viewer.viewer);seats.put(B.toString(),viewer.nativePlayer.equals(B.toString())?viewer.viewer:"other-"+viewer.viewer);
        return new ManaforgeOpeningProjection.ObserverResult(snapshot,objects,seats);
    }
    static JsonObject snapshot(List<Packet> packets,String seat) throws Exception {
        JsonObject last=null;for(Packet packet:packets)if(packet.seat.equals(seat) && packet.kind==ViewerChannelExtension.Kind.SNAPSHOT)last=OrganizationV4Messages.parseContract(packet.raw).getAsJsonObject("body");
        check(last!=null,"SNAPSHOT_MISSING");return last;
    }
    static String handle(JsonObject state,String reference){for(JsonElement item:state.getAsJsonArray("mappings")){JsonObject mapping=item.getAsJsonObject();if(mapping.get("object_reference").getAsString().equals(reference))return mapping.get("handle").getAsString();}throw new AssertionError("HANDLE_MISSING");}
    static String command(JsonObject state,String id,String member) throws Exception {
        JsonObject wire=JsonParser.parseString(OrganizationV4Checks.command(id,state.get("organization_revision").getAsLong(),state.get("basis_revision").getAsLong(),member,.7,.2)).getAsJsonObject();wire.getAsJsonObject("body").add("match_epoch",state.get("match_epoch"));return wire.toString();
    }
    static boolean placed(JsonObject state,String member){for(JsonElement item:state.getAsJsonArray("seats"))for(JsonElement place:item.getAsJsonObject().getAsJsonArray("placements")){JsonObject p=place.getAsJsonObject();if(p.get("handle").getAsString().equals(member) && p.get("x").getAsLong()==700000 && p.get("y").getAsLong()==200000)return true;}return false;}
    public static void main(String[] args) throws Exception {
        List<Packet> packets=new ArrayList<>();byte[] ka=new byte[32],kb=new byte[32];Arrays.fill(kb,(byte)1);
        try(ManaforgeMatchCoordinator transport=new ManaforgeMatchCoordinator("organization-fixture",MatchCoordinatorChecks.ENGINE,MatchCoordinatorChecks.HASH,()->{},()->false)){
            ManaforgeMatchCoordinator.Viewer a=transport.register("a",A.toString(),"session-a","viewer-a",ka),b=transport.register("b",B.toString(),"session-b","viewer-b",kb);
            Map<String,ManaforgeMatchCoordinator.Viewer> registrations=new TreeMap<>();registrations.put("a",a);registrations.put("b",b);
            try(NativeOrganizationBridge bridge=new NativeOrganizationBridge(GAME,registrations,(seat,kind,raw)->{packets.add(new Packet(seat,kind,raw));return true;},4)){
                bridge.connected("a");bridge.connected("b");
                bridge.observeInteractive("a",nativeView(A,10,false,"a"),projection(a,1,"a"));
                bridge.observeInteractive("b",nativeView(B,10,false,"b"),projection(b,5,"b"));
                String caps="{\"wire_version\":1,\"organization_version\":4,\"message_type\":\"organization_capabilities\",\"message_id\":\"cap\",\"body\":{\"versions\":[4]}}";
                bridge.receive("a",caps);bridge.receive("b",caps);
                JsonObject av=snapshot(packets,"a"),bv=snapshot(packets,"b");String ah=handle(av,"a-one"),bh=handle(bv,"b-one");check(!ah.equals(bh),"VIEWER_HANDLES_SHARED");packets.clear();
                bridge.receive("a",command(av,"place",ah));av=snapshot(packets,"a");bv=snapshot(packets,"b");
                check(placed(av,ah) && placed(bv,bh),"PLACEMENT_NOT_SHARED");check(av.get("gameplay_revision").getAsLong()==1 && bv.get("gameplay_revision").getAsLong()==5,"GAMEPLAY_REVISIONS_COUPLED");
                long organization=bv.get("organization_revision").getAsLong(),basis=bv.get("basis_revision").getAsLong();packets.clear();
                bridge.observeInteractive("a",nativeView(A,10,false,"fresh-a"),projection(a,2,"fresh-a"));
                av=snapshot(packets,"a");bv=snapshot(packets,"b");check(bv.get("gameplay_revision").getAsLong()==5 && bv.get("organization_revision").getAsLong()==organization && bv.get("basis_revision").getAsLong()>basis,"INDEPENDENT_BASIS_REFRESH");check(placed(av,handle(av,"fresh-a-one")) && placed(bv,bh),"PLACEMENT_LOST_ON_VIEW_REFRESH");packets.clear();
                bridge.receive("b",command(bv,"foreign",bh));boolean rejected=false;for(Packet p:packets)if(p.kind==ViewerChannelExtension.Kind.RECEIPT)rejected|=p.raw.contains("MEMBER_NOT_OWNED_OR_ELIGIBLE");check(rejected,"OPPONENT_CARD_MOVED");packets.clear();
                bridge.observeInteractive("a",nativeView(A,11,true,"transferred-a"),projection(a,3,"transferred-a"));bv=snapshot(packets,"b");check(bv.getAsJsonArray("mappings").size()==1,"STALE_CONTROLLER_HANDLE_RETAINED");check(bridge.snapshot().state.seats.get("a").placements.isEmpty() && bridge.snapshot().state.seats.get("b").placements.isEmpty(),"TRANSFER_INHERITED_POSITION");packets.clear();
                bridge.observeInteractive("b",nativeView(B,11,true,"fresh-b"),projection(b,6,"fresh-b"));bv=snapshot(packets,"b");String replacement=handle(bv,"fresh-b-one");check(!replacement.equals(bh),"TRANSFER_REUSED_OLD_HANDLE");packets.clear();bridge.receive("b",command(bv,"new-owner",replacement));check(placed(snapshot(packets,"a"),handle(snapshot(packets,"a"),"transferred-a-one")),"NEW_OWNER_POSITION_NOT_SHARED");
                for(Packet p:packets)check(!p.raw.contains(SECRET.toString()) && !p.raw.contains(P1.toString()) && !p.raw.contains(A.toString()),"NATIVE_OR_PRIVATE_ID_EXPOSED");
            }
        }
        System.out.println("Interactive multiplayer shared placement, independent revisions, controller authority and private references passed; no rules transport");
    }
}

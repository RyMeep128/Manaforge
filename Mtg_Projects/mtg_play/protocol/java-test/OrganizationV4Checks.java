import com.google.gson.*;
import java.util.*;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;
/** Hosted two-view proof for free placement, receipts, privacy and lifecycle. */
public final class OrganizationV4Checks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static String command(String id,long revision,long basis,String handle,double x,double y) throws Exception {
        JsonObject message=JsonParser.parseString(OrganizationV4Messages.upgrade(OrganizationChannelUnitChecks.command(id,revision,basis,Operation.move(Collections.singletonList(handle),null,0)),11)).getAsJsonObject(),op=message.getAsJsonObject("body").getAsJsonObject("operation");
        op.addProperty("kind","place");op.add("index",JsonNull.INSTANCE);op.addProperty("x",Math.round(x*1000000));op.addProperty("y",Math.round(y*1000000));return message.toString();
    }
    public static void main(String[] args) throws Exception {
        Basis basis=OrganizationChannelUnitChecks.basis();List<OrganizationChannelUnitChecks.Packet> packets=new ArrayList<>();
        try(OrganizationV4Channel channel=new OrganizationV4Channel((seat,kind,raw)->{packets.add(new OrganizationChannelUnitChecks.Packet(seat,kind,raw));return true;},basis,7,11,OrganizationChannelUnitChecks.contexts(basis,7))){
            for(String seat:Arrays.asList("a","b")){channel.connected(seat);channel.receive(seat,OrganizationV4Messages.upgrade(OrganizationChannelUnitChecks.capabilities(),11));}packets.clear();
            String place=command("place",0,7,OrganizationChannelUnitChecks.handle("a","p1",7),.7,.2);channel.receive("a",place);check(channel.snapshot().state.seats.get("a").placements.get("p1").equals(new Placement(.7,.2)),"FREE_POSITION");String receipt=OrganizationChannelUnitChecks.receipt(packets).raw;
            check(packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT).count()==2,"POSITION_FANOUT");
            for(OrganizationChannelUnitChecks.Packet p:packets)if(p.kind==ViewerChannelExtension.Kind.SNAPSHOT){JsonObject snapshot=OrganizationV4Messages.parse(p.raw,OrganizationChannelUnitChecks.contexts(basis,7).get(p.seat).viewer);check(!p.raw.contains("SECRET"),"PLACEMENT_PRIVACY");JsonObject first=snapshot.getAsJsonObject("body").getAsJsonArray("seats").get(0).getAsJsonObject();check(first.getAsJsonArray("placements").get(0).getAsJsonObject().get("handle").getAsString().startsWith(p.seat+"-h-"),"POSITION_VIEWER_HANDLE");}
            packets.clear();channel.receive("b",command("foreign",1,7,OrganizationChannelUnitChecks.handle("b","p1",7),.1,.1));check("MEMBER_NOT_OWNED_OR_ELIGIBLE".equals(OrganizationChannelUnitChecks.reason(OrganizationChannelUnitChecks.receipt(packets))),"POSITION_AUTHORITY");
            channel.update(basis,8,12,OrganizationChannelUnitChecks.contexts(basis,8));check(channel.snapshot().state.seats.get("a").placements.containsKey("p1"),"SURVIVING_POSITION");packets.clear();channel.receive("a",place);check(packets.size()==1 && packets.get(0).raw.equals(receipt),"POSITION_HISTORICAL_RETRY");
            packets.clear();channel.disconnected("b");channel.connected("b");channel.receive("b",OrganizationV4Messages.upgrade(OrganizationChannelUnitChecks.capabilities(),12));check(packets.stream().anyMatch(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT && p.raw.contains("700000")),"POSITION_RECONNECT");
            channel.receive("a",OrganizationV4Messages.upgrade(OrganizationChannelUnitChecks.command("group",1,8,Operation.create("g","Here",.7,.2)),12));channel.receive("a",OrganizationV4Messages.upgrade(OrganizationChannelUnitChecks.command("move",2,8,Operation.move(Collections.singletonList(OrganizationChannelUnitChecks.handle("a","p1",8)),"g",0)),12));check(channel.snapshot().state.seats.get("a").placements.isEmpty(),"GROUP_CLEARS_FREE_POSITION");
            channel.receive("a",command("extract",3,8,OrganizationChannelUnitChecks.handle("a","p1",8),.4,.5));check(channel.snapshot().state.seats.get("a").groups.get(0).members.isEmpty() && channel.snapshot().state.seats.get("a").root.contains("p1"),"DRAG_OUT_OF_GROUP");
            Basis departed=new Basis("match",basis.seats,Arrays.asList(new Member("replacement","a",true),new Member("p2","b",true)));channel.update(departed,9,13,OrganizationChannelUnitChecks.contexts(departed,9));check(channel.snapshot().state.seats.get("a").placements.isEmpty(),"REPLACEMENT_INHERITED_POSITION");
        }
        State placed=apply(create(basis),"a",Operation.place("p1",.2,.3),basis);
        Basis stolen=new Basis("match",basis.seats,Arrays.asList(new Member("p1","b",true)));check(reconcile(placed,stolen).seats.get("b").placements.isEmpty(),"CONTROL_CHANGE_INHERITED_POSITION");
        try{apply(create(basis),"a",Operation.place("p1",Double.NaN,0),basis);throw new AssertionError("INVALID_POSITION_ACCEPTED");}catch(Rejected expected){}
        System.out.println("Organization v4 shared positions, authority, viewer privacy, reconnect, historical retry and incarnation lifecycle passed");
    }
}

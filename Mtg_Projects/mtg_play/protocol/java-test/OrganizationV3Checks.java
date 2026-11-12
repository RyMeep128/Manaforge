import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import manaforge.protocol.*;
import manaforge.organization.*;
import static manaforge.organization.BattlefieldOrganizationService.*;
public final class OrganizationV3Checks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject(),fixture=corpus.getAsJsonObject("context");Map<String,String> refs=new HashMap<>(),objects=new HashMap<>(),seats=new HashMap<>();for(Map.Entry<String,JsonElement> entry:fixture.getAsJsonObject("seats").entrySet())refs.put(entry.getKey(),entry.getValue().getAsString());for(JsonElement token:fixture.getAsJsonArray("bindings")){JsonObject b=token.getAsJsonObject();objects.put(b.get("handle").getAsString(),b.get("object_reference").getAsString());seats.put(b.get("handle").getAsString(),refs.get(b.get("host_seat").getAsString()));}
        OrganizationMessages.Context context=new OrganizationMessages.Context("match","viewer-a",7,objects,seats,objects.values(),refs.values());int count=0;
        for(JsonElement token:corpus.getAsJsonArray("cases")){JsonObject test=token.getAsJsonObject();boolean valid=false;try{OrganizationV3Messages.parse(test.get("text").getAsString(),context);valid=true;}catch(IOException expected){}check(valid==test.get("valid").getAsBoolean(),"V3_CORPUS_"+test.get("name"));count++;}
        List<OrganizationChannelUnitChecks.Packet> packets=new ArrayList<>();Basis basis=OrganizationChannelUnitChecks.basis();Map<String,OrganizationCodec.HostContext> contexts=OrganizationChannelUnitChecks.contexts(basis,7);
        try(OrganizationV3Channel channel=new OrganizationV3Channel((seat,kind,raw)->{packets.add(new OrganizationChannelUnitChecks.Packet(seat,kind,raw));return true;},basis,7,11,Collections.singletonMap("a",contexts.get("a")))){
            channel.connected("a");channel.receive("a",OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.capabilities(),11));packets.clear();
            String command=OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.command("create",0,7,Operation.create("g","Live",0,0)),11);channel.receive("a",command);String receipt=OrganizationChannelUnitChecks.receipt(packets).raw;
            JsonObject snapshot=OrganizationV3Messages.parseContract(packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT).findFirst().get().raw);check(snapshot.getAsJsonObject("body").get("gameplay_revision").getAsLong()==11,"V3_GAMEPLAY_CORRELATION");
            channel.update(basis,8,12,Collections.singletonMap("a",OrganizationChannelUnitChecks.contexts(basis,8).get("a")));packets.clear();channel.receive("a",command);check(packets.size()==1 && packets.get(0).raw.equals(receipt),"V3_HISTORICAL_REPLAY");OrganizationV3Messages.parseReceipt(receipt,"match",Collections.singletonList("create"));
            packets.clear();channel.rejectUnready("a",command);check(packets.size()==1 && packets.get(0).raw.equals(receipt),"UNREADY_LOST_HISTORICAL_RECEIPT");packets.clear();
            String unready=OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.command("unready",1,8,Operation.rename("g","Changed")),12);channel.rejectUnready("a",unready);String rejection=packets.get(0).raw;packets.clear();channel.receive("a",unready);check(packets.size()==1 && packets.get(0).raw.equals(rejection) && channel.snapshot().organizationRevision==1,"UNREADY_REJECTION_NOT_RECORDED");
            try{channel.connected("b");throw new AssertionError("AI_IS_NOT_RECIPIENT");}catch(IOException expected){}
        }
        packets.clear();
        try(OrganizationV3Channel channel=new OrganizationV3Channel((seat,kind,raw)->{packets.add(new OrganizationChannelUnitChecks.Packet(seat,kind,raw));return true;},basis,7,11,contexts)){
            for(String seat:Arrays.asList("a","b")){channel.connected(seat);channel.receive(seat,OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.capabilities(),11));}
            channel.receive("a",OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.command("group",0,7,Operation.create("g","Mana Rocks",.2,.3)),11));
            JsonObject mode=JsonParser.parseString(OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.command("mode",1,7,Operation.rename("g","Unused")),11)).getAsJsonObject(),op=mode.getAsJsonObject("body").getAsJsonObject("operation");op.addProperty("kind","set_mode");op.add("name",JsonNull.INSTANCE);op.addProperty("presentation_mode","drawer");packets.clear();channel.receive("a",mode.toString());
            check(channel.snapshot().state.seats.get("a").groups.get(0).presentationMode==PresentationMode.DRAWER,"DRAWER_NOT_APPLIED");check(packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT).count()==2,"DRAWER_NOT_SHARED");String historical=OrganizationChannelUnitChecks.receipt(packets).raw;packets.clear();channel.receive("a",mode.toString());check(packets.size()==1 && packets.get(0).raw.equals(historical),"MODE_RETRY");
            mode.getAsJsonObject("body").addProperty("command_id","foreign");mode.getAsJsonObject("body").addProperty("expected_organization_revision",2);packets.clear();channel.receive("b",mode.toString());check("GROUP_NOT_OWNED".equals(OrganizationChannelUnitChecks.reason(OrganizationChannelUnitChecks.receipt(packets))),"MODE_AUTHORITY");
            channel.receive("a",OrganizationV3Messages.upgrade(OrganizationChannelUnitChecks.command("rename",2,7,Operation.rename("g","Renamed")),11));check(channel.snapshot().state.seats.get("a").groups.get(0).presentationMode==PresentationMode.DRAWER,"RENAME_RESET_MODE");
            channel.update(basis,8,12,OrganizationChannelUnitChecks.contexts(basis,8));check(channel.snapshot().state.seats.get("a").groups.get(0).presentationMode==PresentationMode.DRAWER,"RECONCILE_RESET_MODE");
        }
        System.out.println("Organization v3: "+count+" shared cases, exact gameplay correlation, historical retries and single-recipient/two-seat admission passed");
    }
}

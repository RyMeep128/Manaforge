import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import manaforge.protocol.*;
import manaforge.organization.*;
import static manaforge.organization.BattlefieldOrganizationService.*;
public final class OrganizationV2Checks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject(),fixture=corpus.getAsJsonObject("context");Map<String,String> refs=new HashMap<>(),objects=new HashMap<>(),seats=new HashMap<>();for(Map.Entry<String,JsonElement> entry:fixture.getAsJsonObject("seats").entrySet())refs.put(entry.getKey(),entry.getValue().getAsString());for(JsonElement token:fixture.getAsJsonArray("bindings")){JsonObject b=token.getAsJsonObject();objects.put(b.get("handle").getAsString(),b.get("object_reference").getAsString());seats.put(b.get("handle").getAsString(),refs.get(b.get("host_seat").getAsString()));}
        OrganizationMessages.Context context=new OrganizationMessages.Context("match","viewer-a",7,objects,seats,objects.values(),refs.values());int count=0;
        for(JsonElement token:corpus.getAsJsonArray("cases")){JsonObject test=token.getAsJsonObject();boolean valid=false;try{OrganizationV2Messages.parse(test.get("text").getAsString(),context);valid=true;}catch(IOException expected){}check(valid==test.get("valid").getAsBoolean(),"V2_CORPUS_"+test.get("name"));count++;}
        List<OrganizationChannelUnitChecks.Packet> packets=new ArrayList<>();Basis basis=OrganizationChannelUnitChecks.basis();Map<String,OrganizationCodec.HostContext> contexts=OrganizationChannelUnitChecks.contexts(basis,7);
        try(OrganizationV2Channel channel=new OrganizationV2Channel((seat,kind,raw)->{packets.add(new OrganizationChannelUnitChecks.Packet(seat,kind,raw));return true;},basis,7,11,Collections.singletonMap("a",contexts.get("a")))){
            channel.connected("a");channel.receive("a",OrganizationV2Messages.upgrade(OrganizationChannelUnitChecks.capabilities(),11));packets.clear();
            String command=OrganizationV2Messages.upgrade(OrganizationChannelUnitChecks.command("create",0,7,Operation.create("g","Live",0,0)),11);channel.receive("a",command);String receipt=OrganizationChannelUnitChecks.receipt(packets).raw;
            JsonObject snapshot=OrganizationV2Messages.parseContract(packets.stream().filter(p->p.kind==ViewerChannelExtension.Kind.SNAPSHOT).findFirst().get().raw);check(snapshot.getAsJsonObject("body").get("gameplay_revision").getAsLong()==11,"V2_GAMEPLAY_CORRELATION");
            channel.update(basis,8,12,Collections.singletonMap("a",OrganizationChannelUnitChecks.contexts(basis,8).get("a")));packets.clear();channel.receive("a",command);check(packets.size()==1 && packets.get(0).raw.equals(receipt),"V2_HISTORICAL_REPLAY");OrganizationV2Messages.parseReceipt(receipt,"match",Collections.singletonList("create"));
            packets.clear();channel.rejectUnready("a",command);check(packets.size()==1 && packets.get(0).raw.equals(receipt),"UNREADY_LOST_HISTORICAL_RECEIPT");packets.clear();
            String unready=OrganizationV2Messages.upgrade(OrganizationChannelUnitChecks.command("unready",1,8,Operation.rename("g","Changed")),12);channel.rejectUnready("a",unready);String rejection=packets.get(0).raw;packets.clear();channel.receive("a",unready);check(packets.size()==1 && packets.get(0).raw.equals(rejection) && channel.snapshot().organizationRevision==1,"UNREADY_REJECTION_NOT_RECORDED");
            try{channel.connected("b");throw new AssertionError("AI_IS_NOT_RECIPIENT");}catch(IOException expected){}
        }
        System.out.println("Organization v2: "+count+" shared cases, exact gameplay correlation, historical retries and single-recipient/two-seat admission passed");
    }
}

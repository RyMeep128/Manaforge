package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import manaforge.organization.OrganizationCodec;
import manaforge.organization.BattlefieldOrganizationSession;
import static manaforge.organization.BattlefieldOrganizationService.*;

public final class OrganizationFixtureConsumer {
    private static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    private interface Checked {void run() throws Exception;}
    private static void rejects(Checked action,String code) throws Exception {try{action.run();}catch(IOException | IllegalArgumentException expected){return;}throw new AssertionError(code);}
    private static Map<String,String> strings(JsonObject object){Map<String,String> result=new HashMap<>();for(Map.Entry<String,JsonElement> entry:object.entrySet())result.put(entry.getKey(),entry.getValue().getAsString());return result;}
    private static OrganizationCodec.HostContext context(JsonObject fixture){
        Map<String,String> seatRefs=strings(fixture.getAsJsonObject("seats")),objects=new HashMap<>(),seats=new HashMap<>();Map<String,OrganizationCodec.Binding> bindings=new HashMap<>();List<String> admitted=new ArrayList<>();
        for(JsonElement item:fixture.getAsJsonArray("admitted"))admitted.add(item.getAsString());
        for(JsonElement item:fixture.getAsJsonArray("bindings")){JsonObject b=item.getAsJsonObject();String handle=b.get("handle").getAsString(),host=b.get("host_seat").getAsString();objects.put(handle,b.get("object_reference").getAsString());seats.put(handle,seatRefs.get(host));bindings.put(handle,new OrganizationCodec.Binding(b.get("incarnation").getAsString(),host));}
        OrganizationMessages.Context wire=new OrganizationMessages.Context(fixture.get("match_epoch").getAsString(),fixture.get("viewer_id").getAsString(),fixture.get("basis_revision").getAsLong(),objects,seats,admitted,seatRefs.values());
        objects.clear();seats.clear();admitted.clear(); // Constructor must have copied its authorization inputs.
        return new OrganizationCodec.HostContext(wire,bindings,seatRefs);
    }
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();OrganizationCodec.HostContext context=context(corpus.getAsJsonObject("context"));Map<String,String> messages=new HashMap<>();int count=0;
        for(JsonElement item:corpus.getAsJsonArray("cases")){
            JsonObject test=item.getAsJsonObject();String name=test.get("name").getAsString(),raw=test.get("text").getAsString();boolean expected=test.get("valid").getAsBoolean();messages.put(name,raw);
            JsonObject parsed=null;try{parsed=OrganizationMessages.parse(raw,context.viewer);}catch(IOException failure){if(expected)throw new AssertionError("Rejected "+name+" "+failure.getMessage(),failure);}
            check((parsed!=null)==expected,"CORPUS_"+name);
            if(parsed!=null){check(OrganizationMessages.parse(OrganizationMessages.serialize(parsed,context.viewer),context.viewer).equals(parsed),"ROUNDTRIP_"+name);rejects(()->WireEnvelope.parse(raw),"LEGACY_ACCEPTED_ORGANIZATION");}
            count++;
        }
        JsonObject historical=JsonParser.parseString(messages.get("receipt-command_limit_reached")).getAsJsonObject();historical.getAsJsonObject("body").addProperty("basis_revision",6);String oldReceipt=historical.toString();
        OrganizationMessages.parseReceipt(oldReceipt,"match",Collections.singletonList("cmd-1"));
        rejects(()->OrganizationMessages.parse(oldReceipt,context.viewer),"HISTORICAL_RECEIPT_CURRENT_CONTEXT");
        rejects(()->OrganizationMessages.parseReceipt(oldReceipt,"other",Collections.singletonList("cmd-1")),"RECEIPT_FOREIGN_MATCH");
        rejects(()->OrganizationMessages.parseReceipt(oldReceipt,"match",Collections.singletonList("other")),"RECEIPT_UNKNOWN_COMMAND");
        rejects(()->OrganizationMessages.parseReceipt(messages.get("command-create"),"match",Collections.singletonList("cmd-1")),"COMMAND_AS_RECEIPT");
        check(OrganizationMessages.negotiate(Arrays.asList(1),Arrays.asList(1),true)==1 && OrganizationMessages.negotiate(Arrays.asList(1),Arrays.asList(1),false)==0 && OrganizationMessages.negotiate(Arrays.asList(1),Arrays.asList(2),true)==0 && OrganizationMessages.negotiate(null,Arrays.asList(1),true)==0,"CAPABILITY_SELECTION");
        rejects(()->OrganizationCodec.command(messages.get("command-move"),context,"host-b"),"FOREIGN_ACTOR_HANDLE");
        OrganizationCodec.DecodedCommand decoded=OrganizationCodec.command(messages.get("command-create"),context,"host-a");check(decoded.expectedOrganizationRevision==0 && decoded.basisRevision==7 && decoded.commandId.equals("cmd-1") && decoded.operation.x==.25 && decoded.operation.y==.75,"COMMAND_CONVERSION");
        Basis basis=new Basis("match",Arrays.asList("host-a","host-b"),Arrays.asList(new Member("SECRET-INCARNATION-1","host-a",true),new Member("SECRET-INCARNATION-2","host-b",true),new Member("SECRET-HIDDEN","host-a",false),new Member("SECRET-UNADMITTED","host-a",true)));
        try(BattlefieldOrganizationSession session=new BattlefieldOrganizationSession(basis,7)){
            session.apply("host-a",0,7,Operation.create("g1","Mana Rocks",.25,.75));
            decoded=OrganizationCodec.command(messages.get("command-move"),context,"host-a");check(decoded.operation.members.equals(Collections.singletonList("SECRET-INCARNATION-1")),"HANDLE_NOT_RESOLVED");
            check(session.apply("host-a",decoded.expectedOrganizationRevision,decoded.basisRevision,decoded.operation).outcome==BattlefieldOrganizationSession.Outcome.REJECTED,"CODEC_BYPASSED_SESSION_REVISION");
            BattlefieldOrganizationSession.Result result=session.apply("host-a",1,7,decoded.operation);
            String raw=OrganizationCodec.snapshot("snapshot-1",session.snapshot(),context);JsonObject snapshot=OrganizationMessages.parse(raw,context.viewer).getAsJsonObject("body");
            check(!raw.contains("SECRET") && !raw.contains("host-a") && !raw.contains("host-b") && snapshot.getAsJsonArray("mappings").size()==2,"PROJECTION_LEAK");
            check(snapshot.getAsJsonArray("seats").get(0).getAsJsonObject().getAsJsonArray("root").size()==0,"UNADMITTED_COUNT_LEAK");
            OrganizationMessages.parse(OrganizationCodec.receipt("receipt-1","cmd-1",result,context),context.viewer);
            BattlefieldOrganizationSession.Result rejected=session.apply("host-b",0,7,Operation.delete("g1"));OrganizationMessages.parse(OrganizationCodec.receipt("receipt-2","cmd-2",rejected,context),context.viewer);
            session.apply("host-a",2,7,Operation.rename("g1",String.join("",Collections.nCopies(65,"x"))));rejects(()->OrganizationCodec.snapshot("too-long",session.snapshot(),context),"SNAPSHOT_TRUNCATED_NAME");
        }
        rejects(()->new OrganizationMessages.Context("match","viewer-a",7,Collections.singletonMap("h1","private"),Collections.singletonMap("h1","seat-a"),Collections.singletonList("object-1"),Collections.singletonList("seat-a")),"UNADMITTED_CONTEXT");
        Map<String,OrganizationCodec.Binding> aliases=new HashMap<>(context.bindings);aliases.put("h1",new OrganizationCodec.Binding("h1","host-a"));rejects(()->new OrganizationCodec.HostContext(context.viewer,aliases,context.seatReferences),"HOST_ID_AS_HANDLE");
        aliases.put("h1",new OrganizationCodec.Binding("h2","host-a"));rejects(()->new OrganizationCodec.HostContext(context.viewer,aliases,context.seatReferences),"OTHER_HOST_ID_AS_HANDLE");
        JsonObject command=OrganizationMessages.parse(messages.get("command-create"),context.viewer);OrganizationContracts.OrganizationCommand dto=new Gson().fromJson(command.get("body"),OrganizationContracts.OrganizationCommand.class);check(dto.operation.x==250000 && dto.operation.y==750000,"GENERATED_DTO_DRIFT");
        Map<String,String> largeObjects=new HashMap<>(),largeSeats=new HashMap<>();Map<String,OrganizationCodec.Binding> largeBindings=new HashMap<>();List<Member> largeMembers=new ArrayList<>();String padding=String.join("",Collections.nCopies(115,"x"));
        for(int i=0;i<1024;i++){String handle="h"+padding+i,reference="o"+padding+i,incarnation="secret-"+i;largeObjects.put(handle,reference);largeSeats.put(handle,"seat-a");largeBindings.put(handle,new OrganizationCodec.Binding(incarnation,"host-a"));largeMembers.add(new Member(incarnation,"host-a",true));}
        OrganizationMessages.Context largeViewer=new OrganizationMessages.Context("match","viewer-a",7,largeObjects,largeSeats,largeObjects.values(),Collections.singletonList("seat-a"));
        OrganizationCodec.HostContext largeContext=new OrganizationCodec.HostContext(largeViewer,largeBindings,Collections.singletonMap("host-a","seat-a"));
        try(BattlefieldOrganizationSession largeSession=new BattlefieldOrganizationSession(new Basis("match",Collections.singletonList("host-a"),largeMembers),7)){
            try{OrganizationCodec.snapshot("large",largeSession.snapshot(),largeContext);throw new AssertionError("OVERSIZED_SNAPSHOT_TRUNCATED");}catch(IOException expected){check(expected.getMessage().equals("ORGANIZATION_SIZE"),"WRONG_SIZE_FAILURE");}
        }
        System.out.println("Organization shared corpus: "+count+" cases; contextual codecs, capability/legacy isolation and privacy canaries passed");
    }
}

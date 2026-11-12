package manaforge.organization;

import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import manaforge.protocol.OrganizationMessages;
import manaforge.protocol.OrganizationV3Messages;
import manaforge.protocol.ViewerChannelExtension;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Serialized host adapter. Contexts are trusted integration inputs, never packet identity. */
public final class OrganizationChannel implements ViewerChannelExtension {
    public static final int COMMAND_LIMIT=4096;
    private static final class Record {
        final byte[] digest;final String receipt;
        Record(byte[] digest,String receipt){this.digest=digest.clone();this.receipt=receipt;}
    }
    private final Thread owner=Thread.currentThread();
    private final Sender sender;private final BattlefieldOrganizationSession session;
    private Map<String,OrganizationCodec.HostContext> contexts;
    private final Map<String,Map<String,Record>> ledger=new TreeMap<>();
    private final Set<String> connected=new HashSet<>(),negotiated=new HashSet<>();
    private final int version;private final java.util.function.LongSupplier gameplay;
    private long serial;private boolean closed;
    public OrganizationChannel(Sender sender,Basis basis,long basisRevision,Map<String,OrganizationCodec.HostContext> contexts) throws Exception {
        this(sender,basis,basisRevision,contexts,1,()->0);
    }
    public OrganizationChannel(Sender sender,Basis basis,long basisRevision,Map<String,OrganizationCodec.HostContext> contexts,int version,java.util.function.LongSupplier gameplay) throws Exception {
        if(version!=1 && version!=3)throw new IllegalArgumentException("ORGANIZATION_VERSION");this.version=version;this.gameplay=gameplay;
        this.sender=Objects.requireNonNull(sender);session=new BattlefieldOrganizationSession(basis,basisRevision);
        try{this.contexts=checkedContexts(contexts,basis,basisRevision);render(session.snapshot().state,0,basisRevision,this.contexts);for(String seat:this.contexts.keySet())ledger.put(seat,new LinkedHashMap<>());}
        catch(Exception failure){session.close();throw failure;}
    }
    private void owned(){if(Thread.currentThread()!=owner)throw new IllegalStateException("ORGANIZATION_OWNER_THREAD");if(closed)throw new IllegalStateException("ORGANIZATION_CLOSED");}
    private static void require(boolean value) throws IOException {if(!value)throw new IOException("ORGANIZATION_CONTEXT");}
    private String messageId(){return "organization-"+(serial++);}
    private static Map<String,OrganizationCodec.HostContext> checkedContexts(Map<String,OrganizationCodec.HostContext> contexts,Basis basis,long revision) throws IOException {
        require(contexts!=null && !contexts.isEmpty() && basis.seats.containsAll(contexts.keySet()));Map<String,OrganizationCodec.HostContext> result=new TreeMap<>();Set<String> viewers=new HashSet<>();
        for(Map.Entry<String,OrganizationCodec.HostContext> entry:contexts.entrySet()){
            OrganizationCodec.HostContext context=entry.getValue();require(context!=null && context.viewer.matchEpoch.equals(basis.matchEpoch) && context.viewer.basisRevision==revision && context.seatReferences.containsKey(entry.getKey()) && viewers.add(context.viewer.viewerId));result.put(entry.getKey(),context);
        }
        return Collections.unmodifiableMap(result);
    }
    private Map<String,String> render(State state,long organizationRevision,long basisRevision,Map<String,OrganizationCodec.HostContext> contexts) throws Exception {
        Map<String,String> result=new TreeMap<>();for(Map.Entry<String,OrganizationCodec.HostContext> entry:contexts.entrySet())result.put(entry.getKey(),OrganizationCodec.snapshotState(messageId(),state,organizationRevision,basisRevision,entry.getValue(),version,gameplay.getAsLong()));return result;
    }
    private void snapshot(String seat) throws Exception {require(contexts.containsKey(seat));sender.send(seat,Kind.SNAPSHOT,OrganizationCodec.snapshotState(messageId(),session.snapshot().state,session.snapshot().organizationRevision,session.snapshot().basisRevision,contexts.get(seat),version,gameplay.getAsLong()));}
    private void broadcast(Map<String,String> snapshots) throws Exception {for(String seat:new TreeSet<>(negotiated))sender.send(seat,Kind.SNAPSHOT,snapshots.get(seat));}
    public void connected(String seat) throws Exception {
        owned();require(contexts.containsKey(seat));connected.add(seat);negotiated.remove(seat);
        JsonObject message=new JsonObject(),body=new JsonObject();JsonArray versions=new JsonArray();versions.add(1);body.add("versions",versions);message.addProperty("wire_version",1);message.addProperty("organization_version",1);message.addProperty("message_type","organization_capabilities");message.addProperty("message_id",messageId());message.add("body",body);
        sender.send(seat,Kind.CONTROL,wire(OrganizationMessages.serialize(message,null)));
    }
    private String wire(String raw) throws IOException {return version==3?OrganizationV3Messages.upgrade(raw,gameplay.getAsLong()):raw;}
    private JsonObject parse(String raw) throws IOException {return version==3?OrganizationV3Messages.parseContract(raw):OrganizationMessages.parseContract(raw);}
    public void disconnected(String seat){owned();connected.remove(seat);negotiated.remove(seat);}
    private static JsonElement canonical(JsonElement element){
        if(element.isJsonObject()){JsonObject result=new JsonObject();for(String key:new TreeSet<>(element.getAsJsonObject().keySet()))result.add(key,canonical(element.getAsJsonObject().get(key)));return result;}
        if(element.isJsonArray()){JsonArray result=new JsonArray();for(JsonElement item:element.getAsJsonArray())result.add(canonical(item));return result;}return element.deepCopy();
    }
    private void reject(String seat,String commandId,String code,byte[] digest,boolean record) throws Exception {
        String receipt=wire(OrganizationCodec.rejectedReceipt(messageId(),commandId,code,session.snapshot(),contexts.get(seat)));
        if(record)ledger.get(seat).put(commandId,new Record(digest,receipt));sender.send(seat,Kind.RECEIPT,receipt);snapshot(seat);
    }
    /** A newer rules publication has no safe basis yet; still honor the historical ledger. */
    public void rejectUnready(String seat,String raw) throws Exception {
        owned();require(connected.contains(seat) && negotiated.contains(seat));JsonObject message=parse(raw);require(message.get("message_type").getAsString().equals("organization_command"));JsonObject body=message.getAsJsonObject("body");String id=body.get("command_id").getAsString();byte[] digest=MessageDigest.getInstance("SHA-256").digest(canonical(body).toString().getBytes(StandardCharsets.UTF_8));Map<String,Record> records=ledger.get(seat);Record previous=records.get(id);
        if(previous!=null){if(MessageDigest.isEqual(previous.digest,digest))sender.send(seat,Kind.RECEIPT,previous.receipt);else reject(seat,id,"COMMAND_CONFLICT",digest,false);return;}
        boolean capacity=records.size()>=COMMAND_LIMIT;reject(seat,id,capacity?"COMMAND_LIMIT_REACHED":"STALE_BASIS_REVISION",digest,!capacity);
    }
    public void receive(String seat,String raw) throws Exception {
        owned();require(connected.contains(seat));JsonObject message=parse(raw);String type=message.get("message_type").getAsString();JsonObject body=message.getAsJsonObject("body");
        if(type.equals("organization_capabilities")){
            List<Integer> peer=new ArrayList<>();for(JsonElement version:body.getAsJsonArray("versions"))peer.add(version.getAsInt());
            if(peer.contains(version)){negotiated.add(seat);snapshot(seat);}else negotiated.remove(seat);return;
        }
        require(type.equals("organization_command") && negotiated.contains(seat));String commandId=body.get("command_id").getAsString();
        byte[] digest=MessageDigest.getInstance("SHA-256").digest(canonical(body).toString().getBytes(StandardCharsets.UTF_8));Map<String,Record> records=ledger.get(seat);Record previous=records.get(commandId);
        // A known command is replayed before checking today's revisions or handles.
        if(previous!=null){if(MessageDigest.isEqual(previous.digest,digest))sender.send(seat,Kind.RECEIPT,previous.receipt);else reject(seat,commandId,"COMMAND_CONFLICT",digest,false);return;}
        if(records.size()>=COMMAND_LIMIT){reject(seat,commandId,"COMMAND_LIMIT_REACHED",digest,false);return;}
        BattlefieldOrganizationSession.Snapshot before=session.snapshot();String code=null;
        if(!body.get("match_epoch").getAsString().equals(before.matchEpoch))code="FOREIGN_MATCH";
        else if(body.get("expected_organization_revision").getAsLong()!=before.organizationRevision)code="STALE_ORGANIZATION_REVISION";
        else if(body.get("basis_revision").getAsLong()!=before.basisRevision)code="STALE_BASIS_REVISION";
        JsonObject operation=body.getAsJsonObject("operation");Set<String> handles=new HashSet<>();
        if(code==null)for(JsonElement token:operation.getAsJsonArray("members")){
            String handle=token.getAsString();OrganizationCodec.Binding binding=contexts.get(seat).bindings.get(handle);
            if(!handles.add(handle)){code="DUPLICATE_SELECTION";break;}if(binding==null){code="UNKNOWN_MEMBER_HANDLE";break;}if(!binding.hostSeat.equals(seat)){code="MEMBER_NOT_OWNED_OR_ELIGIBLE";break;}
        }
        if(code!=null){reject(seat,commandId,code,digest,true);return;}
        OrganizationCodec.DecodedCommand decoded;
        try{decoded=OrganizationCodec.command(raw,contexts.get(seat),seat,version);}catch(IOException invalid){reject(seat,commandId,"INVALID_OPERATION",digest,true);return;}
        Operation actual=decoded.operation;
        if(actual.kind==BattlefieldOrganizationService.Kind.MOVE && actual.groupId==null){
            Set<String> moving=new HashSet<>(actual.members),admitted=new HashSet<>();for(OrganizationCodec.Binding binding:contexts.get(seat).bindings.values()){Member member=before.state.basis.members.get(binding.incarnation);if(member!=null && member.eligible)admitted.add(binding.incarnation);}
            List<String> remaining=new ArrayList<>(),visible=new ArrayList<>();for(String member:before.state.seats.get(seat).root)if(!moving.contains(member)){remaining.add(member);if(admitted.contains(member))visible.add(member);}
            if(actual.index<0 || actual.index>visible.size()){reject(seat,commandId,"INVALID_INDEX",digest,true);return;}
            actual=Operation.move(actual.members,null,actual.index==visible.size()?remaining.size():remaining.indexOf(visible.get(actual.index)));
        }
        State candidate;
        try{candidate=BattlefieldOrganizationService.apply(before.state,seat,actual,before.state.basis);}catch(Rejected invalid){reject(seat,commandId,invalid.getMessage(),digest,true);return;}
        boolean changed=!candidate.seats.equals(before.state.seats);if(changed && before.organizationRevision==Long.MAX_VALUE){reject(seat,commandId,"ORGANIZATION_REVISION_EXHAUSTED",digest,true);return;}
        Map<String,String> snapshots;
        try{snapshots=changed?render(candidate,before.organizationRevision+1,before.basisRevision,contexts):Collections.emptyMap();}catch(IOException invalid){reject(seat,commandId,"ORGANIZATION_LIMIT_REACHED",digest,true);return;}
        BattlefieldOrganizationSession.Result result=session.apply(seat,decoded.expectedOrganizationRevision,decoded.basisRevision,actual);
        String receipt=wire(OrganizationCodec.receipt(messageId(),commandId,result,contexts.get(seat)));records.put(commandId,new Record(digest,receipt));sender.send(seat,Kind.RECEIPT,receipt);
        if(result.organizationChanged)broadcast(snapshots);else snapshot(seat);
    }
    public final class PreparedBasis {
        private final BattlefieldOrganizationSession.PreparedBasis prepared;
        private final Map<String,OrganizationCodec.HostContext> checked;private final Map<String,String> snapshots;
        private PreparedBasis(BattlefieldOrganizationSession.PreparedBasis prepared,Map<String,OrganizationCodec.HostContext> checked,Map<String,String> snapshots){this.prepared=prepared;this.checked=checked;this.snapshots=snapshots;}
        public BattlefieldOrganizationSession.Result commit() throws Exception {owned();BattlefieldOrganizationSession.Result result=prepared.commit();contexts=checked;broadcast(snapshots);return result;}
    }
    public PreparedBasis prepareBasis(Basis basis,long revision,Map<String,OrganizationCodec.HostContext> nextContexts) throws Exception {
        owned();require(revision>session.snapshot().basisRevision);
        BattlefieldOrganizationSession.PreparedBasis prepared=session.prepareBasis(basis,revision);
        require(prepared.result.outcome==BattlefieldOrganizationSession.Outcome.APPLIED);
        Map<String,OrganizationCodec.HostContext> checked=checkedContexts(nextContexts,basis,revision);
        BattlefieldOrganizationSession.Snapshot after=prepared.result.snapshot;
        return new PreparedBasis(prepared,checked,render(after.state,after.organizationRevision,revision,checked));
    }
    public BattlefieldOrganizationSession.Result updateBasis(Basis basis,long revision,Map<String,OrganizationCodec.HostContext> nextContexts) throws Exception {
        owned();BattlefieldOrganizationSession.Snapshot before=session.snapshot();
        if(basis==null || !basis.matchEpoch.equals(before.matchEpoch) || revision<=before.basisRevision)return session.updateBasis(basis,revision);
        return prepareBasis(basis,revision,nextContexts).commit();
    }
    /** Immutable host snapshot, not a viewer DTO. */
    public BattlefieldOrganizationSession.Snapshot snapshot(){return session.snapshot();}
    public void close(){owned();closed=true;negotiated.clear();connected.clear();ledger.clear();contexts=Collections.emptyMap();session.close();}
}

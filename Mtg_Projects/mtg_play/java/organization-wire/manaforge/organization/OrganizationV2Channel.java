package manaforge.organization;
import com.google.gson.*;
import java.util.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;
/** Wire adapter; ledger, admission and ownership stay in the existing channel. */
public final class OrganizationV2Channel implements ViewerChannelExtension {
    private final OrganizationChannel inner;private long gameplayRevision;
    public OrganizationV2Channel(Sender sender,Basis basis,long revision,long gameplay,Map<String,OrganizationCodec.HostContext> contexts) throws Exception {
        for(OrganizationCodec.HostContext context:contexts.values())OrganizationV2Messages.upgrade(OrganizationCodec.snapshotState("initial",BattlefieldOrganizationService.create(basis),0,revision,context),gameplay);
        gameplayRevision=gameplay;inner=new OrganizationChannel((seat,kind,raw)->sender.send(seat,kind,OrganizationV2Messages.upgrade(raw,gameplayRevision)),basis,revision,contexts);
    }
    public void update(Basis basis,long revision,long gameplay,Map<String,OrganizationCodec.HostContext> contexts) throws Exception {
        BattlefieldOrganizationSession.Snapshot before=inner.snapshot();State candidate=BattlefieldOrganizationService.reconcile(before.state,basis);long next=before.organizationRevision+(candidate.seats.equals(before.state.seats)?0:1);
        for(OrganizationCodec.HostContext context:contexts.values())OrganizationV2Messages.upgrade(OrganizationCodec.snapshotState("preflight",candidate,next,revision,context),gameplay);
        OrganizationChannel.PreparedBasis prepared=inner.prepareBasis(basis,revision,contexts);gameplayRevision=gameplay;prepared.commit();
    }
    public void connected(String seat) throws Exception {inner.connected(seat);}
    public void receive(String seat,String raw) throws Exception {
        JsonObject message=OrganizationV2Messages.parseContract(raw);boolean cap=message.get("message_type").getAsString().equals("organization_capabilities");
        if(cap){boolean supports=false;for(JsonElement version:message.getAsJsonObject("body").getAsJsonArray("versions"))supports|=version.getAsInt()==2;if(!supports)throw new java.io.IOException("ORGANIZATION_VERSION");}
        JsonObject legacy=OrganizationV2Messages.legacy(message);if(cap){JsonArray versions=new JsonArray();versions.add(1);legacy.getAsJsonObject("body").add("versions",versions);}inner.receive(seat,legacy.toString());
    }
    public void rejectUnready(String seat,String raw) throws Exception {inner.rejectUnready(seat,OrganizationV2Messages.legacy(OrganizationV2Messages.parseContract(raw)).toString());}
    public void disconnected(String seat){inner.disconnected(seat);}
    public BattlefieldOrganizationSession.Snapshot snapshot(){return inner.snapshot();}
    public void close(){inner.close();}
}

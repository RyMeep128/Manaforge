package manaforge.organization;
import java.util.Map;
import manaforge.protocol.ViewerChannelExtension;
import manaforge.organization.BattlefieldOrganizationService.Basis;
public interface CorrelatedOrganizationChannel extends ViewerChannelExtension {
    void update(Basis basis,long revision,long gameplay,Map<String,OrganizationCodec.HostContext> contexts) throws Exception;
    void rejectUnready(String seat,String raw) throws Exception;
    BattlefieldOrganizationSession.Snapshot snapshot();
}

package manaforge.organization;
import java.util.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;
/** V3 sessions use one version for all recipients; no mixed-mode negotiation. */
public final class OrganizationV3Channel implements CorrelatedOrganizationChannel {
    private final OrganizationChannel inner;private long gameplay;
    public OrganizationV3Channel(Sender sender,Basis basis,long revision,long gameplay,Map<String,OrganizationCodec.HostContext> contexts) throws Exception {this.gameplay=gameplay;inner=new OrganizationChannel(sender,basis,revision,contexts,3,()->this.gameplay);}
    public void update(Basis basis,long revision,long gameplay,Map<String,OrganizationCodec.HostContext> contexts) throws Exception {long previous=this.gameplay;this.gameplay=gameplay;try{inner.prepareBasis(basis,revision,contexts).commit();}catch(Exception failure){this.gameplay=previous;throw failure;}}
    public void connected(String seat) throws Exception {inner.connected(seat);}
    public void receive(String seat,String raw) throws Exception {inner.receive(seat,raw);}
    public void rejectUnready(String seat,String raw) throws Exception {inner.rejectUnready(seat,raw);}
    public void disconnected(String seat){inner.disconnected(seat);}
    public BattlefieldOrganizationSession.Snapshot snapshot(){return inner.snapshot();}
    public void close(){inner.close();}
}

package manaforge.organization;

import java.util.Objects;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** One serialized host owner. This is not authentication or a network endpoint. */
public final class BattlefieldOrganizationSession implements AutoCloseable {
    public enum Outcome { APPLIED, REJECTED }
    public static final class Snapshot {
        public final String matchEpoch;
        public final long organizationRevision,basisRevision;
        public final State state;
        private Snapshot(State state,long organizationRevision,long basisRevision){this.state=state;matchEpoch=state.basis.matchEpoch;this.organizationRevision=organizationRevision;this.basisRevision=basisRevision;}
    }
    public static final class Result {
        public final Outcome outcome;
        public final String reasonCode;
        public final boolean organizationChanged;
        public final Snapshot snapshot;
        private Result(Outcome outcome,String reasonCode,boolean changed,Snapshot snapshot){this.outcome=outcome;this.reasonCode=reasonCode;organizationChanged=changed;this.snapshot=snapshot;}
    }
    private final Thread owner=Thread.currentThread();
    private volatile Snapshot current;
    public BattlefieldOrganizationSession(Basis basis,long basisRevision){
        if(basisRevision<0)throw new IllegalArgumentException("INVALID_BASIS_REVISION");
        current=new Snapshot(create(Objects.requireNonNull(basis)),0,basisRevision);
    }
    private Snapshot owned(){
        if(Thread.currentThread()!=owner)throw new IllegalStateException("ORGANIZATION_OWNER_THREAD");
        return snapshot();
    }
    /** Immutable historical snapshots can be read and retained by other threads. */
    public Snapshot snapshot(){Snapshot value=current;if(value==null)throw new IllegalStateException("ORGANIZATION_CLOSED");return value;}
    private Result rejected(String code,Snapshot snapshot){return new Result(Outcome.REJECTED,code,false,snapshot);}
    public Result apply(String trustedActorSeat,long expectedOrganizationRevision,long expectedBasisRevision,Operation operation){
        Snapshot before=owned();
        if(expectedOrganizationRevision!=before.organizationRevision)return rejected("STALE_ORGANIZATION_REVISION",before);
        if(expectedBasisRevision!=before.basisRevision)return rejected("STALE_BASIS_REVISION",before);
        if(operation==null)return rejected("INVALID_OPERATION",before);
        final State next;
        try{next=BattlefieldOrganizationService.apply(before.state,trustedActorSeat,operation,before.state.basis);}
        catch(Rejected invalid){return rejected(invalid.getMessage(),before);}
        boolean changed=!next.seats.equals(before.state.seats);
        if(changed && before.organizationRevision==Long.MAX_VALUE)return rejected("ORGANIZATION_REVISION_EXHAUSTED",before);
        Snapshot after=changed?new Snapshot(next,before.organizationRevision+1,before.basisRevision):before;
        current=after;return new Result(Outcome.APPLIED,null,changed,after);
    }
    public void close(){
        if(Thread.currentThread()!=owner)throw new IllegalStateException("ORGANIZATION_OWNER_THREAD");
        current=null;
    }
}

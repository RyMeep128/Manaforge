package manaforge.organization;

import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import static manaforge.organization.BattlefieldOrganizationService.*;
import static manaforge.organization.BattlefieldOrganizationSession.*;

/** Hosted-only session checks. No native engine, network or Unity ownership. */
public final class OrganizationSessionChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static Basis basis(){return new Basis("match",Arrays.asList("a","b"),Arrays.asList(new Member("p","a",true),new Member("q","b",true)));}
    static Result edit(BattlefieldOrganizationSession session,String seat,Operation operation){Snapshot current=session.snapshot();return session.apply(seat,current.organizationRevision,current.basisRevision,operation);}
    static void rejected(Result result,String code,Snapshot before){check(result.outcome==Outcome.REJECTED && code.equals(result.reasonCode) && !result.organizationChanged && result.snapshot==before,"REJECTION_"+code);}
    static void fails(Runnable action,String code){try{action.run();}catch(IllegalStateException expected){check(code.equals(expected.getMessage()),"WRONG_STATE_FAILURE");return;}throw new AssertionError("EXPECTED_"+code);}
    static void edits(){
        try(BattlefieldOrganizationSession session=new BattlefieldOrganizationSession(basis(),7)){
            Snapshot initial=session.snapshot();check(initial.organizationRevision==0 && initial.basisRevision==7 && initial.matchEpoch.equals("match"),"INITIAL_SNAPSHOT");
            Result create=edit(session,"a",Operation.create("g","Group",.2,.4));check(create.outcome==Outcome.APPLIED && create.organizationChanged && create.reasonCode==null && create.snapshot.organizationRevision==1,"CREATE_REVISION");
            check(initial.state.seats.get("a").groups.isEmpty(),"HISTORICAL_SNAPSHOT_MUTATED");
            Snapshot first=session.snapshot();Result unchanged=edit(session,"a",Operation.rename("g","Group"));check(unchanged.outcome==Outcome.APPLIED && !unchanged.organizationChanged && unchanged.snapshot==first,"NOOP_ADVANCED_REVISION");
            rejected(session.apply("a",0,7,Operation.delete("g")),"STALE_ORGANIZATION_REVISION",first);
            rejected(session.apply("a",1,6,Operation.delete("g")),"STALE_BASIS_REVISION",first);
            rejected(edit(session,"b",Operation.delete("g")),"GROUP_NOT_OWNED",first);
            rejected(edit(session,"a",Operation.move(Arrays.asList("p","q"),"g",0)),"MEMBER_NOT_OWNED_OR_ELIGIBLE",first);
            rejected(edit(session,"a",null),"INVALID_OPERATION",first);
            check(session.snapshot()==first,"REJECTED_EDIT_PUBLISHED");
            Result second=edit(session,"b",Operation.create("other","Opponent",.8,.4));check(second.snapshot.organizationRevision==2,"SECOND_SEAT_REVISION");
            edit(session,"a",Operation.move(Collections.singletonList("p"),"g",0));edit(session,"b",Operation.move(Collections.singletonList("q"),"other",0));
            Snapshot finalState=session.snapshot();check(finalState.organizationRevision==4 && finalState.state.seats.get("a").groups.get(0).members.equals(Collections.singletonList("p")) && finalState.state.seats.get("b").groups.get(0).members.equals(Collections.singletonList("q")),"TWO_SEAT_EDITS");
            check(first.state.seats.get("a").root.equals(Collections.singletonList("p")),"OLD_SNAPSHOT_MEMBERS_MUTATED");
        }
        try{new BattlefieldOrganizationSession(basis(),-1);throw new AssertionError("NEGATIVE_BASIS_REVISION");}catch(IllegalArgumentException expected){check(expected.getMessage().equals("INVALID_BASIS_REVISION"),"INVALID_CONSTRUCTOR_CODE");}
    }
    static void ownershipAndClose() throws Exception {
        BattlefieldOrganizationSession session=new BattlefieldOrganizationSession(basis(),0);Snapshot old=session.snapshot();AtomicReference<Throwable> failure=new AtomicReference<>();
        Thread other=new Thread(()->{try{
            check(session.snapshot()==old,"IMMUTABLE_CROSS_THREAD_READ");
            fails(()->session.apply("a",0,0,Operation.create("g","G",0,0)),"ORGANIZATION_OWNER_THREAD");
            fails(session::close,"ORGANIZATION_OWNER_THREAD");
        }catch(Throwable error){failure.set(error);}},"organization-non-owner");
        other.start();other.join(5000);check(!other.isAlive(),"THREAD_CHECK_TIMEOUT");if(failure.get()!=null)throw new AssertionError("THREAD_CHECK_FAILED",failure.get());
        check(session.snapshot()==old,"FOREIGN_THREAD_MUTATED_STATE");session.close();session.close();
        fails(session::snapshot,"ORGANIZATION_CLOSED");fails(()->session.apply("a",0,0,Operation.create("g","G",0,0)),"ORGANIZATION_CLOSED");
        check(old.state.seats.get("a").root.equals(Collections.singletonList("p")),"CLOSE_MUTATED_HISTORICAL_SNAPSHOT");
    }
    public static void main(String[] args) throws Exception {edits();ownershipAndClose();System.out.println("Organization session edit admission, revisions, immutable snapshots and ownership passed");}
}

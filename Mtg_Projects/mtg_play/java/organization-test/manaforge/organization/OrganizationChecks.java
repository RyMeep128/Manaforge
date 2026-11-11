package manaforge.organization;

import java.util.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** JDK-only hosted reducer checks; never constructs XMage or Unity. */
public final class OrganizationChecks {
    static void check(boolean condition,String code){if(!condition)throw new AssertionError(code);}
    static void rejects(Runnable operation,String code){try{operation.run();}catch(Rejected expected){return;}throw new AssertionError(code);}
    static Basis basis(){return new Basis("match",Arrays.asList("a","b"),Arrays.asList(new Member("p1","a",true),new Member("p2","a",true),new Member("p3","a",true),new Member("q1","b",true)));}
    static State edit(State state,Operation operation){return apply(state,"a",operation,state.basis);}
    static Group group(State state,String id){return state.seats.get("a").groups.stream().filter(g->g.id.equals(id)).findFirst().orElseThrow(()->new AssertionError("GROUP_MISSING"));}
    static void manual(){
        State initial=create(basis());State state=edit(initial,Operation.create("mana"," Mana Sources ",.2,.3));
        check(group(state,"mana").name.equals("Mana Sources") && group(state,"mana").members.isEmpty(),"CREATE_GROUP");
        check(initial.seats.get("a").groups.isEmpty(),"INPUT_MUTATED");
        state=edit(state,Operation.create("engine","Engine",.6,.4));
        state=edit(state,Operation.reorder("engine",0));check(state.seats.get("a").groups.get(0).id.equals("engine"),"REORDER_GROUP");
        state=edit(state,Operation.rename("mana","Lands"));state=edit(state,Operation.position("mana",1,0));
        check(group(state,"mana").name.equals("Lands") && group(state,"mana").x==1 && group(state,"mana").y==0,"RENAME_POSITION");
        state=edit(state,Operation.move(Arrays.asList("p3","p1"),"mana",0));check(group(state,"mana").members.equals(Arrays.asList("p3","p1")),"SELECTION_ORDER");
        check(state.seats.get("a").root.equals(Collections.singletonList("p2")),"ROOT_REMOVAL");
        state=edit(state,Operation.move(Collections.singletonList("p3"),"mana",1));check(group(state,"mana").members.equals(Arrays.asList("p1","p3")),"REORDER_MEMBER");
        state=edit(state,Operation.move(Collections.singletonList("p1"),"engine",0));
        state=edit(state,Operation.move(Collections.singletonList("p1"),null,1));check(group(state,"engine").members.isEmpty(),"EMPTY_GROUP_PRESERVED");
        state=edit(state,Operation.delete("mana"));check(state.seats.get("a").root.equals(Arrays.asList("p2","p1","p3")),"DELETE_REPARENTS_IN_ORDER");
        check(state.seats.get("b").equals(initial.seats.get("b")),"FOREIGN_SEAT_CHANGED");state.validate();
        try{state.seats.get("a").root.add("bad");throw new AssertionError("MUTABLE_ROOT");}catch(UnsupportedOperationException expected){}
        try{state.seats.clear();throw new AssertionError("MUTABLE_STATE");}catch(UnsupportedOperationException expected){}
    }
    static void rejection(){
        State state=edit(create(basis()),Operation.create("g","Group",0,1));State before=state;
        List<Operation> invalid=Arrays.asList(Operation.create("g","Duplicate",0,0),Operation.create("bad"," ",0,0),Operation.position("g",Double.NaN,.2),Operation.position("g",.2,Double.POSITIVE_INFINITY),Operation.position("g",-.1,.2),Operation.position("g",.2,1.1),Operation.rename("missing","Name"),Operation.delete("missing"),Operation.reorder("g",1),Operation.move(Arrays.asList("p1","p1"),"g",0),Operation.move(Arrays.asList("p1","q1"),"g",0),Operation.move(Arrays.asList("p1","departed"),"g",0),Operation.move(Collections.singletonList("p1"),"g",1),Operation.move(Collections.singletonList("p1"),null,-1),Operation.move(Collections.emptyList(),"g",0));
        for(Operation operation:invalid){rejects(()->edit(state,operation),"INVALID_ACCEPTED_"+operation.kind);check(state.equals(before),"REJECT_MUTATED_INPUT");state.validate();}
        rejects(()->apply(state,"b",Operation.rename("g","Stolen"),state.basis),"CROSS_SEAT_GROUP");
        rejects(()->apply(state,"b",Operation.create("g","Collision",0,0),state.basis),"GLOBAL_GROUP_ID_COLLISION");
        rejects(()->apply(state,"stranger",Operation.create("x","X",0,0),state.basis),"UNKNOWN_ACTOR");
        Basis stale=new Basis("match",Arrays.asList("a","b"),Collections.singletonList(new Member("p1","a",true)));
        rejects(()->apply(state,"a",Operation.rename("g","Stale"),stale),"STALE_BASIS");
        Basis hidden=new Basis("match",Arrays.asList("a","b"),Collections.singletonList(new Member("p1","a",false)));State concealed=create(hidden);
        rejects(()->edit(concealed,Operation.move(Collections.singletonList("p1"),null,0)),"INELIGIBLE_MOVE");
    }
    static void lifecycle(){
        State original=edit(create(basis()),Operation.create("g","Keep empty",.25,.75));original=edit(original,Operation.move(Arrays.asList("p3","p1"),"g",0));
        check(reconcile(original,original.basis).equals(original),"UNCHANGED_BASIS_CHANGED_LAYOUT");
        Basis changed=new Basis("match",Arrays.asList("b","a"),Arrays.asList(new Member("p2","a",true),new Member("p3","b",true),new Member("q1","b",false),new Member("n2","a",true),new Member("n1","a",true)));
        State next=reconcile(original,changed);
        check(next.seats.get("a").root.equals(Arrays.asList("p2","n1","n2")),"ORDERED_ARRIVALS");
        check(next.seats.get("b").root.equals(Arrays.asList("q1","p3")),"CONTROL_TRANSFER_ROOT");
        check(group(next,"g").members.isEmpty() && group(next,"g").name.equals("Keep empty") && group(next,"g").x==.25,"EMPTY_GROUP_LOST");
        check(group(original,"g").members.equals(Arrays.asList("p3","p1")),"RECONCILE_MUTATED_INPUT");
        rejects(()->apply(next,"a",Operation.move(Collections.singletonList("p1"),"g",0),next.basis),"DEPARTED_SELECTION");
        rejects(()->apply(next,"a",Operation.move(Collections.singletonList("p3"),"g",0),next.basis),"TRANSFERRED_SELECTION");
        rejects(()->apply(next,"a",Operation.rename("g","Old basis"),basis()),"OLD_BASIS_ACCEPTED");
        Basis hidden=new Basis("match",Arrays.asList("a","b"),Arrays.asList(new Member("p1","a",false),new Member("p2","a",true),new Member("p3","a",true),new Member("q1","b",true)));
        State concealed=reconcile(original,hidden);
        check(group(concealed,"g").members.equals(Collections.singletonList("p3")) && concealed.seats.get("a").root.equals(Arrays.asList("p2","p1")),"CONCEALED_CUSTOM_MEMBERSHIP");
        State revealed=reconcile(concealed,basis());check(group(revealed,"g").members.equals(Collections.singletonList("p3")) && revealed.seats.get("a").root.equals(Arrays.asList("p2","p1")),"REVEAL_RESTORED_MANUAL_MEMBERSHIP");
        Basis blinked=new Basis("match",Arrays.asList("a","b"),Arrays.asList(new Member("p1-new","a",true),new Member("p2","a",true),new Member("p3","a",true),new Member("q1","b",true)));
        State blink=reconcile(original,blinked);check(group(blink,"g").members.equals(Collections.singletonList("p3")) && blink.seats.get("a").root.equals(Arrays.asList("p2","p1-new")),"BLINK_INHERITED_MEMBERSHIP");
        State stable=original;
        rejects(()->reconcile(stable,new Basis("other-match",Arrays.asList("a","b"),Collections.emptyList())),"FOREIGN_RECONCILE");
        rejects(()->reconcile(stable,new Basis("match",Collections.singletonList("a"),Collections.emptyList())),"ROSTER_CHANGE_ACCEPTED");
        next.validate();concealed.validate();revealed.validate();blink.validate();
    }
    static String fingerprint(State state){
        StringBuilder out=new StringBuilder(state.basis.matchEpoch);
        for(Member m:state.basis.members.values())out.append('|').append(m.incarnation).append(':').append(m.controller).append(':').append(m.eligible);
        for(Map.Entry<String,Seat> seat:state.seats.entrySet()){
            out.append('|').append(seat.getKey()).append(seat.getValue().root);
            for(Group g:seat.getValue().groups)out.append('|').append(g.id).append(':').append(g.name).append(':').append(g.x).append(':').append(g.y).append(g.members);
        }
        return out.toString();
    }
    static State generated(long seed){
        Random random=new Random(seed);State state=create(basis());int applied=0,rejected=0,reconciled=0;
        for(int step=0;step<400;step++){
            State before=state;String snapshot=fingerprint(before);String actor=random.nextBoolean()?"a":"b";Seat seat=state.seats.get(actor);int kind=random.nextInt(9);
            try{
                if(kind==8){
                    List<Member> members=new ArrayList<>(state.basis.members.values());int mutation=random.nextInt(4);
                    if(!members.isEmpty() && mutation!=3){int at=random.nextInt(members.size());Member old=members.get(at);
                        if(mutation==0)members.remove(at);else members.set(at,new Member(old.incarnation,mutation==1?(old.controller.equals("a")?"b":"a"):old.controller,mutation==2?!old.eligible:old.eligible));
                    }else members.add(new Member("arrival-"+step,actor,true));
                    Collections.shuffle(members,random);state=reconcile(state,new Basis("match",Arrays.asList("b","a"),members));reconciled++;
                }else{
                    String target=seat.groups.isEmpty()?"missing":seat.groups.get(random.nextInt(seat.groups.size())).id;Operation operation;
                    switch(kind){
                        case 0:operation=Operation.create("g-"+step,"Group "+step,random.nextDouble(),random.nextDouble());break;
                        case 1:operation=Operation.rename(target,"Renamed "+step);break;
                        case 2:operation=Operation.position(target,random.nextDouble(),random.nextDouble());break;
                        case 3:operation=Operation.delete(target);break;
                        case 4:operation=Operation.reorder(target,seat.groups.isEmpty()?0:random.nextInt(seat.groups.size()));break;
                        case 5:operation=Operation.move(Arrays.asList("p1","p1"),target,0);break;
                        case 6:operation=Operation.position(target,Double.NaN,.5);break;
                        default:
                            List<String> eligible=new ArrayList<>();for(Member m:state.basis.members.values())if(m.controller.equals(actor) && m.eligible)eligible.add(m.incarnation);
                            Collections.shuffle(eligible,random);List<String> selected=new ArrayList<>(eligible.subList(0,Math.min(eligible.size(),1+random.nextInt(3))));
                            boolean root=seat.groups.isEmpty() || random.nextBoolean();List<String> destination=root?seat.root:seat.groups.stream().filter(g->g.id.equals(target)).findFirst().get().members;
                            int remaining=0;for(String member:destination)if(!selected.contains(member))remaining++;
                            operation=Operation.move(selected,root?null:target,random.nextInt(remaining+1));break;
                    }
                    state=apply(state,actor,operation,state.basis);applied++;
                }
            }catch(Rejected expected){check(state==before && snapshot.equals(fingerprint(state)),"GENERATED_REJECTION_MUTATED_STATE_"+seed+"_"+step);rejected++;}
            check(snapshot.equals(fingerprint(before)),"GENERATED_OLD_STATE_MUTATED_"+seed+"_"+step);state.validate();
            check(reconcile(state,state.basis).equals(state),"RECONCILE_NOT_IDEMPOTENT_"+seed+"_"+step);
        }
        check(applied>0 && rejected>0 && reconciled>0,"GENERATED_COVERAGE");return state;
    }
    static void defensiveCopies(){
        List<Member> members=new ArrayList<>(Collections.singletonList(new Member("p","a",true)));List<String> roster=new ArrayList<>(Arrays.asList("a","b"));
        Basis basis=new Basis("match",roster,members);members.clear();roster.clear();State state=create(basis);
        List<String> selection=new ArrayList<>(Collections.singletonList("p"));Operation move=Operation.move(selection,null,0);selection.clear();
        check(edit(state,move).seats.get("a").root.equals(Collections.singletonList("p")),"DEFENSIVE_COPY");
        rejects(()->apply(state,null,Operation.create("g","G",0,0),basis),"NULL_ACTOR");
        rejects(()->edit(state,Operation.move(Collections.singletonList(null),null,0)),"NULL_MEMBER");
        try{basis.members.clear();throw new AssertionError("MUTABLE_BASIS");}catch(UnsupportedOperationException expected){}
        try{move.members.clear();throw new AssertionError("MUTABLE_OPERATION");}catch(UnsupportedOperationException expected){}
    }
    public static void main(String[] args){
        manual();rejection();lifecycle();defensiveCopies();
        for(long seed=2026111100L;seed<2026111116L;seed++){State first=generated(seed),replay=generated(seed);check(first.equals(replay) && first.hashCode()==replay.hashCode(),"NONDETERMINISTIC_REPLAY_"+seed);System.out.println("Organization retained seed passed: "+seed);}
        System.out.println("Organization manual operations, lifecycle reconciliation, atomic rejection and deterministic replay passed");
    }
}

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
    public static void main(String[] args){manual();rejection();System.out.println("Organization manual operations, atomic rejection and immutable ownership passed");}
}

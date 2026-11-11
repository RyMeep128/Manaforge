package manaforge.organization;

import java.util.*;

/** Pure host-side organization. No native objects, transport, game actions or IO. */
public final class BattlefieldOrganizationService {
    private BattlefieldOrganizationService(){}
    public static final class Rejected extends IllegalArgumentException {
        public Rejected(String code){super(code);}
    }
    private static void require(boolean value,String code){if(!value)throw new Rejected(code);}
    private static String id(String value){require(value!=null && !value.isEmpty() && value.equals(value.trim()),"INVALID_ID");return value;}
    private static String name(String value){require(value!=null && !value.trim().isEmpty(),"INVALID_NAME");return value.trim();}
    private static void position(double x,double y){require(Double.isFinite(x) && Double.isFinite(y) && x>=0 && x<=1 && y>=0 && y<=1,"INVALID_POSITION");}
    private static <T> List<T> frozen(Collection<T> values){return Collections.unmodifiableList(new ArrayList<>(values));}

    public static final class Member {
        public final String incarnation,controller;
        public final boolean eligible;
        public Member(String incarnation,String controller,boolean eligible){this.incarnation=id(incarnation);this.controller=id(controller);this.eligible=eligible;}
        @Override public boolean equals(Object other){if(!(other instanceof Member))return false;Member m=(Member)other;return incarnation.equals(m.incarnation) && controller.equals(m.controller) && eligible==m.eligible;}
        @Override public int hashCode(){return Objects.hash(incarnation,controller,eligible);}
    }
    /** Server-owned immutable basis, not a client-supplied authorization document. */
    public static final class Basis {
        public final String matchEpoch;
        public final Set<String> seats;
        public final Map<String,Member> members;
        public Basis(String matchEpoch,Collection<String> seats,Collection<Member> members){
            this.matchEpoch=id(matchEpoch);Set<String> roster=new TreeSet<>();
            for(String seat:seats)require(roster.add(id(seat)),"DUPLICATE_SEAT");require(!roster.isEmpty(),"EMPTY_ROSTER");
            Map<String,Member> objects=new TreeMap<>();for(Member member:members){require(member!=null && roster.contains(member.controller),"UNKNOWN_CONTROLLER");require(objects.put(member.incarnation,member)==null,"DUPLICATE_MEMBER");}
            this.seats=Collections.unmodifiableSet(roster);this.members=Collections.unmodifiableMap(objects);
        }
        @Override public boolean equals(Object other){if(!(other instanceof Basis))return false;Basis b=(Basis)other;return matchEpoch.equals(b.matchEpoch) && seats.equals(b.seats) && members.equals(b.members);}
        @Override public int hashCode(){return Objects.hash(matchEpoch,seats,members);}
    }
    public static final class Group {
        public final String id,name;
        public final double x,y;
        public final List<String> members;
        private Group(String id,String name,double x,double y,Collection<String> members){this.id=id(id);this.name=name(name);position(x,y);this.x=x;this.y=y;this.members=frozen(members);}
        private Group withMembers(Collection<String> members){return new Group(id,name,x,y,members);}
        @Override public boolean equals(Object other){if(!(other instanceof Group))return false;Group g=(Group)other;return id.equals(g.id) && name.equals(g.name) && Double.compare(x,g.x)==0 && Double.compare(y,g.y)==0 && members.equals(g.members);}
        @Override public int hashCode(){return Objects.hash(id,name,x,y,members);}
    }
    public static final class Seat {
        public final List<String> root;
        public final List<Group> groups;
        private Seat(Collection<String> root,Collection<Group> groups){this.root=frozen(root);this.groups=frozen(groups);}
        @Override public boolean equals(Object other){if(!(other instanceof Seat))return false;Seat s=(Seat)other;return root.equals(s.root) && groups.equals(s.groups);}
        @Override public int hashCode(){return Objects.hash(root,groups);}
    }
    public static final class State {
        public final Basis basis;
        public final Map<String,Seat> seats;
        private State(Basis basis,Map<String,Seat> seats){this.basis=Objects.requireNonNull(basis);this.seats=Collections.unmodifiableMap(new TreeMap<>(seats));validate();}
        /** Also used by retained-seed hosted checks. Every live object has one location. */
        public void validate(){
            require(seats.keySet().equals(basis.seats),"ROSTER_MISMATCH");Set<String> seen=new HashSet<>(),groups=new HashSet<>();
            for(Map.Entry<String,Seat> entry:seats.entrySet()){
                for(String member:entry.getValue().root)validateMember(member,entry.getKey(),false,seen);
                for(Group group:entry.getValue().groups){require(groups.add(group.id),"DUPLICATE_GROUP");for(String member:group.members)validateMember(member,entry.getKey(),true,seen);}
            }
            require(seen.equals(basis.members.keySet()),"MISSING_MEMBERS");
        }
        private void validateMember(String id,String seat,boolean grouped,Set<String> seen){Member member=basis.members.get(id);require(member!=null && member.controller.equals(seat) && (!grouped || member.eligible),"INVALID_MEMBERSHIP");require(seen.add(id),"DUPLICATE_MEMBERSHIP");}
        @Override public boolean equals(Object other){if(!(other instanceof State))return false;State s=(State)other;return basis.equals(s.basis) && seats.equals(s.seats);}
        @Override public int hashCode(){return Objects.hash(basis,seats);}
    }
    public enum Kind { CREATE, RENAME, DELETE, POSITION, REORDER, MOVE }
    public static final class Operation {
        public final Kind kind;
        public final String groupId,name;
        public final double x,y;
        public final int index;
        public final List<String> members;
        private Operation(Kind kind,String group,String name,double x,double y,int index,Collection<String> members){this.kind=kind;groupId=group;this.name=name;this.x=x;this.y=y;this.index=index;this.members=frozen(members);}
        public static Operation create(String group,String name,double x,double y){return new Operation(Kind.CREATE,group,name,x,y,0,Collections.emptyList());}
        public static Operation rename(String group,String name){return new Operation(Kind.RENAME,group,name,0,0,0,Collections.emptyList());}
        public static Operation delete(String group){return new Operation(Kind.DELETE,group,null,0,0,0,Collections.emptyList());}
        public static Operation position(String group,double x,double y){return new Operation(Kind.POSITION,group,null,x,y,0,Collections.emptyList());}
        public static Operation reorder(String group,int index){return new Operation(Kind.REORDER,group,null,0,0,index,Collections.emptyList());}
        /** Null group means default root. Index is measured after selected objects are removed. */
        public static Operation move(Collection<String> members,String group,int index){return new Operation(Kind.MOVE,group,null,0,0,index,members);}
    }
    public static State create(Basis basis){
        Map<String,Seat> seats=new TreeMap<>();for(String seat:basis.seats){List<String> root=new ArrayList<>();for(Member member:basis.members.values())if(member.controller.equals(seat))root.add(member.incarnation);seats.put(seat,new Seat(root,Collections.emptyList()));}return new State(basis,seats);
    }
    public static State apply(State state,String trustedActorSeat,Operation operation,Basis battlefieldBasis){
        require(state!=null && operation!=null && state.basis.equals(battlefieldBasis),"STALE_BASIS");require(state.seats.containsKey(trustedActorSeat),"UNKNOWN_ACTOR");
        Seat original=state.seats.get(trustedActorSeat);List<String> root=new ArrayList<>(original.root);List<Group> groups=new ArrayList<>(original.groups);
        int selected=-1;for(int i=0;i<groups.size();i++)if(groups.get(i).id.equals(operation.groupId))selected=i;
        if(operation.kind!=Kind.CREATE && !(operation.kind==Kind.MOVE && operation.groupId==null))require(selected>=0,"GROUP_NOT_OWNED");
        Group group=selected<0?null:groups.get(selected);
        switch(operation.kind){
            case CREATE:
                String groupId=id(operation.groupId);for(Seat seat:state.seats.values())for(Group existing:seat.groups)require(!existing.id.equals(groupId),"DUPLICATE_GROUP");
                groups.add(new Group(groupId,operation.name,operation.x,operation.y,Collections.emptyList()));break;
            case RENAME:groups.set(selected,new Group(group.id,operation.name,group.x,group.y,group.members));break;
            case POSITION:groups.set(selected,new Group(group.id,group.name,operation.x,operation.y,group.members));break;
            case DELETE:root.addAll(group.members);groups.remove(selected);break;
            case REORDER:require(operation.index>=0 && operation.index<groups.size(),"INVALID_INDEX");groups.remove(selected);groups.add(operation.index,group);break;
            case MOVE:
                Set<String> moving=new HashSet<>();require(!operation.members.isEmpty(),"EMPTY_SELECTION");
                for(String memberId:operation.members){Member member=state.basis.members.get(memberId);require(member!=null && member.controller.equals(trustedActorSeat) && member.eligible,"MEMBER_NOT_OWNED_OR_ELIGIBLE");require(moving.add(memberId),"DUPLICATE_SELECTION");}
                root.removeIf(moving::contains);for(int i=0;i<groups.size();i++){Group current=groups.get(i);List<String> members=new ArrayList<>(current.members);members.removeIf(moving::contains);groups.set(i,current.withMembers(members));}
                List<String> destination=selected<0?root:new ArrayList<>(groups.get(selected).members);
                require(operation.index>=0 && operation.index<=destination.size(),"INVALID_INDEX");destination.addAll(operation.index,operation.members);
                if(selected>=0)groups.set(selected,groups.get(selected).withMembers(destination));break;
            default:throw new Rejected("UNKNOWN_OPERATION");
        }
        Map<String,Seat> next=new TreeMap<>(state.seats);next.put(trustedActorSeat,new Seat(root,groups));return new State(state.basis,next);
    }
}

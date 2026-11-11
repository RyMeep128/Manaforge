import java.util.*;

/** Host-only, caller-owned match identity. Not a wire model or game-action authority. */
final class BattlefieldIdentityRegistry implements AutoCloseable {
    static final class Observation {
        final UUID nativeId,controller; final int generation; final boolean eligible;
        Observation(UUID nativeId,int generation,UUID controller){this(nativeId,generation,controller,true);}
        Observation(UUID nativeId,int generation,UUID controller,boolean eligible){this.nativeId=Objects.requireNonNull(nativeId);this.generation=generation;this.controller=Objects.requireNonNull(controller);this.eligible=eligible;}
        String key(){return nativeId+":"+generation;}
    }
    static final class Snapshot {
        final UUID game,viewer; final int cycle;
        final Set<UUID> seats; final List<Observation> permanents; final Map<UUID,String> admitted;
        Snapshot(UUID game,UUID viewer,int cycle,Collection<UUID> seats,Collection<Observation> permanents,Map<UUID,String> admitted){
            this.game=Objects.requireNonNull(game);this.viewer=Objects.requireNonNull(viewer);this.cycle=cycle;
            this.seats=Collections.unmodifiableSet(new LinkedHashSet<>(seats));this.permanents=Collections.unmodifiableList(new ArrayList<>(permanents));this.admitted=Collections.unmodifiableMap(new HashMap<>(admitted));
        }
    }
    static final class Identity {
        final String incarnation,seat; final Observation nativeObject;
        Identity(String incarnation,String seat,Observation object){this.incarnation=incarnation;this.seat=seat;nativeObject=object;}
    }
    static final class Member {
        final String handle,seat,objectReference;
        Member(String handle,String seat,String reference){this.handle=handle;this.seat=seat;objectReference=reference;}
    }
    static final class Result {
        final List<Identity> current; final Set<String> removed;
        Result(Collection<Identity> current,Set<String> removed){this.current=Collections.unmodifiableList(new ArrayList<>(current));this.removed=Collections.unmodifiableSet(new HashSet<>(removed));}
    }
    private final UUID game;
    final String matchEpoch=UUID.randomUUID().toString();
    private final Map<UUID,String> seats=new HashMap<>();
    private Map<String,Identity> live=new LinkedHashMap<>();
    private final Map<UUID,Map<String,Member>> viewers=new HashMap<>();
    private int cycle=-1; private boolean closed;
    BattlefieldIdentityRegistry(UUID game){this.game=Objects.requireNonNull(game);}
    private void validate(Snapshot snapshot){
        if(closed)throw new IllegalStateException("IDENTITY_CLOSED");
        if(!game.equals(snapshot.game) || snapshot.cycle<cycle || !snapshot.seats.contains(snapshot.viewer))throw new IllegalArgumentException("IDENTITY_BASIS");
        Set<UUID> ids=new HashSet<>();
        for(Observation object:snapshot.permanents)if(object.generation<0 || !snapshot.seats.contains(object.controller) || !ids.add(object.nativeId))throw new IllegalArgumentException("IDENTITY_OBSERVATION");
        if(snapshot.cycle==cycle){
            if(snapshot.permanents.size()!=live.size() || !snapshot.seats.equals(seats.keySet()))throw new IllegalArgumentException("IDENTITY_CONFLICTING_BASIS");
            for(Observation object:snapshot.permanents){Identity previous=live.get(object.key());
                if(previous==null || !previous.nativeObject.controller.equals(object.controller) || previous.nativeObject.eligible!=object.eligible)throw new IllegalArgumentException("IDENTITY_CONFLICTING_BASIS");
            }
        }
        if(!ids.containsAll(snapshot.admitted.keySet()) || snapshot.admitted.values().stream().anyMatch(Objects::isNull))throw new IllegalArgumentException("IDENTITY_ADMISSION");
    }
    synchronized Result reconcile(Snapshot snapshot){
        validate(snapshot);
        Map<UUID,String> nextSeats=new HashMap<>(seats);for(UUID seat:snapshot.seats)nextSeats.computeIfAbsent(seat,id->UUID.randomUUID().toString());
        Map<String,Identity> next=new LinkedHashMap<>();
        for(Observation object:snapshot.permanents){Identity previous=live.get(object.key());next.put(object.key(),new Identity(previous==null?UUID.randomUUID().toString():previous.incarnation,nextSeats.get(object.controller),object));}
        Set<String> removed=new HashSet<>();for(Identity old:live.values())if(!next.containsKey(old.nativeObject.key()))removed.add(old.incarnation);
        // Revoke disappeared and transferred objects for every viewer, even before their next projection.
        for(Map<String,Member> handles:viewers.values())handles.entrySet().removeIf(entry->{Identity now=next.get(entry.getKey());return now==null || !now.nativeObject.eligible || !now.seat.equals(entry.getValue().seat);});
        seats.clear();seats.putAll(nextSeats);live=next;cycle=snapshot.cycle;
        return new Result(next.values(),removed);
    }
    synchronized List<Member> project(Snapshot snapshot){
        reconcile(snapshot);
        Map<String,Member> old=viewers.getOrDefault(snapshot.viewer,Collections.emptyMap()),next=new LinkedHashMap<>();
        for(Identity identity:live.values()){
            String reference=snapshot.admitted.get(identity.nativeObject.nativeId);if(reference==null || !identity.nativeObject.eligible)continue;
            Member previous=old.get(identity.nativeObject.key());
            next.put(identity.nativeObject.key(),new Member(previous==null?UUID.randomUUID().toString():previous.handle,identity.seat,reference));
        }
        viewers.put(snapshot.viewer,next);return Collections.unmodifiableList(new ArrayList<>(next.values()));
    }
    synchronized String resolve(UUID viewer,String handle){
        if(closed)return null;for(Member member:viewers.getOrDefault(viewer,Collections.emptyMap()).values())if(member.handle.equals(handle))return member.objectReference;return null;
    }
    synchronized String incarnation(UUID nativeId){for(Identity identity:live.values())if(identity.nativeObject.nativeId.equals(nativeId))return identity.incarnation;return null;}
    synchronized String seat(UUID nativeId){return seats.get(nativeId);}
    public synchronized void close(){closed=true;live.clear();seats.clear();viewers.clear();}
}

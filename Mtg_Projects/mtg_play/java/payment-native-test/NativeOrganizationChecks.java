import com.google.gson.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import mage.cards.Card;
import mage.constants.*;
import mage.game.events.PlayerQueryEvent;
import mage.game.permanent.token.SoldierToken;
import manaforge.organization.BattlefieldOrganizationSession;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;

/** Real pinned game + authenticated sockets. Organization cannot answer native queries. */
public final class NativeOrganizationChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static final class Capture {
        final Map<String,ManaforgeMatchCoordinator.Observation> observations;
        final Map<String,BattlefieldIdentityRegistry.Snapshot> identities=new TreeMap<>();
        Capture(NativePaymentAcceptanceChecks.Engine e,PlayerQueryEvent query,AtomicInteger submissions) throws Exception {
            NativeBattlefieldIdentity.Batch<Map<String,ManaforgeMatchCoordinator.Observation>> batch=NativeBattlefieldIdentity.captureBatchPaused(e.game,Arrays.asList(e.payer.getId(),e.opponent.getId()),views->NativeMultiViewerChecks.observations(e,query,submissions,views));
            observations=batch.value;identities.put("a",batch.identities.get(e.payer.getId()));identities.put("b",batch.identities.get(e.opponent.getId()));
        }
    }
    static final class Peer implements AutoCloseable {
        final String seat;final MatchCoordinatorChecks.Client client;final Set<String> pending=new HashSet<>();
        JsonObject game,state;long revision,basis;String epoch;
        Peer(String seat,ManaforgeMatchCoordinator.Viewer viewer,byte[] key) throws Exception {
            this.seat=seat;client=new MatchCoordinatorChecks.Client(viewer,key,false);
            JsonObject cap=OrganizationMessages.parseContract(raw());check(cap.get("message_type").getAsString().equals("organization_capabilities"),"NATIVE_CAPABILITIES_FIRST");
            client.send("{\"wire_version\":1,\"organization_version\":1,\"message_type\":\"organization_capabilities\",\"message_id\":\"cap\",\"body\":{\"versions\":[1]}}");
        }
        String raw() throws IOException {String raw=TextFrame.read(client.socket.getInputStream());check(raw!=null,"NATIVE_ORGANIZATION_EOF");return raw;}
        void game() throws Exception {game=NativeMultiViewerChecks.snapshot(client.read());}
        void organization() throws Exception {
            String raw=raw();JsonObject message=OrganizationMessages.parseContract(raw),body=message.getAsJsonObject("body");check(message.get("message_type").getAsString().equals("organization_snapshot"),"NATIVE_EXPECTED_SNAPSHOT");
            Map<String,String> objects=new HashMap<>(),seats=new HashMap<>(),admitted=new HashMap<>();Set<String> visibleSeats=new HashSet<>();
            if(game!=null){
                for(JsonElement item:game.getAsJsonArray("players"))visibleSeats.add(item.getAsJsonObject().get("player_id").getAsString());
                for(JsonElement item:game.getAsJsonArray("objects")){JsonObject object=item.getAsJsonObject();if(object.get("zone").getAsString().equals("battlefield") && !object.get("hidden").getAsBoolean() && !object.get("face_down").getAsBoolean())admitted.put(object.get("object_id").getAsString(),object.get("controller_id").getAsString());}
            }else for(JsonElement item:body.getAsJsonArray("seats"))visibleSeats.add(item.getAsJsonObject().get("seat_id").getAsString());
            for(JsonElement item:body.getAsJsonArray("mappings")){JsonObject mapping=item.getAsJsonObject();String handle=mapping.get("handle").getAsString(),reference=mapping.get("object_reference").getAsString(),owner=mapping.get("seat_id").getAsString();check(owner.equals(admitted.get(reference)),"MAPPING_NOT_IN_GAMEPLAY");objects.put(handle,reference);seats.put(handle,owner);}
            check(new HashSet<>(objects.values()).equals(admitted.keySet()),"ADMITTED_PUBLIC_OBJECT_MISSING");
            epoch=body.get("match_epoch").getAsString();basis=body.get("basis_revision").getAsLong();revision=body.get("organization_revision").getAsLong();
            OrganizationMessages.parse(raw,new OrganizationMessages.Context(epoch,client.viewer.viewer,basis,objects,seats,admitted.keySet(),visibleSeats));
            check(!raw.contains("incarnation") && !raw.contains("host_seat") && !raw.contains("Goblin Guide") && !raw.contains("Llanowar Elves"),"NATIVE_METADATA_PRIVACY");state=body;
        }
        String handle(String reference){for(JsonElement item:state.getAsJsonArray("mappings")){JsonObject mapping=item.getAsJsonObject();if(mapping.get("object_reference").getAsString().equals(reference))return mapping.get("handle").getAsString();}return null;}
        List<String> handles(String name){List<String> result=new ArrayList<>();for(JsonElement item:game.getAsJsonArray("objects")){JsonObject object=item.getAsJsonObject();if(object.get("zone").getAsString().equals("battlefield") && object.get("characteristics").isJsonObject() && name.equals(object.getAsJsonObject("characteristics").get("name").getAsString())){String handle=handle(object.get("object_id").getAsString());if(handle!=null)result.add(handle);}}return result;}
        String reference(String handle){for(JsonElement item:state.getAsJsonArray("mappings"))if(item.getAsJsonObject().get("handle").getAsString().equals(handle))return item.getAsJsonObject().get("object_reference").getAsString();return null;}
        JsonObject group(String id){for(JsonElement seat:state.getAsJsonArray("seats"))for(JsonElement group:seat.getAsJsonObject().getAsJsonArray("groups"))if(group.getAsJsonObject().get("group_id").getAsString().equals(id))return group.getAsJsonObject();throw new AssertionError("NATIVE_GROUP_MISSING");}
        boolean grouped(String group,String handle){return group(group).getAsJsonArray("members").contains(new JsonPrimitive(handle));}
        String command(String id,Operation operation){
            JsonObject message=new JsonObject(),body=new JsonObject(),op=new JsonObject();message.addProperty("wire_version",1);message.addProperty("organization_version",1);message.addProperty("message_type","organization_command");message.addProperty("message_id","packet-"+id);message.add("body",body);
            body.addProperty("match_epoch",epoch);body.addProperty("command_id",id);body.addProperty("expected_organization_revision",revision);body.addProperty("basis_revision",basis);body.add("operation",op);
            op.addProperty("kind",operation.kind.name().toLowerCase(Locale.ROOT));for(String field:new String[]{"group_id","name","x","y","index"})op.add(field,JsonNull.INSTANCE);JsonArray members=new JsonArray();op.add("members",members);
            if(operation.groupId!=null)op.addProperty("group_id",operation.groupId);
            switch(operation.kind){case CREATE:case POSITION:op.addProperty("x",Math.round(operation.x*1000000));op.addProperty("y",Math.round(operation.y*1000000));break;default:break;}
            if(operation.kind==Kind.CREATE || operation.kind==Kind.RENAME)op.addProperty("name",operation.name);if(operation.kind==Kind.MOVE || operation.kind==Kind.REORDER)op.addProperty("index",operation.index);for(String handle:operation.members)members.add(handle);return message.toString();
        }
        void send(String id,String raw) throws Exception {pending.add(id);client.send(raw);}
        String receipt(String id,String reason) throws Exception {
            String raw=raw();JsonObject body=OrganizationMessages.parseReceipt(raw,epoch,pending).getAsJsonObject("body");check(body.get("command_id").getAsString().equals(id),"NATIVE_RECEIPT_ID");
            check(reason==null?body.get("reason_code").isJsonNull():reason.equals(body.get("reason_code").getAsString()),"NATIVE_RECEIPT_REASON_"+reason);pending.remove(id);return raw;
        }
        public void close() throws IOException {client.close();}
    }
    static String apply(Peer actor,Peer other,String id,Operation operation) throws Exception {
        long before=actor.revision;actor.send(id,actor.command(id,operation));String receipt=actor.receipt(id,null);actor.organization();if(other!=null)other.organization();check(actor.revision==before+1 && (other==null || actor.revision==other.revision),"NATIVE_EDIT_FANOUT");return receipt;
    }
    static void reject(Peer actor,String id,String raw,String reason) throws Exception {long before=actor.revision;actor.send(id,raw);actor.receipt(id,reason);actor.organization();check(actor.revision==before,"NATIVE_REJECT_MUTATED_ORGANIZATION");}
    static void publish(ManaforgeMatchCoordinator coordinator,NativeOrganizationBridge host,Capture capture,Peer a,Peer b) throws Exception {
        coordinator.publishNative(capture.observations,host.publication(capture.identities));
        if(a!=null){a.game();a.organization();}if(b!=null){b.game();b.organization();}
        for(Peer peer:Arrays.asList(a,b))if(peer!=null){String raw=peer.state.toString();for(BattlefieldIdentityRegistry.Snapshot nativeView:capture.identities.values()){check(!raw.contains(nativeView.game.toString()) && !raw.contains(nativeView.viewer.toString()),"NATIVE_IDENTITY_METADATA_LEAK");for(BattlefieldIdentityRegistry.Observation object:nativeView.permanents)check(!raw.contains(object.nativeId.toString()),"NATIVE_PERMANENT_ID_LEAK");}}
    }
    static void rejectedBatch(ManaforgeMatchCoordinator coordinator,NativeOrganizationBridge host,Capture capture,Map<String,BattlefieldIdentityRegistry.Snapshot> identities) throws Exception {
        BattlefieldOrganizationSession.Snapshot before=host.snapshot();try{coordinator.publishNative(capture.observations,host.publication(identities));throw new AssertionError("INVALID_NATIVE_BATCH_ACCEPTED");}catch(IOException | IllegalArgumentException expected){}
        check(host.snapshot()==before,"INVALID_NATIVE_BATCH_PARTIALLY_COMMITTED");
    }
    public static void main(String[] args) throws Exception {
        NativeBattlefieldIdentityChecks.Fixture fixture=new NativeBattlefieldIdentityChecks.Fixture();NativePaymentAcceptanceChecks.Engine e=fixture.e;
        AtomicInteger disposed=new AtomicInteger(),submissions=new AtomicInteger();AtomicBoolean cancel=new AtomicBoolean();AtomicReference<NativeOrganizationBridge> bridge=new AtomicReference<>();byte[] keyA=MatchCoordinatorChecks.key(51),keyB=MatchCoordinatorChecks.key(52);
        try(ManaforgeMatchCoordinator coordinator=new ManaforgeMatchCoordinator(e.game.getId().toString(),MatchCoordinatorChecks.ENGINE,MatchCoordinatorChecks.HASH,()->{disposed.incrementAndGet();fixture.close();},cancel::get,10000,300,false)){
            ManaforgeMatchCoordinator.Viewer a=coordinator.register("a",e.payer.getId().toString(),"session-a","viewer-a",keyA,true),b=coordinator.register("b",e.opponent.getId().toString(),"session-b","viewer-b",keyB,true);Map<String,ManaforgeMatchCoordinator.Viewer> roster=new TreeMap<>();roster.put("a",a);roster.put("b",b);
            coordinator.installExtension(sender->{NativeOrganizationBridge host=new NativeOrganizationBridge(e.game.getId(),roster,sender);bridge.set(host);return host;});coordinator.start();
            Card forest=fixture.forest(),forest2=fixture.forest(),bear=fixture.bear(),equipment=fixture.load(new mage.cards.b.Bonesplitter(e.payer.getId(),NativePaymentAcceptanceChecks.info("Bonesplitter"))),delver=fixture.load(new mage.cards.d.DelverOfSecrets(e.payer.getId(),NativePaymentAcceptanceChecks.info("Delver of Secrets")));Card front=fixture.battlefieldCard(delver);SoldierToken token=new SoldierToken();
            e.load(new mage.cards.g.GoblinGuide(e.payer.getId(),NativePaymentAcceptanceChecks.info("Goblin Guide")),Zone.HAND);e.load(new mage.cards.l.LlanowarElves(e.opponent.getId(),NativePaymentAcceptanceChecks.info("Llanowar Elves")),Zone.HAND);
            PlayerQueryEvent query=NativeMultiViewerChecks.priority(e,()->{for(Card card:Arrays.asList(forest,forest2,bear,equipment,delver))fixture.enter(card);check(token.putOntoBattlefield(1,e.game,NativeBattlefieldIdentityChecks.fixtureSource(e,forest),e.payer.getId(),false,false,null,null,false,Collections.singletonList(token)),"NATIVE_ORGANIZATION_TOKEN_ENTRY");});UUID tokenId=token.getLastAddedTokenIds().get(0);
            try(Peer clientA=new Peer("a",a,keyA);Peer clientB=new Peer("b",b,keyB)){
                clientA.organization();clientB.organization();publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);
                check(clientA.state.getAsJsonArray("mappings").size()==6 && clientB.state.getAsJsonArray("mappings").size()==6,"PRIVATE_HAND_ADMITTED");NativeMultiViewerChecks.privacy(envelope(clientA.game),"Goblin Guide","Llanowar Elves");NativeMultiViewerChecks.privacy(envelope(clientB.game),"Llanowar Elves","Goblin Guide");
                int unchangedCycle=e.game.getState().getApplyEffectsCounter();
                String original=clientA.command("create",Operation.create("g","Mana Rocks",.2,.3));String originalReceipt=apply(clientA,clientB,"create",Operation.create("g","Mana Rocks",.2,.3));
                List<String> all=new ArrayList<>();for(JsonElement member:clientA.state.getAsJsonArray("mappings"))all.add(member.getAsJsonObject().get("handle").getAsString());apply(clientA,clientB,"members",Operation.move(all,"g",0));
                apply(clientA,clientB,"rename",Operation.rename("g","Engine"));apply(clientA,clientB,"position",Operation.position("g",.7,.1));apply(clientA,clientB,"second",Operation.create("g2","Empty",0,0));apply(clientA,clientB,"order",Operation.reorder("g2",0));check(clientB.group("g").get("name").getAsString().equals("Engine") && clientB.group("g").get("x").getAsLong()==700000,"NATIVE_SHARED_PROPERTIES");apply(clientA,clientB,"delete",Operation.delete("g2"));
                String landHandle=clientA.handles("Forest").get(0),bearHandle=clientA.handles("Grizzly Bears").get(0),delverHandle=clientA.handles("Delver of Secrets").get(0);String oldReference=clientA.reference(landHandle);
                apply(clientA,clientB,"remove-one",Operation.move(Collections.singletonList(landHandle),null,0));apply(clientA,clientB,"return-one",Operation.move(Collections.singletonList(landHandle),"g",0));
                reject(clientB,"foreign-group",clientB.command("foreign-group",Operation.rename("g","Stolen")),"GROUP_NOT_OWNED");reject(clientB,"foreign-owner",clientB.command("foreign-owner",Operation.move(Collections.singletonList(clientB.handles("Forest").get(0)),null,0)),"MEMBER_NOT_OWNED_OR_ELIGIBLE");reject(clientB,"foreign-handle",clientB.command("foreign-handle",Operation.move(Collections.singletonList(landHandle),null,0)),"UNKNOWN_MEMBER_HANDLE");
                String stale=clientA.command("stale-basis",Operation.rename("g","Changed"));long org=clientA.revision,basis=clientA.basis;publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);
                check(clientA.basis==basis+1 && clientA.revision==org && !oldReference.equals(clientA.reference(landHandle)) && clientA.grouped("g",landHandle),"SAME_CYCLE_REFERENCE_REFRESH");reject(clientA,"stale-basis",stale,"STALE_BASIS_REVISION");
                clientA.send("create",original);check(clientA.receipt("create",null).equals(originalReceipt),"NATIVE_HISTORICAL_RETRY");check(submissions.get()==0 && !e.running.isDone() && e.game.getState().getApplyEffectsCounter()==unchangedCycle && !e.game.getPermanent(forest.getId()).isTapped() && e.game.getPermanent(bear.getId()).getDamage()==0,"ORGANIZATION_ANSWERED_OR_MUTATED_NATIVE_QUERY");
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->{check(e.game.getPermanent(forest.getId()).tap(equipment.getSpellAbility(),e.game),"NATIVE_GROUP_TAP");e.game.getPermanent(bear.getId()).getCounters(e.game).addCounter(mage.counters.CounterType.P1P1.createInstance());e.game.getPermanent(bear.getId()).damage(1,equipment.getId(),equipment.getSpellAbility(),e.game);e.game.getPermanent(equipment.getId()).attachTo(bear.getId(),equipment.getSpellAbility(),e.game);});
                publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);check(clientA.revision==org && clientA.grouped("g",bearHandle) && clientA.grouped("g",landHandle) && e.game.getPermanent(forest.getId()).isTapped() && !e.game.getPermanent(forest2.getId()).isTapped() && e.game.getPermanent(bear.getId()).getDamage()==1 && e.game.getPermanent(bear.getId()).getCounters(e.game).getCount(mage.counters.CounterType.P1P1)==1 && e.game.getPermanent(equipment.getId()).getAttachedTo().equals(bear.getId()),"ORDINARY_CHANGES_LOST_MEMBERSHIP");
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->check(e.game.getPermanent(front.getId()).transform(front.getSpellAbility(),e.game),"NATIVE_GROUP_TRANSFORM"));publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);check(clientA.grouped("g",delverHandle) && e.game.getPermanent(front.getId()).isTransformed(),"TRANSFORM_LOST_MEMBERSHIP");
                Set<String> oldLandHandles=new HashSet<>(clientA.handles("Forest"));NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->{check(e.game.getPermanent(forest.getId()).moveToZone(Zone.EXILED,forest.getSpellAbility(),e.game,false),"NATIVE_GROUP_BLINK_OUT");check(e.game.getCard(forest.getId()).putOntoBattlefield(e.game,Zone.EXILED,forest.getSpellAbility(),e.payer.getId()),"NATIVE_GROUP_BLINK_IN");});publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);Set<String> newLandHandles=new HashSet<>(clientA.handles("Forest"));check(!newLandHandles.equals(oldLandHandles) && clientA.group("g").getAsJsonArray("members").size()==5,"BLINK_INHERITED_MEMBERSHIP");oldLandHandles.removeAll(newLandHandles);String revoked=oldLandHandles.iterator().next();reject(clientA,"revoked",clientA.command("revoked",Operation.move(Collections.singletonList(revoked),"g",0)),"UNKNOWN_MEMBER_HANDLE");
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->NativeBattlefieldIdentityChecks.transfer(e,bear));check(e.game.getPermanent(bear.getId()).getControllerId().equals(e.opponent.getId()),"NATIVE_BRIDGE_CONTROL_FIXTURE");publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);check(clientA.reference(bearHandle)==null && clientA.group("g").getAsJsonArray("members").size()==4,"CONTROL_KEPT_OLD_MEMBERSHIP_OR_HANDLE");apply(clientB,clientA,"b-group",Operation.create("bg","Transferred",0,0));apply(clientB,clientA,"b-member",Operation.move(clientB.handles("Grizzly Bears"),"bg",0));
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->e.game.getPermanent(front.getId()).setFaceDown(true,e.game));publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);check(clientA.reference(delverHandle)==null && clientA.state.getAsJsonArray("mappings").size()==5,"CONCEALED_MAPPING_LEAK");
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->e.game.getPermanent(front.getId()).setFaceDown(false,e.game));publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);check(clientA.reference(delverHandle)==null && clientA.state.getAsJsonArray("mappings").size()==6 && clientA.group("g").getAsJsonArray("members").size()==3,"REVEAL_REUSED_OLD_MEMBERSHIP");
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->check(e.game.getPermanent(tokenId).moveToZone(Zone.GRAVEYARD,forest.getSpellAbility(),e.game,false),"NATIVE_GROUP_TOKEN_REMOVAL"));publish(coordinator,bridge.get(),new Capture(e,query,submissions),clientA,clientB);check(clientA.state.getAsJsonArray("mappings").size()==5 && clientA.group("g").getAsJsonArray("members").size()==2,"TOKEN_MEMBERSHIP_RETAINED");
                Capture captured=new Capture(e,query,submissions);BattlefieldIdentityRegistry.Snapshot current=captured.identities.get("a");
                Set<String> priorHandles=mappingHandles(clientA.state);
                for(int failure=0;failure<4;failure++){
                    Map<String,BattlefieldIdentityRegistry.Snapshot> invalid=new TreeMap<>(captured.identities);Map<UUID,String> admission=new HashMap<>(current.admitted);Set<UUID> seats=new HashSet<>(current.seats);if(failure==2)seats.remove(e.opponent.getId());if(failure==3)admission.clear();
                    invalid.put("a",new BattlefieldIdentityRegistry.Snapshot(failure==0?UUID.randomUUID():current.game,current.viewer,failure==1?current.cycle-1:current.cycle,seats,current.permanents,admission));rejectedBatch(coordinator,bridge.get(),captured,invalid);
                }
                publish(coordinator,bridge.get(),captured,clientA,clientB);check(clientA.group("g").getAsJsonArray("members").size()==2 && mappingHandles(clientA.state).equals(priorHandles),"FAILED_BATCH_CORRUPTED_IDENTITY");
                apply(clientB,null,"non-reading-peer",Operation.rename("bg","Peer is not reading"));
                clientA.close();MatchCoordinatorChecks.await(()->coordinator.status("a").status==ManaforgeMatchCoordinator.Status.DISCONNECTED,"NATIVE_ORGANIZATION_DISCONNECT");apply(clientB,null,"independent",Operation.rename("bg","Still active"));
                NativeMultiViewerChecks.resume(e);query=NativeMultiViewerChecks.priority(e,()->check(e.game.getPermanent(forest2.getId()).tap(equipment.getSpellAbility(),e.game),"NATIVE_AFTER_DISCONNECT_TAP"));publish(coordinator,bridge.get(),new Capture(e,query,submissions),null,clientB);check(disposed.get()==0 && submissions.get()==0 && !e.running.isDone(),"DISCONNECT_STOPPED_NATIVE_MATCH");
                try(Peer reattached=new Peer("a",a,keyA)){
                    reattached.game();reattached.organization();check(reattached.revision==clientB.revision && reattached.group("bg").get("name").getAsString().equals("Still active"),"NATIVE_REATTACH_RECONSTRUCTION");reattached.send("create",original);check(reattached.receipt("create",null).equals(originalReceipt),"NATIVE_REATTACH_RETRY_HISTORY");
                }
                cancel.set(true);MatchCoordinatorChecks.await(coordinator::isClosed,"NATIVE_ORGANIZATION_PARENT_CLEANUP");coordinator.close();check(disposed.get()==1 && submissions.get()==0,"NATIVE_ORGANIZATION_OWNERSHIP");try{bridge.get().snapshot();throw new AssertionError("NATIVE_ORGANIZATION_LEAK");}catch(IllegalStateException expected){}
            }
        }finally{Arrays.fill(keyA,(byte)0);Arrays.fill(keyB,(byte)0);if(disposed.get()==0)fixture.close();}
        check(disposed.get()==1,"NATIVE_ORGANIZATION_DOUBLE_DISPOSE");System.out.println("Real native organization: two authenticated viewers, exact gameplay mappings, lifecycle, privacy, staged rejection, reference rotation, retry, reattachment and zero native submissions passed");
    }
    static Set<String> mappingHandles(JsonObject state){Set<String> result=new HashSet<>();for(JsonElement item:state.getAsJsonArray("mappings"))result.add(item.getAsJsonObject().get("handle").getAsString());return result;}
    static JsonObject envelope(JsonObject game){JsonObject body=new JsonObject(),result=new JsonObject();body.add("snapshot",game);result.add("body",body);return result;}
}

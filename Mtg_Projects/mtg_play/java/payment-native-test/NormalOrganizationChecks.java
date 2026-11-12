import com.google.gson.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;
import mage.cards.Card;
import mage.game.events.PlayerQueryEvent;
import mage.interfaces.callback.*;
import mage.view.*;
import manaforge.organization.*;
import manaforge.protocol.*;
import static manaforge.organization.BattlefieldOrganizationService.*;
/** Real owner metadata path, one human recipient and a two-seat native roster. */
public final class NormalOrganizationChecks {
    static int version=2;
    static JsonObject parse(String raw) throws Exception {return version==3?OrganizationV3Messages.parseContract(raw):OrganizationV2Messages.parseContract(raw);}
    static String upgrade(String raw,long revision) throws Exception {return version==3?OrganizationV3Messages.upgrade(raw,revision):OrganizationV2Messages.upgrade(raw,revision);}
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static JsonObject project(NativePaymentAcceptanceChecks.Engine e,PlayerQueryEvent query,ManaforgeOpeningProjection projection,AtomicInteger submissions) throws Exception {
        synchronized(e.response.get(e.payer)){
            ManaforgeBridge bridge=new ManaforgeBridge(value->{},null,new ManaforgeBridge.ResponseTransport(){public boolean object(UUID game,UUID source){submissions.incrementAndGet();return false;}public boolean mana(UUID game,UUID player,mage.constants.ManaType type){submissions.incrementAndGet();return false;}public boolean bool(UUID game,boolean value){submissions.incrementAndGet();return false;}});
            ClientCallback callback=new ClientCallback(ClientCallbackMethod.GAME_SELECT,e.game.getId(),new GameClientMessage(new GameView(e.game.getState(),e.game,e.payer.getId(),null),query.getOptions(),query.getMessage()));callback.setMessageId(1);bridge.onCallback(callback);
            JsonObject snapshot=projection.projectObserverWithBindings(bridge.currentState(),bridge.currentDecision()).snapshot(),envelope=new JsonObject(),body=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","normal-view");body.addProperty("fixture_only",false);body.add("snapshot",snapshot);envelope.add("body",body);return envelope;
        }
    }
    static String command(String epoch,String id,long organization,long basis,Operation operation) throws Exception {
        JsonObject message=JsonParser.parseString(upgrade(OrganizationChannelUnitChecks.command(id,organization,basis,operation),1)).getAsJsonObject();message.getAsJsonObject("body").addProperty("match_epoch",epoch);return message.toString();
    }
    public static void main(String[] args) throws Exception {for(int value:new int[]{2,3}){version=value;run();}}
    static void run() throws Exception {
        AtomicInteger submissions=new AtomicInteger();AtomicBoolean unavailable=new AtomicBoolean();
        try(NativeBattlefieldIdentityChecks.Fixture f=new NativeBattlefieldIdentityChecks.Fixture()){
            NativePaymentAcceptanceChecks.Engine e=f.e;Card forest=f.forest();PlayerQueryEvent query=NativeMultiViewerChecks.priority(e,()->f.enter(forest));int cycle=e.game.getState().getApplyEffectsCounter();ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection("normal-session","viewer-a",e.payer.getId().toString(),Collections.emptyMap());List<String> packets=new ArrayList<>();
            try(NormalOrganizationEndpoint endpoint=new NormalOrganizationEndpoint(projection,e.game.getId().toString(),e.payer.getId().toString(),"viewer-a",(raw,ids)->{
                if(unavailable.get()){JsonObject retry=new JsonObject();retry.addProperty("status","retry");return retry;}
                JsonObject request=new JsonObject();JsonArray objects=new JsonArray();for(String id:ids)objects.add(id);request.add("object_ids",objects);request.add("identified_ids",objects.deepCopy());return ManaforgeGameMetadata.readPaused(e.game,e.payer.getId(),raw.get("cycle").getAsInt(),request,()->new GameView(e.game.getState(),e.game,e.payer.getId(),null));
            },packets::add,version)){
                endpoint.observe(project(e,query,projection,submissions).toString());check(packets.size()==1 && parse(packets.get(0)).get("message_type").getAsString().equals("organization_capabilities"),"NORMAL_CAPABILITIES");packets.clear();endpoint.receive(upgrade(OrganizationChannelUnitChecks.capabilities(),1));
                JsonObject snapshot=parse(packets.get(packets.size()-1)).getAsJsonObject("body");String epoch=snapshot.get("match_epoch").getAsString(),handle=snapshot.getAsJsonArray("mappings").get(0).getAsJsonObject().get("handle").getAsString();check(snapshot.getAsJsonArray("seats").size()==2 && snapshot.getAsJsonArray("mappings").size()==1 && snapshot.get("gameplay_revision").getAsLong()==1,"NORMAL_ROSTER_AND_CORRELATION");packets.clear();
                String create=command(epoch,"create",0,1,Operation.create("g","Normal game",0,0));endpoint.receive(create);String original=packets.get(0);packets.clear();endpoint.receive(command(epoch,"move",1,1,Operation.move(Collections.singletonList(handle),"g",0)));check(packets.size()==2,"NORMAL_EDIT_RECEIPT_AND_SNAPSHOT");
                snapshot=parse(packets.get(1)).getAsJsonObject("body");check(snapshot.get("organization_revision").getAsLong()==2 && snapshot.get("gameplay_revision").getAsLong()==1,"NORMAL_EDIT_ADVANCED_RULES_REVISION");
                packets.clear();endpoint.observe(project(e,query,projection,submissions).toString());snapshot=parse(packets.get(0)).getAsJsonObject("body");check(snapshot.get("gameplay_revision").getAsLong()==2 && snapshot.get("organization_revision").getAsLong()==2 && snapshot.getAsJsonArray("mappings").get(0).getAsJsonObject().get("handle").getAsString().equals(handle),"NORMAL_REFERENCE_REFRESH");packets.clear();
                endpoint.receive(create);check(packets.size()==1 && packets.get(0).equals(original),"NORMAL_RETRY_LEDGER");check(!endpoint.receive("{\"wire_version\":1,\"message_type\":\"command\",\"message_id\":\"native\",\"body\":{}}"),"NORMAL_NATIVE_ROUTE_INTERCEPTED");
                unavailable.set(true);packets.clear();endpoint.observe(project(e,query,projection,submissions).toString());check(packets.isEmpty(),"UNREADY_PUBLISHED_STATE");endpoint.receive(create);check(packets.size()==1 && packets.get(0).equals(original),"UNREADY_RETRY_LOST");packets.clear();String newCommand=command(epoch,"unready",2,2,Operation.rename("g","Changed"));endpoint.receive(newCommand);String rejection=packets.get(0);check(parse(rejection).getAsJsonObject("body").get("reason_code").getAsString().equals("STALE_BASIS_REVISION"),"UNREADY_COMMAND_APPLIED");unavailable.set(false);packets.clear();endpoint.observe(project(e,query,projection,submissions).toString());packets.clear();endpoint.receive(newCommand);check(packets.size()==1 && packets.get(0).equals(rejection),"UNREADY_REJECTION_NOT_HISTORICAL");
                if(version==3){
                    JsonObject conversion=JsonParser.parseString(command(epoch,"drawer",2,3,Operation.rename("g","Unused"))).getAsJsonObject(),op=conversion.getAsJsonObject("body").getAsJsonObject("operation");op.addProperty("kind","set_mode");op.add("name",JsonNull.INSTANCE);op.addProperty("presentation_mode","drawer");packets.clear();endpoint.receive(conversion.toString());JsonObject converted=parse(packets.get(1)).getAsJsonObject("body");boolean found=false;for(JsonElement seat:converted.getAsJsonArray("seats"))for(JsonElement group:seat.getAsJsonObject().getAsJsonArray("groups")){found=true;check(group.getAsJsonObject().get("presentation_mode").getAsString().equals("drawer") && group.getAsJsonObject().getAsJsonArray("members").size()==1,"NORMAL_DRAWER_MEMBERSHIP");}check(found,"NORMAL_DRAWER_MISSING");
                }
                check(submissions.get()==0 && e.nativeSourceResponses==0 && !e.running.isDone() && e.game.getState().getApplyEffectsCounter()==cycle && !e.game.getPermanent(forest.getId()).isTapped(),"NORMAL_ORGANIZATION_MUTATED_NATIVE_GAME");
            }
            NativeMultiViewerChecks.resume(e);
        }
        System.out.println("Normal organization owner metadata, two-seat/single-recipient admission, exact references, retry and zero native submissions passed");
    }
}

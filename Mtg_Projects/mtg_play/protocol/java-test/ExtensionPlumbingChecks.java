import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.*;
import manaforge.protocol.*;

/** Explicit opt-in transport fixture; intentionally not organization admission. */
public final class ExtensionPlumbingChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static void owner(){check(Thread.currentThread().getName().equals("match-coordinator-owner"),"EXTENSION_NOT_ON_OWNER");}
    public static void main(String[] args) throws Exception {
        AtomicInteger matchClosed=new AtomicInteger(),extensionClosed=new AtomicInteger(),received=new AtomicInteger();AtomicBoolean cancel=new AtomicBoolean();
        JsonObject fixture=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonArray("cases").get(0).getAsJsonObject().getAsJsonArray("steps").get(0).getAsJsonObject().getAsJsonObject("envelope");
        byte[] keyA=MatchCoordinatorChecks.key(31),keyB=MatchCoordinatorChecks.key(32);
        try(ManaforgeMatchCoordinator coordinator=new ManaforgeMatchCoordinator("game",MatchCoordinatorChecks.ENGINE,MatchCoordinatorChecks.HASH,matchClosed::incrementAndGet,cancel::get,5000,5000,true)){
            ManaforgeMatchCoordinator.Viewer a=coordinator.register("a","native-a","session-a","viewer-a",keyA,true),b=coordinator.register("b","native-b","session-b","viewer-b",keyB);
            coordinator.installExtension(sender->{owner();return new ViewerChannelExtension(){
                public void connected(String seat) throws Exception {owner();check(seat.equals("a"),"LEGACY_RECEIVED_EXTENSION");sender.send(seat,Kind.CONTROL,"{\"probe\":\"ready\"}");}
                public void receive(String seat,String raw) throws Exception {owner();check(seat.equals("a"),"EDITABLE_ACTOR");received.incrementAndGet();sender.send(seat,Kind.RECEIPT,"{\"actor\":\"a\"}");}
                public void disconnected(String seat){owner();}
                public void close(){owner();extensionClosed.incrementAndGet();}
            };});
            coordinator.start();
            try(MatchCoordinatorChecks.Client clientA=new MatchCoordinatorChecks.Client(a,keyA,true);MatchCoordinatorChecks.Client clientB=new MatchCoordinatorChecks.Client(b,keyB,true)){
                check(JsonParser.parseString(TextFrame.read(clientA.socket.getInputStream())).getAsJsonObject().get("probe").getAsString().equals("ready"),"CONTROL_NOT_SENT");
                coordinator.publishSnapshots(MatchCoordinatorChecks.batch(fixture,a,b,1,false));clientA.read();clientB.read();
                clientA.send("{\"claimed_seat\":\"b\"}");check(JsonParser.parseString(TextFrame.read(clientA.socket.getInputStream())).getAsJsonObject().get("actor").getAsString().equals("a"),"AUTHENTICATED_SEAT_LOST");
                check(received.get()==1 && coordinator.status("a").queuedReceipts<=32 && coordinator.status("a").pendingOrganizationSnapshots<=1,"EXTENSION_BOUNDS");
                clientB.send("{\"claimed_seat\":\"a\"}");MatchCoordinatorChecks.await(()->"READ_ONLY_TRAFFIC".equals(coordinator.status("b").reason),"LEGACY_COMMAND_PATH_CHANGED");
                coordinator.updateExtension(extension->owner());cancel.set(true);MatchCoordinatorChecks.await(coordinator::isClosed,"EXTENSION_PARENT_CANCEL");coordinator.close();
            }
        }
        check(matchClosed.get()==1 && extensionClosed.get()==1,"EXTENSION_CLOSE_OWNERSHIP");
        System.out.println("Optional viewer extension owner binding, one writer, legacy isolation and cleanup passed");
    }
}

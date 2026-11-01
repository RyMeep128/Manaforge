import com.google.gson.*;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

/** Engine-free public fixture over real authenticated sockets and production admission. */
public final class OpeningSessionChecks {
    static JsonObject envelope(JsonObject snapshot) {
        JsonObject envelope=new JsonObject(),body=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","opening");
        body.addProperty("fixture_only",false);body.add("snapshot",snapshot);envelope.add("body",body);return envelope;
    }
    public static void main(String[] args) throws Exception {
        AtomicInteger calls=new AtomicInteger();String hash=String.join("",java.util.Collections.nCopies(64,"0"));
        ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();
        JsonObject snapshot=projection.project(OpeningProjectionChecks.state(),OpeningProjectionChecks.prompt());
        ManaforgeOpeningLoopback.exchange(envelope(snapshot),projection,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->{
            if(!command.get("value").getAsBoolean() || !command.get("game_id").getAsString().equals("raw-game") || command.get("decision_id").getAsInt()!=41)throw new AssertionError("BAD_NATIVE_BINDING");
            calls.incrementAndGet();
        },()->false);
        if(calls.get()!=1)throw new AssertionError("DUPLICATE_NATIVE_IO");
        try{OpeningProjectionChecks.claim(projection,OpeningProjectionChecks.choose(snapshot,0));throw new AssertionError("DISCONNECTED_CHOICE_ACCEPTED");}
        catch(IOException expected){if(!expected.getMessage().equals("STALE_DECISION"))throw expected;}
        ManaforgeOpeningProjection cancelled=OpeningProjectionChecks.projection();
        JsonObject offered=cancelled.project(OpeningProjectionChecks.state(),OpeningProjectionChecks.prompt());
        try {
            ManaforgeOpeningLoopback.exchange(envelope(offered),cancelled,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->calls.incrementAndGet(),()->true);
            throw new AssertionError("CANCELLED_AUTH_ACCEPTED");
        }catch(IOException failure){if(!failure.getMessage().equals("AUTH_CANCELLED"))throw failure;}
        if(calls.get()!=1)throw new AssertionError("CANCELLED_NATIVE_IO");
        try{OpeningProjectionChecks.claim(cancelled,OpeningProjectionChecks.choose(offered,0));throw new AssertionError("CANCELLED_CHOICE_RETAINED");}
        catch(IOException expected){if(!expected.getMessage().equals("STALE_DECISION"))throw expected;}
        System.out.println("Opening session: authenticated snapshot/choice, duplicate receipt, one native enqueue, disconnect uncertainty and cancelled-auth checks passed");
    }
}

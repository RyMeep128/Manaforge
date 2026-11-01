import com.google.gson.*;
import java.util.*;
import java.io.IOException;
import manaforge.protocol.PlayContracts.CardIdentity;
import manaforge.protocol.ReceiveMessages;

/** Synthetic privacy/shape checks; no engine installation or private deck fixture. */
public final class OpeningProjectionChecks {
    static int checks;
    static void check(boolean value){checks++;if(!value)throw new AssertionError("OPENING_PROJECTION_CHECK");}
    static JsonObject state() {
        return JsonParser.parseString("{\"viewer\":\"raw-human\",\"cycle\":8,\"turn\":0,\"phase\":null,\"step\":null,\"active_player\":\"raw-name\",\"priority_player\":null,\"stack\":[],\"exile\":[],\"combat\":[],\"players\":[{\"id\":\"raw-human\",\"name\":\"raw-name\",\"life\":20,\"hand_count\":1,\"library_count\":59,\"left\":false,\"battlefield\":[],\"graveyard\":[],\"command\":[]},{\"id\":\"raw-ai\",\"name\":\"raw-opponent-name\",\"life\":20,\"hand_count\":7,\"library_count\":53,\"left\":false,\"battlefield\":[],\"graveyard\":[],\"command\":[],\"hand\":[{\"name\":\"OPPONENT_SECRET\"}]}],\"hand\":[{\"id\":\"raw-card\",\"hidden\":false,\"face_down\":false,\"name\":\"Forest\",\"set\":\"M10\",\"number\":\"248\",\"view_rules\":[\"Tap for mana\"]}]}").getAsJsonObject();
    }
    static JsonObject prompt(){return JsonParser.parseString("{\"kind\":\"GAME_ASK\",\"decision_id\":41,\"cycle\":8,\"message\":\"Keep?\"}").getAsJsonObject();}
    static ManaforgeOpeningProjection projection() {
        CardIdentity id=new CardIdentity();id.printing_id="exact-selected-printing";id.deck_entry_id="native-entry";
        Map<String,CardIdentity> bindings=new HashMap<>();bindings.put("M10/248",id);
        ManaforgeOpeningProjection projection=new ManaforgeOpeningProjection("session","human","raw-human",bindings);
        id.printing_id="MUTATED_BINDING";return projection;
    }
    static void shape(JsonObject snapshot) throws Exception {
        JsonObject body=new JsonObject();body.addProperty("fixture_only",false);body.add("snapshot",snapshot);
        JsonObject envelope=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","opening");envelope.add("body",body);
        ReceiveMessages.parse(envelope.toString(),"session","human",1,false);check(true);
    }
    static void rejects(JsonObject raw,JsonObject request) throws Exception {
        try{projection().project(raw,request);throw new AssertionError("ACCEPTED_UNSUPPORTED_OPENING");}
        catch(IOException error){check(error.getMessage().equals("LIVE_OPENING_PROJECTION_UNSUPPORTED") && error.getCause()==null);}
    }
    public static void main(String[] args) throws Exception {
        ManaforgeOpeningProjection projection=projection();JsonObject raw=state(),request=prompt();JsonObject snapshot=projection.project(raw,request);shape(snapshot);
        String text=snapshot.toString();for(String secret:new String[]{"raw-human","raw-ai","raw-card","raw-name","raw-opponent-name","OPPONENT_SECRET","MUTATED_BINDING"})check(!text.contains(secret));
        check(snapshot.get("revision").getAsLong()==1);check(!snapshot.get("actions_complete").getAsBoolean());
        check(snapshot.getAsJsonArray("objects").size()==1 && snapshot.getAsJsonArray("actions").size()==0);
        JsonObject card=snapshot.getAsJsonArray("objects").get(0).getAsJsonObject();check(card.getAsJsonObject("card_identity").get("printing_id").getAsString().equals("exact-selected-printing"));
        check(snapshot.getAsJsonObject("decision").getAsJsonArray("options").size()==2);
        card.addProperty("zone","MUTATED_OUTPUT");JsonObject second=projection.project(raw,request);shape(second);
        check(second.get("revision").getAsLong()==2 && !second.toString().contains("MUTATED_OUTPUT"));
        check(!second.getAsJsonArray("objects").get(0).getAsJsonObject().get("object_id").equals(card.get("object_id")));
        for(String hiddenFlag:new String[]{"hidden","face_down"}) {
            raw=state();raw.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty(hiddenFlag,true);
            snapshot=projection().project(raw,prompt());shape(snapshot);text=snapshot.toString();
            check(!text.contains("Forest") && !text.contains("exact-selected-printing") && !text.contains("Tap for mana"));
        }
        raw=state();raw.getAsJsonArray("hand").get(0).getAsJsonObject().addProperty("set","UNKNOWN");
        check(projection().project(raw,prompt()).getAsJsonArray("objects").get(0).getAsJsonObject().get("card_identity").isJsonNull());
        raw=state();raw.addProperty("viewer","wrong-viewer");rejects(raw,prompt());
        request=prompt();request.addProperty("cycle",9);rejects(state(),request);
        request=prompt();request.addProperty("kind","GAME_SELECT");rejects(state(),request);
        raw=state();raw.getAsJsonArray("stack").add(new JsonObject());rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(new JsonObject());rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("hand").get(0).getAsJsonObject().remove("hidden");rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("players").add(raw.getAsJsonArray("players").get(0).deepCopy());rejects(raw,prompt());
        raw=state();raw.getAsJsonArray("players").get(0).getAsJsonObject().addProperty("life",true);rejects(raw,prompt());
        request=prompt();request.addProperty("message","Use 12345678-abcd-1234-abcd-123456789abc");check(!projection().project(state(),request).toString().contains("12345678-abcd-1234-abcd-123456789abc"));
        System.out.println("Opening projection: "+checks+" privacy, schema, isolation and fail-closed checks passed");
    }
}

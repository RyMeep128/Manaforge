import com.google.gson.*;
import java.util.*;

/** Focused native-to-Unity priority boundary checks; no engine process. */
public final class UnityPriorityProjectionChecks {
    private static int checks;
    private static void require(boolean value){checks++;if(!value)throw new AssertionError("UNITY_PRIORITY_PROJECTION");}
    private static List<String> stackIds(JsonObject snapshot){List<String> ids=new ArrayList<>();for(JsonElement row:snapshot.getAsJsonArray("objects"))if("stack".equals(row.getAsJsonObject().get("zone").getAsString()))ids.add(row.getAsJsonObject().get("object_id").getAsString());return ids;}
    static void run() throws Exception {
        JsonObject raw=OpeningProjectionChecks.attackState(),prompt=OpeningProjectionChecks.priorityPrompt();
        raw.addProperty("priority_player","raw-name");raw.add("playable",new JsonArray());raw.add("action_kinds",new JsonObject());
        raw.addProperty("playable_information_complete",true);
        ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();
        JsonObject snapshot=projection.projectCoreCombat(raw,prompt,true);OpeningProjectionChecks.shape(snapshot);
        require(snapshot.get("actions_complete").getAsBoolean());require(snapshot.getAsJsonObject("decision").get("is_priority").getAsBoolean());
        require(snapshot.getAsJsonArray("actions").size()==1);require(!snapshot.getAsJsonArray("unsupported_fields").asList().contains(new JsonPrimitive("actions")));
        raw.remove("playable_information_complete");require(!projection.projectCoreCombat(raw,prompt,true).get("actions_complete").getAsBoolean());
        raw.addProperty("playable_information_complete",false);require(!projection.projectCoreCombat(raw,prompt,true).get("actions_complete").getAsBoolean());
        raw.addProperty("playable_information_complete",true);raw.getAsJsonArray("playable").add("unprojected-source");raw.getAsJsonObject("action_kinds").addProperty("unprojected-source","activate");
        require(!projection.projectCoreCombat(raw,prompt,true).get("actions_complete").getAsBoolean());
        raw.add("playable",new JsonArray());raw.getAsJsonArray("playable").add("raw-card");raw.getAsJsonObject("action_kinds").addProperty("raw-card","activate");
        snapshot=projection.projectCoreCombat(raw,prompt,true);OpeningProjectionChecks.shape(snapshot);
        require(snapshot.get("actions_complete").getAsBoolean());require(snapshot.getAsJsonArray("actions").size()==2);
        JsonObject classes=new JsonObject();classes.addProperty("raw-card","basic_mana");raw.add("priority_classes",classes);
        snapshot=projection.projectCoreCombat(raw,prompt,true);
        require(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("priority_class").getAsString().equals("basic_mana"));
        classes.addProperty("raw-card","meaningful");snapshot=projection.projectCoreCombat(raw,prompt,true);
        require(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("priority_class").getAsString().equals("meaningful"));
        raw.remove("priority_classes");snapshot=projection.projectCoreCombat(raw,prompt,true);
        require(snapshot.getAsJsonArray("actions").get(0).getAsJsonObject().get("priority_class").getAsString().equals("meaningful"));
        snapshot=projection.projectCoreCombat(raw,OpeningProjectionChecks.attackPrompt());require(!snapshot.get("actions_complete").getAsBoolean());require(!snapshot.getAsJsonObject("decision").get("is_priority").getAsBoolean());
        JsonArray duplicate=new JsonArray();duplicate.add("one");duplicate.add("one");
        require(!ManaforgeOpeningProjection.completePriorityActions(duplicate,Arrays.asList("one",null)));
        raw.add("playable",new JsonArray());
        JsonObject card=raw.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject().deepCopy();
        card.addProperty("id","native-stack-a");card.addProperty("stack_owner","raw-human");card.addProperty("stack_controller","raw-human");
        JsonObject second=card.deepCopy();second.addProperty("id","native-stack-b");
        JsonArray stack=new JsonArray();stack.add(card);stack.add(second);raw.add("stack",stack);
        List<String> first=stackIds(projection.projectCoreCombat(raw,prompt,true));
        require(first.size()==2);require(first.equals(stackIds(projection.projectCoreCombat(raw,prompt,true))));
        raw.add("stack",new JsonArray());raw.getAsJsonArray("stack").add(second);raw.getAsJsonArray("stack").add(card);
        List<String> reordered=stackIds(projection.projectCoreCombat(raw,prompt,true));
        require(reordered.equals(Arrays.asList(first.get(1),first.get(0))));
        raw.add("stack",new JsonArray());projection.projectCoreCombat(raw,prompt,true);raw.getAsJsonArray("stack").add(card);
        require(!stackIds(projection.projectCoreCombat(raw,prompt,true)).get(0).equals(first.get(0)));
        require(!projection.projectCoreCombat(raw,prompt,true).toString().contains("native-stack-a"));
        System.out.println("Unity priority projection: "+checks+" focused checks passed");
    }
    public static void main(String[] args) throws Exception {run();}
}

package manaforge.protocol;

import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Public native-document fixtures only; no engine, file references or user decks are opened. */
public final class LaunchReaderFixtureConsumer {
    private static int checks;private static String engine,adapter,pin;
    private static void check(boolean valid){checks++;if(!valid)throw new AssertionError("LAUNCH_READER_CHECK_"+checks);}
    private static JsonObject read(Path file) throws Exception {return JsonParser.parseString(new String(Files.readAllBytes(file),StandardCharsets.UTF_8)).getAsJsonObject();}
    private static LaunchContracts.LaunchManifest parse(JsonObject value) throws Exception {return LaunchManifestReader.parse(value.toString(),engine,adapter,pin);}
    private static void invalid(String text) throws Exception {
        try{LaunchManifestReader.parse(text,engine,adapter,pin);throw new AssertionError("LAUNCH_READER_ACCEPTED_INVALID");}
        catch(LaunchManifestReader.LaunchException error){check(error.getMessage().equals(error.code) && error.getCause()==null && !error.getMessage().contains("private-canary"));}
    }
    private static void invalid(JsonObject value) throws Exception {invalid(value.toString());}
    private static JsonObject deck(JsonObject root){return root.getAsJsonArray("seats").get(0).getAsJsonObject().getAsJsonObject("document").getAsJsonObject("deck");}
    private static JsonObject entry(JsonObject root){return deck(root).getAsJsonArray("entries").get(0).getAsJsonObject();}
    public static void main(String[] args) throws Exception {
        Path fixtures=Paths.get(args[0]).resolve("fixtures");
        JsonArray positives=read(fixtures.resolve("launch-positive-v1.json")).getAsJsonArray("cases");
        JsonObject base=positives.get(0).getAsJsonObject().getAsJsonObject("payload");
        JsonObject trusted=base.getAsJsonObject("engine");engine=trusted.get("engine_version").getAsString();adapter=trusted.get("adapter_version").getAsString();pin=trusted.get("artifact_manifest_sha256").getAsString();
        Gson gson=new GsonBuilder().serializeNulls().create();
        for(JsonElement item:positives){JsonObject value=item.getAsJsonObject().getAsJsonObject("payload");check(gson.toJsonTree(parse(value)).equals(value));}
        for(JsonElement item:read(fixtures.resolve("launch-negative-v1.json")).getAsJsonArray("cases"))invalid(item.getAsJsonObject().getAsJsonObject("payload"));
        JsonObject value=base.deepCopy();value.addProperty("private-canary","must not appear in exceptions");invalid(value);
        value=base.deepCopy();value.addProperty("protocol_version","1");invalid(value);
        value=base.deepCopy();value.addProperty("protocol_version",2);invalid(value);
        value=base.deepCopy();value.getAsJsonObject("engine").addProperty("engine_version","private-canary");invalid(value);
        value=base.deepCopy();value.getAsJsonObject("engine").addProperty("adapter_version","private-canary");invalid(value);
        value=base.deepCopy();value.getAsJsonObject("engine").addProperty("artifact_manifest_sha256",new String(new char[64]).replace('\0','b'));invalid(value);
        value=base.deepCopy();value.getAsJsonArray("seats").get(1).getAsJsonObject().add("seat_id",value.getAsJsonArray("seats").get(0).getAsJsonObject().get("seat_id"));invalid(value);
        value=base.deepCopy();entry(value).addProperty("quantity",true);invalid(value);
        value=base.deepCopy();entry(value).addProperty("quantity",0);invalid(value);
        value=base.deepCopy();entry(value).addProperty("owned",-1);invalid(value);
        value=base.deepCopy();entry(value).addProperty("card_id",true);invalid(value);
        value=base.deepCopy();entry(value).addProperty("section","considering");invalid(value);
        value=base.deepCopy();deck(value).getAsJsonArray("entries").add(entry(value).deepCopy());invalid(value);
        value=base.deepCopy();JsonArray ids=new JsonArray();ids.add("private-canary");deck(value).add("commander_entry_ids",ids);invalid(value);
        value=base.deepCopy();ids=new JsonArray();ids.add(entry(value).get("entry_id"));ids.add(entry(value).get("entry_id"));deck(value).add("commander_entry_ids",ids);invalid(value);
        value=base.deepCopy();entry(value).addProperty("section","mainboard");deck(value).add("companion_entry_id",entry(value).get("entry_id"));invalid(value);
        value=base.deepCopy();value.getAsJsonArray("seats").get(0).getAsJsonObject().getAsJsonObject("document").addProperty("schema_version",2);invalid(value);
        value=base.deepCopy();deck(value).addProperty("notes","private-canary");invalid(value);
        invalid(base.toString().replace("\"manifest_id\":","\"manifest_id\":\"private-canary\",\"manifest_id\":"));
        invalid(base.toString()+"{}");invalid(String.valueOf((char)0xfeff)+base.toString());
        invalid(base.toString().replace("\"launch_manifest_version\":1","\"launch_manifest_version\":1.0"));
        invalid(base.toString().replace("\"launch_manifest_version\":1","\"launch_manifest_version\":9223372036854775808"));
        String astral=new String(Character.toChars(0x1f600));
        value=base.deepCopy();entry(value).addProperty("name",String.join("",Collections.nCopies(4096,astral)));check(parse(value).seats[0].document.deck.entries[0].name.codePointCount(0,8192)==4096);
        value=base.deepCopy();entry(value).addProperty("name",String.join("",Collections.nCopies(4097,astral)));invalid(value);
        value=base.deepCopy();deck(value).addProperty("name",String.valueOf((char)0x85));invalid(value);
        value=base.deepCopy();entry(value).addProperty("name","");check(parse(value).seats[0].document.deck.entries[0].name.isEmpty());
        value=base.deepCopy();entry(value).addProperty("quantity",Long.MAX_VALUE);check(parse(value).seats[0].document.deck.entries[0].quantity==Long.MAX_VALUE);
        value=base.deepCopy();for(int i=2;i<6;i++){JsonObject seat=value.getAsJsonArray("seats").get(0).getAsJsonObject().deepCopy();seat.addProperty("seat_id","seat-"+i);value.getAsJsonArray("seats").add(seat);}check(parse(value).seats.length==6);
        LaunchContracts.LaunchManifest first=parse(base);first.seats[0].document.deck.name="private-canary";check(!parse(base).seats[0].document.deck.name.equals("private-canary"));
        try{LaunchManifestReader.parse(base.toString(),null,adapter,pin);throw new AssertionError("MISSING_TRUSTED_PIN_ACCEPTED");}
        catch(LaunchManifestReader.LaunchException error){check(error.code.equals("LAUNCH_PIN_CONTEXT"));}
        invalid(String.join("",Collections.nCopies(TextFrame.MAX_BYTES/2,astral)));
        System.out.println("Java runtime launch reader: "+checks+" structural/pin/privacy checks passed; no engine resolution or process delivery");
    }
}

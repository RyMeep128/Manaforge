package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Trusted Java gateway input ONLY, not a viewer message or another persistent deck format.
 * Structural/pin validation never certifies engine card support, format rules or seat ownership.
 * No file access, card substitution, engine startup or output/logging is performed. */
public final class LaunchManifestReader {
    private LaunchManifestReader() {}
    public static final class LaunchException extends IOException {
        public final String code;
        private LaunchException(String code){super(code);this.code=code;}
    }
    private static void fail(String code) throws LaunchException {throw new LaunchException(code);}
    private static void invalid() throws LaunchException {fail("LAUNCH_MANIFEST_INVALID");}
    private static JsonObject fields(JsonElement value,String... names) throws LaunchException {
        if(value==null || !value.isJsonObject())invalid();JsonObject object=value.getAsJsonObject();
        if(object.size()!=names.length)invalid();for(String name:names)if(!object.has(name))invalid();return object;
    }
    private static boolean blank(String value) {
        return value.codePoints().allMatch(c->Character.isWhitespace(c) || Character.isSpaceChar(c) || c==0x85);
    }
    private static String text(JsonElement value,boolean optional,boolean empty) throws LaunchException {
        if(optional && value!=null && value.isJsonNull())return null;
        if(value==null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString())invalid();
        String result=value.getAsString();if(result.codePointCount(0,result.length())>4096 || (!empty && blank(result)))invalid();return result;
    }
    private static String text(JsonElement value) throws LaunchException {return text(value,false,false);}
    private static long integer(JsonElement value,long minimum) throws LaunchException {
        if(value==null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber())invalid();
        long result=value.getAsLong();if(result<minimum)invalid();return result;
    }
    private static JsonArray array(JsonElement value) throws LaunchException {
        if(value==null || !value.isJsonArray())invalid();return value.getAsJsonArray();
    }
    private static void document(JsonElement value) throws LaunchException {
        JsonObject document=fields(value,"schema_version","deck");
        if(integer(document.get("schema_version"),Long.MIN_VALUE)!=1)fail("INCOMPATIBLE_DECK_SCHEMA");
        JsonObject deck=fields(document.get("deck"),"deck_id","name","format","entries","commander_entry_ids","companion_entry_id");
        for(String field:new String[]{"deck_id","name","format"})text(deck.get(field));
        JsonArray entries=array(deck.get("entries"));if(entries.size()>4096)invalid();
        Map<String,String> sections=new HashMap<>();
        for(JsonElement item:entries) {
            JsonObject entry=fields(item,"entry_id","name","quantity","section","card_id","oracle_id","set_code","collector_number","owned","image_asset_id","backside_asset_id");
            String id=text(entry.get("entry_id")),section=text(entry.get("section"));
            if(!Arrays.asList("mainboard","sideboard","commander").contains(section) || sections.put(id,section)!=null)invalid();
            text(entry.get("name"),false,true);integer(entry.get("quantity"),1);integer(entry.get("owned"),0);
            for(String field:new String[]{"card_id","oracle_id","set_code","collector_number","image_asset_id","backside_asset_id"})text(entry.get(field),true,false);
        }
        Set<String> commanders=new HashSet<>();
        for(JsonElement item:array(deck.get("commander_entry_ids"))) {
            String id=text(item);if(!commanders.add(id) || !sections.containsKey(id))invalid();
        }
        String companion=text(deck.get("companion_entry_id"),true,false);
        if(companion!=null && !"sideboard".equals(sections.get(companion)))invalid();
    }
    /** Expected pins must come from the host's validated runtime, never from this input itself.
     * Returned generated DTO is newly gateway-owned and mutable, not a public GameSnapshot.
     * Caller owns its lifetime and must never serialize it into a viewer channel. */
    public static LaunchContracts.LaunchManifest parse(String input,String expectedEngine,String expectedAdapter,String expectedManifestHash) throws LaunchException {
        if(expectedEngine==null || blank(expectedEngine) || expectedAdapter==null || blank(expectedAdapter)
                || expectedManifestHash==null || !expectedManifestHash.matches("[0-9a-f]{64}"))fail("LAUNCH_PIN_CONTEXT");
        try {
            JsonObject root=fields(WireEnvelope.parseObject(input),"launch_manifest_version","protocol_version","manifest_id","manaforge_version","engine","format","seats");
            if(integer(root.get("launch_manifest_version"),Long.MIN_VALUE)!=1)fail("INCOMPATIBLE_LAUNCH_VERSION");
            if(integer(root.get("protocol_version"),Long.MIN_VALUE)!=1)fail("INCOMPATIBLE_GAME_PROTOCOL");
            text(root.get("manifest_id"));text(root.get("manaforge_version"));
            String format=text(root.get("format"));if(!format.equals("freeform") && !format.equals("commander"))invalid();
            JsonObject pin=fields(root.get("engine"),"engine_version","adapter_version","artifact_manifest_sha256");
            if(!text(pin.get("engine_version")).equals(expectedEngine) || !text(pin.get("adapter_version")).equals(expectedAdapter)
                    || !text(pin.get("artifact_manifest_sha256")).equals(expectedManifestHash))fail("ENGINE_PIN_MISMATCH");
            JsonArray seats=array(root.get("seats"));if(seats.size()<2)invalid();Set<String> ids=new HashSet<>();
            for(JsonElement item:seats) {
                JsonObject seat=fields(item,"seat_id","name","controller","deck_owner_id","document");
                if(!ids.add(text(seat.get("seat_id"))))invalid();text(seat.get("name"));text(seat.get("deck_owner_id"),true,false);
                String controller=text(seat.get("controller"));if(!controller.equals("local_human") && !controller.equals("engine_ai"))invalid();
                document(seat.get("document"));
            }
            return new Gson().fromJson(root,LaunchContracts.LaunchManifest.class);
        }catch(LaunchException failure){throw failure;}
        catch(IOException | RuntimeException failure){throw new LaunchException("LAUNCH_MANIFEST_INVALID");}
    }
}

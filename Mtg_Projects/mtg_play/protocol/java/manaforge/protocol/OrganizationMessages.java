package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Pattern;

/** Standalone contract validator. Never call legacy dispatch with these messages. */
public final class OrganizationMessages {
    public static final int MAX_BYTES=262144;
    private static final JsonObject schema=JsonParser.parseString(OrganizationContractSchema.JSON).getAsJsonObject();
    private static final Pattern ID=Pattern.compile("[A-Za-z0-9_.:-]{1,128}");
    private static final String WHITE="[ \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
    private OrganizationMessages(){}
    public static final class Context {
        public final String matchEpoch,viewerId;
        public final long basisRevision;
        public final Map<String,String> objects,seats;
        public final Set<String> visibleSeats;
        public Context(String epoch,String viewer,long basis,Map<String,String> objects,Map<String,String> seats,Collection<String> admitted,Collection<String> visibleSeats){
            Set<String> allowed=new HashSet<>(admitted),roster=new HashSet<>(visibleSeats);
            if(!id(epoch) || !id(viewer) || basis<0 || objects.size()>1024 || roster.isEmpty() || roster.size()>8 || !objects.keySet().equals(seats.keySet()) || new HashSet<>(objects.values()).size()!=objects.size())throw new IllegalArgumentException("ORGANIZATION_CONTEXT");
            for(String seat:roster)if(!id(seat))throw new IllegalArgumentException("ORGANIZATION_CONTEXT");
            for(String handle:objects.keySet())if(!id(handle) || !id(objects.get(handle)) || !allowed.contains(objects.get(handle)) || !roster.contains(seats.get(handle)))throw new IllegalArgumentException("ORGANIZATION_CONTEXT");
            matchEpoch=epoch;viewerId=viewer;basisRevision=basis;this.objects=Collections.unmodifiableMap(new HashMap<>(objects));this.seats=Collections.unmodifiableMap(new HashMap<>(seats));this.visibleSeats=Collections.unmodifiableSet(roster);
        }
    }
    private static boolean id(String value){return value!=null && ID.matcher(value).matches();}
    public static int negotiate(Collection<Integer> local,Collection<Integer> peer,boolean authenticated){return authenticated && local!=null && peer!=null && local.contains(1) && peer.contains(1)?1:0;}
    private static boolean valid(JsonElement value,JsonElement element,JsonObject root){
        if(element.isJsonPrimitive())return element.getAsBoolean();JsonObject rule=element.getAsJsonObject();
        if(rule.has("$ref")){String ref=rule.get("$ref").getAsString();return valid(value,root.getAsJsonObject("$defs").get(ref.substring(ref.lastIndexOf('/')+1)),root);}
        if(rule.has("anyOf")){boolean found=false;for(JsonElement option:rule.getAsJsonArray("anyOf"))found|=valid(value,option,root);if(!found)return false;}
        if(rule.has("allOf"))for(JsonElement part:rule.getAsJsonArray("allOf"))if(!valid(value,part,root))return false;
        if(rule.has("if") && valid(value,rule.get("if"),root) && rule.has("then") && !valid(value,rule.get("then"),root))return false;
        if(rule.has("const") && !value.equals(rule.get("const")))return false;
        if(rule.has("enum")){boolean found=false;for(JsonElement option:rule.getAsJsonArray("enum"))found|=value.equals(option);if(!found)return false;}
        if(rule.has("type")){
            String type=rule.get("type").getAsString();boolean matches;
            switch(type){case "null":matches=value.isJsonNull();break;case "object":matches=value.isJsonObject();break;case "array":matches=value.isJsonArray();break;case "string":matches=value.isJsonPrimitive() && value.getAsJsonPrimitive().isString();break;case "integer":matches=value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber();break;default:return false;}
            if(!matches)return false;
        }
        if(value.isJsonObject()){
            JsonObject object=value.getAsJsonObject(),properties=rule.has("properties")?rule.getAsJsonObject("properties"):new JsonObject();
            if(rule.has("required"))for(JsonElement key:rule.getAsJsonArray("required"))if(!object.has(key.getAsString()))return false;
            for(Map.Entry<String,JsonElement> field:object.entrySet()){
                if(properties.has(field.getKey())){if(!valid(field.getValue(),properties.get(field.getKey()),root))return false;}
                else if(rule.has("additionalProperties") && !rule.get("additionalProperties").getAsBoolean())return false;
            }
        }
        if(value.isJsonArray()){
            JsonArray array=value.getAsJsonArray();if(rule.has("minItems") && array.size()<rule.get("minItems").getAsInt() || rule.has("maxItems") && array.size()>rule.get("maxItems").getAsInt())return false;
            Set<JsonElement> unique=new HashSet<>();for(JsonElement item:array){if(rule.has("items") && !valid(item,rule.get("items"),root))return false;if(rule.has("uniqueItems") && rule.get("uniqueItems").getAsBoolean() && !unique.add(item))return false;}
        }
        if(value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()){
            String text=value.getAsString();int length=text.codePointCount(0,text.length());
            if(rule.has("minLength") && length<rule.get("minLength").getAsInt() || rule.has("maxLength") && length>rule.get("maxLength").getAsInt())return false;
            if(rule.has("pattern") && !Pattern.compile(rule.get("pattern").getAsString()).matcher(text).find())return false;
        }
        if(value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber()){
            long number=value.getAsLong();if(rule.has("minimum") && number<rule.get("minimum").getAsLong() || rule.has("maximum") && number>rule.get("maximum").getAsLong())return false;
        }
        return true;
    }
    private static String text(JsonObject object,String field){return object.get(field).getAsString();}
    private static void require(boolean value,String code) throws IOException {if(!value)throw new WireEnvelope.EnvelopeException(code);}
    private static void name(JsonElement value) throws IOException {if(!value.isJsonNull())require(!value.getAsString().replaceAll(WHITE,"").isEmpty(),"ORGANIZATION_INVALID");}
    public static JsonObject parseContract(String raw) throws IOException {
        require(raw!=null && raw.length()<=MAX_BYTES && raw.getBytes(StandardCharsets.UTF_8).length<=MAX_BYTES,"ORGANIZATION_SIZE");
        JsonObject message=WireEnvelope.parseObject(raw);require(valid(message,schema,schema),"ORGANIZATION_INVALID");return message;
    }
    static JsonObject parseV2Contract(String raw) throws IOException {
        require(raw!=null && raw.length()<=MAX_BYTES && raw.getBytes(StandardCharsets.UTF_8).length<=MAX_BYTES,"ORGANIZATION_SIZE");JsonObject message=WireEnvelope.parseObject(raw);JsonObject v2=JsonParser.parseString(OrganizationV2ContractSchema.JSON).getAsJsonObject();require(valid(message,v2,v2),"ORGANIZATION_INVALID");return message;
    }
    /** Receipts carry no object mappings; only a known pending command can admit historical basis. */
    public static JsonObject parseReceipt(String raw,String trustedMatchEpoch,Collection<String> pendingCommandIds) throws IOException {
        JsonObject message=parseContract(raw);require(text(message,"message_type").equals("organization_receipt"),"ORGANIZATION_INVALID");JsonObject body=message.getAsJsonObject("body");
        require(text(body,"match_epoch").equals(trustedMatchEpoch) && pendingCommandIds!=null && pendingCommandIds.contains(text(body,"command_id")),"ORGANIZATION_CONTEXT");return message;
    }
    public static JsonObject parse(String raw,Context context) throws IOException {
        JsonObject message=parseContract(raw);String type=text(message,"message_type");JsonObject body=message.getAsJsonObject("body");
        if(type.equals("organization_capabilities"))return message;
        require(context!=null && text(body,"match_epoch").equals(context.matchEpoch) && body.get("basis_revision").getAsLong()==context.basisRevision,"ORGANIZATION_CONTEXT");
        if(type.equals("organization_command")){
            JsonObject operation=body.getAsJsonObject("operation");name(operation.get("name"));Set<String> selected=new HashSet<>();
            for(JsonElement token:operation.getAsJsonArray("members")){String handle=token.getAsString();require(selected.add(handle) && context.objects.containsKey(handle),"ORGANIZATION_CONTEXT");}
        }
        if(type.equals("organization_snapshot")){
            require(text(body,"viewer_id").equals(context.viewerId),"ORGANIZATION_CONTEXT");
            Set<String> seats=new HashSet<>(),groups=new HashSet<>(),objects=new HashSet<>();Map<String,String> membership=new HashMap<>();
            for(JsonElement token:body.getAsJsonArray("seats")){
                JsonObject seat=token.getAsJsonObject();String seatId=text(seat,"seat_id");require(seats.add(seatId) && context.visibleSeats.contains(seatId),"ORGANIZATION_CONTEXT");
                for(JsonElement member:seat.getAsJsonArray("root"))require(membership.put(member.getAsString(),seatId)==null,"ORGANIZATION_INVALID");
                for(JsonElement entry:seat.getAsJsonArray("groups")){JsonObject group=entry.getAsJsonObject();require(groups.add(text(group,"group_id")),"ORGANIZATION_INVALID");name(group.get("name"));for(JsonElement member:group.getAsJsonArray("members"))require(membership.put(member.getAsString(),seatId)==null,"ORGANIZATION_INVALID");}
            }
            require(membership.size()<=1024,"ORGANIZATION_INVALID");Set<String> mapped=new HashSet<>();
            for(JsonElement token:body.getAsJsonArray("mappings")){
                JsonObject mapping=token.getAsJsonObject();String handle=text(mapping,"handle"),reference=text(mapping,"object_reference"),seat=text(mapping,"seat_id");
                require(mapped.add(handle) && objects.add(reference) && reference.equals(context.objects.get(handle)) && seat.equals(context.seats.get(handle)) && seat.equals(membership.get(handle)),"ORGANIZATION_CONTEXT");
            }
            require(mapped.equals(membership.keySet()),"ORGANIZATION_INVALID");
        }
        return message;
    }
    public static String serialize(JsonObject message,Context context) throws IOException {String raw=message.toString();parse(raw,context);return raw;}
}

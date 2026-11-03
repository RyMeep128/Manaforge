package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Header plus decision-family command/ack/shutdown bodies; not a gameplay dispatcher. */
public final class WireMessages {
    public static final int MAX_AMOUNT_VALUES = 1024;
    private static final List<String> REJECTIONS = Arrays.asList("SESSION_MISMATCH", "VIEWER_MISMATCH", "STALE_REVISION",
        "STALE_DECISION", "ACTION_UNAVAILABLE", "COMMAND_PENDING", "ENGINE_REJECTED");
    private static boolean id(JsonElement token) {
        return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isString()
            && token.getAsString().matches("[A-Za-z0-9_.:-]{1,128}");
    }
    private static boolean string(JsonElement token) { return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isString(); }
    private static boolean revision(JsonElement token) {
        return token != null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isNumber() && token.getAsLong() >= 0;
    }
    private static boolean keys(JsonObject body, String... keys) {
        return body.size() == keys.length && body.keySet().containsAll(Arrays.asList(keys));
    }
    private static void fail() throws WireEnvelope.EnvelopeException { throw new WireEnvelope.EnvelopeException("MESSAGE_INVALID"); }
    public static JsonObject parse(String text) throws IOException {
        JsonObject envelope = WireEnvelope.parse(text), body = envelope.getAsJsonObject("body");
        String type = envelope.get("message_type").getAsString();
        if (type.equals("command")) {
            if (!id(body.get("session_id")) || !id(body.get("viewer_id")) || !revision(body.get("revision"))
                || !id(body.get("decision_id")) || !string(body.get("operation"))) fail();
            String argument=null;
            switch(body.get("operation").getAsString()) {
                case "perform": argument="action_id";if(!id(body.get(argument)))fail();break;
                case "choose": argument="option_id";if(!id(body.get(argument)))fail();break;
                case "select_mana_source": argument="object_id";if(!id(body.get(argument)))fail();break;
                case "choose_number": argument="value";if(!integer(body.get(argument)))fail();break;
                case "choose_amounts":
                    argument="values";
                    if(!body.has(argument) || !body.get(argument).isJsonArray() || body.getAsJsonArray(argument).size()>MAX_AMOUNT_VALUES)fail();
                    for(JsonElement amount:body.getAsJsonArray(argument))if(!integer(amount))fail();
                    break;
                case "finish_selection":case "cancel":break;
                default:fail();
            }
            List<String> required=new ArrayList<>(Arrays.asList("session_id","viewer_id","revision","operation","decision_id"));
            if(argument!=null)required.add(argument);
            if(!keys(body,required.toArray(new String[0])))fail();
        } else if (type.equals("ack")) {
            if (!keys(body, "session_id", "viewer_id", "command_id", "request_revision", "outcome", "code")
                || !id(body.get("session_id")) || !id(body.get("viewer_id")) || !(id(body.get("command_id")) && body.get("command_id").getAsString().matches("[A-Za-z0-9_-]{1,128}"))
                || !revision(body.get("request_revision")) || !string(body.get("outcome"))) fail();
            String outcome = body.get("outcome").getAsString();
            String code = string(body.get("code")) ? body.get("code").getAsString() : null;
            boolean noCode = body.get("code").isJsonNull();
            if (!((outcome.equals("submitted") || outcome.equals("confirmed")) && noCode)
                && !(outcome.equals("rejected") && REJECTIONS.contains(code))
                && !(outcome.equals("uncertain") && "COMMAND_UNCERTAIN".equals(code))) fail();
        } else if (type.equals("shutdown")) {
            if (!keys(body, "session_id", "viewer_id", "reason") || !id(body.get("session_id")) || !id(body.get("viewer_id"))
                || !string(body.get("reason")) || !Arrays.asList("client_close", "cancel", "startup_failed").contains(body.get("reason").getAsString())) fail();
        } else throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
        return envelope;
    }
    private static boolean integer(JsonElement token) {
        return token!=null && token.isJsonPrimitive() && token.getAsJsonPrimitive().isNumber();
    }
    private static String binding(JsonObject body,String session,String viewer,long revision,String decision) {
        if(!body.get("session_id").getAsString().equals(session))return "SESSION_MISMATCH";
        if(!body.get("viewer_id").getAsString().equals(viewer))return "VIEWER_MISMATCH";
        if(body.get("revision").getAsLong()!=revision)return "STALE_REVISION";
        if(!body.get("decision_id").getAsString().equals(decision))return "STALE_DECISION";
        return null;
    }
    /** Context comparison only, never authorization of an option/source/value/cancellation. */
    public static String checkBinding(String text,String session,String viewer,long revision,String decision) throws IOException {
        JsonObject envelope=parse(text);
        if(!envelope.get("message_type").getAsString().equals("command"))throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
        return binding(envelope.getAsJsonObject("body"),session,viewer,revision,decision);
    }
    /** Existing perform-only action comparison, serialized with execution by future gateway. */
    public static String checkCurrent(String text, String session, String viewer, long revision,
        String decision, Collection<String> actions) throws IOException {
        JsonObject envelope = parse(text);
        if (!envelope.get("message_type").getAsString().equals("command") || !envelope.getAsJsonObject("body").get("operation").getAsString().equals("perform"))
            throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
        JsonObject body = envelope.getAsJsonObject("body");
        String mismatch=binding(body,session,viewer,revision,decision);
        if(mismatch!=null)return mismatch;
        return actions.contains(body.get("action_id").getAsString())?null:"ACTION_UNAVAILABLE";
    }
}

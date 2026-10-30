package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.math.BigInteger;
import java.util.*;

/** Viewer-offered address/bounds checks only. Never executes or confirms engine actions. */
public final class GatewayCommandGate implements AutoCloseable {
    private final String session,viewer;
    private final ReceiveHistory history;
    private final Set<String> actions=new HashSet<>(),options=new HashSet<>(),objects=new HashSet<>();
    private JsonObject decision;
    private boolean closed,faulted;
    public GatewayCommandGate(GatewayHandshake.ViewerContext context,boolean fixtureMode,int capacity) {
        if(context==null)throw new IllegalArgumentException("GATE_CONTEXT");
        session=context.sessionId;viewer=context.viewerId;
        history=new ReceiveHistory(session,viewer,fixtureMode,capacity);
    }
    private void clear(){decision=null;actions.clear();options.clear();objects.clear();}
    private void open() throws WireEnvelope.EnvelopeException {
        if(closed || faulted)throw new WireEnvelope.EnvelopeException("GATE_CLOSED");
    }
    /** Trusted viewer-filtered output, serialized with engine dispatch by the future session owner. */
    public synchronized void observe(String text) throws IOException {
        open();
        try {
            long previous=history.revision();JsonObject envelope=history.accept(text);
            if(envelope==null)return;
            String type=envelope.get("message_type").getAsString();
            if(type.equals("event")){if(history.revision()>previous)clear();return;}
            clear();JsonObject snapshot=envelope.getAsJsonObject("body").getAsJsonObject("snapshot");
            if(type.equals("result") || !snapshot.get("status").getAsString().equals("active") || snapshot.get("decision").isJsonNull())return;
            JsonObject offered=snapshot.getAsJsonObject("decision");
            if(!offered.get("player_id").getAsString().equals(viewer))return;
            decision=new JsonObject();
            for(String field:new String[]{"decision_id","family","can_finish","cancellable","minimum","maximum"})decision.add(field,offered.get(field).deepCopy());
            JsonArray ranges=new JsonArray();
            for(JsonElement item:offered.getAsJsonArray("amounts")) {
                JsonObject range=new JsonObject();
                for(String field:new String[]{"minimum","maximum"})range.add(field,item.getAsJsonObject().get(field).deepCopy());
                ranges.add(range);
            }
            decision.add("amounts",ranges);
            for(JsonElement action:snapshot.getAsJsonArray("actions"))actions.add(action.getAsJsonObject().get("action_id").getAsString());
            for(JsonElement option:offered.getAsJsonArray("options"))options.add(option.getAsJsonObject().get("option_id").getAsString());
            for(JsonElement object:snapshot.getAsJsonArray("objects"))objects.add(object.getAsJsonObject().get("object_id").getAsString());
        }catch(IOException | RuntimeException error){clear();faulted=true;history.close();throw error;}
    }
    /** Null means offered, not legal or submitted. No state mutation, replay reservation or engine call. */
    public synchronized String check(String text) throws IOException {
        open();JsonObject envelope=WireMessages.parse(text);
        if(!envelope.get("message_type").getAsString().equals("command"))throw new WireEnvelope.EnvelopeException("MESSAGE_UNSUPPORTED");
        String mismatch=WireMessages.checkBinding(text,session,viewer,history.revision(),decision==null?null:decision.get("decision_id").getAsString());
        if(mismatch!=null)return mismatch;
        if(decision==null)return "ACTION_UNAVAILABLE";
        JsonObject body=envelope.getAsJsonObject("body");String operation=body.get("operation").getAsString(),family=decision.get("family").getAsString();boolean allowed=false;
        switch(operation) {
            case "perform":allowed=actions.contains(body.get("action_id").getAsString());break;
            case "choose":allowed=options.contains(body.get("option_id").getAsString());break;
            case "finish_selection":allowed=decision.get("can_finish").getAsBoolean();break;
            case "cancel":allowed=decision.get("cancellable").getAsBoolean();break;
            case "select_mana_source":allowed=family.equals("mana") && objects.contains(body.get("object_id").getAsString());break;
            case "choose_number":case "choose_amounts":allowed=numeric(operation,family,body);break;
            default:break;
        }
        return allowed?null:"ACTION_UNAVAILABLE";
    }
    private boolean numeric(String operation,String family,JsonObject body) {
        if(!family.equals(operation.equals("choose_number")?"number":"amounts") || decision.get("minimum").isJsonNull() || decision.get("maximum").isJsonNull())return false;
        long minimum=decision.get("minimum").getAsLong(),maximum=decision.get("maximum").getAsLong();
        if(minimum>maximum)return false;
        if(operation.equals("choose_number")){long value=body.get("value").getAsLong();return value>=minimum && value<=maximum;}
        JsonArray values=body.getAsJsonArray("values"),ranges=decision.getAsJsonArray("amounts");
        if(values.size()!=ranges.size() || ranges.size()>WireMessages.MAX_AMOUNT_VALUES)return false;
        BigInteger total=BigInteger.ZERO;
        for(int i=0;i<values.size();i++) {
            JsonObject range=ranges.get(i).getAsJsonObject();long value=values.get(i).getAsLong(),low=range.get("minimum").getAsLong(),high=range.get("maximum").getAsLong();
            if(low>high || value<low || value>high)return false;total=total.add(BigInteger.valueOf(value));
        }
        return total.compareTo(BigInteger.valueOf(minimum))>=0 && total.compareTo(BigInteger.valueOf(maximum))<=0;
    }
    public synchronized void close(){if(closed)return;closed=true;clear();history.close();}
}

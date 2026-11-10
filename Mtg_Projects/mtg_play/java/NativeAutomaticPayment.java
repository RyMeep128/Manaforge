import com.google.gson.*;
import java.io.IOException;
import java.util.*;
import manaforge.payment.PaymentCoordinator;
import manaforge.payment.PaymentCoordinator.*;

/** Private automatic responses between viewer decision windows. Enqueue only claims a local
 * job; native IO happens after consider() returns, on the same serialized response owner.
 * No client command/receipt is invented for an internal payment response. */
public final class NativeAutomaticPayment implements AutoCloseable {
    private final PaymentCoordinator coordinator;private final String session,viewer;
    private String reason="NONE";private Context current;private Long cycle;private JsonObject assessment;private Attempt queued;private int steps,fallbacks,completed,reassessments;private final Map<String,Integer> outcomes=new TreeMap<>();private String lastFallback;
    public NativeAutomaticPayment(String session,String viewer,Mode mode) {
        this.session=session;this.viewer=viewer;
        coordinator=new PaymentCoordinator(session,viewer,true,mode,new EnginePort(){
            public boolean isCurrent(Context context){return context==current;}
            public Assessment inspect(Context context){
                if(context!=current || assessment==null || !new JsonPrimitive("VERIFIED_ORDINARY_EQUIVALENT").equals(assessment.get("safety")))return new Assessment(Safety.UNKNOWN,Collections.emptyList());
                List<String> tokens=new ArrayList<>();for(JsonElement item:assessment.getAsJsonArray("steps"))tokens.add(item.getAsJsonObject().get("source").getAsString());
                return new Assessment(Safety.VERIFIED_ORDINARY_EQUIVALENT,tokens);
            }
            public Submission enqueue(Attempt attempt){if(attempt.context!=current || queued!=null)return Submission.REJECTED;queued=attempt;return Submission.ENQUEUED;}
        });
    }
    public JsonObject prepare(JsonObject state,JsonObject prompt,JsonObject guard) {
        if(coordinator.mode()!=Mode.AUTO){reason=coordinator.mode().name()+"_MODE";return null;}
        if(queued!=null || !"GAME_PLAY_MANA".equals(text(prompt,"kind")) || !viewer.equals(text(state,"viewer")))return null;
        if(!"ok".equals(text(guard,"status")) || !state.get("cycle").equals(guard.get("cycle")))return null;
        cycle=state.get("cycle").getAsLong();assessment=guard.has("ordinary_payment")?guard.getAsJsonObject("ordinary_payment").deepCopy():null;
        reason=assessment==null?"NO_CONTEXT":text(assessment,"reason");if(assessment==null || !assessment.has("sequence")){
            String key=text(prompt,"decision_id")+":"+reason;if(!key.equals(lastFallback)){fallbacks++;String outcome=assessment==null?"NO_CONTEXT":text(assessment,"outcome");outcomes.put(outcome,outcomes.getOrDefault(outcome,0)+1);lastFallback=key;}return null;}
        current=new Context(session,viewer,"payment-"+(assessment.has("plan_token")?text(assessment,"plan_token"):text(assessment,"sequence"))+"-"+reassessments,"native-"+text(prompt,"decision_id"),prompt.get("decision_id").getAsLong());
        if(!coordinator.offer(current)){reason=coordinator.state()==State.UNCERTAIN?"PREVIOUS_PAYMENT_UNCERTAIN":"PAYMENT_ALREADY_ATTEMPTED";return null;}Attempt attempt=coordinator.consider();if(attempt==null){coordinator.claimManual(current);fallbacks++;return null;}
        JsonObject command=new JsonObject();command.addProperty("protocol",1);command.addProperty("command","respond");command.addProperty("request_id","auto-mana-"+UUID.randomUUID());command.add("game_id",state.get("game_id"));command.add("decision_id",prompt.get("decision_id"));if(attempt.engineStepToken.startsWith("pool:")){command.addProperty("kind","mana_type");command.addProperty("value",attempt.engineStepToken.substring(5));command.addProperty("player_id",viewer);}
        else{command.addProperty("kind","object");command.addProperty("value",attempt.engineStepToken);}return command;
    }
    public boolean revalidate(JsonObject guard) {
        if(queued==null || !"ok".equals(text(guard,"status")) || !guard.has("cycle") || cycle==null || guard.get("cycle").getAsLong()!=cycle || !guard.has("ordinary_payment"))return false;
        JsonObject fresh=guard.getAsJsonObject("ordinary_payment");if(!assessment.equals(fresh))return false;
        return new JsonPrimitive("VERIFIED_ORDINARY_EQUIVALENT").equals(fresh.get("safety"));
    }
    public void observed(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeGuard,JsonObject accepted,JsonObject after,JsonObject next,JsonObject afterGuard) throws IOException {
        if(queued==null || NativeCastCorrelation.coreCombatResponseEvidence(before,prompt,command,beforeGuard,accepted,after,next,afterGuard)==null){uncertain();throw new IOException("AUTO_PAYMENT_UNPROVEN");}
        String id=queued.engineStepToken;
        if(id.startsWith("pool:")){
            JsonObject probe=afterGuard.has("payment_probe")?afterGuard.getAsJsonObject("payment_probe"):null;
            boolean progress=probe!=null && probe.has("unpaid_mana_count") && probe.get("unpaid_mana_count").getAsInt()<assessment.get("unpaid_count").getAsInt();
            JsonObject execution=afterGuard.has("payment_execution")?afterGuard.getAsJsonObject("payment_execution"):null;
            boolean done=execution!=null && assessment.has("plan_token") && assessment.get("plan_token").equals(execution.get("plan_token")) && new JsonPrimitive(true).equals(execution.get("completed"));
            if(!progress && !done){uncertain();throw new IOException("AUTO_PAYMENT_POOL_UNPROVEN");}
            coordinator.observe(queued,done?Observation.COMPLETE:Observation.PROGRESS);queued=null;steps++;if(done)completed++;return;
        }
        JsonObject receipt=afterGuard.has("payment_execution")?afterGuard.getAsJsonObject("payment_execution"):null;
        if(receipt==null || !assessment.has("plan_token") || !assessment.get("plan_token").equals(receipt.get("plan_token"))
            || !assessment.get("sequence").equals(receipt.get("sequence")) || !id.equals(text(receipt,"source"))
            || receipt.get("activated")==null || !receipt.get("activated").isJsonPrimitive() || !receipt.getAsJsonPrimitive("activated").isBoolean()){uncertain();throw new IOException("AUTO_PAYMENT_EXECUTION_UNPROVEN");}
        if(!receipt.get("activated").getAsBoolean()){coordinator.observe(queued,Observation.REJECTED);queued=null;reason="NATIVE_ACTIVATION_REJECTED";return;}
        boolean paid=new JsonPrimitive(true).equals(receipt.get("completed"));
        JsonObject probe=afterGuard.has("payment_probe")?afterGuard.getAsJsonObject("payment_probe"):null;
        if(!paid && (probe==null || !probe.has("sequence") || probe.get("sequence").getAsLong()<=assessment.get("sequence").getAsLong())) {
            // The game may pause for another genuine choice before the enclosing
            // spell/ability finishes. Activation is proven; completion is not.
            reason="PAYMENT_PAUSED_FOR_CHOICE";
        }
        coordinator.observe(queued,paid?Observation.COMPLETE:Observation.PROGRESS);queued=null;steps++;if(paid)completed++;
    }
    public void observedTerminal(JsonObject command,JsonObject accepted,JsonObject terminal) {
        JsonObject receipt=terminal.has("payment_execution")?terminal.getAsJsonObject("payment_execution"):null;
        boolean proved=queued!=null && receipt!=null && assessment!=null && assessment.has("plan_token")
            && assessment.get("plan_token").equals(receipt.get("plan_token")) && assessment.get("sequence").equals(receipt.get("sequence"))
            && new JsonPrimitive(true).equals(receipt.get("activated")) && new JsonPrimitive(true).equals(receipt.get("completed"))
            && new JsonPrimitive(true).equals(accepted.get("accepted")) && command.get("request_id").equals(accepted.get("request_id"));
        if(proved){coordinator.observe(queued,Observation.COMPLETE);queued=null;steps++;completed++;}else uncertain();
    }
    public void rejectedBeforeSubmission(){if(queued!=null)coordinator.observe(queued,Observation.REJECTED);queued=null;assessment=null;current=null;reassessments++;outcomes.put("STALE_CONTEXT",outcomes.getOrDefault("STALE_CONTEXT",0)+1);reason="STALE_CONTEXT";}
    public void setMode(Mode mode){coordinator.setMode(mode);}
    public void uncertain(){if(queued!=null)coordinator.observe(queued,Observation.UNCERTAIN);}
    public String reason(){return reason;}
    public JsonObject report(){JsonObject result=new JsonObject();result.addProperty("native_auto_payment_last_reason",reason);result.addProperty("native_auto_payment_steps",steps);result.addProperty("native_auto_payment_completed",completed);result.addProperty("native_auto_payment_manual_windows",fallbacks);result.addProperty("native_auto_payment_mode",coordinator.mode().name());result.add("native_auto_payment_outcomes",new Gson().toJsonTree(outcomes));return result;}
    private static String text(JsonObject row,String key){JsonElement value=row.get(key);return value==null || value.isJsonNull()?"":value.getAsString();}
    public void close(){coordinator.close();assessment=null;current=null;queued=null;}
}

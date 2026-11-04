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
    private String reason="NONE";private Context current;private Long cycle;private JsonObject assessment;private Attempt queued;private int steps,fallbacks,completed;
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
        reason=assessment==null?"NO_CONTEXT":text(assessment,"reason");if(assessment==null || !assessment.has("sequence")){fallbacks++;return null;}
        current=new Context(session,viewer,"payment-"+text(assessment,"sequence"),"native-"+text(prompt,"decision_id"),prompt.get("decision_id").getAsLong());
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
            boolean done=!"GAME_PLAY_MANA".equals(text(next,"kind"));
            if(!progress && !done){uncertain();throw new IOException("AUTO_PAYMENT_POOL_UNPROVEN");}
            coordinator.observe(queued,done?Observation.COMPLETE:Observation.PROGRESS);queued=null;steps++;if(done)completed++;return;
        }
        Long incarnation=null;for(JsonElement item:assessment.getAsJsonArray("steps")){JsonObject step=item.getAsJsonObject();if(id.equals(text(step,"source")))incarnation=step.get("incarnation").getAsLong();}
        JsonObject metadata=afterGuard.getAsJsonObject("objects").getAsJsonObject(id);boolean tapped=false;
        for(JsonElement player:after.getAsJsonArray("players"))for(JsonElement card:player.getAsJsonObject().getAsJsonArray("battlefield"))if(id.equals(text(card.getAsJsonObject(),"id")))tapped=new JsonPrimitive(true).equals(card.getAsJsonObject().get("tapped"));
        if(incarnation==null || metadata==null || metadata.get("incarnation").getAsLong()!=incarnation || !viewer.equals(text(metadata,"controller")) || !tapped){uncertain();throw new IOException("AUTO_PAYMENT_SOURCE_UNPROVEN");}
        boolean paid=false;if(new JsonPrimitive(true).equals(next.get("is_priority")))for(JsonElement item:after.getAsJsonArray("stack")){JsonObject entry=afterGuard.getAsJsonObject("objects").getAsJsonObject(text(item.getAsJsonObject(),"id"));paid|=entry!=null && text(assessment,"paying_source").equals(text(entry,"source")) && entry.has("source_incarnation");}
        coordinator.observe(queued,paid?Observation.COMPLETE:Observation.PROGRESS);queued=null;steps++;if(paid)completed++;
    }
    public void setMode(Mode mode){coordinator.setMode(mode);}
    public void uncertain(){if(queued!=null)coordinator.observe(queued,Observation.UNCERTAIN);}
    public String reason(){return reason;}
    public JsonObject report(){JsonObject result=new JsonObject();result.addProperty("native_auto_payment_last_reason",reason);result.addProperty("native_auto_payment_steps",steps);result.addProperty("native_auto_payment_completed",completed);result.addProperty("native_auto_payment_manual_windows",fallbacks);result.addProperty("native_auto_payment_mode",coordinator.mode().name());return result;}
    private static String text(JsonObject row,String key){JsonElement value=row.get(key);return value==null || value.isJsonNull()?"":value.getAsString();}
    public void close(){coordinator.close();assessment=null;current=null;queued=null;}
}

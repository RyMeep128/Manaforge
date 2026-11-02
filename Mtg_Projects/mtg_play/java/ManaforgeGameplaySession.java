import com.google.gson.*;
import java.io.IOException;
import java.util.Objects;

/** Reusable native decision continuation. No fixture policy, card names or rules calculations.
 * The engine/transport is borrowed. All calls belong to the serialized session owner. */
public final class ManaforgeGameplaySession implements AutoCloseable {
    public interface Engine {
        JsonObject metadata(JsonObject state,String... ids) throws Exception;
        JsonObject submit(JsonObject command) throws Exception;
        Advance advance(long previousDecision) throws Exception;
        JsonObject terminalMetadata(JsonObject before) throws Exception;
    }
    public interface Observer {
        default void before(JsonObject state,JsonObject prompt,JsonObject command) throws Exception {}
        default boolean after(JsonObject state,JsonObject prompt) throws Exception {return false;}
        default void terminal(String outcome) throws Exception {}
    }
    public static final class Advance {
        final JsonObject state,prompt,terminal;
        public Advance(JsonObject state,JsonObject prompt,JsonObject terminal) {
            this.state=Objects.requireNonNull(state).deepCopy();
            this.prompt=prompt==null?null:prompt.deepCopy();this.terminal=terminal==null?null:terminal.deepCopy();
        }
    }
    private final Thread owner=Thread.currentThread();
    private final ManaforgeOpeningProjection projection;
    private final Engine engine;private final Observer observer;private final boolean casting;
    private long serial;private boolean stopped;private long generation;
    public ManaforgeGameplaySession(ManaforgeOpeningProjection projection,Engine engine,Observer observer,boolean casting) {
        this.projection=Objects.requireNonNull(projection);this.engine=Objects.requireNonNull(engine);
        this.observer=observer==null?new Observer(){}:observer;this.casting=casting;
    }
    private void current(){if(Thread.currentThread()!=owner || stopped)throw new IllegalStateException("GAMEPLAY_OWNER_CLOSED");}
    private JsonObject envelope(JsonObject snapshot) {
        JsonObject result=new JsonObject(),body=new JsonObject();result.addProperty("wire_version",1);
        result.addProperty("message_type","snapshot");result.addProperty("message_id","gameplay-"+(serial++));
        body.addProperty("fixture_only",false);body.add("snapshot",snapshot);result.add("body",body);return result;
    }
    public ManaforgeUnityOpening.TurnOffer offer(JsonObject state,JsonObject nativePrompt) throws Exception {
        current();if(serial>=4096)throw new IOException("GAMEPLAY_LIMIT");
        final long offered=++generation;
        final JsonObject before=state.deepCopy(),prompt=nativePrompt.deepCopy(),guard=engine.metadata(before);
        if(guard.has("combat_reselect_kind") && "GAME_SELECT".equals(prompt.get("kind").getAsString()) && new JsonPrimitive(false).equals(prompt.get("is_priority"))) {
            String key=guard.get("combat_reselect_kind").getAsString();
            if(!prompt.has(key) || !(key.equals("attackers") ^ key.equals("blockers")))throw new IOException("GAMEPLAY_RESELECT_UNPROVEN");
            for(JsonElement id:guard.getAsJsonArray("combat_reselect"))if(!prompt.getAsJsonArray(key).contains(id))prompt.getAsJsonArray(key).add(id);
        }
        JsonObject view=envelope(projection.projectCoreCombat(before,prompt,casting));
        return new ManaforgeUnityOpening.TurnOffer(view,prompt.get("decision_id").getAsLong(),before.get("cycle").getAsLong(),command->{
            current();if(offered!=generation)throw new IOException("STALE_DECISION");generation++;
            observer.before(before.deepCopy(),prompt.deepCopy(),command.deepCopy());
            JsonObject accepted=engine.submit(command);
            if(!new JsonPrimitive(true).equals(accepted.get("accepted")))throw new IOException("GAMEPLAY_RESPONSE_REJECTED");
            Advance next=engine.advance(prompt.get("decision_id").getAsLong());
            if(next.terminal!=null) {
                JsonObject terminal=engine.terminalMetadata(before);
                NativeCastCorrelation.TurnDecisionEvidence proof=NativeCastCorrelation.terminalCombatEvidence(before,prompt,command,guard,accepted,terminal,next.terminal);
                if(proof==null)throw new IOException("GAMEPLAY_TERMINAL_UNPROVEN");
                String outcome=terminal.get("outcome").getAsString();observer.terminal(outcome);
                JsonObject result=envelope(projection.projectCombatResult(next.state,outcome));result.addProperty("message_type","result");stopped=true;
                return new ManaforgeUnityOpening.TurnResult(result,proof,null);
            }
            if(next.prompt==null)throw new IOException("GAMEPLAY_NEXT_DECISION_MISSING");
            JsonObject nextGuard=engine.metadata(next.state);
            NativeCastCorrelation.TurnDecisionEvidence proof=NativeCastCorrelation.coreCombatResponseEvidence(before,prompt,command,guard,accepted,next.state,next.prompt,nextGuard);
            if(proof==null)throw new IOException("GAMEPLAY_RESPONSE_UNPROVEN");
            if(observer.after(next.state.deepCopy(),next.prompt.deepCopy())) {
                JsonObject last=projection.projectCoreCombat(next.state,next.prompt,casting);last.add("decision",JsonNull.INSTANCE);last.add("actions",new JsonArray());
                projection.invalidateDecision();stopped=true;return new ManaforgeUnityOpening.TurnResult(envelope(last),proof,null);
            }
            ManaforgeUnityOpening.TurnOffer following=offer(next.state,next.prompt);
            return new ManaforgeUnityOpening.TurnResult(following.snapshot(),proof,following);
        });
    }
    public void close(){if(Thread.currentThread()!=owner)throw new IllegalStateException("GAMEPLAY_OWNER");stopped=true;generation++;projection.invalidateDecision();}
}

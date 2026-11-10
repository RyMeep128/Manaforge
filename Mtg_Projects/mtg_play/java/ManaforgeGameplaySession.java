import com.google.gson.*;
import java.io.IOException;
import java.util.Objects;
import java.util.List;
import java.util.ArrayList;

/** Reusable native decision continuation. No fixture policy, card names or rules calculations.
 * The engine/transport is borrowed. All calls belong to the serialized session owner. */
public final class ManaforgeGameplaySession implements AutoCloseable {
    public interface Engine {
        JsonObject metadata(JsonObject state,String... ids) throws Exception;
        JsonObject submit(JsonObject command) throws Exception;
        Advance advance(long previousDecision) throws Exception;
        JsonObject terminalMetadata(JsonObject before) throws Exception;
        default JsonObject pollRequest() throws Exception {return null;}
        default String sessionNotice() throws Exception {return null;}
        default boolean requestCurrent(String id) throws Exception {return false;}
        default Advance refresh() throws Exception {return null;}
        default Advance resume(Advance fresh) throws Exception {return fresh;}
    }
    public interface Observer {
        default void before(JsonObject state,JsonObject prompt,JsonObject command) throws Exception {}
        default boolean after(JsonObject state,JsonObject prompt) throws Exception {return false;}
        default void terminal(String outcome) throws Exception {}
        default void terminal(String outcome,JsonObject state,JsonObject metadata) throws Exception {terminal(outcome);}
        default void unsupported(String code) throws Exception {}
        default void unsupported(String code,JsonObject context) throws Exception {unsupported(code);}
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
        current();if(serial>=4095)throw new IOException("GAMEPLAY_LIMIT");
        JsonObject request=engine.pollRequest();if(request!=null)return offerRequest(state,nativePrompt,request);
        final long offered=++generation;
        final JsonObject before=state.deepCopy(),prompt=nativePrompt.deepCopy();java.util.List<String> stackedIds=new java.util.ArrayList<>();for(JsonElement card:before.getAsJsonArray("stack"))stackedIds.add(card.getAsJsonObject().get("id").getAsString());for(JsonElement card:before.getAsJsonArray("exile")){JsonObject row=card.getAsJsonObject();if(new JsonPrimitive(false).equals(row.get("hidden")) && new JsonPrimitive(false).equals(row.get("face_down")))stackedIds.add(row.get("id").getAsString());}final JsonObject guard=engine.metadata(before,stackedIds.toArray(new String[0]));
        if(!new JsonPrimitive("ok").equals(guard.get("status")) || !before.get("cycle").equals(guard.get("cycle")))throw new IOException("GAMEPLAY_CONTEXT_UNPROVEN");
        JsonObject publicView=decorate(before,guard);
        if(guard.has("combat_reselect_kind") && "GAME_SELECT".equals(prompt.get("kind").getAsString()) && new JsonPrimitive(false).equals(prompt.get("is_priority"))) {
            String key=guard.get("combat_reselect_kind").getAsString();
            if(!prompt.has(key) || !(key.equals("attackers") ^ key.equals("blockers")))throw new IOException("GAMEPLAY_RESELECT_UNPROVEN");
            for(JsonElement id:guard.getAsJsonArray("combat_reselect"))if(!prompt.getAsJsonArray(key).contains(id))prompt.getAsJsonArray(key).add(id);
        }
        if(guard.has("targeting_context") && "GAME_TARGET".equals(prompt.get("kind").getAsString()))prompt.add("targeting_context",guard.get("targeting_context"));
        JsonObject projected;
        try{projected=projection.projectCoreCombat(publicView,prompt,casting);}catch(IOException unsupported){
            if(!"LIVE_OPENING_PROJECTION_UNSUPPORTED".equals(unsupported.getMessage()))throw unsupported;
            String code=projection.unsupportedCode();JsonObject context=new JsonObject();
            for(String key:new String[]{"phase","step"}){JsonElement value=before.get(key);if(value!=null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString() && value.getAsString().matches("[A-Z_]{1,40}"))context.add(key,value);}
            String family=prompt.get("kind").getAsString();if(family.matches("[A-Z_]{1,40}"))context.addProperty("prompt_family",family);
            for(String key:new String[]{"targets","choices","cards","amounts"})if(prompt.has(key) && prompt.get(key).isJsonArray() && prompt.getAsJsonArray(key).size()<=256)context.addProperty(key+"_count",prompt.getAsJsonArray(key).size());
            observer.unsupported(code,context);
            if(!Boolean.getBoolean("manaforge.liveGame"))System.err.println("Unsupported native choice: "+code);
            JsonObject unknown=prompt.deepCopy();unknown.addProperty("kind","GAME_ASK");unknown.addProperty("is_priority",false);unknown.remove("attackers");unknown.remove("blockers");unknown.addProperty("message","This choice is not supported yet. Return to Manaforge to end the session.");
            projected=projection.projectCoreCombat(publicView,unknown,false);projected.add("decision",JsonNull.INSTANCE);projected.addProperty("decision_error",code);projected.add("actions",new JsonArray());projected.getAsJsonArray("unsupported_fields").add("decision");projection.invalidateDecision();final JsonObject readonly=envelope(projected);
            return new ManaforgeUnityOpening.TurnOffer(readonly,prompt.get("decision_id").getAsLong(),before.get("cycle").getAsLong(),command->{throw new IOException("GAMEPLAY_DECISION_UNSUPPORTED");});
        }
        JsonObject view=envelope(projected);
        return new ManaforgeUnityOpening.TurnOffer(view,prompt.get("decision_id").getAsLong(),before.get("cycle").getAsLong(),command->{
            current();if(offered!=generation)throw new IOException("STALE_DECISION");generation++;
            observer.before(before.deepCopy(),prompt.deepCopy(),command.deepCopy());
            JsonObject accepted=engine.submit(command);
            if(!new JsonPrimitive(true).equals(accepted.get("accepted")))throw new IOException("GAMEPLAY_RESPONSE_REJECTED");
            Advance next=engine.advance(prompt.get("decision_id").getAsLong());
            if(next.terminal!=null) {
                JsonObject terminal=engine.terminalMetadata(before);
                NativeCastCorrelation.TurnDecisionEvidence proof=NativeCastCorrelation.terminalGameplayEvidence(before,prompt,command,guard,accepted,terminal,next.terminal);
                if(proof==null)throw new IOException("GAMEPLAY_TERMINAL_UNPROVEN");
                String outcome=terminal.get("outcome").getAsString();observer.terminal(outcome,next.state.deepCopy(),terminal.deepCopy());
                JsonObject finalState=next.state.deepCopy();if(terminal.has("commanders") && finalState.get("cycle").equals(terminal.get("cycle"))){finalState.add("commander_metadata",terminal.get("commanders").deepCopy());finalState.add("commander_metadata_complete",terminal.get("commander_metadata_complete"));}JsonObject result=envelope(projection.projectCombatResult(finalState,outcome));result.addProperty("message_type","result");stopped=true;
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
        },()->{current();if(offered!=generation)return null;JsonObject pending=engine.pollRequest();if(pending!=null)return offerRequest(before,prompt,pending);
            JsonElement previous=before.get("session_notice");String notice=previous==null || previous.isJsonNull()?null:previous.getAsString();
            if(!Objects.equals(notice,engine.sessionNotice())){Advance fresh=refreshed(before,prompt);return offer(fresh.state,fresh.prompt);}return null;});
    }
    private JsonObject decorate(JsonObject before,JsonObject guard) {
        JsonObject publicView=before.deepCopy();for(JsonElement card:publicView.getAsJsonArray("stack")){JsonObject row=card.getAsJsonObject(),entry=guard.getAsJsonObject("objects").getAsJsonObject(row.get("id").getAsString());if(entry!=null){if(entry.has("ability_art_set") && entry.has("ability_art_number")){row.add("set",entry.get("ability_art_set"));row.add("number",entry.get("ability_art_number"));}if(entry.has("source"))row.add("target_source",entry.get("source"));if(entry.has("stack_targets")){row.add("stack_targets",entry.get("stack_targets"));row.add("stack_targets_complete",entry.get("stack_targets_complete"));}if(entry.has("controller"))row.add("stack_controller",entry.get("controller"));if(entry.has("owner"))row.add("stack_owner",entry.get("owner"));if(entry.has("source") && entry.has("spell_ability_ids"))row.add("commander_source",entry.get("source"));}}
        for(JsonElement card:publicView.getAsJsonArray("exile")){JsonObject row=card.getAsJsonObject(),entry=guard.getAsJsonObject("objects").getAsJsonObject(row.get("id").getAsString());if(entry!=null && entry.has("owner"))row.add("exile_owner",entry.get("owner"));}
        if(guard.has("commanders")){publicView.add("commander_metadata",guard.get("commanders").deepCopy());publicView.add("commander_metadata_complete",guard.get("commander_metadata_complete"));}
        return publicView;
    }
    private JsonObject requestGuard(JsonObject before) throws Exception {
        List<String> sources=new ArrayList<>();for(JsonElement card:before.getAsJsonArray("stack"))sources.add(card.getAsJsonObject().get("id").getAsString());
        for(JsonElement item:before.getAsJsonArray("exile")){JsonObject card=item.getAsJsonObject();if(new JsonPrimitive(false).equals(card.get("hidden")) && new JsonPrimitive(false).equals(card.get("face_down")))sources.add(card.get("id").getAsString());}
        return engine.metadata(before,sources.toArray(new String[0]));
    }
    private Advance refreshed(JsonObject state,JsonObject prompt) throws Exception {
        Advance fresh=engine.refresh();if(fresh==null)fresh=new Advance(state,prompt,null);
        if(fresh.terminal!=null || fresh.prompt==null)throw new IOException("SESSION_REQUEST_GAME_CHANGED");
        return fresh;
    }
    private ManaforgeUnityOpening.TurnOffer offerRequest(JsonObject state,JsonObject original,JsonObject request) throws Exception {
        current();if(serial>=4095)throw new IOException("GAMEPLAY_LIMIT");
        Advance live=refreshed(state,original);JsonObject before=live.state,prompt=request.deepCopy();prompt.add("cycle",before.get("cycle"));
        JsonObject guard=requestGuard(before);if(!new JsonPrimitive("ok").equals(guard.get("status")) || !before.get("cycle").equals(guard.get("cycle")))throw new IOException("SESSION_REQUEST_CONTEXT_UNPROVEN");
        long offered=++generation;String id=request.get("session_request_id").getAsString();
        JsonObject snapshot=envelope(projection.projectCoreCombat(decorate(before,guard),prompt,false));
        return new ManaforgeUnityOpening.TurnOffer(snapshot,prompt.get("decision_id").getAsLong(),before.get("cycle").getAsLong(),command->{
            current();if(offered!=generation || !engine.requestCurrent(id))throw new IOException("STALE_SESSION_REQUEST");generation++;
            JsonObject accepted=engine.submit(command);Advance after=engine.resume(refreshed(before,live.prompt));JsonObject metadata=engine.metadata(after.state);
            NativeCastCorrelation.TurnDecisionEvidence proof=NativeCastCorrelation.requestResponseEvidence(before,prompt,command,accepted,after.state,metadata);
            if(proof==null)throw new IOException("SESSION_REQUEST_RESPONSE_UNPROVEN");
            ManaforgeUnityOpening.TurnOffer following=offer(after.state,after.prompt);return new ManaforgeUnityOpening.TurnResult(following.snapshot(),proof,following);
        },()->{current();if(offered!=generation || engine.requestCurrent(id))return null;Advance fresh=engine.resume(refreshed(before,live.prompt));return offer(fresh.state,fresh.prompt);});
    }
    public void close(){if(Thread.currentThread()!=owner)throw new IllegalStateException("GAMEPLAY_OWNER");stopped=true;generation++;projection.invalidateDecision();}
}

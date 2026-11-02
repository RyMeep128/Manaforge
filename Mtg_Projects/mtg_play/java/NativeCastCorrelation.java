import com.google.gson.*;
import java.util.*;

/** Private native correlation. Stack evidence proves ability selection, not spell resolution. */
public final class NativeCastCorrelation {
    public static final class AttackFinishEvidence {
        private final JsonObject command;private final String game,viewer,source;private final long incarnation;
        private AttackFinishEvidence(JsonObject command,String viewer,String source,long incarnation){this.command=command.deepCopy();game=string(command,"game_id");this.viewer=viewer;this.source=source;this.incarnation=incarnation;}
        public boolean matchesCommand(JsonObject candidate){return command.equals(candidate);}
        public PriorityEvidence phasePriorityEvidence(JsonObject before,JsonObject prompt,JsonObject pass,JsonObject beforeMetadata,JsonObject accepted,
                JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata) {
            try {
                if(!game.equals(string(before,"game_id")) || !game.equals(string(after,"game_id")) || !viewer.equals(string(before,"viewer")) || !viewer.equals(string(after,"viewer"))
                    || battlefieldCounter(before,beforeMetadata,source)!=incarnation || battlefieldCounter(after,afterMetadata,source)!=incarnation
                    || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || before.getAsJsonArray("combat").size()!=0 || after.getAsJsonArray("combat").size()!=0
                    || !"respond".equals(string(pass,"command")) || !"boolean".equals(string(pass,"kind")) || !new JsonPrimitive(false).equals(pass.get("value"))
                    || !game.equals(string(pass,"game_id")) || number(pass,"decision_id")!=number(prompt,"decision_id")
                    || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || prompt.has("attackers") || prompt.has("blockers")
                    || number(prompt,"cycle")!=number(before,"cycle") || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open"))
                    || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(pass,"request_id").equals(string(accepted,"request_id"))
                    || !"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers")
                    || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open")) || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id")
                    || number(after,"cycle")<number(before,"cycle") || number(after,"turn")<number(before,"turn"))return null;
                String beforePhase=string(before,"phase"),afterPhase=string(after,"phase"),beforeStep=string(before,"step"),afterStep=string(after,"step");
                return number(after,"turn")!=number(before,"turn") || !beforePhase.equals(afterPhase) || !beforeStep.equals(afterStep)?new PriorityEvidence(pass):null;
            }catch(RuntimeException unsupported){return null;}
        }
    }
    private static long battlefieldCounter(JsonObject state,JsonObject metadata,String source) {
        String viewer=string(state,"viewer");
        if(!"ok".equals(string(metadata,"status")) || number(metadata,"cycle")!=number(state,"cycle"))throw new IllegalArgumentException();
        for(JsonElement item:state.getAsJsonArray("hand"))if(source.equals(string(item.getAsJsonObject(),"id")))throw new IllegalArgumentException();
        int found=0;
        for(JsonElement row:state.getAsJsonArray("players")) {
            JsonObject player=row.getAsJsonObject();if(!viewer.equals(string(player,"id")))continue;
            for(JsonElement item:player.getAsJsonArray("battlefield")) {
                JsonObject card=item.getAsJsonObject();if(!source.equals(string(card,"id")))continue;
                if(!new JsonPrimitive(false).equals(card.get("hidden")) || !new JsonPrimitive(false).equals(card.get("face_down")))throw new IllegalArgumentException();found++;
            }
        }
        JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(source);
        if(found!=1 || !viewer.equals(string(entry,"owner")) || !viewer.equals(string(entry,"controller")))throw new IllegalArgumentException();
        return number(entry,"incarnation");
    }
    public static final class AttackerSelectionEvidence {
        private final JsonObject command;
        private AttackerSelectionEvidence(JsonObject command){this.command=command.deepCopy();}
        public boolean matchesCommand(JsonObject candidate){return command.equals(candidate);}
    }
    public static AttackerSelectionEvidence attackerSelectionEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        return observesAttackerSelection(before,prompt,command,beforeMetadata,accepted,after,nextPrompt,afterMetadata,source)?new AttackerSelectionEvidence(command):null;
    }
    /** Observation of one selected attacker and the engine's assignment; not declaration completion. */
    public static boolean observesAttackerSelection(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        try {
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer"))
                || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command")) || !"object".equals(string(command,"kind")) || !source.equals(string(command,"value"))
                || number(command,"decision_id")!=number(prompt,"decision_id") || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(false).equals(prompt.get("is_priority")) || prompt.has("blockers")
                || number(prompt,"cycle")!=number(before,"cycle") || !new JsonPrimitive(false).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(false).equals(afterMetadata.get("priority_open"))
                || before.getAsJsonArray("combat").size()!=0 || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0
                || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source) || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted"))
                || !string(command,"request_id").equals(string(accepted,"request_id")) || !"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(false).equals(nextPrompt.get("is_priority")) || !nextPrompt.has("attackers") || nextPrompt.has("blockers")
                || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle"))return false;
            Set<String> candidates=new HashSet<>();JsonArray offered=prompt.getAsJsonArray("attackers");if(offered.size()>256)return false;
            for(JsonElement item:offered)if(!item.isJsonPrimitive() || !item.getAsJsonPrimitive().isString() || !candidates.add(item.getAsString()))return false;
            if(!candidates.contains(source) || after.getAsJsonArray("combat").size()!=1)return false;
            JsonObject group=after.getAsJsonArray("combat").get(0).getAsJsonObject();
            if(group.getAsJsonArray("attackers").size()!=1 || !source.equals(group.getAsJsonArray("attackers").get(0).getAsString()) || group.getAsJsonArray("blockers").size()!=0)return false;
            String defender=string(group,"defender");int opponents=0;
            for(JsonElement row:after.getAsJsonArray("players")) {JsonObject player=row.getAsJsonObject();if(defender.equals(string(player,"id")) && !defender.equals(string(after,"viewer")) && new JsonPrimitive(false).equals(player.get("left")))opponents++;}
            return opponents==1;
        }catch(RuntimeException unsupported){return false;}
    }
    /** Exact empty attack-selection completion in the owned public fixture, not generic combat success. */
    public static AttackFinishEvidence attackFinishEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        try {
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer"))
                || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command"))
                || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value"))
                || number(command,"decision_id")!=number(prompt,"decision_id") || !"GAME_SELECT".equals(string(prompt,"kind"))
                || !new JsonPrimitive(false).equals(prompt.get("is_priority")) || prompt.has("blockers")
                || number(prompt,"cycle")!=number(before,"cycle") || !new JsonPrimitive(false).equals(beforeMetadata.get("priority_open"))
                || before.getAsJsonArray("combat").size()!=0 || after.getAsJsonArray("combat").size()!=0
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0)return null;
            JsonArray candidates=prompt.getAsJsonArray("attackers");if(candidates.size()>256)return null;Set<String> unique=new HashSet<>();
            for(JsonElement item:candidates){if(!item.isJsonPrimitive() || !item.getAsJsonPrimitive().isString() || !unique.add(item.getAsString()))return null;}
            boolean active=false;for(JsonElement item:before.getAsJsonArray("players")){JsonObject row=item.getAsJsonObject();if(string(before,"viewer").equals(string(row,"id")) && string(before,"active_player").equals(string(row,"name")))active=true;}
            if(!active || !unique.contains(source) || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source)
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted"))
                || !string(command,"request_id").equals(string(accepted,"request_id")) || !"GAME_SELECT".equals(string(nextPrompt,"kind"))
                || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers")
                || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open")) || number(nextPrompt,"cycle")!=number(after,"cycle")
                || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle")
                || number(after,"turn")<number(before,"turn"))return null;
            return new AttackFinishEvidence(command,string(before,"viewer"),source,battlefieldCounter(after,afterMetadata,source));
        }catch(RuntimeException unsupported){return null;}
    }
    public static final class PriorityEvidence {
        private final JsonObject command;
        private PriorityEvidence(JsonObject command){this.command=command.deepCopy();}
        public boolean matchesCommand(JsonObject candidate){return command.equals(candidate);}
    }
    public static final class AbilityEvidence {
        private final JsonObject command;private final NativeCastCorrelation correlation;private final long stackSourceCounter,stackCycle;private final String stackId;
        private AbilityEvidence(JsonObject command,NativeCastCorrelation correlation,long counter,long cycle,String stackId){this.command=command.deepCopy();this.correlation=correlation;stackSourceCounter=counter;stackCycle=cycle;this.stackId=stackId;}
        public boolean matchesCommand(JsonObject candidate){return command.equals(candidate);}
        /** Empty-stack phase transition in the owned fixture; never just a newer cycle. */
        public PriorityEvidence phasePriorityEvidence(JsonObject before,JsonObject prompt,JsonObject pass,JsonObject beforeMetadata,JsonObject accepted,
                JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata) {
            try {
                if(!observesBattlefieldTransition(before,beforeMetadata) || !observesBattlefieldTransition(after,afterMetadata)
                    || !"respond".equals(string(pass,"command")) || !"boolean".equals(string(pass,"kind")) || !new JsonPrimitive(false).equals(pass.get("value"))
                    || !correlation.game.equals(string(pass,"game_id")) || number(pass,"decision_id")!=number(prompt,"decision_id")
                    || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority"))
                    || number(prompt,"cycle")!=number(before,"cycle") || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open"))
                    || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted"))
                    || !string(pass,"request_id").equals(string(accepted,"request_id")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open"))
                    || !"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority"))
                    || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id")
                    || number(after,"cycle")<number(before,"cycle") || number(after,"turn")<number(before,"turn"))return null;
                String beforePhase=string(before,"phase"),afterPhase=string(after,"phase"),beforeStep=string(before,"step"),afterStep=string(after,"step");
                boolean changed=number(after,"turn")!=number(before,"turn") || !beforePhase.equals(afterPhase) || !beforeStep.equals(afterStep);
                return changed?new PriorityEvidence(pass):null;
            }catch(RuntimeException unsupported){return null;}
        }
        /** Fixed cast/resolution slice only: not a general priority-advancement certificate. */
        public PriorityEvidence priorityEvidence(JsonObject before,JsonObject prompt,JsonObject pass,JsonObject beforeMetadata,JsonObject accepted,
                JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata) {
            try {
                if(!"respond".equals(string(pass,"command")) || !"boolean".equals(string(pass,"kind")) || !new JsonPrimitive(false).equals(pass.get("value"))
                    || !correlation.game.equals(string(pass,"game_id")) || number(pass,"decision_id")!=number(prompt,"decision_id")
                    || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority"))
                    || number(prompt,"cycle")!=number(before,"cycle") || number(before,"cycle")<stackCycle
                    || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open"))
                    || before.getAsJsonArray("stack").size()!=1 || !stackId.equals(string(before.getAsJsonArray("stack").get(0).getAsJsonObject(),"id"))
                    || !correlation.matchesStackInstance(before,beforeMetadata,string(command,"value")))return null;
                for(JsonElement item:before.getAsJsonArray("stack")) {
                    JsonObject entry=beforeMetadata.getAsJsonObject("objects").getAsJsonObject(string(item.getAsJsonObject(),"id"));
                    if(entry!=null && correlation.source.equals(string(entry,"source")) && number(entry,"source_incarnation")!=stackSourceCounter)return null;
                }
                if(!"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted"))
                    || !string(pass,"request_id").equals(string(accepted,"request_id")) || !observesBattlefieldTransition(after,afterMetadata)
                    || number(after,"cycle")<number(before,"cycle") || !"GAME_SELECT".equals(string(nextPrompt,"kind"))
                    || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open"))
                    || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id"))return null;
                return new PriorityEvidence(pass);
            }catch(RuntimeException unsupported){return null;}
        }
        /** Observation only. Does not confirm the intervening priority-pass receipt. */
        public boolean observesBattlefieldTransition(JsonObject state,JsonObject metadata) {
            try {
                if(!correlation.game.equals(string(state,"game_id")) || !correlation.viewer.equals(string(state,"viewer"))
                    || number(state,"cycle")<stackCycle || !"ok".equals(string(metadata,"status")) || number(metadata,"cycle")!=number(state,"cycle")
                    || state.getAsJsonArray("stack").size()!=0 || stackSourceCounter==Long.MAX_VALUE)return false;
                for(JsonElement item:state.getAsJsonArray("hand"))if(correlation.source.equals(string(item.getAsJsonObject(),"id")))return false;
                int found=0;
                for(JsonElement row:state.getAsJsonArray("players")) {
                    JsonObject player=row.getAsJsonObject();if(!correlation.viewer.equals(string(player,"id")))continue;
                    for(JsonElement item:player.getAsJsonArray("battlefield")) {
                        JsonObject card=item.getAsJsonObject();if(!correlation.source.equals(string(card,"id")))continue;
                        if(!new JsonPrimitive(false).equals(card.get("hidden")) || !new JsonPrimitive(false).equals(card.get("face_down")))return false;
                        found++;
                    }
                }
                JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(correlation.source);
                return found==1 && correlation.viewer.equals(string(entry,"owner")) && correlation.viewer.equals(string(entry,"controller"))
                    && number(entry,"incarnation")==stackSourceCounter+1;
            }catch(RuntimeException unsupported){return false;}
        }
    }
    private final String game,viewer,source;
    private final long cycle,decision;
    private final Set<String> abilities;
    private final Long sourceIncarnation;
    private NativeCastCorrelation(String game,String viewer,String source,long cycle,long decision,Set<String> abilities) {
        this(game,viewer,source,cycle,decision,abilities,null);
    }
    private NativeCastCorrelation(String game,String viewer,String source,long cycle,long decision,Set<String> abilities,Long sourceIncarnation) {
        this.game=game;this.viewer=viewer;this.source=source;this.cycle=cycle;this.decision=decision;this.abilities=Collections.unmodifiableSet(new HashSet<>(abilities));
        this.sourceIncarnation=sourceIncarnation;
    }
    private static String string(JsonObject value,String key) {
        JsonElement item=value.get(key);if(item==null || !item.isJsonPrimitive() || !item.getAsJsonPrimitive().isString() || item.getAsString().isEmpty())throw new IllegalArgumentException();return item.getAsString();
    }
    private static long number(JsonObject value,String key) {
        JsonElement item=value.get(key);if(item==null || !item.isJsonPrimitive() || !item.getAsJsonPrimitive().isNumber() || !item.toString().matches("[0-9]+"))throw new IllegalArgumentException();return Long.parseLong(item.getAsString());
    }
    private static String uuid(String value){if(!UUID.fromString(value).toString().equals(value))throw new IllegalArgumentException();return value;}
    private static boolean visibleSource(JsonObject state,String source) {
        int found=0;
        for(JsonElement value:state.getAsJsonArray("hand")) {
            JsonObject card=value.getAsJsonObject();if(!source.equals(string(card,"id")))continue;
            if(!new JsonPrimitive(false).equals(card.get("hidden")) || !new JsonPrimitive(false).equals(card.get("face_down")))return false;
            found++;
        }
        return found==1;
    }
    /** Mint only for the exact offered native ability command and its observed stack instance. */
    public AbilityEvidence abilityEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject after,JsonObject metadata) {
        try {
            if(!matches(before,prompt) || !"respond".equals(string(command,"command")) || !"object".equals(string(command,"kind"))
                || !game.equals(string(command,"game_id")) || number(command,"decision_id")!=number(prompt,"decision_id"))return null;
            string(command,"request_id");String selected=uuid(string(command,"value"));
            if(number(after,"cycle")<number(before,"cycle") || !prompt.getAsJsonObject("key_choices").has(selected) || !matchesStackInstance(after,metadata,selected))return null;
            for(JsonElement item:after.getAsJsonArray("stack")) {
                JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(string(item.getAsJsonObject(),"id"));
                if(entry!=null && source.equals(string(entry,"source")))return new AbilityEvidence(command,this,number(entry,"source_incarnation"),number(after,"cycle"),string(item.getAsJsonObject(),"id"));
            }
            return null;
        }catch(RuntimeException unsupported){return null;}
    }
    public static NativeCastCorrelation capture(JsonObject state,JsonObject prompt,JsonObject command) {
        try {
            String game=string(state,"game_id"),viewer=string(state,"viewer"),source=uuid(string(command,"value"));
            long cycle=number(state,"cycle"),decision=number(prompt,"decision_id");
            if(decision>Integer.MAX_VALUE || !game.equals(string(command,"game_id")) || number(command,"decision_id")!=decision || number(prompt,"cycle")!=cycle
                || !"respond".equals(string(command,"command")) || !"object".equals(string(command,"kind"))
                || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority"))
                || !visibleSource(state,source) || !"cast_spell".equals(string(state.getAsJsonObject("action_kinds"),source)))return null;
            boolean offered=false;for(JsonElement id:state.getAsJsonArray("playable"))offered|=source.equals(id.getAsString());if(!offered)return null;
            JsonArray raw=state.getAsJsonObject("casting_ability_ids").getAsJsonArray(source);if(raw.size()==0 || raw.size()>32)return null;
            Set<String> ids=new HashSet<>();for(JsonElement id:raw){if(!id.isJsonPrimitive() || !id.getAsJsonPrimitive().isString() || !ids.add(uuid(id.getAsString())))return null;}
            return new NativeCastCorrelation(game,viewer,source,cycle,decision,ids);
        }catch(RuntimeException unsupported){return null;}
    }
    public boolean matches(JsonObject state,JsonObject prompt) {
        try {
            if(!game.equals(string(state,"game_id")) || !viewer.equals(string(state,"viewer")) || number(state,"cycle")<cycle
                || number(prompt,"cycle")!=number(state,"cycle") || number(prompt,"decision_id")<=decision || number(prompt,"decision_id")>Integer.MAX_VALUE
                || !"GAME_CHOOSE_ABILITY".equals(string(prompt,"kind")) || !visibleSource(state,source))return false;
            JsonObject choices=prompt.getAsJsonObject("key_choices");if(choices.size()!=1)return false;
            Map.Entry<String,JsonElement> choice=choices.entrySet().iterator().next();
            return abilities.contains(uuid(choice.getKey())) && choice.getValue().isJsonPrimitive() && choice.getValue().getAsJsonPrimitive().isString();
        }catch(RuntimeException unsupported){return false;}
    }
    public NativeCastCorrelation withSourceMetadata(JsonObject metadata) {
        try {
            if(sourceIncarnation!=null || !"ok".equals(string(metadata,"status")) || number(metadata,"cycle")!=cycle)return null;
            JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(source);
            if(!viewer.equals(string(entry,"owner")))return null;
            return new NativeCastCorrelation(game,viewer,source,cycle,decision,abilities,number(entry,"incarnation"));
        }catch(RuntimeException unsupported){return null;}
    }
    /** Exact chosen ability plus an observed source-counter transition; still no receipt permission. */
    public boolean matchesStackInstance(JsonObject state,JsonObject metadata,String selectedAbility) {
        try {
            if(sourceIncarnation==null || !abilities.contains(uuid(selectedAbility)) || !matchesStack(state,metadata))return false;
            for(JsonElement value:state.getAsJsonArray("stack")) {
                JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(string(value.getAsJsonObject(),"id"));
                if(entry==null || !source.equals(string(entry,"source")))continue;
                JsonArray ids=entry.getAsJsonArray("spell_ability_ids");
                return number(entry,"source_incarnation")>sourceIncarnation && ids.size()==1 && ids.get(0).isJsonPrimitive()
                    && ids.get(0).getAsJsonPrimitive().isString() && selectedAbility.equals(uuid(ids.get(0).getAsString()));
            }
            return false;
        }catch(RuntimeException unsupported){return false;}
    }
    /** Still observation only: guarded native stack-source metadata, not a receipt settlement. */
    public boolean matchesStack(JsonObject state,JsonObject metadata) {
        try {
            if(!game.equals(string(state,"game_id")) || !viewer.equals(string(state,"viewer")) || !"ok".equals(string(metadata,"status"))
                || number(state,"cycle")<cycle || number(metadata,"cycle")!=number(state,"cycle"))return false;
            for(JsonElement value:state.getAsJsonArray("hand"))if(source.equals(string(value.getAsJsonObject(),"id")))return false;
            int found=0;
            for(JsonElement value:state.getAsJsonArray("stack")) {
                JsonObject card=value.getAsJsonObject(),entry=metadata.getAsJsonObject("objects").getAsJsonObject(uuid(string(card,"id")));
                if(entry==null)continue;
                if(source.equals(string(entry,"source")) && viewer.equals(string(entry,"owner")) && viewer.equals(string(entry,"controller"))
                    && new JsonPrimitive(false).equals(card.get("hidden")) && new JsonPrimitive(false).equals(card.get("face_down"))){number(entry,"incarnation");found++;}
            }
            return found==1;
        }catch(RuntimeException unsupported){return false;}
    }
}

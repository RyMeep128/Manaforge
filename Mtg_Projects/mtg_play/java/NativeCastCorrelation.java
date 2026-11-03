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
    public static final class TurnDecisionEvidence {
        private final JsonObject command;private TurnDecisionEvidence(JsonObject command){this.command=command.deepCopy();}
        public boolean matchesCommand(JsonObject candidate){return command.equals(candidate);}
    }
    public static TurnDecisionEvidence turnDecisionEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        try {
            boolean discard="GAME_TARGET".equals(string(prompt,"kind"));boolean nextDiscard="GAME_TARGET".equals(string(nextPrompt,"kind"));
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer")) || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command")) || number(command,"decision_id")!=number(prompt,"decision_id")
                || number(prompt,"cycle")!=number(before,"cycle") || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle") || number(after,"turn")<number(before,"turn") || number(after,"turn")>number(before,"turn")+1
                || !new JsonPrimitive(!discard).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(!nextDiscard).equals(afterMetadata.get("priority_open")) || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source)
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || before.getAsJsonArray("combat").size()!=0 || after.getAsJsonArray("combat").size()!=0
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id")))return null;
            if(discard){
                if(!new JsonPrimitive(false).equals(prompt.get("is_priority")) || !"END".equals(string(before,"phase")) || !"CLEANUP".equals(string(before,"step")) || before.getAsJsonArray("hand").size()!=8 || !"object".equals(string(command,"kind")))return null;boolean active=false;for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(string(before,"viewer").equals(string(player,"id")) && string(player,"name").equals(string(before,"active_player")))active=true;}if(!active)return null;
                String chosen=string(command,"value");boolean offered=false,inHand=false,inGrave=false;for(JsonElement id:prompt.getAsJsonArray("targets"))offered|=chosen.equals(id.getAsString());for(JsonElement item:before.getAsJsonArray("hand"))inHand|=chosen.equals(string(item.getAsJsonObject(),"id"));
                for(JsonElement item:after.getAsJsonArray("hand"))if(chosen.equals(string(item.getAsJsonObject(),"id")))return null;
                for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(string(after,"viewer").equals(string(player,"id")))for(JsonElement item:player.getAsJsonArray("graveyard"))inGrave|=chosen.equals(string(item.getAsJsonObject(),"id"));}
                if(!offered || !inHand || !inGrave || after.getAsJsonArray("hand").size()!=7)return null;
            }else if(!"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || prompt.has("attackers") || prompt.has("blockers") || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value")))return null;
            if(nextDiscard){if(!new JsonPrimitive(false).equals(nextPrompt.get("is_priority")) || !"END".equals(string(after,"phase")) || !"CLEANUP".equals(string(after,"step")) || after.getAsJsonArray("hand").size()!=8)return null;}
            else if(!"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers"))return null;
            Map<String,Long> lives=new HashMap<>();if(before.getAsJsonArray("players").size()!=2 || after.getAsJsonArray("players").size()!=2)return null;for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(lives.put(string(player,"id"),number(player,"life"))!=null)return null;}
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id))return null;}
            return new TurnDecisionEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    /** One native unblocked combat with an existing creature, preserving the other public zones. */
    public static TurnDecisionEvidence terminalCombatEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject guard,JsonObject accepted,JsonObject terminal,JsonObject callback) {
        try {
            String outcome=string(terminal,"outcome");if(!Arrays.asList("win","loss","draw").contains(outcome) || !"finished".equals(string(terminal,"status")) || !string(before,"game_id").equals(string(terminal,"game_id")) || !string(before,"viewer").equals(string(terminal,"viewer")) || !string(terminal,"game_id").equals(string(callback,"game_id")) || !string(terminal,"viewer").equals(string(callback,"viewer")) || !"game_result".equals(string(callback,"event")) || !new JsonPrimitive("win".equals(outcome)).equals(callback.get("won")))return null;
            if(!"respond".equals(string(command,"command")) || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value")) || !string(before,"game_id").equals(string(command,"game_id")) || number(command,"decision_id")!=number(prompt,"decision_id") || number(prompt,"cycle")!=number(before,"cycle") || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || !new JsonPrimitive(true).equals(guard.get("priority_open")) || number(guard,"cycle")!=number(before,"cycle") || !"ok".equals(string(guard,"status")) || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id")))return null;
            return new TurnDecisionEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    /** Native response consumed at a later guarded combat/turn decision; not a damage/outcome claim. */
    public static TurnDecisionEvidence coreCombatResponseEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject guard,JsonObject accepted,JsonObject after,JsonObject nextPrompt,JsonObject nextGuard) {
        try {
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer")) || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command")) || number(prompt,"decision_id")!=number(command,"decision_id") || number(prompt,"cycle")!=number(before,"cycle") || number(guard,"cycle")!=number(before,"cycle") || !"ok".equals(string(guard,"status")) || !"ok".equals(string(nextGuard,"status")) || number(nextGuard,"cycle")!=number(after,"cycle") || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle") || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id")))return null;
            boolean nextPriority="GAME_SELECT".equals(string(nextPrompt,"kind")) && new JsonPrimitive(true).equals(nextPrompt.get("is_priority"));if(!new JsonPrimitive(nextPriority).equals(nextGuard.get("priority_open")))return null;
            return gameplayResponseEvidence(before,prompt,command,guard);
        }catch(RuntimeException unsupported){return null;}
    }
    /** Validate the exact native input family without inventing a subsequent decision. */
    private static TurnDecisionEvidence gameplayResponseEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject guard) {
        try {
            boolean priority="GAME_SELECT".equals(string(prompt,"kind")) && new JsonPrimitive(true).equals(prompt.get("is_priority"));if(!new JsonPrimitive(priority).equals(guard.get("priority_open")))return null;
            String kind=string(command,"kind");if("boolean".equals(kind) && "GAME_ASK".equals(string(prompt,"kind"))){if(!command.get("value").isJsonPrimitive() || !command.getAsJsonPrimitive("value").isBoolean())return null;}
            else if("boolean".equals(kind)){if(!new JsonPrimitive(false).equals(command.get("value")) || !(priority || "GAME_SELECT".equals(string(prompt,"kind")) && (prompt.has("attackers") ^ prompt.has("blockers")) || "GAME_TARGET".equals(string(prompt,"kind")) && new JsonPrimitive(true).equals(prompt.get("can_finish")) || Arrays.asList("GAME_PLAY_MANA","GAME_CHOOSE_CHOICE","GAME_GET_MULTI_AMOUNT").contains(string(prompt,"kind")) && new JsonPrimitive(true).equals(prompt.get("cancellable"))))return null;}
            else if("mana_type".equals(kind)){if(!"GAME_PLAY_MANA".equals(string(prompt,"kind")) || !string(before,"viewer").equals(string(command,"player_id")) || !Arrays.asList("WHITE","BLUE","BLACK","RED","GREEN","COLORLESS").contains(string(command,"value")))return null;boolean available=false;for(JsonElement player:before.getAsJsonArray("players")){JsonObject seat=player.getAsJsonObject();if(string(before,"viewer").equals(string(seat,"id")) && seat.has("mana") && seat.get("mana").isJsonArray())for(JsonElement value:seat.getAsJsonArray("mana")){JsonArray pair=value.getAsJsonArray();available|=pair.size()==2 && string(command,"value").equalsIgnoreCase(pair.get(0).getAsString()) && pair.get(1).getAsLong()>0;}}if(!available)return null;}
            else if("object".equals(kind)){String candidates=prompt.has("attackers")?"attackers":prompt.has("blockers")?"blockers":"GAME_TARGET".equals(string(prompt,"kind"))?"targets":null;if("GAME_PLAY_MANA".equals(string(prompt,"kind"))){boolean found=false;for(JsonElement source:before.getAsJsonArray("playable"))found|=source.equals(command.get("value"));if(!found)return null;controlledPermanent(before,string(command,"value"),string(before,"viewer"));return new TurnDecisionEvidence(command);}if(priority){boolean found=false;for(JsonElement source:before.getAsJsonArray("playable"))found|=source.equals(command.get("value"));JsonElement action=before.getAsJsonObject("action_kinds").get(string(command,"value"));if(!found || action==null || !("cast_spell".equals(action.getAsString()) || "play_land".equals(action.getAsString()) || "select_object".equals(action.getAsString()) || "activate".equals(action.getAsString())))return null;return new TurnDecisionEvidence(command);}if("GAME_CHOOSE_ABILITY".equals(string(prompt,"kind"))){if(!prompt.getAsJsonObject("key_choices").has(string(command,"value")))return null;return new TurnDecisionEvidence(command);}if(candidates==null)return null;Set<String> legal=new HashSet<>();JsonArray offered=prompt.getAsJsonArray(candidates);if(offered.size()>256)return null;for(JsonElement item:offered)if(!item.isJsonPrimitive() || !item.getAsJsonPrimitive().isString() || !legal.add(item.getAsString()))return null;if(!legal.contains(string(command,"value")))return null;}
            else if(!NativeCombatChoices.matchesResponse(prompt,command))return null;
            return new TurnDecisionEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    /** A guarded native result may follow any supported input, including a final cost or target. */
    public static TurnDecisionEvidence terminalGameplayEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject guard,JsonObject accepted,JsonObject terminal,JsonObject callback) {
        try {
            String outcome=string(terminal,"outcome");
            if(!Arrays.asList("win","loss","draw").contains(outcome) || !"finished".equals(string(terminal,"status")) || !string(before,"game_id").equals(string(terminal,"game_id")) || !string(before,"viewer").equals(string(terminal,"viewer")) || !string(terminal,"game_id").equals(string(callback,"game_id")) || !string(terminal,"viewer").equals(string(callback,"viewer")) || !"game_result".equals(string(callback,"event")) || !new JsonPrimitive("win".equals(outcome)).equals(callback.get("won")))return null;
            if(!"respond".equals(string(command,"command")) || !string(before,"game_id").equals(string(command,"game_id")) || number(command,"decision_id")!=number(prompt,"decision_id") || number(prompt,"cycle")!=number(before,"cycle") || number(guard,"cycle")!=number(before,"cycle") || !"ok".equals(string(guard,"status")) || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id")))return null;
            return gameplayResponseEvidence(before,prompt,command,guard);
        }catch(RuntimeException unsupported){return null;}
    }
    public static boolean observesExistingCombat(JsonObject before,JsonObject beforeMetadata,JsonObject after,JsonObject afterMetadata,String attacker) {
        try {
            String viewer=string(before,"viewer");if(!viewer.equals(string(after,"viewer")) || !string(before,"game_id").equals(string(after,"game_id")) || number(before,"turn")!=number(after,"turn") || number(after,"cycle")<=number(before,"cycle") || !"PRECOMBAT_MAIN".equals(string(before,"phase")) || !"POSTCOMBAT_MAIN".equals(string(after,"phase")) || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open")) || battlefieldCounter(before,beforeMetadata,attacker)!=battlefieldCounter(after,afterMetadata,attacker) || !before.get("hand").equals(after.get("hand")))return false;
            for(JsonObject state:Arrays.asList(before,after))if(state.getAsJsonArray("combat").size()!=0 || state.getAsJsonArray("stack").size()!=0 || state.getAsJsonArray("players").size()!=2)return false;
            JsonObject original=controlledPermanent(before,attacker,viewer),last=controlledPermanent(after,attacker,viewer);if(!new JsonPrimitive(false).equals(original.get("tapped")) || !new JsonPrimitive(true).equals(last.get("tapped")) || !"Memnite".equals(string(last,"name")) || !"1".equals(string(last,"power")) || !"1".equals(string(last,"toughness")))return false;
            Map<String,JsonObject> first=new HashMap<>();for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(first.put(string(player,"id"),player)!=null)return false;}
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");JsonObject previous=first.get(id);if(!seen.add(id) || previous==null || number(player,"life")!=number(previous,"life")-(viewer.equals(id)?0:1) || number(player,"library_count")!=number(previous,"library_count") || !player.get("graveyard").equals(previous.get("graveyard")))return false;
                if(viewer.equals(id)){if(!string(player,"name").equals(string(before,"active_player")) || !string(player,"name").equals(string(after,"active_player")) || !string(player,"name").equals(string(before,"priority_player")) || !string(player,"name").equals(string(after,"priority_player")))return false;Set<String> oldCards=new HashSet<>(),newCards=new HashSet<>();for(JsonElement card:previous.getAsJsonArray("battlefield"))if(!oldCards.add(string(card.getAsJsonObject(),"id")))return false;for(JsonElement card:player.getAsJsonArray("battlefield"))if(!newCards.add(string(card.getAsJsonObject(),"id")))return false;if(!oldCards.equals(newCards))return false;}
            }
            return first.containsKey(viewer);
        }catch(RuntimeException unsupported){return false;}
    }
    public static boolean observesRepeatedCombat(JsonObject before,JsonObject beforeMetadata,JsonObject after,JsonObject afterMetadata,String attacker,String added) {
        try {
            String viewer=string(before,"viewer");if(!new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open")) || attacker.equals(added) || !viewer.equals(string(after,"viewer")) || !string(before,"game_id").equals(string(after,"game_id")) || number(before,"turn")!=number(after,"turn") || !"PRECOMBAT_MAIN".equals(string(before,"phase")) || !"POSTCOMBAT_MAIN".equals(string(after,"phase")) || after.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("combat").size()!=0 || battlefieldCounter(before,beforeMetadata,attacker)!=battlefieldCounter(after,afterMetadata,attacker))return false;
            JsonObject original=controlledPermanent(after,attacker,viewer),created=controlledPermanent(after,added,viewer),createdMetadata=afterMetadata.getAsJsonObject("objects").getAsJsonObject(added);if(!new JsonPrimitive(false).equals(controlledPermanent(before,attacker,viewer).get("tapped")) || !new JsonPrimitive(true).equals(original.get("tapped")) || !viewer.equals(string(createdMetadata,"owner")) || !viewer.equals(string(createdMetadata,"controller")) || number(createdMetadata,"incarnation")<0 || !"Memnite".equals(string(created,"name")) || !"1".equals(string(created,"power")) || !"1".equals(string(created,"toughness")))return false;
            boolean held=false;for(JsonElement item:before.getAsJsonArray("hand"))held|=added.equals(string(item.getAsJsonObject(),"id"));if(!held || after.getAsJsonArray("hand").size()!=before.getAsJsonArray("hand").size()-1)return false;Set<String> kept=new HashSet<>(),remaining=new HashSet<>();for(JsonElement item:before.getAsJsonArray("hand")){String id=string(item.getAsJsonObject(),"id");if(!id.equals(added))kept.add(id);else if(!"Memnite".equals(string(item.getAsJsonObject(),"name")))return false;}for(JsonElement item:after.getAsJsonArray("hand"))if(!remaining.add(string(item.getAsJsonObject(),"id")))return false;if(!kept.equals(remaining))return false;
            Map<String,Long> lives=new HashMap<>();JsonObject first=null,last=null;if(before.getAsJsonArray("players").size()!=2 || after.getAsJsonArray("players").size()!=2)return false;for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(lives.put(string(player,"id"),number(player,"life"))!=null)return false;if(viewer.equals(string(player,"id")))first=player;}
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id)-(viewer.equals(id)?0:1))return false;if(viewer.equals(id))last=player;}
            return first!=null && last!=null && string(first,"name").equals(string(before,"active_player")) && string(first,"name").equals(string(before,"priority_player")) && string(last,"name").equals(string(after,"active_player")) && string(last,"name").equals(string(after,"priority_player")) && last.getAsJsonArray("battlefield").size()==first.getAsJsonArray("battlefield").size()+1 && number(first,"library_count")==number(last,"library_count") && first.get("graveyard").equals(last.get("graveyard"));
        }catch(RuntimeException unsupported){return false;}
    }
    /** Native return to the same human seat after one opposing turn, including cleanup/draw. */
    public static boolean observesNextHumanTurn(JsonObject before,JsonObject beforeMetadata,JsonObject after,JsonObject prompt,JsonObject afterMetadata,String source,Set<String> discarded) {
        try {
            String viewer=string(before,"viewer");if(!viewer.equals(string(after,"viewer")) || !string(before,"game_id").equals(string(after,"game_id")) || number(after,"turn")!=number(before,"turn")+2
                || !"POSTCOMBAT_MAIN".equals(string(before,"phase")) || !"PRECOMBAT_MAIN".equals(string(after,"phase")) || !"PRECOMBAT_MAIN".equals(string(after,"step"))
                || before.getAsJsonArray("combat").size()!=0 || after.getAsJsonArray("combat").size()!=0 || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0
                || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source) || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open"))
                || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || prompt.has("attackers") || prompt.has("blockers") || number(prompt,"cycle")!=number(after,"cycle") || number(after,"cycle")<=number(before,"cycle") || discarded.size()>16)return false;
            JsonObject first=null,last=null;Map<String,Long> lives=new HashMap<>();if(before.getAsJsonArray("players").size()!=2 || after.getAsJsonArray("players").size()!=2)return false;
            for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(lives.put(string(player,"id"),number(player,"life"))!=null)return false;if(viewer.equals(string(player,"id")))first=player;}
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id))return false;if(viewer.equals(id))last=player;}
            if(first==null || last==null || !string(first,"name").equals(string(before,"active_player")) || !string(last,"name").equals(string(after,"active_player")) || !string(last,"name").equals(string(after,"priority_player"))
                || number(last,"library_count")!=number(first,"library_count")-1 || after.getAsJsonArray("hand").size()!=before.getAsJsonArray("hand").size()+1-discarded.size() || last.getAsJsonArray("graveyard").size()!=first.getAsJsonArray("graveyard").size()+discarded.size())return false;
            Set<String> originalHand=new HashSet<>(),finalHand=new HashSet<>(),grave=new HashSet<>();for(JsonElement item:before.getAsJsonArray("hand"))originalHand.add(string(item.getAsJsonObject(),"id"));for(JsonElement item:after.getAsJsonArray("hand"))finalHand.add(string(item.getAsJsonObject(),"id"));for(JsonElement item:last.getAsJsonArray("graveyard"))grave.add(string(item.getAsJsonObject(),"id"));
            if(originalHand.size()!=before.getAsJsonArray("hand").size() || finalHand.size()!=after.getAsJsonArray("hand").size() || !originalHand.containsAll(discarded) || !grave.containsAll(discarded))return false;for(String id:discarded)if(finalHand.contains(id))return false;Set<String> kept=new HashSet<>(originalHand);kept.removeAll(discarded);if(!finalHand.containsAll(kept))return false;Set<String> drawn=new HashSet<>(finalHand);drawn.removeAll(originalHand);if(drawn.size()!=1)return false;
            Set<String> firstBattlefield=new HashSet<>(),lastBattlefield=new HashSet<>(),originalGrave=new HashSet<>();
            for(JsonElement item:first.getAsJsonArray("battlefield"))if(!firstBattlefield.add(string(item.getAsJsonObject(),"id")))return false;
            for(JsonElement item:last.getAsJsonArray("battlefield")){JsonObject card=item.getAsJsonObject();if(!lastBattlefield.add(string(card,"id")) || !string(last,"name").equals(string(card,"controller_name")) || !new JsonPrimitive(false).equals(card.get("tapped")))return false;}
            for(JsonElement item:first.getAsJsonArray("graveyard"))if(!originalGrave.add(string(item.getAsJsonObject(),"id")))return false;
            originalGrave.addAll(discarded);if(!firstBattlefield.equals(lastBattlefield) || grave.size()!=last.getAsJsonArray("graveyard").size() || !grave.equals(originalGrave))return false;
            return new JsonPrimitive(true).equals(controlledPermanent(before,source,viewer).get("tapped")) && new JsonPrimitive(false).equals(controlledPermanent(after,source,viewer).get("tapped"));
        }catch(RuntimeException unsupported){return false;}
    }
    /** Exact native tail of the unblocked fixture; no inferred phase ordering. */
    public static PriorityEvidence combatCleanupEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        try {
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer")) || !string(before,"game_id").equals(string(command,"game_id"))
                || !"respond".equals(string(command,"command")) || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value")) || number(command,"decision_id")!=number(prompt,"decision_id")
                || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || prompt.has("attackers") || prompt.has("blockers") || number(prompt,"cycle")!=number(before,"cycle")
                || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open")) || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source)
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || number(before,"turn")!=number(after,"turn")
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id"))
                || !"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers")
                || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(nextPrompt,"cycle")!=number(after,"cycle") || number(after,"cycle")<number(before,"cycle")
                || !"COMBAT".equals(string(before,"phase")) || !"COMBAT_DAMAGE".equals(string(before,"step"))
                || !"POSTCOMBAT_MAIN".equals(string(after,"phase")) || !"POSTCOMBAT_MAIN".equals(string(after,"step")))return null;
            JsonArray first=before.getAsJsonArray("combat"),last=after.getAsJsonArray("combat");if(first.size()!=1 || last.size()!=0)return null;
            for(JsonArray groups:Arrays.asList(first,last))for(JsonElement item:groups){JsonObject group=item.getAsJsonObject();if(group.getAsJsonArray("attackers").size()!=1 || !source.equals(group.getAsJsonArray("attackers").get(0).getAsString()) || group.getAsJsonArray("blockers").size()!=0 || !new JsonPrimitive(false).equals(group.get("blocked")))return null;}
            if(first.size()==1 && last.size()==1 && !first.equals(last))return null;
            Map<String,Long> lives=new HashMap<>();if(before.getAsJsonArray("players").size()!=2 || after.getAsJsonArray("players").size()!=2)return null;
            for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(lives.put(string(player,"id"),number(player,"life"))!=null)return null;}
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id))return null;}
            for(JsonArray groups:Arrays.asList(first,last))for(JsonElement item:groups){String defender=string(item.getAsJsonObject(),"defender");if(!lives.containsKey(defender) || defender.equals(string(before,"viewer")))return null;}
            return new PriorityEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    /** Bounded public 1/1 fixture: native combat-damage step plus exact defender life delta. */
    public static PriorityEvidence combatDamageEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        PriorityEvidence pass=declaredPriorityEvidence(before,prompt,command,beforeMetadata,accepted,after,nextPrompt,afterMetadata,source);if(pass==null)return null;
        try {
            if(!"COMBAT".equals(string(before,"phase")) || !"COMBAT".equals(string(after,"phase")) || !"COMBAT_DAMAGE".equals(string(after,"step")) || string(before,"step").equals(string(after,"step"))
                || !before.get("combat").equals(after.get("combat")) || before.getAsJsonArray("players").size()!=2 || after.getAsJsonArray("players").size()!=2)return null;
            String defender=string(after.getAsJsonArray("combat").get(0).getAsJsonObject(),"defender"),viewer=string(before,"viewer");Map<String,Long> lives=new HashMap<>();boolean fixtureSource=false;
            for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(lives.put(id,number(player,"life"))!=null)return null;
                if(viewer.equals(id))for(JsonElement item:player.getAsJsonArray("battlefield")){JsonObject card=item.getAsJsonObject();if(source.equals(string(card,"id")) && "Memnite".equals(string(card,"name")) && "1".equals(string(card,"power")) && "1".equals(string(card,"toughness")))fixtureSource=true;}}
            if(!fixtureSource || !lives.containsKey(viewer) || !lives.containsKey(defender) || lives.get(defender)<=1)return null;
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id)-(defender.equals(id)?1:0))return null;}
            return pass;
        }catch(RuntimeException unsupported){return null;}
    }
    private static JsonObject controlledPermanent(JsonObject state,String id,String controller) {
        JsonObject found=null;for(JsonElement row:state.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(!controller.equals(string(player,"id")))continue;
            for(JsonElement item:player.getAsJsonArray("battlefield")){JsonObject card=item.getAsJsonObject();if(!id.equals(string(card,"id")))continue;
                if(found!=null || !new JsonPrimitive(false).equals(card.get("hidden")) || !new JsonPrimitive(false).equals(card.get("face_down")) || !string(player,"name").equals(string(card,"controller_name")))throw new IllegalArgumentException();found=card;}}
        if(found==null)throw new IllegalArgumentException();return found;
    }
    /** One Memnite blocked by one Ornithopter; no lethal or general blocked combat support. */
    public static PriorityEvidence blockedDamageEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        PriorityEvidence pass=combatPriorityEvidence(before,prompt,command,beforeMetadata,accepted,after,nextPrompt,afterMetadata,source,true);if(pass==null)return null;
        try {
            if(!"COMBAT".equals(string(before,"phase")) || !"COMBAT".equals(string(after,"phase")) || !"COMBAT_DAMAGE".equals(string(after,"step")) || string(before,"step").equals(string(after,"step")) || !before.get("combat").equals(after.get("combat")) || before.getAsJsonArray("players").size()!=2 || after.getAsJsonArray("players").size()!=2)return null;
            JsonObject group=before.getAsJsonArray("combat").get(0).getAsJsonObject();String blocker=group.getAsJsonArray("blockers").get(0).getAsString(),defender=string(group,"defender"),viewer=string(before,"viewer");
            JsonObject first=controlledPermanent(before,blocker,defender),last=controlledPermanent(after,blocker,defender);
            for(JsonObject card:Arrays.asList(first,last))if(!"Ornithopter".equals(string(card,"name")) || !"0".equals(string(card,"power")) || !"2".equals(string(card,"toughness")))return null;
            if(number(first,"damage")!=0 || number(last,"damage")!=1)return null;
            JsonObject firstEntry=beforeMetadata.getAsJsonObject("objects").getAsJsonObject(blocker),lastEntry=afterMetadata.getAsJsonObject("objects").getAsJsonObject(blocker);
            if(number(firstEntry,"incarnation")!=number(lastEntry,"incarnation"))return null;for(JsonObject entry:Arrays.asList(firstEntry,lastEntry))if(!defender.equals(string(entry,"owner")) || !defender.equals(string(entry,"controller")))return null;
            for(JsonObject state:Arrays.asList(before,after)){JsonObject card=controlledPermanent(state,source,viewer);if(!"Memnite".equals(string(card,"name")) || !"1".equals(string(card,"power")) || !"1".equals(string(card,"toughness")) || number(card,"damage")!=0)return null;}
            Map<String,Long> lives=new HashMap<>();for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(lives.put(string(player,"id"),number(player,"life"))!=null)return null;}
            Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id))return null;}
            return pass;
        }catch(RuntimeException unsupported){return null;}
    }
    /** Exact post-declaration pass and next guarded native combat observation; no damage claim. */
    public static PriorityEvidence declaredPriorityEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        return combatPriorityEvidence(before,prompt,command,beforeMetadata,accepted,after,nextPrompt,afterMetadata,source,false);
    }
    private static PriorityEvidence combatPriorityEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source,boolean blocked) {
        try {
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer"))
                || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command")) || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value"))
                || number(command,"decision_id")!=number(prompt,"decision_id") || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || prompt.has("attackers") || prompt.has("blockers")
                || number(prompt,"cycle")!=number(before,"cycle") || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open"))
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source)
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id"))
                || !"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers")
                || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle") || number(after,"turn")!=number(before,"turn")
                || before.getAsJsonArray("combat").size()!=1 || after.getAsJsonArray("combat").size()!=1)return null;
            JsonObject first=before.getAsJsonArray("combat").get(0).getAsJsonObject(),last=after.getAsJsonArray("combat").get(0).getAsJsonObject();
            if(first.getAsJsonArray("attackers").size()!=1 || !source.equals(first.getAsJsonArray("attackers").get(0).getAsString()) || !first.get("attackers").equals(last.get("attackers")) || !string(first,"defender").equals(string(last,"defender"))
                || (blocked?(first.getAsJsonArray("blockers").size()!=1 || !new JsonPrimitive(true).equals(first.get("blocked")) || !first.get("blockers").equals(last.get("blockers"))):(first.getAsJsonArray("blockers").size()!=0 || !new JsonPrimitive(false).equals(first.get("blocked")))) || !last.get("blocked").isJsonPrimitive() || !last.getAsJsonPrimitive("blocked").isBoolean())return null;
            String defender=string(last,"defender"),viewer=string(after,"viewer");Set<String> visible=new HashSet<>();int opponents=0;
            for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(defender.equals(string(player,"id")) && !viewer.equals(defender) && new JsonPrimitive(false).equals(player.get("left"))){opponents++;for(JsonElement item:player.getAsJsonArray("battlefield")){JsonObject card=item.getAsJsonObject();if(new JsonPrimitive(false).equals(card.get("hidden")) && new JsonPrimitive(false).equals(card.get("face_down")) && string(player,"name").equals(string(card,"controller_name")))visible.add(string(card,"id"));}}}
            JsonArray blockers=last.getAsJsonArray("blockers");Set<String> unique=new HashSet<>();if(opponents!=1 || blockers.size()>256)return null;
            for(JsonElement blocker:blockers)if(!blocker.isJsonPrimitive() || !blocker.getAsJsonPrimitive().isString() || !unique.add(blocker.getAsString()) || !visible.contains(blocker.getAsString()) || source.equals(blocker.getAsString()))return null;
            return new PriorityEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    public static final class DeclaredAttackEvidence {
        private final JsonObject command;
        private DeclaredAttackEvidence(JsonObject command){this.command=command.deepCopy();}
        public boolean matchesCommand(JsonObject candidate){return command.equals(candidate);}
    }
    /** One selected source retained as declaration closes; no blocking or damage claim. */
    public static DeclaredAttackEvidence declaredAttackEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,
            JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        try {
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer"))
                || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command")) || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value"))
                || number(command,"decision_id")!=number(prompt,"decision_id") || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(false).equals(prompt.get("is_priority")) || !prompt.has("attackers") || prompt.has("blockers")
                || number(prompt,"cycle")!=number(before,"cycle") || !new JsonPrimitive(false).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(true).equals(afterMetadata.get("priority_open"))
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source)
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id"))
                || !"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers")
                || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle") || number(after,"turn")!=number(before,"turn")
                || before.getAsJsonArray("combat").size()!=1 || !before.get("combat").equals(after.get("combat")))return null;
            JsonArray candidates=prompt.getAsJsonArray("attackers");Set<String> unique=new HashSet<>();if(candidates.size()>256)return null;
            for(JsonElement candidate:candidates)if(!candidate.isJsonPrimitive() || !candidate.getAsJsonPrimitive().isString() || !unique.add(candidate.getAsString()))return null;
            JsonObject group=before.getAsJsonArray("combat").get(0).getAsJsonObject();
            if(group.getAsJsonArray("attackers").size()!=1 || !source.equals(group.getAsJsonArray("attackers").get(0).getAsString()) || group.getAsJsonArray("blockers").size()!=0 || !new JsonPrimitive(false).equals(group.get("blocked")))return null;
            String viewer=string(before,"viewer"),defender=string(group,"defender");int opponents=0;boolean active=false;
            for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(viewer.equals(string(player,"id")) && string(before,"active_player").equals(string(player,"name")))active=true;}
            for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(defender.equals(string(player,"id")) && !viewer.equals(defender) && new JsonPrimitive(false).equals(player.get("left")))opponents++;}
            return active && opponents==1?new DeclaredAttackEvidence(command):null;
        }catch(RuntimeException unsupported){return null;}
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
    public static PriorityEvidence combatEntryEvidence(JsonObject before,JsonObject prompt,JsonObject command,JsonObject beforeMetadata,JsonObject accepted,JsonObject after,JsonObject nextPrompt,JsonObject afterMetadata,String source) {
        try {
            boolean selecting="GAME_SELECT".equals(string(nextPrompt,"kind")) && new JsonPrimitive(false).equals(nextPrompt.get("is_priority")) && nextPrompt.has("attackers");
            if(!string(before,"game_id").equals(string(after,"game_id")) || !string(before,"viewer").equals(string(after,"viewer")) || !string(before,"game_id").equals(string(command,"game_id")) || !"respond".equals(string(command,"command")) || !"boolean".equals(string(command,"kind")) || !new JsonPrimitive(false).equals(command.get("value")) || number(command,"decision_id")!=number(prompt,"decision_id")
                || !"GAME_SELECT".equals(string(prompt,"kind")) || !new JsonPrimitive(true).equals(prompt.get("is_priority")) || prompt.has("attackers") || prompt.has("blockers") || number(prompt,"cycle")!=number(before,"cycle") || number(nextPrompt,"cycle")!=number(after,"cycle") || number(nextPrompt,"decision_id")<=number(prompt,"decision_id") || number(after,"cycle")<number(before,"cycle") || number(before,"turn")!=number(after,"turn")
                || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || !new JsonPrimitive(!selecting).equals(afterMetadata.get("priority_open")) || battlefieldCounter(before,beforeMetadata,source)!=battlefieldCounter(after,afterMetadata,source)
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || before.getAsJsonArray("combat").size()!=0 || after.getAsJsonArray("combat").size()!=0 || !"COMBAT".equals(string(after,"phase"))
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id")))return null;
            if(selecting){boolean offered=false;Set<String> unique=new HashSet<>();JsonArray candidates=nextPrompt.getAsJsonArray("attackers");if(candidates.size()>256 || nextPrompt.has("blockers"))return null;for(JsonElement candidate:candidates){if(!candidate.isJsonPrimitive() || !candidate.getAsJsonPrimitive().isString() || !unique.add(candidate.getAsString()))return null;offered|=source.equals(candidate.getAsString());}if(!offered)return null;}
            else if(!"GAME_SELECT".equals(string(nextPrompt,"kind")) || !new JsonPrimitive(true).equals(nextPrompt.get("is_priority")) || nextPrompt.has("attackers") || nextPrompt.has("blockers"))return null;
            Map<String,Long> lives=new HashMap<>();for(JsonElement row:before.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();if(lives.put(string(player,"id"),number(player,"life"))!=null)return null;}Set<String> seen=new HashSet<>();for(JsonElement row:after.getAsJsonArray("players")){JsonObject player=row.getAsJsonObject();String id=string(player,"id");if(!seen.add(id) || !lives.containsKey(id) || number(player,"life")!=lives.get(id))return null;}if(!seen.equals(lives.keySet()))return null;
            return new PriorityEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    public static TurnDecisionEvidence turnAttackerEvidence(AttackerSelectionEvidence proof,JsonObject command){return proof!=null && proof.matchesCommand(command)?new TurnDecisionEvidence(command):null;}
    public static TurnDecisionEvidence turnDeclaredEvidence(DeclaredAttackEvidence proof,JsonObject command){return proof!=null && proof.matchesCommand(command)?new TurnDecisionEvidence(command):null;}
    public TurnDecisionEvidence selectionEvidence(JsonObject before,JsonObject beforeMetadata,JsonObject command,JsonObject accepted,JsonObject after,JsonObject prompt,JsonObject metadata) {
        try {
            if(sourceIncarnation==null || !"ok".equals(string(beforeMetadata,"status")) || number(beforeMetadata,"cycle")!=cycle || !new JsonPrimitive(true).equals(beforeMetadata.get("priority_open")) || (!viewer.equals(string(beforeMetadata.getAsJsonObject("objects").getAsJsonObject(source),"owner")) || number(beforeMetadata.getAsJsonObject("objects").getAsJsonObject(source),"incarnation")!=sourceIncarnation) || number(before,"cycle")!=cycle || !game.equals(string(before,"game_id")) || !viewer.equals(string(before,"viewer")) || !"respond".equals(string(command,"command")) || !"object".equals(string(command,"kind")) || !source.equals(string(command,"value")) || !game.equals(string(command,"game_id")) || number(command,"decision_id")!=decision
                || !"response_sent".equals(string(accepted,"event")) || !new JsonPrimitive(true).equals(accepted.get("accepted")) || !string(command,"request_id").equals(string(accepted,"request_id")) || !matches(after,prompt)
                || before.getAsJsonArray("stack").size()!=0 || after.getAsJsonArray("stack").size()!=0 || before.getAsJsonArray("hand").size()!=after.getAsJsonArray("hand").size() || !"ok".equals(string(metadata,"status")) || number(metadata,"cycle")!=number(after,"cycle") || !new JsonPrimitive(false).equals(metadata.get("priority_open")))return null;
            JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(source);if(number(entry,"incarnation")!=sourceIncarnation || !viewer.equals(string(entry,"owner")))return null;return new TurnDecisionEvidence(command);
        }catch(RuntimeException unsupported){return null;}
    }
    public static TurnDecisionEvidence turnAbilityEvidence(AbilityEvidence proof,JsonObject command){return proof!=null && proof.matchesCommand(command)?new TurnDecisionEvidence(command):null;}
    public static TurnDecisionEvidence turnPriorityEvidence(PriorityEvidence proof,JsonObject command){return proof!=null && proof.matchesCommand(command)?new TurnDecisionEvidence(command):null;}
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

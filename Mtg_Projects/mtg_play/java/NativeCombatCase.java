import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Explicit deterministic public-card acceptance scenarios; never a rules or autoplay service. */
public final class NativeCombatCase {
    public interface Metadata {JsonObject read(JsonObject state,String... ids) throws Exception;}
    public static final Set<String> KEYS=Collections.unmodifiableSet(new LinkedHashSet<>(Arrays.asList("haste","flying","reach","defender","first-strike","double-strike","deathtouch","lifelink","trample","menace","vigilance","indestructible","planeswalker","battle","draw")));
    private static final Map<String,String[]> CARDS=new HashMap<>();
    static {
        add("Forest","TRK","325");add("Mountain","TRK","323");add("Plains","TRK","317");add("Island","TRK","319");add("Phyrexian Walker","VIS","152");add("Suntail Hawk","M14","40");add("Memnite","SOM","174");add("Ornithopter","M15","223");add("Shield Sphere","ALL","129");add("Raging Goblin","M10","153");add("Scryb Sprites","5ED","324");add("Serra Angel","FDN","147");add("Goblin Trailblazer","RIX","105");add("Porcelain Legionnaire","NPH","19");add("Fencing Ace","M20","16");add("Sedge Scorpion","M20","192");add("Garruk's Companion","M12","175");add("Healer's Hawk","FDN","142");add("Darksteel Myr","SOM","151");add("Wall of Vines","M19","210");add("Jace Beleren","M11","58");add("Invasion of Regatha","MOM","148");add("Divine Intervention","LEG","8");
    }
    private static void add(String name,String set,String number){CARDS.put(name,new String[]{name,set,number});}
    public final String key,actorName,landName,opponentName;
    public final boolean blocking;
    private String actor,permanent,permanentMain,viewer;private long castTurn=-1,actorIncarnation=-1,permanentIncarnation=-1,permanentMainIncarnation=-1,attackTurn=-1,ownLifeAtAttack,otherLifeAtAttack,defenderBefore=-1;
    private boolean sourceVerified,declared,blocked,damageCorrect,defenderDamage,defenderDefeated,matureDefender,damageMarked,completed,flyingBlocked,firstDamage,normalDamage;
    private boolean reselectRequested,reselectRemoved,reselectAssigned,backFaceSeen,mainCardMatched,mainCounterAdvanced;
    private int maximumBlockers,manaResponses,amountResponses;private long steps;
    public NativeCombatCase(String key) {
        if(!KEYS.contains(key))throw new IllegalArgumentException("COMBAT_CASE_INVALID");this.key=key;
        String actor="Memnite",land="Forest",opponent="Phyrexian Walker";
        switch(key){
            case "haste":actor="Raging Goblin";land="Mountain";break;
            case "flying":actor="Scryb Sprites";break;
            case "reach":actor="Wall of Vines";opponent="Suntail Hawk";break;
            case "defender":actor="Shield Sphere";opponent="Memnite";break;
            case "first-strike":actor="Porcelain Legionnaire";land="Plains";break;
            case "double-strike":actor="Fencing Ace";land="Plains";break;
            case "deathtouch":actor="Sedge Scorpion";break;
            case "lifelink":actor="Healer's Hawk";land="Plains";break;
            case "trample":actor="Garruk's Companion";opponent="Ornithopter";break;
            case "menace":actor="Goblin Trailblazer";land="Mountain";break;
            case "vigilance":case "planeswalker":actor="Serra Angel";land="Plains";break;
            case "indestructible":actor="Darksteel Myr";opponent="Memnite";break;
            case "battle":land="Mountain";opponent="Forest";break;
            case "draw":actor="Divine Intervention";land="Plains";break;
            default:throw new IllegalArgumentException("COMBAT_CASE_INVALID");
        }
        actorName=actor;landName=land;opponentName=opponent;blocking=Arrays.asList("reach","defender","indestructible").contains(key);
    }
    public Set<String> handNames(){Set<String> names=new HashSet<>(Arrays.asList(actorName,landName));if(key.equals("battle"))names.add("Invasion of Regatha");return names;}
    public boolean openingMatches(JsonArray hand){Set<String> observed=new HashSet<>();for(JsonElement value:hand){String name=text(value.getAsJsonObject(),"name");if(!handNames().contains(name))return false;observed.add(name);}return observed.containsAll(handNames());}
    public JsonArray deck(boolean ai) {
        JsonArray cards=new JsonArray();for(int i=0;i<60;i++){
            String name;
            if(!ai){name=key.equals("battle")?new String[]{landName,actorName,"Invasion of Regatha"}[i%3]:i%2==0?landName:actorName;}
            else if(key.equals("planeswalker"))name=i%5==0?"Jace Beleren":"Island";
            else if(key.equals("reach"))name=i%5==0?"Suntail Hawk":"Plains";
            else if(blocking)name=i%5==0?"Memnite":"Forest";
            else name=opponentName;
            String[] printing=CARDS.get(name);JsonObject row=new JsonObject();row.addProperty("name",printing[0]);row.addProperty("set",printing[1]);row.addProperty("number",printing[2]);row.addProperty("quantity",1);cards.add(row);
        }return cards;
    }
    private static String text(JsonObject row,String key){JsonElement value=row.get(key);return value==null || value.isJsonNull()?"":value.getAsString();}
    private static long number(JsonObject row,String key){return row.get(key).getAsLong();}
    private static JsonObject card(JsonObject state,String id,String zone){for(JsonElement row:state.getAsJsonArray("players"))for(JsonElement value:row.getAsJsonObject().getAsJsonArray(zone))if(id.equals(text(value.getAsJsonObject(),"id")))return value.getAsJsonObject();return null;}
    private static long life(JsonObject state,String viewer,boolean mine){for(JsonElement value:state.getAsJsonArray("players")){JsonObject row=value.getAsJsonObject();if(viewer.equals(text(row,"id"))==mine)return number(row,"life");}throw new IllegalArgumentException("COMBAT_CASE_SEATS");}
    private static JsonObject guard(JsonObject state,String id,Metadata reader) throws Exception {JsonObject metadata=reader.read(state,id);if(!"ok".equals(text(metadata,"status")) || number(metadata,"cycle")!=number(state,"cycle"))throw new IOException("COMBAT_CASE_UNGUARDED");JsonObject entry=metadata.getAsJsonObject("objects").getAsJsonObject(id);if(entry==null || number(entry,"incarnation")<0)throw new IOException("COMBAT_CASE_SOURCE_UNPROVEN");return entry;}
    public void before(JsonObject state,JsonObject prompt,JsonObject command) {
        viewer=text(state,"viewer");String kind=text(prompt,"kind");if(kind.equals("GAME_PLAY_MANA"))manaResponses++;if(kind.equals("GAME_GET_AMOUNT") || kind.equals("GAME_GET_MULTI_AMOUNT"))amountResponses++;
        if(!"object".equals(text(command,"kind")))return;String id=text(command,"value");
        if(kind.equals("GAME_SELECT") && (prompt.has("attackers") || prompt.has("blockers")) && id.equals(actor))for(JsonElement row:state.getAsJsonArray("combat")){JsonObject group=row.getAsJsonObject();for(JsonElement source:group.getAsJsonArray(blocking?"blockers":"attackers"))reselectRequested|=id.equals(source.getAsString());}
        if(kind.equals("GAME_SELECT") && new JsonPrimitive(true).equals(prompt.get("is_priority"))){for(JsonElement item:state.getAsJsonArray("hand")){JsonObject value=item.getAsJsonObject();if(id.equals(text(value,"id"))){if(actorName.equals(text(value,"name")) && actor==null){actor=id;castTurn=number(state,"turn");}if(key.equals("battle") && "Invasion of Regatha".equals(text(value,"name")))permanent=id;}}}
        if(kind.equals("GAME_TARGET") && "COMBAT".equals(text(state,"phase"))){JsonObject value=card(state,id,"battlefield");if(value!=null && ((key.equals("planeswalker") && "Jace Beleren".equals(text(value,"name"))) || (key.equals("battle") && "Invasion of Regatha".equals(text(value,"name"))))){if(!id.equals(permanent)){permanentIncarnation=-1;permanentMainIncarnation=-1;permanentMain=null;}permanent=id;String field=key.equals("planeswalker")?"loyalty":"defense";defenderBefore=Long.parseLong(text(value,field));}}
    }
    public boolean observe(JsonObject state,JsonObject prompt,Metadata reader) throws Exception {
        if(++steps>512)throw new IOException("COMBAT_CASE_BUDGET");if(viewer==null)viewer=text(state,"viewer");if(actor==null)return false;
        JsonObject live=card(state,actor,"battlefield"),dead=card(state,actor,"graveyard");
        if(live!=null){JsonObject entry=guard(state,actor,reader);long incarnation=number(entry,"incarnation");if(actorIncarnation<0){actorIncarnation=incarnation;}if(incarnation!=actorIncarnation || !viewer.equals(text(entry,"owner")) || !viewer.equals(text(entry,"controller")))throw new IOException("COMBAT_CASE_ACTOR_CHANGED");
            if(!actorName.equals(text(live,"name")))throw new IOException("COMBAT_CASE_ACTOR_CHANGED");String expected=key.replace('-',' ');boolean property=Arrays.asList("planeswalker","battle","draw").contains(key);
            if(entry.has("live_abilities"))for(JsonElement rule:entry.getAsJsonArray("live_abilities"))property|=rule.getAsString().toLowerCase(Locale.ROOT).contains(expected);sourceVerified|=property;
            if(!new JsonPrimitive(false).equals(live.get("hidden")) || !new JsonPrimitive(false).equals(live.get("face_down")))throw new IOException("COMBAT_CASE_ACTOR_HIDDEN");
            damageMarked|=live.has("damage") && number(live,"damage")>0;
            boolean ownTurn=false;for(JsonElement row:state.getAsJsonArray("players"))if(viewer.equals(text(row.getAsJsonObject(),"id")))ownTurn=text(row.getAsJsonObject(),"name").equals(text(state,"active_player"));
            matureDefender|=ownTurn && number(state,"turn")>castTurn && new JsonPrimitive(false).equals(live.get("tapped")) && new JsonPrimitive(false).equals(live.get("can_attack"));
        }else if(dead!=null && actorIncarnation>=0){if(number(guard(state,actor,reader),"incarnation")!=actorIncarnation+1)throw new IOException("COMBAT_CASE_ACTOR_CHANGED");}
        String step=text(state,"step");boolean first=step.contains("FIRST") && step.contains("DAMAGE"),normal=step.equals("COMBAT_DAMAGE");
        boolean actorAssigned=false;for(JsonElement value:state.getAsJsonArray("combat")){JsonObject group=value.getAsJsonObject();boolean attacking=false,blockingActor=false;for(JsonElement id:group.getAsJsonArray("attackers"))attacking|=actor.equals(id.getAsString());for(JsonElement id:group.getAsJsonArray("blockers"))blockingActor|=actor.equals(id.getAsString());
            actorAssigned|=attacking || blockingActor;if(attacking){if(attackTurn!=number(state,"turn")){ownLifeAtAttack=life(state,viewer,true);otherLifeAtAttack=life(state,viewer,false);attackTurn=number(state,"turn");}declared|=new JsonPrimitive(true).equals(prompt.get("is_priority")) || first || normal;maximumBlockers=Math.max(maximumBlockers,group.getAsJsonArray("blockers").size());}
            if(blockingActor && key.equals("reach"))for(JsonElement source:group.getAsJsonArray("attackers")){JsonObject target=card(state,source.getAsString(),"battlefield");if(target!=null && "Suntail Hawk".equals(text(target,"name"))){JsonObject entry=guard(state,source.getAsString(),reader);for(JsonElement rule:entry.getAsJsonArray("live_abilities"))flyingBlocked|=rule.getAsString().toLowerCase(Locale.ROOT).contains("flying");}}blocked|=blockingActor;if(attacking || blockingActor){firstDamage|=first;normalDamage|=normal;}
        }
        if(reselectRequested && !actorAssigned)reselectRemoved=true;if(reselectRemoved && actorAssigned)reselectAssigned=true;
        boolean post=text(state,"phase").equals("POSTCOMBAT_MAIN");boolean opponentDead=false,opponentMarked=false;for(JsonElement row:state.getAsJsonArray("players"))if(!viewer.equals(text(row.getAsJsonObject(),"id"))){for(JsonElement item:row.getAsJsonObject().getAsJsonArray("graveyard"))opponentDead|=opponentName.equals(text(item.getAsJsonObject(),"name"));for(JsonElement item:row.getAsJsonObject().getAsJsonArray("battlefield")){JsonObject target=item.getAsJsonObject();opponentMarked|=opponentName.equals(text(target,"name")) && target.has("damage") && number(target,"damage")>=2;}}
        if(permanent!=null && (key.equals("battle") || key.equals("planeswalker"))){JsonObject defended=card(state,permanent,"battlefield");if(defended!=null){JsonObject entry=guard(state,permanent,reader);long incarnation=number(entry,"incarnation");if(permanentIncarnation<0){permanentIncarnation=incarnation;if(entry.has("main_card")){permanentMain=text(entry,"main_card");permanentMainIncarnation=number(entry,"main_card_incarnation");}}
                if(key.equals("battle") && "Disciples of the Inferno".equals(text(defended,"name"))){if(incarnation<=permanentIncarnation)throw new IOException("COMBAT_CASE_BATTLE_TRANSITION");defenderDefeated=true;}
                else{if(incarnation!=permanentIncarnation)throw new IOException("COMBAT_CASE_DEFENDER_CHANGED");String field=key.equals("battle")?"defense":"loyalty";String remaining=text(defended,field);if(defenderBefore>=0 && !remaining.isEmpty() && number(state,"turn")==attackTurn && (firstDamage || normalDamage))defenderDamage|=Long.parseLong(remaining)<defenderBefore;}
            }else if(key.equals("planeswalker") && card(state,permanent,"graveyard")!=null && number(state,"turn")==attackTurn && (firstDamage || normalDamage)){if(number(guard(state,permanent,reader),"incarnation")!=permanentIncarnation+1)throw new IOException("COMBAT_CASE_DEFENDER_CHANGED");defenderDamage=true;defenderDefeated=true;}}
        if(key.equals("battle") && permanent!=null && permanentIncarnation>=0)for(JsonElement player:state.getAsJsonArray("players"))for(JsonElement card:player.getAsJsonObject().getAsJsonArray("battlefield")){JsonObject back=card.getAsJsonObject();if("Disciples of the Inferno".equals(text(back,"name"))){backFaceSeen=true;JsonObject entry=guard(state,text(back,"id"),reader);mainCardMatched|=permanentMain!=null && permanentMain.equals(text(entry,"main_card"));mainCounterAdvanced|=entry.has("main_card_incarnation") && number(entry,"main_card_incarnation")>permanentMainIncarnation;if(permanentMain!=null && permanentMain.equals(text(entry,"main_card")) && number(entry,"main_card_incarnation")>permanentMainIncarnation && viewer.equals(text(entry,"owner")) && viewer.equals(text(entry,"controller")))defenderDefeated=true;}}
        long own=life(state,viewer,true),other=life(state,viewer,false);boolean alive=live!=null;
        switch(key){
            case "haste":damageCorrect|=declared && attackTurn==castTurn && normalDamage;break;
            case "flying":damageCorrect|=declared && normalDamage && maximumBlockers==0 && other==otherLifeAtAttack-1;break;
            case "vigilance":damageCorrect|=declared && normalDamage && alive && new JsonPrimitive(false).equals(live.get("tapped")) && other==otherLifeAtAttack-4;break;
            case "first-strike":damageCorrect|=declared && firstDamage && opponentDead && alive;break;
            case "double-strike":damageCorrect|=declared && firstDamage && normalDamage && opponentMarked;break;
            case "deathtouch":damageCorrect|=declared && normalDamage && maximumBlockers>0 && opponentDead && alive;break;
            case "lifelink":damageCorrect|=declared && normalDamage && own==ownLifeAtAttack+1 && other==otherLifeAtAttack-1;break;
            case "trample":damageCorrect|=declared && normalDamage && maximumBlockers>0 && other<otherLifeAtAttack;break;
            case "menace":damageCorrect|=declared && normalDamage && maximumBlockers>=2 && (opponentMarked || opponentDead);break;
            case "indestructible":damageCorrect|=blocked && normalDamage && alive && number(live,"damage")>=Long.parseLong(text(live,"toughness"));break;
            case "reach":damageCorrect|=blocked && normalDamage && flyingBlocked && damageMarked && alive;break;
            case "defender":damageCorrect|=blocked && normalDamage && damageMarked && matureDefender && alive;break;
            case "planeswalker":damageCorrect|=defenderDamage && defenderDefeated;break;
            case "battle":damageCorrect|=defenderDamage && defenderDefeated;break;
            default:break;
        }
        completed|=sourceVerified && damageCorrect && post && (!(key.equals("haste") || key.equals("reach")) || reselectAssigned);return completed;
    }
    public void terminal(String outcome) throws IOException {if(!key.equals("draw") || !outcome.equals("draw") || !sourceVerified)throw new IOException("COMBAT_CASE_RESULT_UNPROVEN");completed=true;}
    public JsonObject report(){JsonObject result=new JsonObject();result.addProperty("native_combat_case",key);result.addProperty("native_combat_case_reselected",reselectAssigned);result.addProperty("native_combat_case_back_face_seen",backFaceSeen);result.addProperty("native_combat_case_main_card_matched",mainCardMatched);result.addProperty("native_combat_case_main_counter_advanced",mainCounterAdvanced);result.addProperty("native_combat_case_completed",completed);result.addProperty("native_combat_case_source_verified",sourceVerified);result.addProperty("native_combat_case_first_damage",firstDamage);result.addProperty("native_combat_case_normal_damage",normalDamage);result.addProperty("native_combat_case_maximum_blockers",maximumBlockers);result.addProperty("native_combat_case_mana_responses",manaResponses);result.addProperty("native_combat_case_amount_responses",amountResponses);result.addProperty("native_combat_case_defender_damage",defenderDamage);result.addProperty("native_combat_case_damage_verified",damageCorrect);result.addProperty("native_combat_case_cast_turn",castTurn);result.addProperty("native_combat_case_attack_turn",attackTurn);result.addProperty("native_combat_case_defender_defeated",defenderDefeated);return result;}
}

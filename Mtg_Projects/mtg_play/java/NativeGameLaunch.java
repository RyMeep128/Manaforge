import com.google.gson.*;
import java.io.IOException;
import java.util.*;
import manaforge.protocol.LaunchContracts.*;
import manaforge.protocol.PlayContracts.CardIdentity;

/** Gateway-private projection of a validated saved-deck manifest. No card resolution or rules. */
public final class NativeGameLaunch {
    private final LaunchManifest manifest;private final LaunchSeat human,ai;
    public NativeGameLaunch(LaunchManifest manifest) throws IOException {
        if(manifest==null || !"freeform".equals(manifest.format) || manifest.seats.length!=2)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");
        this.manifest=manifest;LaunchSeat h=null,a=null;
        for(LaunchSeat seat:manifest.seats){if(seat.document.deck.commander_entry_ids.length!=0 || seat.document.deck.companion_entry_id!=null)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");if(!seat.seat_id.matches("[A-Za-z0-9_.:-]{1,128}"))throw new IOException("UNITY_GAME_SEAT_INVALID");if(seat.controller.equals("local_human")){if(h!=null)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");h=seat;}else{if(a!=null)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");a=seat;}}
        if(h==null || a==null || !manifest.manifest_id.matches("[A-Za-z0-9_.:-]{1,128}"))throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");human=h;ai=a;
        cards(false,false);cards(true,false);cards(false,true);cards(true,true);
    }
    public String session(){return manifest.manifest_id;}
    public String viewer(){return human.seat_id;}
    public JsonArray controllers(){JsonArray result=new JsonArray();for(LaunchSeat seat:manifest.seats)result.add(seat.controller);return result;}
    public JsonArray cards(boolean opponent,boolean sideboard) throws IOException {
        JsonArray result=new JsonArray();long count=0;
        for(NativeLaunchEntry entry:(opponent?ai:human).document.deck.entries){if(!entry.section.equals(sideboard?"sideboard":"mainboard"))continue;
            if(entry.set_code==null || entry.collector_number==null || entry.name==null || entry.name.isEmpty() || entry.name.contains(" // "))throw new IOException("UNITY_GAME_PRINTING_UNSUPPORTED");
            count+=entry.quantity;if(count>10000)throw new IOException("UNITY_GAME_DECK_LIMIT");JsonObject row=new JsonObject();row.addProperty("name",entry.name);row.addProperty("set",entry.set_code);row.addProperty("number",entry.collector_number);row.addProperty("quantity",entry.quantity);result.add(row);
        }if(!sideboard && count==0)throw new IOException("UNITY_GAME_DECK_EMPTY");return result;
    }
    public Map<String,CardIdentity> bindings(){Map<String,CardIdentity> result=new HashMap<>();Set<String> ambiguous=new HashSet<>();for(NativeLaunchEntry entry:human.document.deck.entries){if(!entry.section.equals("mainboard") || entry.card_id==null)continue;String key=entry.set_code.toUpperCase(Locale.ROOT)+"/"+entry.collector_number;CardIdentity identity=new CardIdentity();identity.printing_id=entry.card_id;identity.oracle_id=entry.oracle_id;identity.deck_entry_id=entry.entry_id;if(result.containsKey(key))ambiguous.add(key);result.put(key,identity);}for(String key:ambiguous)result.get(key).deck_entry_id=null;return result;}
}

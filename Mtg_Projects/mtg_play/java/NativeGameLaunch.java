import com.google.gson.*;
import java.io.IOException;
import java.util.*;
import manaforge.protocol.LaunchContracts.*;
import manaforge.protocol.PlayContracts.CardIdentity;

/** Gateway-private projection of a validated saved-deck manifest. No card resolution or rules. */
public final class NativeGameLaunch {
    private final LaunchManifest manifest;private final LaunchSeat human,ai;
    public NativeGameLaunch(LaunchManifest manifest) throws IOException {
        if(manifest==null || !Arrays.asList("freeform","commander","unrestricted_commander").contains(manifest.format) || manifest.seats.length!=2)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");
        this.manifest=manifest;LaunchSeat h=null,a=null;
        for(LaunchSeat seat:manifest.seats){if(("freeform".equals(manifest.format) && seat.document.deck.commander_entry_ids.length!=0) || seat.document.deck.companion_entry_id!=null)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");if(!seat.seat_id.matches("[A-Za-z0-9_.:-]{1,128}"))throw new IOException("UNITY_GAME_SEAT_INVALID");if(seat.controller.equals("local_human")){if(h!=null)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");h=seat;}else if(seat.controller.equals("engine_ai")){if(a!=null)throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");a=seat;}else throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");}
        if(h==null || a==null || !manifest.manifest_id.matches("[A-Za-z0-9_.:-]{1,128}"))throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");human=h;ai=a;
        cards(false,false);cards(true,false);cards(false,true);cards(true,true);if(format().equals("commander") && (designations(human).isEmpty() || designations(ai).isEmpty()))throw new IOException("UNITY_GAME_SETUP_UNSUPPORTED");
    }
    private List<NativeLaunchEntry> designations(LaunchSeat seat){List<NativeLaunchEntry> result=new ArrayList<>();for(NativeLaunchEntry entry:seat.document.deck.entries)if(entry.section.equals("commander") || Arrays.asList(seat.document.deck.commander_entry_ids).contains(entry.entry_id))result.add(entry);return result;}
    public void verifyCommanders(JsonObject state,JsonObject metadata) throws IOException {
        if(!(format().equals("commander") || format().equals("unrestricted_commander")) || !new JsonPrimitive(true).equals(metadata.get("priority_open")))return;
        if(!new JsonPrimitive(true).equals(metadata.get("commander_metadata_complete")))throw new IOException("UNITY_GAME_COMMANDERS_UNPROVEN");
        String viewer=state.get("viewer").getAsString();Map<String,Integer> expected=new HashMap<>(),actual=new HashMap<>();
        for(JsonElement player:state.getAsJsonArray("players")){String owner=player.getAsJsonObject().get("id").getAsString();for(NativeLaunchEntry entry:designations(owner.equals(viewer)?human:ai)){String key=owner+"/"+entry.set_code.toUpperCase(Locale.ROOT)+"/"+entry.collector_number+"/"+entry.name;expected.put(key,expected.getOrDefault(key,0)+entry.quantity.intValue());}}
        for(JsonElement item:metadata.getAsJsonArray("commanders")){JsonObject row=item.getAsJsonObject();String key=row.get("owner").getAsString()+"/"+row.get("set").getAsString().toUpperCase(Locale.ROOT)+"/"+row.get("number").getAsString()+"/"+row.get("name").getAsString();actual.put(key,actual.getOrDefault(key,0)+1);}
        if(!expected.equals(actual))throw new IOException("UNITY_GAME_COMMANDERS_MISMATCH");
    }
    public String format(){return manifest.format;}
    public String session(){return manifest.manifest_id;}
    public String viewer(){return human.seat_id;}
    public JsonArray controllers(){JsonArray result=new JsonArray();for(LaunchSeat seat:manifest.seats)result.add(seat.controller);return result;}
    public JsonArray cards(boolean opponent,boolean sideboard) throws IOException {
        JsonArray result=new JsonArray();long count=0;
        LaunchSeat seat=opponent?ai:human;Set<String> designated=new HashSet<>(Arrays.asList(seat.document.deck.commander_entry_ids));
        for(NativeLaunchEntry entry:seat.document.deck.entries){boolean command=entry.section.equals("commander") || designated.contains(entry.entry_id);if(sideboard?!(command || (entry.section.equals("sideboard") && !format().equals("unrestricted_commander"))):!entry.section.equals("mainboard") || command)continue;
            if(entry.set_code==null || entry.collector_number==null || entry.name==null || entry.name.isEmpty() || entry.name.contains(" // "))throw new IOException("UNITY_GAME_PRINTING_UNSUPPORTED");
            count+=entry.quantity;if(count>10000)throw new IOException("UNITY_GAME_DECK_LIMIT");JsonObject row=new JsonObject();row.addProperty("name",entry.name);row.addProperty("set",entry.set_code);row.addProperty("number",entry.collector_number);row.addProperty("quantity",entry.quantity);result.add(row);
        }if(!sideboard && count==0 && !format().equals("unrestricted_commander"))throw new IOException("UNITY_GAME_DECK_EMPTY");return result;
    }
    public Map<String,CardIdentity> bindings() {
        Map<String,CardIdentity> result = new HashMap<>();
        Set<String> ambiguousEntries = new HashSet<>(), ambiguousArtwork = new HashSet<>();
        for (LaunchSeat owner : new LaunchSeat[]{human,ai}) for (NativeLaunchEntry entry : owner.document.deck.entries) {
            if (!(entry.section.equals("mainboard") || entry.section.equals("commander")
                    || Arrays.asList(owner.document.deck.commander_entry_ids).contains(entry.entry_id)) || entry.card_id == null) continue;
            String key = (owner==human?"":"opponent/")+entry.set_code.toUpperCase(Locale.ROOT) + "/" + entry.collector_number;
            CardIdentity identity = new CardIdentity();
            identity.printing_id = entry.card_id; identity.oracle_id = entry.oracle_id; identity.deck_entry_id = owner==human?entry.entry_id:null;
            CardIdentity previous = result.get(key);
            if (previous != null) {
                ambiguousEntries.add(key);
                if (!Objects.equals(previous.oracle_id, identity.oracle_id)) ambiguousArtwork.add(key);
                // Engine printings can collapse several selected arts. Keep a stable
                // representative of the SAME Oracle card instead of dropping all art.
                else if(previous.printing_id.compareTo(identity.printing_id)<0)identity=previous;
            }
            result.put(key, identity);
        }
        for (String key : ambiguousEntries) result.get(key).deck_entry_id = null;
        // Different Oracle identities remain ambiguous and must never be guessed.
        for (String key : ambiguousArtwork) result.remove(key);
        return result;
    }
    public static CardIdentity observationArtwork(JsonObject row){
        String path=System.getProperty("manaforge.publicArtwork");if(path==null)return null;
        try{
            JsonObject manifest=JsonParser.parseString(new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(path)),java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
            JsonObject resolver=manifest.getAsJsonObject("resolver");if(resolver==null || !"127.0.0.1".equals(resolver.get("host").getAsString()))return null;
            JsonObject request=new JsonObject();request.addProperty("action","resolve_printing");request.add("key",resolver.get("key"));request.add("session_id",manifest.get("session_id"));request.add("viewer_id",manifest.get("viewer_id"));
            for(String field:new String[]{"name","set","number"})if(row.has(field))request.add(field,row.get(field));
            try(java.net.Socket socket=new java.net.Socket()){
                socket.connect(new java.net.InetSocketAddress("127.0.0.1",resolver.get("port").getAsInt()),3000);socket.setSoTimeout(5000);
                manaforge.protocol.TextFrame.write(socket.getOutputStream(),request.toString());JsonObject response=manaforge.protocol.WireEnvelope.parseObject(manaforge.protocol.TextFrame.read(socket.getInputStream()));
                if(response.has("unavailable"))return null;CardIdentity identity=new CardIdentity();identity.oracle_id=response.get("oracle_id").getAsString();identity.printing_id=response.get("printing_id").getAsString();return identity;
            }
        }catch(Exception missing){return null;}
    }
    private static final Map<String,CardIdentity> tokenArtwork=new HashMap<>();
    public static synchronized CardIdentity tokenArtwork(JsonObject row) {
        String path=System.getProperty("manaforge.publicArtwork");if(path==null)return null;
        String object=row.get("id").getAsString();if(tokenArtwork.containsKey(object))return tokenArtwork.get(object);
        if(tokenArtwork.size()>=4096)return null;
        try {
            JsonObject manifest=JsonParser.parseString(new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(path)),java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
            JsonObject resolver=manifest.getAsJsonObject("resolver");if(resolver==null || !"127.0.0.1".equals(resolver.get("host").getAsString()))return null;
            JsonObject request=new JsonObject();request.addProperty("action","resolve_token");request.add("key",resolver.get("key"));request.add("session_id",manifest.get("session_id"));request.add("viewer_id",manifest.get("viewer_id"));
            for(String field:new String[]{"name","type","power","toughness","color"})request.add(field,row.has("token_"+field)?row.get("token_"+field):row.get(field));
            try(java.net.Socket socket=new java.net.Socket()) {
                socket.connect(new java.net.InetSocketAddress("127.0.0.1",resolver.get("port").getAsInt()),3000);socket.setSoTimeout(15000);
                manaforge.protocol.TextFrame.write(socket.getOutputStream(),request.toString());
                JsonObject response=manaforge.protocol.WireEnvelope.parseObject(manaforge.protocol.TextFrame.read(socket.getInputStream()));
                if(response.has("unavailable"))return null;
                CardIdentity identity=new CardIdentity();identity.printing_id=response.get("printing_id").getAsString();identity.oracle_id=response.get("oracle_id").getAsString();tokenArtwork.put(object,identity);return identity;
            }
        }catch(Exception unavailable){return null;}
    }
}

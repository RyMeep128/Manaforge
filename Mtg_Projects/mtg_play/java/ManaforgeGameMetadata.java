import com.google.gson.*;
import java.lang.reflect.Field;
import java.util.*;
import mage.game.Game;
import mage.game.GameState;
import mage.players.Player;
import mage.server.game.GameController;
import mage.server.managers.ManagerFactory;
import mage.view.*;
import mage.watchers.common.CommanderInfoWatcher;
import mage.watchers.common.CommanderPlaysCountWatcher;
import org.jboss.remoting.transport.Connector;

/** Narrow, pinned access to metadata omitted by XMage's serializable client views.
 * Never exports a Game, Card, library, hand, or unrestricted object collection.
 * The human response monitor keeps the engine game thread paused during the read.
 */
public final class ManaforgeGameMetadata {
    // Retain only bounded authorized game references so monotonic terminal flags survive controller removal.
    private static final Map<UUID,Game> recentGames=Collections.synchronizedMap(new LinkedHashMap<UUID,Game>() {
        protected boolean removeEldestEntry(Map.Entry<UUID,Game> eldest){return size()>32;}
    });
    private static JsonObject terminal(Game game,UUID gameId,UUID viewerId) {
        JsonObject result=status("finished");Player viewer=game.getPlayer(viewerId);
        if(viewer!=null && viewer.getClass().getName().equals("manaforge.payment.xmage.ContextHumanPlayer"))try {
            Object execution=viewer.getClass().getMethod("paymentExecution",Game.class,UUID.class,int.class).invoke(viewer,game,viewerId,game.getState().getApplyEffectsCounter());
            if(execution instanceof JsonObject)result.add("payment_execution",(JsonObject)execution);
        }catch(ReflectiveOperationException unavailable){ /* A terminal result is still valid without payment evidence. */ }
        if(game.hasEnded() && viewer!=null){String outcome=game.isADraw()?"draw":viewer.hasWon()?"win":viewer.hasLost()?"loss":null;
            if(outcome!=null){result.addProperty("game_id",gameId.toString());result.addProperty("viewer",viewerId.toString());result.addProperty("outcome",outcome);}}
        if(result.has("outcome")){GameState state=game.getState();int cycle=state.getApplyEffectsCounter();List<UUID> seats=new ArrayList<>(game.getPlayers().keySet());JsonObject commanderData=publicCommanders(game,state,seats);JsonArray players=new JsonArray();for(UUID seat:seats){Player player=game.getPlayer(seat);JsonObject row=new JsonObject();row.addProperty("id",seat.toString());row.addProperty("life",player.getLife());row.addProperty("lost",player.hasLost());players.add(row);}if(game.getState()==state && state.getApplyEffectsCounter()==cycle){result.add("commanders",commanderData.get("commanders"));result.add("commander_metadata_complete",commanderData.get("commander_metadata_complete"));result.add("public_players",players);result.addProperty("cycle",cycle);}}
        return result;
    }
    private static JsonObject publicCommanders(Game game,GameState state,Collection<UUID> seats) {
        JsonArray commanders=new JsonArray();int commanderCount=0;CommanderPlaysCountWatcher plays=state.getWatcher(CommanderPlaysCountWatcher.class);
        for(UUID seat:seats){Player current=game.getPlayer(seat);if(current==null)continue;
                    for (UUID commander : current.getCommandersIds()) {
                        commanderCount++;
                        CommanderInfoWatcher damage = state.getWatcher(CommanderInfoWatcher.class, commander);
                        if (damage == null) continue; // signature spells and unsupported designations are not guessed.
                        JsonObject info = new JsonObject(); info.addProperty("id", commander.toString());
                        info.addProperty("owner", current.getId().toString());
                        mage.cards.Card source = game.getCard(commander);
                        if (source != null) {
                            info.addProperty("name", source.getName());
                            info.addProperty("set", source.getExpansionSetCode());
                            info.addProperty("number", source.getCardNumber());
                            if (source.getSpellAbility() != null && plays != null) {
                                // Ask XMage to calculate its commander-only increase on an
                                // isolated ability copy. Never duplicate the tax formula.
                                mage.abilities.SpellAbility probe = source.getSpellAbility().copy();
                                probe.clearManaCostsToPay();
                                source.commanderCost(game, null, probe);
                                info.addProperty("tax", probe.getManaCostsToPay().getText());
                            }
                        }
                        if (plays != null) info.addProperty("plays", plays.getPlaysCount(commander));
                        JsonObject dealt = new JsonObject();
                        for (UUID target : seats)
                            dealt.addProperty(target.toString(), damage.getDamageToPlayer().getOrDefault(target, 0));
                        info.add("damage", dealt); commanders.add(info);
                    }
        }
        JsonObject result=new JsonObject();result.add("commanders",commanders);result.addProperty("commander_metadata_complete",commanders.size()==commanderCount);return result;
    }
    private static Object field(Object target, Class<?> owner, String name) throws Exception {
        Field member = owner.getDeclaredField(name);
        member.setAccessible(true);
        return member.get(target);
    }

    private static ManagerFactory managers() throws Exception {
        Object server = field(null, mage.server.Main.class, "server");
        Connector connector = (Connector) field(server, server.getClass(), "connector");
        for (org.jboss.remoting.ServerInvocationHandler handler : connector.getInvocationHandlers()) {
            if (handler.getClass().getName().equals("mage.server.Main$MageServerInvocationHandler")) {
                return (ManagerFactory) field(handler, handler.getClass(), "managerFactory");
            }
        }
        throw new ReflectiveOperationException("PINNED_METADATA_INTERFACE_CHANGED");
    }

    private static JsonObject status(String status) {
        JsonObject result = new JsonObject(); result.addProperty("status", status); return result;
    }

    private static void cards(Set<UUID> ids, CardsView cards) {
        if (cards != null) for (CardView card : cards.values()) if (card.getId() != null) ids.add(card.getId());
    }

    private static void known(Set<UUID> ids, Collection<? extends CardView> cards) {
        for (CardView card : cards) if (!card.isFaceDown() && !card.hideInfo()) ids.add(card.getId());
    }

    public static JsonObject read(JsonObject command) throws Exception {
        UUID gameId = UUID.fromString(command.get("game").getAsString());
        UUID playerId = UUID.fromString(command.get("player").getAsString());
        int cycle = command.get("cycle").getAsInt();
        GameController controller = managers().gameManager().getGameController().get(gameId);
        Game game=controller==null?recentGames.get(gameId):(Game)field(controller,GameController.class,"game");
        if(game==null)return status("finished");
        Player viewer=game.getPlayer(playerId);if(viewer==null)return status("unauthorized");recentGames.put(gameId,game);if(controller==null && !game.hasEnded())return status("finished");
        return readPaused(game,playerId,cycle,command,()->controller.getGameView(playerId));
    }
    /** Server-owned game capability only; never a wire endpoint or caller-supplied game ID lookup. */
    static JsonObject readPaused(Game game,UUID playerId,int cycle,JsonObject command,java.util.function.Supplier<GameView> views) throws Exception {
        UUID gameId=game.getId();Player viewer=game.getPlayer(playerId);if(viewer==null)return status("unauthorized");
        // Terminal flags are monotonic. A departed viewer has no fresh cycle,
        // even when there is no remaining human response monitor to acquire.
        if (game.hasEnded() || (viewer != null && (viewer.hasLost() || viewer.hasLeft())))
            return terminal(game,gameId,playerId);
        // HumanPlayer.waitForResponse holds no game work while its response monitor
        // is acquired with responseOpenedForAnswer=true. No game-state mutation or
        // feedback is performed here. Reject mismatched cycles instead of guessing.
        for (Player player : game.getPlayers().values()) {
            // A departed HumanPlayer can retain an open response flag. Its
            // monitor no longer pauses the game thread and cannot guard a read.
            if (player.hasLost() || player.hasLeft()) continue;
            Object human = player.getRealPlayer();
            Class<?> type = human.getClass();
            boolean paymentProbe=type.getName().equals("manaforge.payment.xmage.ContextHumanPlayer");
            Class<?> humanType=paymentProbe?type.getSuperclass():type;
            if (!humanType.getName().equals("mage.player.human.HumanPlayer")) continue;
            Object response = field(human, humanType, "response");
            synchronized (response) {
                if (!Boolean.TRUE.equals(field(human, humanType, "responseOpenedForAnswer"))) continue;
                // Eliminated seats stop receiving fresh views while other seats
                // continue playing. Their last cycle cannot become current again.
                if (game.hasEnded() || (viewer != null && (viewer.hasLost() || viewer.hasLeft())))
                    return terminal(game,gameId,playerId);
                GameView permitted = views.get();
                GameState state = game.getState();
                if (permitted == null || permitted.getGameCycle() != cycle) return status("retry");
                if (permitted.getMyPlayer() == null || !permitted.getMyPlayer().getPlayerId().equals(playerId))
                    return status("unauthorized");
                if (state.getApplyEffectsCounter() != cycle) {
                    // Concessions can advance live state after the current prompt's
                    // view was sent. Do not join card metadata from another cycle,
                    // or block the very response needed to advance the game.
                    JsonObject result = status("view_only");
                    JsonArray players = new JsonArray();
                    for (PlayerView view : permitted.getPlayers()) {
                        Player current = game.getPlayer(view.getPlayerId());
                        JsonObject row = new JsonObject(); row.addProperty("id", current.getId().toString());
                        row.addProperty("lost", current.hasLost()); row.addProperty("left", current.hasLeft());
                        players.add(row);
                    }
                    result.add("players", players);
                    return result;
                }
                Set<UUID> visible = new HashSet<>();
                cards(visible, permitted.getMyHand()); cards(visible, permitted.getStack());
                for (PlayerView view : permitted.getPlayers()) {
                    visible.addAll(view.getBattlefield().keySet()); cards(visible, view.getGraveyard());
                    for (CommandObjectView object : view.getCommandObjectList()) if (object instanceof CommanderView) visible.add(object.getId());
                }
                for (ExileView zone : permitted.getExile()) cards(visible, zone);
                for (RevealedView zone : permitted.getRevealed()) cards(visible, zone.getCards());
                for (LookedAtView zone : permitted.getLookedAt()) visible.addAll(zone.getCards().keySet());
                Set<UUID> identified = new HashSet<>();
                known(identified, permitted.getMyHand().values()); known(identified, permitted.getStack().values());
                for (PlayerView view : permitted.getPlayers()) {
                    known(identified, view.getBattlefield().values()); known(identified, view.getGraveyard().values());
                    for (CommandObjectView object : view.getCommandObjectList())
                        if (object instanceof CommanderView) known(identified, Collections.singletonList((CardView) object));
                }
                for (ExileView zone : permitted.getExile()) known(identified, zone.values());
                Set<UUID> requested = new HashSet<>(), requestedIdentified = new HashSet<>();
                for (JsonElement value : command.getAsJsonArray("object_ids")) requested.add(UUID.fromString(value.getAsString()));
                for (JsonElement value : command.getAsJsonArray("identified_ids")) requestedIdentified.add(UUID.fromString(value.getAsString()));
                if (!visible.containsAll(requested)) return status("retry");
                Set<UUID> publicArtworkSources=new HashSet<>(identified);
                Set<UUID> permittedTargets=new HashSet<>(visible);for(PlayerView seat:permitted.getPlayers())permittedTargets.add(seat.getPlayerId());visible.retainAll(requested); identified.retainAll(requestedIdentified);
                JsonObject objects = new JsonObject();
                for (UUID id : visible) {
                    JsonObject metadata = new JsonObject();
                    metadata.addProperty("incarnation", state.getZoneChangeCounter(id));
                    mage.cards.Card source = game.getCard(id);
                    mage.game.permanent.Permanent permanent = game.getPermanent(id);
                    mage.game.stack.StackObject stacked = game.getStack().getStackObject(id);
                    // A spell has its own stack ID; its physical card retains the source ID.
                    if (source == null && stacked != null)
                        source = game.getCard(stacked.getSourceId());
                    UUID owner = source == null ? null : source.getOwnerId();
                    UUID control = permanent != null ? permanent.getControllerId() : stacked == null ? null : stacked.getControllerId();
                    if (stacked != null && stacked.getSourceId() != null) metadata.addProperty("source", stacked.getSourceId().toString());
                    if (identified.contains(id)) {
                        // An ability borrows artwork only from a source whose identity
                        // is independently visible to this viewer in the same context.
                        if(stacked instanceof mage.game.stack.StackAbility && source!=null
                                && publicArtworkSources.contains(source.getId())){
                            metadata.addProperty("ability_art_set",source.getExpansionSetCode());
                            metadata.addProperty("ability_art_number",source.getCardNumber());
                        }
                        if(stacked instanceof mage.game.stack.Spell && source!=null) {
                            metadata.addProperty("source_incarnation",state.getZoneChangeCounter(stacked.getSourceId()));
                            JsonArray spellAbilities=new JsonArray();
                            for(mage.abilities.SpellAbility ability:((mage.game.stack.Spell)stacked).getSpellAbilities())spellAbilities.add(ability.getId().toString());
                            metadata.add("spell_ability_ids",spellAbilities);
                        }
                        if(stacked!=null && stacked.getStackAbility()!=null){JsonArray targets=new JsonArray();boolean complete=true;List<UUID> selectedTargets=new ArrayList<>();for(mage.abilities.Ability ability:stacked instanceof mage.game.stack.Spell?((mage.game.stack.Spell)stacked).getSpellAbilities():Collections.singletonList(stacked.getStackAbility()))for(mage.target.Target target:ability.getTargets())if(!target.isNotTarget())selectedTargets.addAll(target.getTargets());if(selectedTargets.size()>256)complete=false;else for(UUID target:selectedTargets)if(target!=null && permittedTargets.contains(target))targets.add(target.toString());else complete=false;metadata.add("stack_targets",targets);metadata.addProperty("stack_targets_complete",complete);}
                        mage.MageObject live = permanent != null ? permanent : stacked != null ? stacked : source;
                        if (live != null) metadata.addProperty("name", live.getName());
                        if (permanent != null) {
                            JsonArray abilities = new JsonArray();
                            for (mage.abilities.Ability ability : permanent.getAbilities(game)) abilities.add(ability.getRule(permanent.getName()));
                            metadata.add("live_abilities", abilities);
                        }
                    }
                    if (permanent != null && permanent.isCopy() && permanent.getCopyFrom() instanceof mage.game.permanent.Permanent) {
                        mage.MageObject copied = permanent.getCopyFrom();
                        if (identified.contains(copied.getId()) && visible.contains(copied.getId())
                                && copied.getZoneChangeCounter(game) == state.getZoneChangeCounter(copied.getId()))
                            metadata.addProperty("copy_source", copied.getId().toString());
                    }
                    if (source != null && identified.contains(id) && (stacked==null || stacked instanceof mage.game.stack.Spell || publicArtworkSources.contains(source.getId()))) {
                        mage.cards.Card original = source.getMainCard();
                        // Private physical-card correlation across a native double-face zone transition.
                        metadata.addProperty("main_card",original.getId().toString());metadata.addProperty("main_card_incarnation",state.getZoneChangeCounter(original.getId()));
                        metadata.addProperty("physical_set", original.getExpansionSetCode());
                        metadata.addProperty("physical_number", original.getCardNumber());
                    }
                    if (owner != null) metadata.addProperty("owner", owner.toString());
                    if (control != null) metadata.addProperty("controller", control.toString());
                    objects.add(id.toString(), metadata);
                }
                JsonArray players=new JsonArray();List<UUID> publicSeats=new ArrayList<>();
                for(PlayerView view:permitted.getPlayers()){Player current=game.getPlayer(view.getPlayerId());JsonObject row=new JsonObject();row.addProperty("id",current.getId().toString());row.addProperty("life",current.getLife());row.addProperty("lost",current.hasLost());row.addProperty("left",current.hasLeft());players.add(row);publicSeats.add(current.getId());}
                JsonObject commanderData=publicCommanders(game,state,publicSeats);
                if (game.getState() != state || state.getApplyEffectsCounter() != cycle) return status("retry");
                // Confirm the engine is waiting in HumanPlayer.priority(), not a
                // generic GAME_SELECT choice. Never export the diagnostic string.
                Object activeAction = response.getClass().getMethod("getActiveAction").invoke(response);
                boolean priorityOpen = player.getId().equals(playerId)
                        && playerId.equals(game.getPriorityPlayerId())
                        && activeAction instanceof String
                        && ((String) activeAction).startsWith("priority - HumanPlayer.java:");
                JsonObject result = status("ok"); result.addProperty("cycle", cycle);
                result.addProperty("priority_open", priorityOpen);
                // Match the pinned HumanPlayer selection branches under the same response monitor.
                // Native requirement effects still decide whether an attacker click can remove it.
                String declaration=activeAction instanceof String && ((String)activeAction).startsWith("selectAttackers - HumanPlayer.java:")?"attackers":activeAction instanceof String && ((String)activeAction).startsWith("selectBlockers - HumanPlayer.java:")?"blockers":null;
                if(declaration!=null && player.getId().equals(playerId) && game.getStack().isEmpty()) {
                    JsonArray reselect=new JsonArray();
                    for(UUID id:permitted.getMyPlayer().getBattlefield().keySet()) {
                        mage.game.permanent.Permanent permanent=game.getPermanent(id);
                        if(permanent!=null && (declaration.equals("attackers")?new mage.filter.common.FilterAttackingCreature().match(permanent,playerId,null,game):new mage.filter.common.FilterBlockingCreature().match(permanent,playerId,null,game)))reselect.add(id.toString());
                    }
                    if(reselect.size()>256)return status("retry");
                    result.addProperty("combat_reselect_kind",declaration);result.add("combat_reselect",reselect);
                }

                if(paymentProbe && player.getId().equals(playerId)) {
                    Object probe=type.getMethod("paymentProbe",Game.class,UUID.class,int.class,UUID[].class)
                        .invoke(human,game,playerId,cycle,visible.toArray(new UUID[0]));
                    if(probe instanceof JsonObject)result.add("payment_probe",(JsonObject)probe);
                    List<UUID> ordinarySources=new ArrayList<>();boolean ordinaryVisible=true;for(CardView source:permitted.getMyPlayer().getBattlefield().values()){if(!source.isFaceDown() && !source.hideInfo())ordinarySources.add(source.getId());}
                    Object assessment=ordinaryVisible?type.getMethod("ordinaryPayment",Game.class,UUID.class,int.class,UUID[].class).invoke(human,game,playerId,cycle,ordinarySources.toArray(new UUID[0])):null;
                    if(assessment instanceof JsonObject)result.add("ordinary_payment",(JsonObject)assessment);
                    Object execution=type.getMethod("paymentExecution",Game.class,UUID.class,int.class).invoke(human,game,playerId,cycle);
                    if(execution instanceof JsonObject)result.add("payment_execution",(JsonObject)execution);

                }
                if(paymentProbe && player.getId().equals(playerId)){Object targetProbe=type.getMethod("targetingProbe",Game.class,UUID.class,int.class).invoke(human,game,playerId,cycle);if(targetProbe instanceof JsonObject)result.add("targeting_context",(JsonObject)targetProbe);}
                result.add("objects", objects); result.add("players", players); result.add("commanders", commanderData.get("commanders"));result.add("commander_metadata_complete",commanderData.get("commander_metadata_complete"));
                return result;
            }
        }
        return game.hasEnded() ? terminal(game,gameId,playerId) : status("retry");
    }
}

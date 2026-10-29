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
        if (controller == null) return status("finished");
        Game game = (Game) field(controller, GameController.class, "game");
        Player viewer = game.getPlayer(playerId);
        // Terminal flags are monotonic. A departed viewer has no fresh cycle,
        // even when there is no remaining human response monitor to acquire.
        if (game.hasEnded() || (viewer != null && (viewer.hasLost() || viewer.hasLeft())))
            return status("finished");
        // HumanPlayer.waitForResponse holds no game work while its response monitor
        // is acquired with responseOpenedForAnswer=true. No game-state mutation or
        // feedback is performed here. Reject mismatched cycles instead of guessing.
        for (Player player : game.getPlayers().values()) {
            // A departed HumanPlayer can retain an open response flag. Its
            // monitor no longer pauses the game thread and cannot guard a read.
            if (player.hasLost() || player.hasLeft()) continue;
            Object human = player.getRealPlayer();
            Class<?> type = human.getClass();
            if (!type.getName().equals("mage.player.human.HumanPlayer")) continue;
            Object response = field(human, type, "response");
            synchronized (response) {
                if (!Boolean.TRUE.equals(field(human, type, "responseOpenedForAnswer"))) continue;
                // Eliminated seats stop receiving fresh views while other seats
                // continue playing. Their last cycle cannot become current again.
                if (game.hasEnded() || (viewer != null && (viewer.hasLost() || viewer.hasLeft())))
                    return status("finished");
                GameView permitted = controller.getGameView(playerId);
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
                visible.retainAll(requested); identified.retainAll(requestedIdentified);
                JsonObject objects = new JsonObject();
                for (UUID id : visible) {
                    JsonObject metadata = new JsonObject();
                    metadata.addProperty("incarnation", state.getZoneChangeCounter(id));
                    mage.cards.Card source = game.getCard(id);
                    mage.game.permanent.Permanent permanent = game.getPermanent(id);
                    UUID owner = source == null ? null : source.getOwnerId();
                    mage.game.stack.StackObject stacked = game.getStack().getStackObject(id);
                    UUID control = permanent != null ? permanent.getControllerId() : stacked == null ? null : stacked.getControllerId();
                    if (stacked != null && stacked.getSourceId() != null) metadata.addProperty("source", stacked.getSourceId().toString());
                    if (identified.contains(id)) {
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
                    if (source != null && identified.contains(id)) {
                        mage.cards.Card original = source.getMainCard();
                        metadata.addProperty("physical_set", original.getExpansionSetCode());
                        metadata.addProperty("physical_number", original.getCardNumber());
                    }
                    if (owner != null) metadata.addProperty("owner", owner.toString());
                    if (control != null) metadata.addProperty("controller", control.toString());
                    objects.add(id.toString(), metadata);
                }
                JsonArray players = new JsonArray(), commanders = new JsonArray();
                CommanderPlaysCountWatcher plays = state.getWatcher(CommanderPlaysCountWatcher.class);
                for (PlayerView view : permitted.getPlayers()) {
                    Player current = game.getPlayer(view.getPlayerId());
                    JsonObject row = new JsonObject(); row.addProperty("id", current.getId().toString());
                    row.addProperty("lost", current.hasLost()); row.addProperty("left", current.hasLeft());
                    players.add(row);
                    for (UUID commander : current.getCommandersIds()) {
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
                        for (PlayerView target : permitted.getPlayers())
                            dealt.addProperty(target.getPlayerId().toString(), damage.getDamageToPlayer().getOrDefault(target.getPlayerId(), 0));
                        info.add("damage", dealt); commanders.add(info);
                    }
                }
                if (game.getState() != state || state.getApplyEffectsCounter() != cycle) return status("retry");
                JsonObject result = status("ok"); result.addProperty("cycle", cycle);
                result.add("objects", objects); result.add("players", players); result.add("commanders", commanders);
                return result;
            }
        }
        return game.hasEnded() ? status("finished") : status("retry");
    }
}

import java.lang.reflect.Field;
import java.util.*;
import java.util.function.Supplier;
import mage.game.Game;
import mage.game.GameState;
import mage.game.permanent.Permanent;
import mage.players.Player;
import mage.view.*;

/** Read-only adapter using the same native response-monitor boundary as metadata. */
final class NativeBattlefieldIdentity {
    private NativeBattlefieldIdentity(){}
    interface Capture<T> {T capture(Map<UUID,GameView> views) throws Exception;}
    static final class Batch<T> {
        final Map<UUID,BattlefieldIdentityRegistry.Snapshot> identities;final T value;
        private Batch(Map<UUID,BattlefieldIdentityRegistry.Snapshot> identities,T value){this.identities=Collections.unmodifiableMap(new HashMap<>(identities));this.value=value;}
    }
    /** Views, native observations and callback projection share one response-monitor checkpoint. */
    static <T> Batch<T> captureBatchPaused(Game game,Collection<UUID> viewers,Capture<T> capture) throws Exception {
        if(viewers.isEmpty() || new HashSet<>(viewers).size()!=viewers.size())throw new IllegalArgumentException("IDENTITY_VIEWERS");
        for(Player player:game.getPlayers().values()){
            if(player.hasLost() || player.hasLeft())continue;Object human=player.getRealPlayer();Class<?> type=human.getClass();
            while(type!=null && !type.getName().equals("mage.player.human.HumanPlayer"))type=type.getSuperclass();if(type==null)continue;
            Field response=type.getDeclaredField("response"),opened=type.getDeclaredField("responseOpenedForAnswer");response.setAccessible(true);opened.setAccessible(true);
            synchronized(response.get(human)){
                if(!Boolean.TRUE.equals(opened.get(human)))continue;GameState state=game.getState();int cycle=state.getApplyEffectsCounter();
                Map<UUID,GameView> views=new LinkedHashMap<>();Map<UUID,BattlefieldIdentityRegistry.Snapshot> snapshots=new LinkedHashMap<>();
                for(UUID viewer:viewers){GameView view=new GameView(state,game,viewer,null);views.put(viewer,view);snapshots.put(viewer,capturePaused(game,viewer,cycle,()->view));}
                T value=capture.capture(Collections.unmodifiableMap(views));
                if(game.getState()!=state || state.getApplyEffectsCounter()!=cycle)throw new IllegalArgumentException("IDENTITY_CYCLE");return new Batch<>(snapshots,value);
            }
        }
        throw new IllegalStateException("IDENTITY_NOT_PAUSED");
    }
    static BattlefieldIdentityRegistry.Snapshot capturePaused(Game game,UUID viewer,int cycle,Supplier<GameView> views) throws Exception {
        Player owner=game.getPlayer(viewer);
        if(owner==null || owner.hasLost() || owner.hasLeft() || game.hasEnded())throw new IllegalArgumentException("IDENTITY_VIEWER");
        for(Player player:game.getPlayers().values()){
            if(player.hasLost() || player.hasLeft())continue;
            Object human=player.getRealPlayer();Class<?> type=human.getClass();
            // HumanPlayer is a server plugin, absent from the ordinary bridge SDK.
            // Mirror metadata's server-owned reflection without linking that plugin.
            while(type!=null && !type.getName().equals("mage.player.human.HumanPlayer"))type=type.getSuperclass();
            if(type==null)continue;
            Field response=type.getDeclaredField("response"),opened=type.getDeclaredField("responseOpenedForAnswer");response.setAccessible(true);opened.setAccessible(true);
            synchronized(response.get(human)){
                if(!Boolean.TRUE.equals(opened.get(human)))continue;
                GameState state=game.getState();GameView view=views.get();
                if(view==null || view.getMyPlayer()==null || !viewer.equals(view.getMyPlayer().getPlayerId()) || view.getGameCycle()!=cycle || state.getApplyEffectsCounter()!=cycle)throw new IllegalArgumentException("IDENTITY_CYCLE");
                List<BattlefieldIdentityRegistry.Observation> objects=new ArrayList<>();Map<UUID,String> admitted=new HashMap<>();
                for(Permanent permanent:game.getBattlefield().getAllPermanents()){
                    int generation=permanent.getZoneChangeCounter(game);
                    if(generation<0 || generation!=state.getZoneChangeCounter(permanent.getId()))throw new IllegalArgumentException("IDENTITY_GENERATION");
                    objects.add(new BattlefieldIdentityRegistry.Observation(permanent.getId(),generation,permanent.getControllerId(),!permanent.isFaceDown(game)));
                }
                Set<UUID> ids=new HashSet<>();for(BattlefieldIdentityRegistry.Observation object:objects)ids.add(object.nativeId);
                for(PlayerView seat:view.getPlayers())for(CardView card:seat.getBattlefield().values())if(ids.contains(card.getId()) && !card.isFaceDown() && !card.hideInfo())admitted.put(card.getId(),card.getId().toString());
                if(state!=game.getState() || state.getApplyEffectsCounter()!=cycle)throw new IllegalArgumentException("IDENTITY_CYCLE");
                return new BattlefieldIdentityRegistry.Snapshot(game.getId(),viewer,cycle,game.getPlayers().keySet(),objects,admitted);
            }
        }
        throw new IllegalStateException("IDENTITY_NOT_PAUSED");
    }
}

import java.lang.reflect.Field;
import java.util.*;
import java.util.function.Supplier;
import mage.game.Game;
import mage.game.GameState;
import mage.game.permanent.Permanent;
import mage.player.human.HumanPlayer;
import mage.players.Player;
import mage.view.*;

/** Read-only adapter using the same native response-monitor boundary as metadata. */
final class NativeBattlefieldIdentity {
    private NativeBattlefieldIdentity(){}
    static BattlefieldIdentityRegistry.Snapshot capturePaused(Game game,UUID viewer,int cycle,Supplier<GameView> views) throws Exception {
        Player owner=game.getPlayer(viewer);
        if(owner==null || owner.hasLost() || owner.hasLeft() || game.hasEnded())throw new IllegalArgumentException("IDENTITY_VIEWER");
        Field response=HumanPlayer.class.getDeclaredField("response"),opened=HumanPlayer.class.getDeclaredField("responseOpenedForAnswer");response.setAccessible(true);opened.setAccessible(true);
        for(Player player:game.getPlayers().values()){
            if(player.hasLost() || player.hasLeft() || !(player.getRealPlayer() instanceof HumanPlayer))continue;
            Object human=player.getRealPlayer();
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

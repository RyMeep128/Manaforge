package manaforge.payment.xmage;

import com.google.gson.*;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;
import mage.game.Game;
import mage.players.Player;
import mage.players.PlayerImpl;
import mage.player.ai.ComputerPlayer7;

/** Owned-server controller handoff. All live player state work runs on the game thread.
 * No client answers, concession, control-changing effects or new player identities. */
public final class NativeMatchRecovery {
    private NativeMatchRecovery() {}
    private static final Map<UUID,Gate> games=new ConcurrentHashMap<>();
    private static final class Gate {
        boolean paused,parked,enabled;UUID ai;RecoveryHumanPlayer waiting;Game game;
    }
    static final class Handoff extends RuntimeException {private static final long serialVersionUID=1L;}
    static boolean ai(Game game,UUID player){Gate gate=games.get(game.getId());if(gate==null || game.isSimulation())return false;synchronized(gate){return player.equals(gate.ai);}}
    static void boundary(RecoveryHumanPlayer player,Game game) {
        if(game.isSimulation())return;
        Gate gate=games.computeIfAbsent(game.getId(),id->new Gate());
        synchronized(gate){
            if(!gate.enabled)return;
            gate.game=game;
            if(gate.paused){gate.parked=true;gate.waiting=player;game.pauseTimer(player.getTurnControlledBy());gate.notifyAll();}
            while(gate.paused){
                try{gate.wait(100);}catch(InterruptedException stopped){Thread.currentThread().interrupt();throw new IllegalStateException("RECOVERY_STOPPED");}
            }
            gate.parked=false;gate.waiting=null;
        }
    }
    /** Trusted stdin owner only. Never exposed on the viewer metadata channel. */
    public static JsonObject control(UUID gameId,String action,UUID seat) {
        Gate gate=games.get(gameId);JsonObject result=new JsonObject();
        if(gate==null){result.addProperty("ready",false);return result;}
        RecoveryHumanPlayer wake;
        synchronized(gate){
            gate.enabled=true;
            if(gate.game==null)for(RecoveryHumanPlayer human:RecoveryHumanPlayer.live(gameId))if(human.recoveryGame()!=null){gate.game=human.recoveryGame();break;}
            if(action.equals("pause"))gate.paused=true;
            else if(action.equals("ai") || action.equals("human")){
                if(!gate.paused || !gate.parked)throw new IllegalStateException("RECOVERY_NOT_PAUSED");
                gate.ai=action.equals("ai")?Objects.requireNonNull(seat):null;
            }else if(action.equals("resume")){
                if(!gate.parked)throw new IllegalStateException("RECOVERY_NOT_READY");
                gate.paused=false;gate.parked=false;gate.notifyAll();
            }else if(!action.equals("status"))throw new IllegalArgumentException("RECOVERY_ACTION_INVALID");
            wake=gate.waiting;
            result.addProperty("ready",gate.parked);result.addProperty("paused",gate.paused);
            result.addProperty("ended",gate.game!=null && gate.game.hasEnded());
        }
        // An existing human response is already a safe pause point. Preserve its native choice.
        if(action.equals("pause"))for(RecoveryHumanPlayer human:RecoveryHumanPlayer.live(gameId))if(human.waitingForResponse())synchronized(gate){if(gate.paused && !gate.parked){gate.parked=true;gate.waiting=human;if(gate.game!=null)gate.game.pauseTimer(human.getTurnControlledBy());}}
        // Wake an abandoned human prompt only when handing it to MAD, with no invented answer.
        boolean wakeAI;synchronized(gate){wakeAI=!gate.paused && wake!=null && wake.getId().equals(gate.ai);if(action.equals("resume") && wake!=null && gate.game!=null)gate.game.resumeTimer(wake.getTurnControlledBy());}
        if((action.equals("resume") || action.equals("status")) && wakeAI)wake.wakeRecovery();
        synchronized(gate){result.addProperty("ready",gate.parked);}
        return result;
    }
    private static void transfer(PlayerImpl from,PlayerImpl to) {
        try{for(Field field:PlayerImpl.class.getDeclaredFields()){
            if(Modifier.isStatic(field.getModifiers()))continue;
            field.setAccessible(true);field.set(to,field.get(from));
        }}catch(ReflectiveOperationException failure){throw new IllegalStateException("RECOVERY_PLAYER_LAYOUT_CHANGED",failure);}
    }
    static <T>T decision(RecoveryHumanPlayer player,Game game,Supplier<T> human,java.util.function.Function<ComputerPlayer7,T> computer) {
        if(game.isSimulation())return human.get();
        player.registerRecovery(game);
        while(true){
            boundary(player,game);
            if(ai(game,player.getId()))break;
            try{return human.get();}catch(Handoff changed){/* The current choice now belongs to MAD; no client answer was invented. */}
        }
        ComputerPlayer7 policy=new ComputerPlayer7(player.getName(),player.getRange(),10);
        transfer(player,policy);setHuman(policy,false);
        Map<UUID,Player> players=game.getPlayers();
        if(players.get(player.getId())!=player)throw new IllegalStateException("RECOVERY_PLAYER_CHANGED");
        players.put(player.getId(),policy);
        try{return computer.apply(policy);}
        finally{transfer(policy,player);setHuman(player,true);players.put(player.getId(),player);}
    }
    private static void setHuman(PlayerImpl player,boolean value){try{Field field=PlayerImpl.class.getDeclaredField("human");field.setAccessible(true);field.setBoolean(player,value);}catch(ReflectiveOperationException failure){throw new IllegalStateException("RECOVERY_PLAYER_LAYOUT_CHANGED",failure);}}
}

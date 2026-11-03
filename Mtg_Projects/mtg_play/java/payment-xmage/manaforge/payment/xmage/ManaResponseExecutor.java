package manaforge.payment.xmage;

import java.util.Objects;
import java.util.UUID;

/** One native payment-source response, not a source planner or payment confirmation.
 * Run on the owned serialized native-response worker, never a renderer or prompt-enqueue callback.
 * The borrowed session remains owned/closed by its parent. */
public final class ManaResponseExecutor {
    public enum Outcome { STALE, SUBMITTED, UNCERTAIN }
    /** Atomically validate and consume this actor's exact GAME_PLAY_MANA decision before IO.
     * Must share the manual/automatic native response authority. No network IO in claim(). */
    public interface Authority {boolean claim(UUID game,int decision,UUID source);}
    public interface Sender {boolean send(UUID game,UUID source) throws Exception;}
    private final Authority authority;private final Sender sender;
    public ManaResponseExecutor(Authority authority,Sender sender) {
        this.authority=Objects.requireNonNull(authority);this.sender=Objects.requireNonNull(sender);
    }
    public Outcome submit(UUID game,int decision,UUID source) {
        if(game==null || source==null || decision<0 || !authority.claim(game,decision,source))return Outcome.STALE;
        // The claim remains consumed for false/exception/fatal outcomes. Never retry this response.
        try{return sender.send(game,source)?Outcome.SUBMITTED:Outcome.UNCERTAIN;}
        catch(InterruptedException failure){Thread.currentThread().interrupt();return Outcome.UNCERTAIN;}
        catch(Exception failure){return Outcome.UNCERTAIN;}
        // Fatal Errors propagate; their consumed native claim still forbids replay.
    }
}

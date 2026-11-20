package manaforge.payment.xmage;
import mage.MageObject;
import mage.abilities.*;
import mage.abilities.costs.mana.ManaCost;
import mage.cards.*;
import mage.choices.Choice;
import mage.constants.*;
import mage.game.Game;
import mage.player.human.HumanPlayer;
import mage.players.Player;
import mage.players.PlayerImpl;
import mage.target.*;
import mage.util.MultiAmountMessage;
import java.io.Serializable;
import java.util.*;
import java.lang.reflect.Field;
import java.lang.ref.WeakReference;
import java.util.concurrent.ConcurrentHashMap;

/** Choice boundary shared by the owned human and native MAD policies. */
public class RecoveryHumanPlayer extends HumanPlayer {
    private static final long serialVersionUID=1L;
    private static final Map<UUID,Map<UUID,WeakReference<RecoveryHumanPlayer>>> live=new ConcurrentHashMap<>();
    public RecoveryHumanPlayer(String name,RangeOfInfluence range,int skill){super(name,range,skill);}
    protected RecoveryHumanPlayer(RecoveryHumanPlayer player){super(player);}
    @Override public RecoveryHumanPlayer copy(){return new RecoveryHumanPlayer(this);}
    @Override public void restore(Player player){super.restore(player);human=true;}
    private transient WeakReference<Game> recoveryGame;
    Game recoveryGame(){return recoveryGame==null?null:recoveryGame.get();}
    void registerRecovery(Game game){recoveryGame=new WeakReference<>(game);live.computeIfAbsent(game.getId(),id->new ConcurrentHashMap<>()).put(getId(),new WeakReference<>(this));}
    static List<RecoveryHumanPlayer> live(UUID game){List<RecoveryHumanPlayer> result=new ArrayList<>();Map<UUID,WeakReference<RecoveryHumanPlayer>> rows=live.get(game);if(rows!=null)for(WeakReference<RecoveryHumanPlayer> ref:rows.values()){RecoveryHumanPlayer player=ref.get();if(player!=null)result.add(player);}return result;}
    void wakeRecovery(){try{Field field=HumanPlayer.class.getDeclaredField("response");field.setAccessible(true);Object response=field.get(this);synchronized(response){response.notifyAll();}}catch(ReflectiveOperationException failure){throw new IllegalStateException("RECOVERY_RESPONSE_LAYOUT_CHANGED",failure);}}
    boolean waitingForResponse(){try{Field responseField=HumanPlayer.class.getDeclaredField("response"),open=HumanPlayer.class.getDeclaredField("responseOpenedForAnswer");responseField.setAccessible(true);open.setAccessible(true);Object response=responseField.get(this);synchronized(response){return Boolean.TRUE.equals(open.get(this));}}catch(ReflectiveOperationException failure){throw new IllegalStateException("RECOVERY_RESPONSE_LAYOUT_CHANGED",failure);}}
    private transient volatile String nativeResponseMethod;
    /** Native HumanPlayer caller, retained while the recovery wrapper adds a stack frame. */
    public final String nativeResponseMethod(){return nativeResponseMethod;}
    @Override protected void waitForResponse(Game game){
        NativeMatchRecovery.boundary(this,game);
        if(NativeMatchRecovery.ai(game,getId()))throw new NativeMatchRecovery.Handoff();
        nativeResponseMethod=null;
        for(StackTraceElement frame:Thread.currentThread().getStackTrace()){
            if(frame.getClassName().equals(HumanPlayer.class.getName())){
                nativeResponseMethod=frame.getMethodName();break;
            }
        }
        try{super.waitForResponse(game);}finally{nativeResponseMethod=null;}
        NativeMatchRecovery.boundary(this,game);
        if(NativeMatchRecovery.ai(game,getId()))throw new NativeMatchRecovery.Handoff();
    }
    @Override public boolean chooseMulligan(Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseMulligan(game),ai->ai.chooseMulligan(game));}
    @Override public boolean chooseUse(Outcome outcome, String message, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseUse(outcome, message, source, game),ai->ai.chooseUse(outcome, message, source, game));}
    @Override public boolean chooseUse(Outcome outcome, String message, String secondMessage, String trueText, String falseText, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseUse(outcome, message, secondMessage, trueText, falseText, source, game),ai->ai.chooseUse(outcome, message, secondMessage, trueText, falseText, source, game));}
    @Override public int chooseReplacementEffect(Map<String, String> effectsMap, Map<String, MageObject> objectsMap, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseReplacementEffect(effectsMap, objectsMap, game),ai->ai.chooseReplacementEffect(effectsMap, objectsMap, game));}
    @Override public boolean choose(Outcome outcome, Choice choice, Game game){return NativeMatchRecovery.decision(this,game,()->super.choose(outcome, choice, game),ai->ai.choose(outcome, choice, game));}
    @Override public boolean choose(Outcome outcome, Target target, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.choose(outcome, target, source, game),ai->ai.choose(outcome, target, source, game));}
    @Override public boolean choose(Outcome outcome, Target target, Ability source, Game game, Map<String, Serializable> options){return NativeMatchRecovery.decision(this,game,()->super.choose(outcome, target, source, game, options),ai->ai.choose(outcome, target, source, game, options));}
    @Override public boolean chooseTarget(Outcome outcome, Target target, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseTarget(outcome, target, source, game),ai->ai.chooseTarget(outcome, target, source, game));}
    @Override public boolean choose(Outcome outcome, Cards cards, TargetCard target, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.choose(outcome, cards, target, source, game),ai->ai.choose(outcome, cards, target, source, game));}
    @Override public boolean chooseTarget(Outcome outcome, Cards cards, TargetCard target, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseTarget(outcome, cards, target, source, game),ai->ai.chooseTarget(outcome, cards, target, source, game));}
    @Override public boolean chooseTargetAmount(Outcome outcome, TargetAmount target, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseTargetAmount(outcome, target, source, game),ai->ai.chooseTargetAmount(outcome, target, source, game));}
    @Override public boolean priority(Game game){return NativeMatchRecovery.decision(this,game,()->super.priority(game),ai->ai.priority(game));}
    @Override public TriggeredAbility chooseTriggeredAbility(java.util.List<TriggeredAbility> abilities, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseTriggeredAbility(abilities, game),ai->ai.chooseTriggeredAbility(abilities, game));}
    @Override public boolean playMana(Ability abilityToCast, ManaCost unpaid, String promptText, Game game){return NativeMatchRecovery.decision(this,game,()->super.playMana(abilityToCast, unpaid, promptText, game),ai->ai.playMana(abilityToCast, unpaid, promptText, game));}
    @Override public int announceRepetitions(Game game){return NativeMatchRecovery.decision(this,game,()->super.announceRepetitions(game),ai->ai.getAmount(0,999,"How many times do you want to repeat your shortcut?",null,game));}
    @Override public int announceX(int min, int max, String message, Game game, Ability source, boolean isManaPay){return NativeMatchRecovery.decision(this,game,()->super.announceX(min, max, message, game, source, isManaPay),ai->ai.announceX(min, max, message, game, source, isManaPay));}
    @Override public void selectAttackers(Game game, UUID attackingPlayerId){NativeMatchRecovery.decision(this,game,()->{super.selectAttackers(game, attackingPlayerId);return null;},ai->{ai.selectAttackers(game, attackingPlayerId);return null;});}
    @Override public void selectBlockers(Ability source, Game game, UUID defendingPlayerId){NativeMatchRecovery.decision(this,game,()->{super.selectBlockers(source, game, defendingPlayerId);return null;},ai->{ai.selectBlockers(source, game, defendingPlayerId);return null;});}
    @Override public int getAmount(int min, int max, String message, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.getAmount(min, max, message, source, game),ai->ai.getAmount(min, max, message, source, game));}
    @Override public List<Integer> getMultiAmountWithIndividualConstraints(Outcome outcome, List<MultiAmountMessage> messages, int totalMin, int totalMax, MultiAmountType type, Game game){return NativeMatchRecovery.decision(this,game,()->super.getMultiAmountWithIndividualConstraints(outcome, messages, totalMin, totalMax, type, game),ai->ai.getMultiAmountWithIndividualConstraints(outcome, messages, totalMin, totalMax, type, game));}
    @Override public SpellAbility chooseAbilityForCast(Card card, Game game, boolean noMana){return NativeMatchRecovery.decision(this,game,()->super.chooseAbilityForCast(card, game, noMana),ai->ai.chooseAbilityForCast(card, game, noMana));}
    @Override public ActivatedAbility chooseLandOrSpellAbility(Card card, Game game, boolean noMana){return NativeMatchRecovery.decision(this,game,()->super.chooseLandOrSpellAbility(card, game, noMana),ai->ai.chooseLandOrSpellAbility(card, game, noMana));}
    @Override public Mode chooseMode(Modes modes, Ability source, Game game){return NativeMatchRecovery.decision(this,game,()->super.chooseMode(modes, source, game),ai->ai.chooseMode(modes, source, game));}
    @Override public boolean choosePile(Outcome outcome, String message, java.util.List<? extends Card> pile1, java.util.List<? extends Card> pile2, Game game){return NativeMatchRecovery.decision(this,game,()->super.choosePile(outcome, message, pile1, pile2, game),ai->ai.choosePile(outcome, message, pile1, pile2, game));}
}

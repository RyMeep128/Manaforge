package manaforge.payment.xmage;

import java.io.Serializable;
import java.util.*;
import mage.abilities.*;
import mage.abilities.costs.mana.ManaCost;
import mage.abilities.mana.ActivatedManaAbilityImpl;
import mage.cards.*;
import mage.choices.Choice;
import mage.constants.*;
import mage.game.Game;
import mage.game.permanent.Permanent;
import mage.player.human.HumanPlayer;
import mage.player.human.PlayerResponse;
import mage.players.*;
import mage.target.*;

/** Isolated copied player. Never borrows the live HumanPlayer response monitor.
 * Any unresolved decision aborts the branch rather than defaulting to the first answer. */
final class PaymentSimulationPlayer extends HumanPlayer {
    private static final long serialVersionUID=1L;
    static final class ChoiceRequired extends RuntimeException {private static final long serialVersionUID=1L;}
    private ManaType color;private final List<String> answers=new ArrayList<>();
    PaymentSimulationPlayer(Player source){super((PlayerImpl)source,new PlayerResponse());}
    @Override public PaymentSimulationPlayer copy(){return new PaymentSimulationPlayer(this);}
    void begin(ManaType color){this.color=color;answers.clear();}
    List<String> recorded(){return new ArrayList<>(answers);}
    Map<UUID,ActivatedManaAbilityImpl> usable(Permanent source,Game game){return getUseableManaAbilities(source,Zone.BATTLEFIELD,game);}
    boolean activate(ActivatedManaAbilityImpl ability,Game game){return playManaAbility((ActivatedManaAbilityImpl)ability.copy(),game);}
    static String answer(Choice choice,ManaType color) {
        if(color==null || !choice.isManaColorChoice())return null;
        String symbol=color==ManaType.WHITE?"W":color==ManaType.BLUE?"U":color==ManaType.BLACK?"B":color==ManaType.RED?"R":color==ManaType.GREEN?"G":"C";
        if(choice.isKeyChoice())for(Map.Entry<String,String> entry:choice.getKeyChoices().entrySet()) {
            String key=entry.getKey(),label=entry.getValue();
            if(key.equalsIgnoreCase(symbol) || label.equalsIgnoreCase(color.name()) || label.equalsIgnoreCase("{"+symbol+"}"))return "key:"+key;
        }
        for(String value:choice.getChoices())if(value.equalsIgnoreCase(color.name()) || value.replace("{","").replace("}","").equalsIgnoreCase(symbol))return "value:"+value;
        return null;
    }
    static boolean apply(Choice choice,String answer) {
        if(answer==null)return false;
        if(answer.startsWith("key:") && choice.isKeyChoice() && choice.getKeyChoices().containsKey(answer.substring(4)))choice.setChoiceByKey(answer.substring(4));
        else if(answer.startsWith("value:") && !choice.isKeyChoice() && choice.getChoices().contains(answer.substring(6)))choice.setChoice(answer.substring(6));
        else return false;
        return choice.isChosen();
    }
    @Override public boolean choose(Outcome outcome,Choice choice,Game game){
        String answer=outcome==Outcome.PutManaInPool?answer(choice,color):null;
        if(!apply(choice,answer))throw new ChoiceRequired();answers.add(answer);return true;
    }
    @Override public boolean chooseUse(Outcome outcome,String message,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean chooseUse(Outcome outcome,String message,String second,String yes,String no,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean choose(Outcome outcome,Target target,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean choose(Outcome outcome,Target target,Ability source,Game game,Map<String,Serializable> options){throw new ChoiceRequired();}
    @Override public boolean choose(Outcome outcome,Cards cards,TargetCard target,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean chooseTarget(Outcome outcome,Target target,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean chooseTarget(Outcome outcome,Cards cards,TargetCard target,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean chooseTargetAmount(Outcome outcome,TargetAmount target,Ability source,Game game){throw new ChoiceRequired();}
    @Override public boolean choosePile(Outcome outcome,String message,List<? extends Card> first,List<? extends Card> second,Game game){throw new ChoiceRequired();}
    @Override public int chooseReplacementEffect(Map<String,String> effects,Map<String,mage.MageObject> objects,Game game){if(effects.size()==1)return Integer.parseInt(effects.keySet().iterator().next());throw new ChoiceRequired();}
    @Override public Mode chooseMode(Modes modes,Ability source,Game game){if(modes.size()==1)return modes.getMode();throw new ChoiceRequired();}
    @Override public List<Integer> getMultiAmountWithIndividualConstraints(Outcome outcome,List<mage.util.MultiAmountMessage> messages,int min,int max,MultiAmountType type,Game game){throw new ChoiceRequired();}
    @Override public int getAmount(int min,int max,String message,Ability source,Game game){if(min==max)return min;throw new ChoiceRequired();}
    @Override public int announceX(int min,int max,String message,Game game,Ability source,boolean manaPay){if(min==max)return min;throw new ChoiceRequired();}
    @Override public boolean playMana(Ability ability,ManaCost unpaid,String message,Game game){throw new ChoiceRequired();}
    @Override public TriggeredAbility chooseTriggeredAbility(List<TriggeredAbility> abilities,Game game){if(abilities.size()==1)return abilities.get(0);throw new ChoiceRequired();}
}

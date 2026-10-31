package manaforge.payment;

import java.util.*;
import mage.Mana;
import mage.abilities.Ability;
import mage.abilities.costs.mana.ManaCostsImpl;
import mage.abilities.mana.*;
import mage.choices.ChoiceColor;
import mage.players.ManaPool;
import mage.players.net.UserData;
import mage.util.ManaUtil;
import manaforge.payment.xmage.SelectedSourceMana;
import manaforge.payment.xmage.ContextHumanPlayer;
import mage.constants.RangeOfInfluence;

/** Real pinned utility objects only. No Game, server, deck, source activation or gameplay claim. */
public final class PinnedPaymentChecks {
    private static int checks;
    private static void check(boolean value){checks++;if(!value)throw new AssertionError("PINNED_PAYMENT_CHECK_"+checks);}
    private static void sourceScopeChecks(ContextHumanPlayer player) throws Exception {
        UUID source=UUID.randomUUID();UUID[] controller={player.getId()};boolean[] present={true};
        mage.game.permanent.Permanent permanent=(mage.game.permanent.Permanent)java.lang.reflect.Proxy.newProxyInstance(
            PinnedPaymentChecks.class.getClassLoader(),new Class<?>[]{mage.game.permanent.Permanent.class},(proxy,method,args)->{
                switch(method.getName()) {
                    case "getId":return source;
                    case "getControllerId":return controller[0];
                    case "canUseActivatedAbilities":return true;
                    case "getAbilities":return new mage.abilities.AbilitiesImpl<Ability>();
                    default:throw new AssertionError("UNEXPECTED_SOURCE_CALL_"+method.getName());
                }
            });
        mage.game.GameState state=new mage.game.GameState();
        mage.game.Game game=(mage.game.Game)java.lang.reflect.Proxy.newProxyInstance(
            PinnedPaymentChecks.class.getClassLoader(),new Class<?>[]{mage.game.Game.class},(proxy,method,args)->{
                switch(method.getName()) {
                    case "getPlayer":return player;
                    case "getPermanent":return present[0] && source.equals(args[0])?permanent:null;
                    case "getState":return state;
                    case "hasEnded":return false;
                    default:throw new AssertionError("UNEXPECTED_GAME_CALL_"+method.getName());
                }
            });
        java.lang.reflect.Field response=mage.player.human.HumanPlayer.class.getDeclaredField("response");response.setAccessible(true);
        java.lang.reflect.Field open=mage.player.human.HumanPlayer.class.getDeclaredField("responseOpenedForAnswer");open.setAccessible(true);
        java.lang.reflect.Field payment=ContextHumanPlayer.class.getDeclaredField("payment");payment.setAccessible(true);
        Class<?> frame=Class.forName("manaforge.payment.xmage.ContextHumanPlayer$Frame");
        java.lang.reflect.Constructor<?> constructor=frame.getDeclaredConstructors()[0];constructor.setAccessible(true);
        payment.set(player,constructor.newInstance(game,new GreenManaAbility(),new ManaCostsImpl<>("{G}"),1L));
        open.set(player,true);player.setPayManaMode(true);
        int cycle=state.getApplyEffectsCounter();int[] calls={0};
        ContextHumanPlayer.SourceInspector<Boolean> inspect=(ability,cost,candidates)->{
            calls[0]++;check(candidates.isEmpty());
            boolean immutable=false;try{candidates.put(UUID.randomUUID(),new GreenManaAbility());}catch(UnsupportedOperationException expected){immutable=true;}
            check(immutable);return true;
        };
        check(player.inspectBattlefieldSource(game,player.getId(),cycle,source,inspect)==null);check(calls[0]==0);
        synchronized(response.get(player)) {
            check(Boolean.TRUE.equals(player.inspectBattlefieldSource(game,player.getId(),cycle,source,inspect)));
            check(player.inspectBattlefieldSource(game,UUID.randomUUID(),cycle,source,inspect)==null);
            check(player.inspectBattlefieldSource(game,player.getId(),cycle+1,source,inspect)==null);
            controller[0]=UUID.randomUUID();check(player.inspectBattlefieldSource(game,player.getId(),cycle,source,inspect)==null);
            controller[0]=player.getId();present[0]=false;check(player.inspectBattlefieldSource(game,player.getId(),cycle,source,inspect)==null);
            present[0]=true;
            check(player.inspectBattlefieldSource(game,player.getId(),cycle,source,(a,c,candidates)->{present[0]=false;return true;})==null);
            present[0]=true;
            check(player.inspectBattlefieldSource(game,player.getId(),cycle,source,(a,c,candidates)->{player.setPayManaMode(false);return true;})==null);
            check(calls[0]==1);
        }
        payment.set(player,null);open.set(player,false);
    }
    public static void main(String[] args) throws Exception {
        ContextHumanPlayer observed=new ContextHumanPlayer("Public fixture",RangeOfInfluence.ALL,0);
        ContextHumanPlayer copied=observed.copy();
        check(copied.getClass()==ContextHumanPlayer.class);check(copied.getId().equals(observed.getId()));
        check(java.lang.reflect.Modifier.isTransient(ContextHumanPlayer.class.getDeclaredField("payment").getModifiers()));
        check(observed.paymentProbe(null,observed.getId(),0)==null);check(copied.paymentProbe(null,copied.getId(),0)==null);
        sourceScopeChecks(observed);
        UserData manual=UserData.getDefaultUserDataView(),automatic=UserData.getDefaultUserDataView();
        check(manual!=automatic);
        manual.setManaPoolAutomatic(false);manual.setManaPoolAutomaticRestricted(false);
        automatic.setManaPoolAutomatic(true);automatic.setManaPoolAutomaticRestricted(true);
        check(!manual.isManaPoolAutomatic() && !manual.isManaPoolAutomaticRestricted());
        check(automatic.isManaPoolAutomatic() && automatic.isManaPoolAutomaticRestricted());
        manual.setManaPoolAutomatic(true);check(automatic.isManaPoolAutomaticRestricted());
        ManaPool pool=new ManaPool(UUID.fromString("00000000-0000-0000-0000-000000000001"));
        pool.setAutoPayment(false);pool.setAutoPaymentRestricted(false);
        check(!pool.isAutoPayment() && !pool.isAutoPaymentRestricted());
        pool.setAutoPayment(true);check(pool.isAutoPayment() && !pool.isAutoPaymentRestricted());
        pool.setAutoPaymentRestricted(true);check(pool.isAutoPaymentRestricted());

        ManaCostsImpl<?> greenCost=new ManaCostsImpl<>("{G}");
        check(greenCost.testPay(Mana.GreenMana(1)));check(!greenCost.testPay(Mana.BlueMana(1)));
        check(!greenCost.testPay(new Mana()));check(!greenCost.isPaid());
        Mana mixed=new Mana();mixed.add(Mana.GreenMana(1));mixed.add(Mana.BlueMana(1));
        check(new ManaCostsImpl<>("{1}{U}").testPay(mixed));
        ManaCostsImpl<?> composite=new ManaCostsImpl<>("{2}{G}");
        check(composite.getMana().count()==3 && mixed.count()==2);
        // Pinned testPay is an ANY-component contribution predicate, NOT whole-cost feasibility.
        check(composite.testPay(mixed));
        mixed.add(Mana.BlueMana(1));check(new ManaCostsImpl<>("{2}{G}").testPay(mixed));

        Map<UUID,ActivatedManaAbilityImpl> abilities=new LinkedHashMap<>();
        GreenManaAbility greenAbility=new GreenManaAbility();BlueManaAbility blueAbility=new BlueManaAbility();
        UUID green=greenAbility.getId(),blue=blueAbility.getId();
        abilities.put(green,greenAbility);abilities.put(blue,blueAbility);
        Map<UUID,ActivatedManaAbilityImpl> scratch=new LinkedHashMap<>(abilities);
        Map<UUID,ActivatedManaAbilityImpl> narrowed=ManaUtil.tryToAutoPay(greenCost,scratch);
        check(narrowed.size()==1 && narrowed.containsKey(green));
        check(scratch==narrowed && scratch.size()==1); // Native helper mutates the supplied map.
        check(SelectedSourceMana.narrow(new ManaCostsImpl<>("{U}"),abilities).keySet().equals(Collections.singleton(blue)));
        check(SelectedSourceMana.narrow(greenCost,abilities).keySet().equals(Collections.singleton(green)));
        check(abilities.size()==2); // Adapter preserves the owner's original map for later inspection.
        boolean readOnly=false;try{SelectedSourceMana.narrow(greenCost,abilities).clear();}catch(UnsupportedOperationException expected){readOnly=true;}check(readOnly);
        boolean wrongKey=false;Map<UUID,ActivatedManaAbilityImpl> invalid=new HashMap<>();invalid.put(UUID.randomUUID(),greenAbility);
        try{SelectedSourceMana.narrow(greenCost,invalid);}catch(IllegalArgumentException expected){wrongKey=true;}check(wrongKey);
        check(ManaUtil.tryToAutoPay(null,abilities)==abilities);
        check(ManaUtil.tryToAutoPay(greenCost,Collections.emptyMap()).isEmpty());
        ChoiceColor choice=new ChoiceColor();check(ManaUtil.tryToAutoSelectAManaColor(choice,greenCost));
        check(choice.isChosen() && choice.getMana(1).getGreen()==1);
        // Generic costs select the first offered color; this helper is NOT a strategic safety test.
        ChoiceColor generic=new ChoiceColor();String firstOffered=generic.getChoices().iterator().next();
        check(ManaUtil.tryToAutoSelectAManaColor(generic,new ManaCostsImpl<>("{2}")));
        check(generic.isChosen() && generic.getChoice().equals(firstOffered));
        ChoiceColor ambiguous=new ChoiceColor();check(!ManaUtil.tryToAutoSelectAManaColor(ambiguous,new ManaCostsImpl<>("{G}{U}")));
        check(!ambiguous.isChosen());check(!greenCost.isPaid());
        System.out.println("Pinned XMage payment helpers: "+checks+" native object checks passed; no source activation or real-game acceptance");
    }
}

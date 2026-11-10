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
import manaforge.payment.xmage.OrdinaryManaShape;
import manaforge.payment.xmage.OrdinaryCostCoverage;
import manaforge.payment.xmage.NativePaymentHazards;
import mage.constants.RangeOfInfluence;

/** Pinned utility objects and synthetic scope guards. No server, deck, activation or real-game claim. */
public final class PinnedPaymentChecks {
    private static int checks;
    private static void check(boolean value){checks++;if(!value)throw new AssertionError("PINNED_PAYMENT_CHECK_"+checks);}
    private static boolean[] priorityStops(UserData preferences) {
        java.util.List<Boolean> values=new java.util.ArrayList<>();
        for (mage.players.net.SkipPrioritySteps steps : new mage.players.net.SkipPrioritySteps[] {
                preferences.getUserSkipPrioritySteps().getYourTurn(),
                preferences.getUserSkipPrioritySteps().getOpponentTurn()}) {
            for(boolean value:new boolean[]{steps.isUpkeep(),steps.isDraw(),steps.isMain1(),
                    steps.isBeforeCombat(),steps.isEndOfCombat(),steps.isMain2(),steps.isEndOfTurn()})values.add(value);
        }
        boolean[] result=new boolean[values.size()];for(int i=0;i<result.length;i++)result[i]=values.get(i);return result;
    }
    private static void priorityScopeChecks() throws Exception {
        String original=System.getProperty("manaforge.liveGame");
        java.lang.reflect.Method configure=Class.forName("ManaforgeBridge").getDeclaredMethod("configurePriorityStops",UserData.class);
        configure.setAccessible(true);
        try {
            UserData preferences=UserData.getDefaultUserDataView();boolean[] expected=priorityStops(preferences);
            for(String mode:new String[]{null,"false"}) {
                if(mode==null)System.clearProperty("manaforge.liveGame");else System.setProperty("manaforge.liveGame",mode);
                configure.invoke(null,preferences);boolean[] actual=priorityStops(preferences);
                for(int i=0;i<expected.length;i++)check(actual[i]==expected[i]);
            }
            System.setProperty("manaforge.liveGame","true");configure.invoke(null,preferences);
            for(boolean value:priorityStops(preferences))check(value);
        } finally {
            if(original==null)System.clearProperty("manaforge.liveGame");else System.setProperty("manaforge.liveGame",original);
        }
    }
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
    private static void ordinaryShapeChecks() {
        for(ActivatedManaAbilityImpl basic:Arrays.asList(new WhiteManaAbility(),new BlueManaAbility(),new BlackManaAbility(),new RedManaAbility(),new GreenManaAbility())) {
            check(OrdinaryManaShape.inspect(basic)==OrdinaryManaShape.Result.ORDINARY_TAP_SHAPE);
            check(OrdinaryManaShape.inspect((ActivatedManaAbilityImpl)basic.copy())==OrdinaryManaShape.Result.ORDINARY_TAP_SHAPE);
        }
        check(OrdinaryManaShape.inspect(null)==OrdinaryManaShape.Result.UNKNOWN);
        check(OrdinaryManaShape.inspect(new GreenManaAbility(){})==OrdinaryManaShape.Result.UNSUPPORTED_ABILITY);
        GreenManaAbility life=new GreenManaAbility();life.addCost(new mage.abilities.costs.common.PayLifeCost(1));
        check(OrdinaryManaShape.inspect(life)==OrdinaryManaShape.Result.ADDITIONAL_COST);
        GreenManaAbility noTap=new GreenManaAbility();noTap.getCosts().clear();
        check(OrdinaryManaShape.inspect(noTap)==OrdinaryManaShape.Result.ADDITIONAL_COST);
        GreenManaAbility manaCost=new GreenManaAbility();manaCost.getManaCostsToPay().add(new ManaCostsImpl<>("{1}"));
        check(OrdinaryManaShape.inspect(manaCost)==OrdinaryManaShape.Result.ADDITIONAL_COST);
        GreenManaAbility multiple=new GreenManaAbility();multiple.addEffect(new mage.abilities.effects.mana.BasicManaEffect(Mana.GreenMana(1)));
        check(OrdinaryManaShape.inspect(multiple)==OrdinaryManaShape.Result.NONSTANDARD_EFFECT);
        GreenManaAbility dynamic=new GreenManaAbility();dynamic.getEffects().clear();dynamic.addEffect(new mage.abilities.effects.mana.BasicManaEffect(Mana.GreenMana(1),mage.abilities.dynamicvalue.common.StaticValue.get(2)));
        check(OrdinaryManaShape.inspect(dynamic)==OrdinaryManaShape.Result.NONSTANDARD_EFFECT);
        GreenManaAbility restricted=new GreenManaAbility();restricted.getEffects().clear();restricted.addEffect(new mage.abilities.effects.mana.BasicManaEffect(new mage.ConditionalMana(Mana.GreenMana(1))));
        check(OrdinaryManaShape.inspect(restricted)==OrdinaryManaShape.Result.NONSTANDARD_EFFECT);
        GreenManaAbility changed=new GreenManaAbility();changed.getEffects().clear();changed.addEffect(new mage.abilities.effects.mana.BasicManaEffect(Mana.BlueMana(1)));
        check(OrdinaryManaShape.inspect(changed)==OrdinaryManaShape.Result.NONSTANDARD_EFFECT);
        GreenManaAbility pool=new GreenManaAbility();pool.setPoolDependant(true);
        check(OrdinaryManaShape.inspect(pool)==OrdinaryManaShape.Result.CHOICE_OR_ADJUSTER);
        GreenManaAbility mode=new GreenManaAbility();mode.getModes().getMode().withCost(new mage.abilities.costs.common.PayLifeCost(1));
        check(OrdinaryManaShape.inspect(mode)==OrdinaryManaShape.Result.CHOICE_OR_ADJUSTER);
        GreenManaAbility tagged=new GreenManaAbility();tagged.setCostsTag("unsupported",true);
        check(OrdinaryManaShape.inspect(tagged)==OrdinaryManaShape.Result.CHOICE_OR_ADJUSTER);
        check(life.getCosts().size()==2 && dynamic.getEffects().size()==1); // Inspection never rewrites native inputs.
    }
    private static void ordinaryCoverageChecks() {
        Mana green=Mana.GreenMana(1),blue=Mana.BlueMana(1),mixed=green.copy();mixed.add(blue);
        ManaCostsImpl<?> cost=new ManaCostsImpl<>("{2}{G}");
        check(cost.testPay(mixed)); // Contribution alone is not coverage.
        check(OrdinaryCostCoverage.inspect(cost,mixed)==OrdinaryCostCoverage.Result.INSUFFICIENT);
        mixed.add(blue);check(OrdinaryCostCoverage.inspect(cost,mixed)==OrdinaryCostCoverage.Result.COVERS);
        check(!cost.isPaid() && cost.getMana().count()==3 && mixed.getBlue()==2 && mixed.getGreen()==1);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{1}{U}"),mixed)==OrdinaryCostCoverage.Result.COVERS);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{G}"),blue)==OrdinaryCostCoverage.Result.INSUFFICIENT);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{G}"),green)==OrdinaryCostCoverage.Result.COVERS);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{C}"),green)==OrdinaryCostCoverage.Result.INSUFFICIENT);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{C}"),Mana.ColorlessMana(1))==OrdinaryCostCoverage.Result.COVERS);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{0}"),green)==OrdinaryCostCoverage.Result.NO_UNPAID_COST);
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>("{1}"),new Mana())==OrdinaryCostCoverage.Result.INSUFFICIENT);
        for(String special:Arrays.asList("{G/U}","{G/P}","{S}","{X}","{129}"))
            check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<>(special),mixed)==OrdinaryCostCoverage.Result.UNSUPPORTED);
        check(OrdinaryCostCoverage.inspect(cost,new mage.ConditionalMana(mixed))==OrdinaryCostCoverage.Result.UNSUPPORTED);
        check(OrdinaryCostCoverage.inspect(cost,Mana.AnyMana(3))==OrdinaryCostCoverage.Result.UNSUPPORTED);
        check(OrdinaryCostCoverage.inspect(cost,Mana.GenericMana(3))==OrdinaryCostCoverage.Result.UNSUPPORTED);
        check(OrdinaryCostCoverage.inspect(cost,Mana.GreenMana(129))==OrdinaryCostCoverage.Result.UNSUPPORTED);
        Mana flagged=green.copy();flagged.setFlag(true);check(OrdinaryCostCoverage.inspect(cost,flagged)==OrdinaryCostCoverage.Result.UNSUPPORTED);
        check(OrdinaryCostCoverage.inspect(null,green)==OrdinaryCostCoverage.Result.UNKNOWN);
        check(OrdinaryCostCoverage.inspect(cost,null)==OrdinaryCostCoverage.Result.UNKNOWN);
        ManaCostsImpl<?> filtered=new ManaCostsImpl<>("{G}");filtered.setSourceFilter(new mage.filter.FilterPermanent());
        check(OrdinaryCostCoverage.inspect(filtered,green)==OrdinaryCostCoverage.Result.UNSUPPORTED);
        ManaCostsImpl<?> paid=new ManaCostsImpl<>("{G}");paid.setPaid();
        check(OrdinaryCostCoverage.inspect(paid,green)==OrdinaryCostCoverage.Result.NO_UNPAID_COST);check(paid.isPaid());
        check(OrdinaryCostCoverage.inspect(new ManaCostsImpl<mage.abilities.costs.mana.ManaCost>("{G}"){},green)==OrdinaryCostCoverage.Result.UNSUPPORTED);
    }
    private static final class PublicCard extends mage.cards.CardImpl {
        PublicCard(){super(UUID.randomUUID(),"Public fixture");}
        private PublicCard(PublicCard original){super(original);}
        @Override public PublicCard copy(){return new PublicCard(this);}
    }
    private static void registeredHazardChecks() {
        PublicCard card=new PublicCard();mage.game.GameState[] state={new mage.game.GameState()};
        ContextHumanPlayer payer=new ContextHumanPlayer("Public fixture",RangeOfInfluence.ALL,0);
        state[0].getPlayers().put(payer.getId(),payer);
        mage.abilities.SpellAbility paying=new mage.abilities.SpellAbility(new ManaCostsImpl<>("{G}"),"Public fixture");
        paying.setSourceId(card.getId());paying.setControllerId(payer.getId());
        boolean[] ended={false},missing={false},replace={false};
        mage.game.Game game=(mage.game.Game)java.lang.reflect.Proxy.newProxyInstance(PinnedPaymentChecks.class.getClassLoader(),new Class<?>[]{mage.game.Game.class},(proxy,method,args)->{
            switch(method.getName()) {
                case "hasEnded":return ended[0];
                case "getState":return state[0];
                case "getCard":if(replace[0])state[0]=new mage.game.GameState();return missing[0]?null:card;
                default:throw new AssertionError("UNEXPECTED_HAZARD_CALL_"+method.getName());
            }
        });
        check(NativePaymentHazards.inspect(null,paying)==NativePaymentHazards.Result.UNKNOWN);
        check(NativePaymentHazards.inspect(game,null)==NativePaymentHazards.Result.UNKNOWN);
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.NO_REGISTERED_HAZARD);
        for(mage.abilities.effects.ReplacementEffect effect:new mage.abilities.effects.ReplacementEffect[]{new mage.abilities.effects.keyword.ShieldCounterEffect(),new mage.abilities.effects.keyword.StunCounterEffect(),new mage.abilities.effects.keyword.FinalityCounterEffect()}){
            check(!effect.checksEventType(mage.game.events.GameEvent.getEvent(mage.game.events.GameEvent.EventType.TAP,card.getId(),paying,payer.getId()),game));state[0].getContinuousEffects().addEffect(effect,paying);
        }
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);check(NativePaymentHazards.inspectOrdinaryTap(game,paying)==NativePaymentHazards.Result.NO_REGISTERED_HAZARD);
        mage.abilities.triggers.BeginningOfFirstMainTriggeredAbility firstMain=new mage.abilities.triggers.BeginningOfFirstMainTriggeredAbility(new mage.abilities.effects.mana.BasicManaEffect(Mana.GreenMana(1)));
        check(!firstMain.checkEventType(mage.game.events.GameEvent.getEvent(mage.game.events.GameEvent.EventType.TAP,card.getId(),paying,payer.getId()),game));state[0].getTriggers().put("first-main",firstMain);check(NativePaymentHazards.inspectOrdinaryTap(game,paying)==NativePaymentHazards.Result.NO_REGISTERED_HAZARD);state[0].getTriggers().clear();
        state[0].getContinuousEffects().addEffect(new mage.abilities.effects.common.continuous.GainAbilityAllEffect(new GreenManaAbility(),mage.constants.Duration.WhileOnBattlefield,new mage.filter.FilterPermanent()),paying);check(NativePaymentHazards.inspectOrdinaryTap(game,paying)==NativePaymentHazards.Result.NO_REGISTERED_HAZARD);
        state[0]=new mage.game.GameState();state[0].getPlayers().put(payer.getId(),payer);
        for(int i=0;i<5;i++){ContextHumanPlayer extra=new ContextHumanPlayer("Public fixture",RangeOfInfluence.ALL,0);state[0].getPlayers().put(extra.getId(),extra);}
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.NO_REGISTERED_HAZARD); // Six is not a protocol limit.
        ended[0]=true;check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.UNKNOWN);ended[0]=false;
        state[0].setManaBurn(true);check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);state[0].setManaBurn(false);
        mage.abilities.common.delayed.AtTheBeginOfNextEndStepDelayedTriggeredAbility trigger=new mage.abilities.common.delayed.AtTheBeginOfNextEndStepDelayedTriggeredAbility(new mage.abilities.effects.mana.BasicManaEffect(Mana.GreenMana(1)));
        trigger.setControllerId(payer.getId());trigger.setSourceId(card.getId());
        state[0].getTriggers().put("private-key-never-exported",trigger);
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);check(NativePaymentHazards.inspectOrdinaryTap(game,paying)==NativePaymentHazards.Result.NO_REGISTERED_HAZARD);state[0].getTriggers().put("mana-sensitive",new ManaTapTrigger());check(NativePaymentHazards.inspectOrdinaryTap(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);state[0].getTriggers().clear();
        state[0].getDelayed().add(trigger);
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);state[0].getDelayed().clear();
        state[0].addTriggeredAbility(trigger);
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);state[0].clearTriggeredAbilities();
        state[0].getContinuousEffects().addEffect(new mage.abilities.effects.common.continuous.GainAbilityAllEffect(new GreenManaAbility(),mage.constants.Duration.WhileOnBattlefield,new mage.filter.FilterPermanent()),paying);
        int before=state[0].getContinuousEffects().getTotalEffectsCount();check(before>0);
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);
        check(state[0].getContinuousEffects().getTotalEffectsCount()==before);state[0].getContinuousEffects().clear();
        missing[0]=true;check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.UNKNOWN);missing[0]=false;
        check(NativePaymentHazards.inspect(game,new GreenManaAbility())==NativePaymentHazards.Result.UNKNOWN);
        card.addAbility(new mage.abilities.keyword.SunburstAbility(card));
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.REQUIRES_MANUAL);
        card.getAbilities().clear();replace[0]=true;
        check(NativePaymentHazards.inspect(game,paying)==NativePaymentHazards.Result.UNKNOWN);
    }
    private static void sourceTicketChecks() throws Exception {
        ContextHumanPlayer player=new ContextHumanPlayer("Public fixture",RangeOfInfluence.ALL,0);
        UUID source=UUID.randomUUID();UUID[] controller={player.getId()};boolean[] tapped={false},legal={true};
        int[] transforms={0};
        GreenManaAbility candidate=new GreenManaAbility(){@Override public mage.abilities.ActivatedAbility.ActivationStatus canActivate(UUID payer,mage.game.Game game){return mage.abilities.ActivatedAbility.ActivationStatus.withoutApprovingObject(legal[0]);}};
        candidate.setControllerId(player.getId());candidate.setSourceId(source);
        java.util.function.Supplier<mage.game.permanent.Permanent> make=()->(mage.game.permanent.Permanent)java.lang.reflect.Proxy.newProxyInstance(PinnedPaymentChecks.class.getClassLoader(),new Class<?>[]{mage.game.permanent.Permanent.class},(proxy,method,args)->{
            switch(method.getName()) {
                case "getId":return source;
                case "getControllerId":return controller[0];
                case "canUseActivatedAbilities":return true;
                case "getAbilities":mage.abilities.AbilitiesImpl<Ability> abilities=new mage.abilities.AbilitiesImpl<>();abilities.add(candidate);return abilities;
                case "isTapped":return tapped[0];
                case "isPhasedIn":return true;
                case "isFlipped":return false;
                case "getTransformCount":return transforms[0];
                default:throw new AssertionError("UNEXPECTED_TICKET_SOURCE_CALL_"+method.getName());
            }
        });
        mage.game.permanent.Permanent[] permanent={make.get()};mage.game.GameState[] state={new mage.game.GameState()};
        mage.game.Game game=(mage.game.Game)java.lang.reflect.Proxy.newProxyInstance(PinnedPaymentChecks.class.getClassLoader(),new Class<?>[]{mage.game.Game.class},(proxy,method,args)->{
            switch(method.getName()) {
                case "getPlayer":return player;
                case "getPermanent":return source.equals(args[0])?permanent[0]:null;
                case "getState":return state[0];
                case "hasEnded":return false;
                default:throw new AssertionError("UNEXPECTED_TICKET_GAME_CALL_"+method.getName());
            }
        });
        java.lang.reflect.Field response=mage.player.human.HumanPlayer.class.getDeclaredField("response");response.setAccessible(true);
        java.lang.reflect.Field open=mage.player.human.HumanPlayer.class.getDeclaredField("responseOpenedForAnswer");open.setAccessible(true);
        java.lang.reflect.Field payment=ContextHumanPlayer.class.getDeclaredField("payment");payment.setAccessible(true);
        java.lang.reflect.Constructor<?> frame=Class.forName("manaforge.payment.xmage.ContextHumanPlayer$Frame").getDeclaredConstructors()[0];frame.setAccessible(true);
        Object originalFrame=frame.newInstance(game,new GreenManaAbility(),new ManaCostsImpl<>("{G}"),1L);
        payment.set(player,originalFrame);open.set(player,true);player.setPayManaMode(true);
        int cycle=state[0].getApplyEffectsCounter();int[] calls={0};
        ContextHumanPlayer.SourceInspector<Boolean> read=(paying,unpaid,available)->{calls[0]++;return true;};
        check(player.captureSourceTicket(game,player.getId(),cycle,source,candidate.getId())==null);
        synchronized(response.get(player)) {
            ContextHumanPlayer.SourceTicket ticket=player.captureSourceTicket(game,player.getId(),cycle,source,candidate.getId());check(ticket!=null);
            check(ticket.toString().equals("NativeSourceTicket(private)"));
            check(Boolean.TRUE.equals(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)));
            check(player.inspectSourceTicket(game,UUID.randomUUID(),cycle,ticket,read)==null);
            check(player.inspectSourceTicket(game,player.getId(),cycle+1,ticket,read)==null);
            check(player.copy().inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);
            tapped[0]=true;check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);tapped[0]=false;
            controller[0]=UUID.randomUUID();check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);controller[0]=player.getId();
            transforms[0]=1;check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);transforms[0]=0;
            int incarnation=state[0].getZoneChangeCounter(source);state[0].setZoneChangeCounter(source,incarnation+1);check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);state[0].setZoneChangeCounter(source,incarnation);
            mage.game.permanent.Permanent previous=permanent[0];permanent[0]=make.get();check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);permanent[0]=previous;
            mage.game.GameState previousState=state[0];state[0]=new mage.game.GameState();check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);state[0]=previousState;
            legal[0]=false;check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);legal[0]=true;
            open.set(player,false);check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);open.set(player,true);
            payment.set(player,frame.newInstance(game,new GreenManaAbility(),new ManaCostsImpl<>("{G}"),1L));
            check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);payment.set(player,originalFrame);
            check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,(a,c,m)->{tapped[0]=true;return true;})==null);tapped[0]=false;
            check(calls[0]==1);candidate.newId();check(player.inspectSourceTicket(game,player.getId(),cycle,ticket,read)==null);
            for(java.lang.reflect.Field field:ContextHumanPlayer.SourceTicket.class.getDeclaredFields())
                check(!mage.game.Game.class.isAssignableFrom(field.getType()) && !mage.abilities.Ability.class.isAssignableFrom(field.getType()) && !mage.game.GameState.class.isAssignableFrom(field.getType()) && !mage.game.permanent.Permanent.class.isAssignableFrom(field.getType()));
        }
        payment.set(player,null);open.set(player,false);player.setPayManaMode(false);
    }
    private static final class ManaTapTrigger extends mage.abilities.TriggeredAbilityImpl {
        ManaTapTrigger(){super(mage.constants.Zone.BATTLEFIELD,new mage.abilities.effects.mana.BasicManaEffect(Mana.RedMana(1)));}
        private ManaTapTrigger(ManaTapTrigger original){super(original);}
        @Override public boolean checkEventType(mage.game.events.GameEvent event,mage.game.Game game){return event.getType()==mage.game.events.GameEvent.EventType.TAPPED_FOR_MANA;}
        @Override public boolean checkTrigger(mage.game.events.GameEvent event,mage.game.Game game){throw new AssertionError("MUST_NOT_EXECUTE_TRIGGER");}
        @Override public ManaTapTrigger copy(){return new ManaTapTrigger(this);}
    }
    private static void targetingContextScopeChecks() throws Exception {
        ContextHumanPlayer player=new ContextHumanPlayer("Public fixture",RangeOfInfluence.ALL,0);mage.game.GameState state=new mage.game.GameState();
        mage.game.Game game=(mage.game.Game)java.lang.reflect.Proxy.newProxyInstance(PinnedPaymentChecks.class.getClassLoader(),new Class<?>[]{mage.game.Game.class},(proxy,method,args)->{
            switch(method.getName()){case "getPlayer":return player;case "getState":return state;case "hasEnded":return false;default:throw new AssertionError("UNEXPECTED_TARGET_PROBE_CALL_"+method.getName());}
        });
        java.lang.reflect.Field response=mage.player.human.HumanPlayer.class.getDeclaredField("response");response.setAccessible(true);java.lang.reflect.Field open=mage.player.human.HumanPlayer.class.getDeclaredField("responseOpenedForAnswer");open.setAccessible(true);
        java.lang.reflect.Field targeting=ContextHumanPlayer.class.getDeclaredField("targeting");targeting.setAccessible(true);check(java.lang.reflect.Modifier.isTransient(targeting.getModifiers()));
        java.lang.reflect.Constructor<?> frame=Class.forName("manaforge.payment.xmage.ContextHumanPlayer$TargetFrame").getDeclaredConstructors()[0];frame.setAccessible(true);
        mage.target.Target target=new mage.target.common.TargetCreaturePermanent();Ability source=new mage.abilities.SpellAbility(new ManaCostsImpl<>("{R}"),"Public fixture");source.setSourceId(UUID.randomUUID());source.setControllerId(player.getId());
        check(player.targetingProbe(game,player.getId(),0)==null);targeting.set(player,frame.newInstance(game,source,target));open.set(player,true);
        check(player.targetingProbe(game,player.getId(),0)==null);
        synchronized(response.get(player)){
            com.google.gson.JsonObject context=player.targetingProbe(game,player.getId(),state.getApplyEffectsCounter());check(context!=null && context.get("minimum").getAsInt()==1 && context.getAsJsonArray("selected").size()==0);
            check(player.copy().targetingProbe(game,player.getId(),state.getApplyEffectsCounter())==null);check(player.targetingProbe(game,UUID.randomUUID(),state.getApplyEffectsCounter())==null);
            target.withNotTarget(true);check(player.targetingProbe(game,player.getId(),state.getApplyEffectsCounter())==null);target.withNotTarget(false);
            open.set(player,false);check(player.targetingProbe(game,player.getId(),state.getApplyEffectsCounter())==null);
        }targeting.set(player,null);
    }
    public static void main(String[] args) throws Exception {
        targetingContextScopeChecks();
        priorityScopeChecks();
        ContextHumanPlayer observed=new ContextHumanPlayer("Public fixture",RangeOfInfluence.ALL,0);
        ContextHumanPlayer copied=observed.copy();
        check(copied.getClass()==ContextHumanPlayer.class);check(copied.getId().equals(observed.getId()));
        check(java.lang.reflect.Modifier.isTransient(ContextHumanPlayer.class.getDeclaredField("payment").getModifiers()));
        check(observed.paymentProbe(null,observed.getId(),0)==null);check(copied.paymentProbe(null,copied.getId(),0)==null);
        sourceScopeChecks(observed);
        ordinaryShapeChecks();
        ordinaryCoverageChecks();
        registeredHazardChecks();
        sourceTicketChecks();
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

package manaforge.payment.xmage;

import java.util.*;
import mage.Mana;
import mage.abilities.Ability;
import mage.abilities.SpellAbility;
import mage.abilities.costs.mana.*;
import mage.abilities.mana.ActivatedManaAbilityImpl;
import mage.cards.*;
import mage.constants.*;
import mage.game.*;
import mage.game.permanent.PermanentCard;

/** Seeded small-board oracle: exhaustive native source sequences, independently
 * of production search ranking/budgets. Also checks copy isolation and resource preservation. */
public final class NativePaymentSearchChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static CardSetInfo info(String name){return new CardSetInfo(name,"TST","1",Rarity.COMMON);}
    static int exhaustive(Game game,UUID payer,Ability paying,ManaCost unpaid,UUID[] ids,int depth) {
        ManaCost cost=unpaid.copy();Game copy=NativePaymentSearch.isolated(game);PaymentSimulationPlayer actor=(PaymentSimulationPlayer)copy.getPlayer(payer);
        actor.getManaPool().setAutoPayment(true);actor.getManaPool().setAutoPaymentRestricted(false);cost.assignPayment(copy,paying,actor.getManaPool(),cost);
        if(cost.isPaid())return 0;if(depth==0)return 999;
        int best=999;
        for(UUID id:ids)for(ActivatedManaAbilityImpl ability:actor.usable(copy.getPermanent(id),copy).values()) {
            Game branch=NativePaymentSearch.isolated(copy);PaymentSimulationPlayer player=(PaymentSimulationPlayer)branch.getPlayer(payer);player.begin(ManaType.RED);
            ActivatedManaAbilityImpl candidate=player.usable(branch.getPermanent(id),branch).get(ability.getId());
            if(candidate!=null && player.activate(candidate,branch))best=Math.min(best,1+exhaustive(branch,payer,paying,cost,ids,depth-1));
        }
        return best;
    }
    static final class OnlySpell extends mage.abilities.mana.conditional.ManaCondition {
        @Override public boolean apply(Game game,Ability source,UUID producer,mage.abilities.costs.Cost cost){return source.getAbilityType()==AbilityType.SPELL;}
    }
    static void restrictedPool() {
        TwoPlayerDuel game=new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),60,20,7);
        // Match startup initializes options before any native simulation copies.
        game.setGameOptions(new GameOptions());
        ContextHumanPlayer player=new ContextHumanPlayer("Restricted mana",RangeOfInfluence.ALL,0);player.setUserData(mage.players.net.UserData.getDefaultUserDataView());game.addPlayer(player,new mage.cards.decks.Deck());player.init(game);
        Card card=new mage.cards.basiclands.Mountain(player.getId(),info("Mountain"));game.loadCards(Collections.singleton(card),player.getId());game.setZone(card.getId(),Zone.BATTLEFIELD);game.addPermanent(new PermanentCard(card,player.getId(),game),0);
        SpellAbility spell=new SpellAbility(new ManaCostsImpl<>("{R}"),"Restricted probe");spell.setSourceId(card.getId());spell.setControllerId(player.getId());
        mage.ConditionalMana restricted=new mage.ConditionalMana(Mana.RedMana(1));restricted.addCondition(new OnlySpell());player.getManaPool().addMana(restricted,game,card.getAbilities().get(0));
        NativePaymentSearch.Result legal=NativePaymentSearch.search(game,player.getId(),spell,new ManaCostsImpl<>("{R}"),new UUID[0]);
        check(legal.outcome==NativePaymentSearch.Outcome.READY && legal.steps.isEmpty(),"RESTRICTED_POOL_NOT_USED_FOR_SPELL");
        mage.abilities.ActivatedAbility activated=new mage.abilities.common.SimpleActivatedAbility(Zone.BATTLEFIELD,new mage.abilities.effects.common.GainLifeEffect(1),new ManaCostsImpl<>("{R}"));activated.setSourceId(card.getId());activated.setControllerId(player.getId());
        NativePaymentSearch.Result illegal=NativePaymentSearch.search(game,player.getId(),activated,new ManaCostsImpl<>("{R}"),new UUID[0]);
        check(illegal.outcome==NativePaymentSearch.Outcome.INSUFFICIENT_MANA,"RESTRICTED_POOL_SPENT_ON_ABILITY");
        check(player.getManaPool().getManaItems().size()==1 && player.getManaPool().getConditionalCount(spell,game,null,spell.getManaCosts())==1,"RESTRICTED_POOL_MUTATED");player.abort();
    }
    static void creatureTypeMenu() {
        TwoPlayerDuel game=new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),60,20,7);
        game.setGameOptions(new GameOptions());ContextHumanPlayer player=new ContextHumanPlayer("Types",RangeOfInfluence.ALL,0);
        mage.cards.decks.Deck deck=new mage.cards.decks.Deck();
        deck.getCards().add(new mage.cards.e.ElvishMystic(player.getId(),info("Elvish Mystic")));
        deck.getCards().add(new mage.cards.d.DelverOfSecrets(player.getId(),info("Delver of Secrets")));
        deck.getCards().add(new mage.cards.basiclands.Forest(player.getId(),info("Forest")));
        game.addPlayer(player,deck);player.useDeck(deck,game);
        mage.choices.ChoiceCreatureType original=new mage.choices.ChoiceCreatureType(game,null);
        for(ContextHumanPlayer owner:new ContextHumanPlayer[]{player,player.copy()}) {
            ContextHumanPlayer.DeckCreatureTypeChoice menu=owner.creatureTypeMenu(original,game);menu.onChooseStart(game,owner.getId());
            check(menu.getKeyChoices().keySet().equals(original.getKeyChoices().keySet()),"TYPE_MENU_CHANGED_LEGAL_CHOICES");
            check(menu.getSortData().get("Elf")==-100 && menu.getSortData().get("Druid")==-100,"TYPE_MENU_DID_NOT_READ_FULL_DECK");
            check(menu.getSortData().get("Insect")==-100,"TYPE_MENU_MISSING_BACK_FACE");
            check(menu.getSortData().get("Goblin")==0 && !menu.getKeyChoices().containsKey("Forest"),"TYPE_MENU_INCLUDED_OFF_DECK_OR_LAND_TYPE");
            check(menu.getKeyChoices().get("Elf").equals("Elf"),"TYPE_MENU_INCLUDED_PUBLIC_ZONE_HINTS");
        }
        mage.choices.ChoiceCreatureType restricted=new mage.choices.ChoiceCreatureType(game,null,true,"Choose",Arrays.asList(SubType.ZOMBIE,SubType.GOBLIN));
        ContextHumanPlayer.DeckCreatureTypeChoice menu=player.creatureTypeMenu(restricted,game);menu.onChooseStart(game,player.getId());
        check(menu.getKeyChoices().size()==2 && !menu.getKeyChoices().containsKey("Elf"),"TYPE_MENU_EXPANDED_RESTRICTED_TYPES");
        check(menu.getSortData().values().stream().allMatch(value->value==0),"EMPTY_DECK_INTERSECTION_NOT_EMPTY");
        player.abort();
    }
    public static void main(String[] args) throws Exception {
        creatureTypeMenu();
        Thread.currentThread().setName("GAME-payment-oracle");restrictedPool();Random seeds=new Random(20261110L);
        for(int seed=0;seed<16;seed++) {
            TwoPlayerDuel game=new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),60,20,7);
            // Match startup initializes options before any native simulation copies.
            game.setGameOptions(new GameOptions());
            ContextHumanPlayer player=new ContextHumanPlayer("Oracle",RangeOfInfluence.ALL,0);player.setUserData(mage.players.net.UserData.getDefaultUserDataView());game.addPlayer(player,new mage.cards.decks.Deck());player.init(game);
            ContextHumanPlayer opponent=new ContextHumanPlayer("Oracle opponent",RangeOfInfluence.ALL,0);opponent.setUserData(mage.players.net.UserData.getDefaultUserDataView());game.addPlayer(opponent,new mage.cards.decks.Deck());opponent.init(game);
            game.getState().getPlayerList().add(opponent.getId());game.getState().getPlayerList().add(player.getId());game.getState().getPlayerList().setCurrent(player.getId());
            java.lang.reflect.Field cursor=GameImpl.class.getDeclaredField("playerList");cursor.setAccessible(true);cursor.set(game,game.getState().getPlayerList());
            game.getState().setActivePlayerId(player.getId());game.getState().setPriorityPlayerId(player.getId());game.getState().setTurnNum(4);game.getTurn().setPhase(new mage.game.turn.PreCombatMainPhase());
            int available=1+seeds.nextInt(3),required=1+seeds.nextInt(3);UUID[] ids=new UUID[available];
            for(int i=0;i<available;i++) {
                Card card=new mage.cards.basiclands.Mountain(player.getId(),info("Mountain"));ids[i]=card.getId();game.loadCards(Collections.singleton(card),player.getId());game.setZone(card.getId(),Zone.BATTLEFIELD);
                PermanentCard permanent=new PermanentCard(card,player.getId(),game);game.addPermanent(permanent,0);for(Ability ability:permanent.getAbilities())game.getState().addAbility(ability,permanent);
            }
            Card spell=new mage.cards.e.EmberHauler(player.getId(),info("Ember Hauler"));game.loadCards(Collections.singleton(spell),player.getId());
            SpellAbility paying=new SpellAbility(new ManaCostsImpl<>("{R}"),"Oracle");paying.setSourceId(spell.getId());paying.setControllerId(player.getId());
            ManaCostsImpl<?> cost=new ManaCostsImpl<>(String.join("",Collections.nCopies(required,"{R}")));
            int oracle=exhaustive(game,player.getId(),paying,cost,ids,available);
            NativePaymentSearch.Result result=NativePaymentSearch.search(game,player.getId(),paying,cost,ids);
            check((oracle<999)==(result.outcome==NativePaymentSearch.Outcome.READY),"PAYMENT_SEED_20261110_"+seed+"_"+result.outcome);
            if(oracle<999)check(result.steps.size()==oracle,"PAYMENT_NONMINIMAL_SEED_"+seed);
            check(!cost.isPaid() && player.getManaPool().count()==0,"PAYMENT_MUTATED_COST_OR_POOL");for(UUID id:ids)check(!game.getPermanent(id).isTapped(),"PAYMENT_MUTATED_LIVE_SOURCE");
            NativePaymentSearch.Result limited=NativePaymentSearch.search(game,player.getId(),paying,cost,ids,0,NativePaymentSearch.MAX_NANOS);
            check(limited.outcome==NativePaymentSearch.Outcome.SEARCH_LIMIT_REACHED && limited.steps.isEmpty(),"PAYMENT_BUDGET_NOT_DISTINCT");
            Game copy=NativePaymentSearch.isolated(game);check(copy.getState()!=game.getState() && copy.getPlayer(player.getId())!=player,"PAYMENT_COPY_SHARED_PLAYER");
            player.abort();opponent.abort();
        }
        System.out.println("Payment native exhaustive oracle: 16 retained seeds, source minimum, budget and live-state isolation passed");
    }
}

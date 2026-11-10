import com.google.gson.*;
import java.lang.reflect.Field;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import mage.abilities.*;
import mage.abilities.costs.mana.ManaCostsImpl;
import mage.cards.*;
import mage.constants.*;
import mage.game.*;
import mage.game.events.PlayerQueryEvent;
import mage.game.permanent.PermanentCard;
import mage.player.human.HumanPlayer;
import mage.view.*;
import mage.interfaces.callback.*;
import manaforge.payment.PaymentCoordinator.Mode;
import manaforge.payment.xmage.ContextHumanPlayer;

/** Real native game -> native query -> bridge -> production automation -> native
 * response transport -> native cast/activation receipt. No Unity or invented payment offers. */
public final class NativePaymentAcceptanceChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    static CardSetInfo info(String name){return new CardSetInfo(name,"TST","1",Rarity.COMMON);}
    static Card card(String type,UUID owner) throws Exception{return (Card)Class.forName(type).getConstructor(UUID.class,CardSetInfo.class).newInstance(owner,info(type));}
    static final class Probe extends CardImpl {
        Probe(UUID owner,String cost){super(owner,info("Payment probe"),new CardType[]{CardType.ARTIFACT},cost);getSpellAbility().addEffect(new mage.abilities.effects.common.GainLifeEffect(1));}
        Probe(Probe original){super(original);}
        @Override public Probe copy(){return new Probe(this);}
    }
    static final class ImmediateAbility extends mage.abilities.common.SimpleActivatedAbility {
        ImmediateAbility(String cost){super(Zone.BATTLEFIELD,new mage.abilities.effects.common.GainLifeEffect(1),new ManaCostsImpl<>(cost));usesStack=false;}
        ImmediateAbility(ImmediateAbility original){super(original);}
        @Override public ImmediateAbility copy(){return new ImmediateAbility(this);}
    }
    static final class Engine implements ManaforgeGameplaySession.Engine,AutoCloseable {
        final Game game;boolean chooseX,declinePhyrexian,staleOnce,ageSources=true;int metadataReads,nativeSourceResponses;JsonObject lastCommand;
        final ContextHumanPlayer payer=new ContextHumanPlayer("Payment human",RangeOfInfluence.ALL,0),opponent=new ContextHumanPlayer("Payment opponent",RangeOfInfluence.ALL,0);
        final BlockingQueue<PlayerQueryEvent> queries=new LinkedBlockingQueue<>();
        final List<JsonObject> events=new ArrayList<>();final ManaforgeBridge bridge;
        final ExecutorService thread=Executors.newSingleThreadExecutor(task->{Thread t=new Thread(task,"GAME-native-payment-acceptance");t.setDaemon(true);return t;});
        final AtomicBoolean paid=new AtomicBoolean();Future<?> running;GameView view;int decision;
        final Field response,opened;
        Engine() throws Exception {this(false);}
        Engine(boolean commander) throws Exception {
            game=commander?(Game)Class.forName("mage.game.FreeformUnlimitedCommander").getConstructor(MultiplayerAttackOption.class,RangeOfInfluence.class,mage.game.mulligan.Mulligan.class,int.class,int.class).newInstance(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),40,7):new TwoPlayerDuel(MultiplayerAttackOption.MULTIPLE,RangeOfInfluence.ALL,new mage.game.mulligan.LondonMulligan(0),20,7,7);
            payer.setUserData(mage.players.net.UserData.getDefaultUserDataView());opponent.setUserData(mage.players.net.UserData.getDefaultUserDataView());
            payer.getUserData().setManaPoolAutomatic(true);payer.getUserData().setManaPoolAutomaticRestricted(false);
            game.addPlayer(payer,new mage.cards.decks.Deck());game.addPlayer(opponent,new mage.cards.decks.Deck());
            game.getState().getPlayerList().add(payer.getId());game.getState().getPlayerList().add(opponent.getId());game.getState().getPlayerList().setCurrent(payer.getId());
            Field cursor=GameImpl.class.getDeclaredField("playerList");cursor.setAccessible(true);cursor.set(game,game.getState().getPlayerList());
            game.getState().setActivePlayerId(payer.getId());game.getState().setPriorityPlayerId(payer.getId());game.getState().setTurnNum(4);game.getTurn().setPhase(new mage.game.turn.PreCombatMainPhase());
            payer.init(game);opponent.init(game);payer.getManaPool().setAutoPayment(true);payer.getManaPool().setAutoPaymentRestricted(false);((GameImpl)game).initGameDefaultWatchers();
            response=HumanPlayer.class.getDeclaredField("response");response.setAccessible(true);opened=HumanPlayer.class.getDeclaredField("responseOpenedForAnswer");opened.setAccessible(true);
            game.addPlayerQueryEventListener(queries::add);
            bridge=new ManaforgeBridge(events::add,null,new ManaforgeBridge.ResponseTransport(){
                public boolean object(UUID id,UUID source){check(id.equals(game.getId()),"TRANSPORT_GAME");nativeSourceResponses++;payer.setResponseUUID(source);return true;}
                public boolean mana(UUID id,UUID player,ManaType type){check(id.equals(game.getId()) && player.equals(payer.getId()),"TRANSPORT_PLAYER");payer.setResponseManaType(player,type);return true;}
                public boolean bool(UUID id,boolean value){payer.setResponseBoolean(value);return true;}
            });
        }
        Card load(Card card,Zone zone){
            game.loadCards(Collections.singleton(card),card.getOwnerId());game.setZone(card.getId(),zone);
            if(zone==Zone.BATTLEFIELD){PermanentCard permanent=new PermanentCard(card,card.getOwnerId(),game);game.addPermanent(permanent,0);if(ageSources)permanent.removeSummoningSickness();for(Ability ability:permanent.getAbilities())game.getState().addAbility(ability,permanent);}
            if(zone==Zone.HAND)game.getPlayer(card.getOwnerId()).getHand().add(card);
            if(zone==Zone.LIBRARY)game.getPlayer(card.getOwnerId()).getLibrary().addAll(Collections.singleton(card),game);
            return card;
        }
        void cast(Card spell,ActivatedAbility activation){cast(spell,activation,spell.getSpellAbility());}
        void cast(Card spell,ActivatedAbility activation,SpellAbility casting){game.applyEffects();game.saveState(false);running=thread.submit(()->{
            boolean success=activation==null?payer.cast(casting,game,false,null):payer.activateAbility(activation,game);paid.set(success);
            payer.chooseUse(Outcome.Benefit,"Acceptance payment finished",spell.getSpellAbility(),game);
        });}
        public JsonObject metadata(JsonObject state,String... ids) throws Exception {
            JsonObject request=new JsonObject();JsonArray objects=new JsonArray();for(String id:ids)objects.add(id);request.add("object_ids",objects);request.add("identified_ids",objects.deepCopy());
            JsonObject result=ManaforgeGameMetadata.readPaused(game,payer.getId(),state.get("cycle").getAsInt(),request,()->view);
            if(staleOnce && ++metadataReads==2 && result.has("ordinary_payment"))result.getAsJsonObject("ordinary_payment").addProperty("cost_fingerprint","different-cost");
            return result;
        }
        public JsonObject submit(JsonObject command){lastCommand=command.deepCopy();int first=events.size();bridge.execute(command);for(int i=first;i<events.size();i++)if("response_sent".equals(events.get(i).get("event").getAsString()))return events.get(i);throw new AssertionError("BRIDGE_RESPONSE_MISSING "+events.subList(first,events.size()));}
        public JsonObject terminalMetadata(JsonObject state){throw new AssertionError("UNEXPECTED_TERMINAL");}
        public ManaforgeGameplaySession.Advance advance(long previous) throws Exception {
            PlayerQueryEvent query;
            while(true) {
                query=queries.poll(10,TimeUnit.SECONDS);
                if(query!=null && chooseX && query.getQueryType()==PlayerQueryEvent.QueryType.AMOUNT){payer.setResponseInteger(2);continue;}
                if(query!=null && declinePhyrexian && !paid.get() && query.getQueryType()==PlayerQueryEvent.QueryType.ASK){payer.setResponseBoolean(false);continue;}
                break;
            }
            if(query==null){if(running!=null && running.isDone())running.get();throw new AssertionError("NATIVE_PAYMENT_PROMPT_TIMEOUT");}
            check(query.getPlayerId().equals(payer.getId()),"FOREIGN_PAYMENT_QUERY");
            long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);Object monitor=response.get(payer);
            while(true){synchronized(monitor){if(Boolean.TRUE.equals(opened.get(payer))){view=new GameView(game.getState(),game,payer.getId(),null);break;}}if(System.nanoTime()>end)throw new AssertionError("NATIVE_RESPONSE_NOT_OPEN");Thread.yield();}
            ClientCallbackMethod method=query.getQueryType()==PlayerQueryEvent.QueryType.PLAY_MANA?ClientCallbackMethod.GAME_PLAY_MANA:ClientCallbackMethod.GAME_ASK;
            check(query.getQueryType()==PlayerQueryEvent.QueryType.PLAY_MANA || query.getQueryType()==PlayerQueryEvent.QueryType.ASK,"UNEXPECTED_NATIVE_QUERY_"+query.getQueryType());
            ClientCallback callback=new ClientCallback(method,game.getId(),new GameClientMessage(view,query.getOptions(),query.getMessage()));callback.setMessageId(++decision);bridge.onCallback(callback);
            return new ManaforgeGameplaySession.Advance(bridge.currentState(),bridge.currentDecision(),null);
        }
        public ManaforgeGameplaySession.Advance refresh(){return new ManaforgeGameplaySession.Advance(bridge.currentState(),bridge.currentDecision(),null);}
        public void close() throws Exception {payer.abort();opponent.abort();if(running!=null)running.cancel(true);thread.shutdownNow();thread.awaitTermination(3,TimeUnit.SECONDS);}
    }
    static void scenario(String name,String cost,String[] sources,boolean manual,boolean ability,boolean counters,boolean doubler) throws Exception {
        try(Engine engine=new Engine(name.startsWith("commander-"))) {
            engine.chooseX=name.equals("chosen-x");engine.declinePhyrexian=name.equals("phyrexian-mana");engine.staleOnce=name.equals("stale-before-submit");engine.ageSources=!name.equals("sick-mana-creature");
            Mode mode=name.equals("manual-mode")?Mode.MANUAL:name.equals("full-control-mode")?Mode.FULL_CONTROL:Mode.AUTO;
            if(mode!=Mode.AUTO){engine.payer.getUserData().setManaPoolAutomatic(false);engine.payer.getManaPool().setAutoPayment(false);}
            if(name.startsWith("commander-") && !name.equals("commander-tax")) {
                Card commander=engine.load(new mage.cards.w.WulfgarOfIcewindDale(engine.payer.getId(),info("Wulfgar of Icewind Dale")),Zone.OUTSIDE);engine.payer.getSideboard().add(commander);
                ((GameCommanderImpl)engine.game).addCommander(commander,engine.payer);((GameCommanderImpl)engine.game).initCommander(commander,engine.payer);
            }
            List<Card> lands=new ArrayList<>();for(String type:sources)lands.add(engine.load(card(type,engine.payer.getId()),Zone.BATTLEFIELD));
            if(name.equals("tapped-source"))engine.game.getPermanent(lands.get(0).getId()).setTapped(true);
            if(name.equals("sacrifice-source"))engine.game.getPermanent(lands.get(0).getId()).getCounters(engine.game).addCounter(mage.counters.CounterType.DEPLETION.createInstance(2));
            if(counters && !lands.isEmpty())engine.game.getPermanent(lands.get(0).getId()).getCounters(engine.game).addCounter(mage.counters.CounterType.P1P1.createInstance());
            if(name.startsWith("affinity-") || name.startsWith("artifact-"))engine.load(new mage.cards.o.Ornithopter(engine.payer.getId(),info("Ornithopter")),Zone.BATTLEFIELD);
            if(name.startsWith("artifact-null-rod"))engine.load(new mage.cards.n.NullRod(engine.opponent.getId(),info("Null Rod")),Zone.BATTLEFIELD);
            if(name.equals("cost-reducer"))engine.load(new mage.cards.h.HelmOfAwakening(engine.payer.getId(),info("Helm of Awakening")),Zone.BATTLEFIELD);
            if(name.equals("cost-increase"))engine.load(new mage.cards.s.SphereOfResistance(engine.opponent.getId(),info("Sphere of Resistance")),Zone.BATTLEFIELD);
            if(doubler)engine.load(new mage.cards.m.ManaFlare(engine.opponent.getId(),info("Mana Flare")),Zone.BATTLEFIELD);
            if(name.equals("manabarbs"))engine.load(new mage.cards.m.Manabarbs(engine.opponent.getId(),info("Manabarbs")),Zone.BATTLEFIELD);
            if(name.equals("denizen")){
                engine.load(new mage.cards.w.WirewoodHerald(engine.opponent.getId(),info("Wirewood Herald")),Zone.BATTLEFIELD);
                engine.load(new mage.cards.l.LlanowarElves(engine.opponent.getId(),info("Llanowar Elves")),Zone.BATTLEFIELD);
            }
            // Whole-library ability registration must not disable normal payment.
            for(int i=0;i<24;i++)engine.load(new mage.cards.basiclands.Forest(engine.payer.getId(),info("Forest")),Zone.LIBRARY);
            Card spell=name.equals("affinity-enforcer")?new mage.cards.m.MyrEnforcer(engine.payer.getId(),info("Myr Enforcer")):name.equals("affinity-thoughtcast")?new mage.cards.t.Thoughtcast(engine.payer.getId(),info("Thoughtcast")):name.equals("affinity-zero")?new mage.cards.f.Frogmite(engine.payer.getId(),info("Frogmite")):name.equals("denizen")?new mage.cards.f.FoundryStreetDenizen(engine.payer.getId(),info("Foundry Street Denizen")):new Probe(engine.payer.getId(),cost);
            ActivatedAbility activation=null;
            if(ability){activation=new mage.abilities.common.SimpleActivatedAbility(Zone.BATTLEFIELD,new mage.abilities.effects.common.GainLifeEffect(1),new ManaCostsImpl<>(cost));if(name.equals("nonstack-activation"))activation=new ImmediateAbility(cost);spell.addAbility(activation);engine.load(spell,Zone.BATTLEFIELD);activation=(ActivatedAbility)engine.game.getPermanent(spell.getId()).getAbilities().get(engine.game.getPermanent(spell.getId()).getAbilities().size()-1);}
            else engine.load(spell,Zone.HAND);
            Map<UUID,Boolean> initialTaps=new HashMap<>();Map<UUID,mage.counters.Counters> initialCounters=new HashMap<>();
            for(Card source:lands){initialTaps.put(source.getId(),engine.game.getPermanent(source.getId()).isTapped());initialCounters.put(source.getId(),engine.game.getPermanent(source.getId()).getCounters(engine.game).copy());}
            int initialLife=engine.payer.getLife();
            if(name.equals("commander-tax")) {
                engine.payer.getHand().remove(spell.getId());engine.game.setZone(spell.getId(),Zone.OUTSIDE);engine.payer.getSideboard().add(spell);
                GameCommanderImpl commander=(GameCommanderImpl)engine.game;commander.addCommander(spell,engine.payer);commander.initCommander(spell,engine.payer);
                SpellAbility commandCast=new SpellAbility(new ManaCostsImpl<>(cost),"Commander probe",Zone.COMMAND);commandCast.setSourceId(spell.getId());commandCast.setControllerId(engine.payer.getId());
                mage.game.events.GameEvent previous=mage.game.events.GameEvent.getEvent(mage.game.events.GameEvent.EventType.SPELL_CAST,spell.getId(),commandCast,engine.payer.getId());previous.setZone(Zone.COMMAND);
                engine.game.getState().getWatcher(mage.watchers.common.CommanderPlaysCountWatcher.class).watch(previous,engine.game);
                engine.cast(spell,null,commandCast);
            }else engine.cast(spell,activation);
            NativeAutomaticPayment payment=new NativeAutomaticPayment("acceptance",engine.payer.getId().toString(),mode);
            try {
                ManaforgeAutomaticEngine wrapper=new ManaforgeAutomaticEngine(engine,payment,()->false);ManaforgeGameplaySession.Advance next=wrapper.advance(0);
                if(manual){check("GAME_PLAY_MANA".equals(next.prompt.get("kind").getAsString()),name+"_DID_NOT_REQUEST_MANUAL");check(!engine.paid.get(),name+"_PAID_UNSAFE");check(engine.payer.getLife()==initialLife,name+"_LOST_LIFE");for(Card source:lands){check(engine.game.getPermanent(source.getId()).isTapped()==initialTaps.get(source.getId()),name+"_PARTIAL_TAP");check(engine.game.getPermanent(source.getId()).getCounters(engine.game).equals(initialCounters.get(source.getId())),name+"_REMOVED_COUNTER");}}
                else {
                    check(engine.paid.get(),name+"_AUTO_FALLBACK_"+payment.reason());check("GAME_ASK".equals(next.prompt.get("kind").getAsString()),name+"_PAYMENT_NOT_FINISHED");
                    check(payment.report().get("native_auto_payment_manual_windows").getAsInt()==0,name+"_MANUAL_INPUT");check(payment.report().get("native_auto_payment_completed").getAsInt()==(name.equals("affinity-zero")?0:1),name+"_COMPLETION_UNPROVEN");
                    int taps=0;for(Card source:lands)if(engine.game.getPermanent(source.getId()).isTapped())taps++;
                    if(name.equals("denizen"))check(taps==1,"DENIZEN_MUST_LEAVE_ONE_MOUNTAIN");if(name.equals("double-red"))check(taps==2,"DOUBLE_RED_NEEDS_BOTH");if(doubler)check(taps==1,"DOUBLER_USED_EXTRA_SOURCE");
                    if(name.equals("chosen-x") || name.equals("commander-tax"))check(taps==3,"FINALIZED_EXTRA_MANA_NOT_PAID");
                    if(name.equals("cost-reducer"))check(taps==1,"REDUCED_COST_OVERPAID");if(name.equals("cost-increase"))check(taps==2,"INCREASED_COST_UNDERPAID");
                    if(name.equals("safe-before-life"))check(!engine.game.getPermanent(lands.get(0).getId()).isTapped() && engine.payer.getLife()==20,"AUTO_USED_LIFE_SOURCE");
                    if(name.equals("affinity-enforcer"))check(taps==3,"AFFINITY_ENFORCER_MUST_PAY_REDUCED_THREE");
                    if(name.equals("affinity-thoughtcast")){check(taps==1,"AFFINITY_THOUGHTCAST_OVERPAID");check(engine.game.getPermanent(lands.get(0).getId()).isTapped(),"AFFINITY_THOUGHTCAST_WRONG_COLOR");}
                    if(name.equals("affinity-zero"))check(taps==0,"FREE_AFFINITY_TAPPED_SOURCE");
                    if(name.equals("artifact-flying"))check(taps==1,"FLYING_PREVENTED_PAYMENT");
                    if(name.equals("artifact-null-rod-basic"))check(taps==1 && !engine.game.getPermanent(lands.get(0).getId()).isTapped() && engine.game.getPermanent(lands.get(1).getId()).isTapped(),"NULL_ROD_BYPASSED_OR_BASIC_UNUSED");
                    if(name.startsWith("generated-"))check(taps==2,"GENERATED_NONMINIMAL_TAPS");
                    if(!ability)check(engine.game.getStack().size()==1 && engine.game.getStack().getFirst().getSourceId().equals(spell.getId()),name+"_SPELL_NOT_STACKED");
                }
                if(engine.lastCommand!=null) {
                    int sent=engine.nativeSourceResponses;engine.bridge.execute(engine.lastCommand);
                    check(engine.nativeSourceResponses==sent,"BRIDGE_REPLAYED_PAYMENT");
                }
                if(name.equals("stale-before-submit"))check(engine.nativeSourceResponses==1,"STALE_PLAN_WAS_SUBMITTED");
                System.out.println("Payment production path: "+name+" "+payment.report());
            } finally {payment.close();}
        }
    }
    static void answer(Engine engine,ManaforgeGameplaySession.Advance next,boolean value){
        JsonObject command=new JsonObject();command.addProperty("protocol",1);command.addProperty("command","respond");command.addProperty("request_id","manual-choice-"+UUID.randomUUID());
        command.add("game_id",next.state.get("game_id"));command.add("decision_id",next.prompt.get("decision_id"));command.addProperty("kind","boolean");command.addProperty("value",value);
        check(new JsonPrimitive(true).equals(engine.submit(command).get("accepted")),"MANUAL_PHYREXIAN_CHOICE_REJECTED");
    }
    static void phyrexianThenOrdinary() throws Exception {
        try(Engine engine=new Engine();NativeAutomaticPayment payment=new NativeAutomaticPayment("acceptance",engine.payer.getId().toString(),Mode.AUTO)){
            List<Card> lands=new ArrayList<>();for(int i=0;i<3;i++)lands.add(engine.load(new mage.cards.basiclands.Mountain(engine.payer.getId(),info("Mountain")),Zone.BATTLEFIELD));
            Card skirge=engine.load(new mage.cards.v.VaultSkirge(engine.payer.getId(),info("Vault Skirge")),Zone.HAND);engine.cast(skirge,null);
            ManaforgeAutomaticEngine wrapper=new ManaforgeAutomaticEngine(engine,payment,()->false);ManaforgeGameplaySession.Advance next=wrapper.advance(0);
            check("GAME_ASK".equals(next.prompt.get("kind").getAsString()) && !engine.paid.get(),"PHYREXIAN_LIFE_MUST_ASK");
            check(engine.payer.getLife()==20 && payment.report().get("native_auto_payment_steps").getAsInt()==0,"AUTO_CHOSE_PHYREXIAN_LIFE");
            answer(engine,next,true);next=wrapper.advance(next.prompt.get("decision_id").getAsLong());
            check(engine.paid.get() && engine.payer.getLife()==18,"EXPLICIT_PHYREXIAN_LIFE_NOT_PAID");
            check(payment.report().get("native_auto_payment_completed").getAsInt()==1,"PHYREXIAN_GENERIC_NOT_AUTOMATIC");
            answer(engine,next,false);engine.running.get(2,TimeUnit.SECONDS);engine.game.getStack().resolve(engine.game);
            check(engine.game.getPermanent(skirge.getId())!=null,"PHYREXIAN_FLYER_NOT_RESOLVED");
            for(int spellIndex=0;spellIndex<2;spellIndex++){
                engine.paid.set(false);Card spell=engine.load(new Probe(engine.payer.getId(),"{R}"),Zone.HAND);int life=engine.payer.getLife();engine.cast(spell,null);
                next=wrapper.advance(next.prompt.get("decision_id").getAsLong());
                check(engine.paid.get(),"AFTER_PHYREXIAN_AUTO_FALLBACK_"+payment.reason());check(engine.payer.getLife()==life,"LATER_AUTO_SPENT_LIFE");
                check(payment.report().get("native_auto_payment_completed").getAsInt()==spellIndex+2,"PHYREXIAN_CHOICE_POISONED_LATER_PAYMENT");
                check("AUTO".equals(payment.report().get("native_auto_payment_mode").getAsString()),"PHYREXIAN_CHANGED_PAYMENT_MODE");
                check(engine.game.getStack().size()==1 && engine.game.getStack().getFirst().getSourceId().equals(spell.getId()),"LATER_SPELL_NOT_ON_STACK");
                answer(engine,next,false);engine.running.get(2,TimeUnit.SECONDS);engine.game.getStack().resolve(engine.game);
            }
            check(payment.report().get("native_auto_payment_manual_windows").getAsInt()==0,"LATER_SPELL_REQUIRED_MANUAL_MANA");
            check(lands.stream().allMatch(card->engine.game.getPermanent(card.getId()).isTapped()),"SEQUENTIAL_PAYMENT_WRONG_SOURCES");
            System.out.println("Payment production path: phyrexian-life-then-two-ordinary-casts "+payment.report());
        }
    }
    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("GAME-payment-acceptance-owner");String mountain="mage.cards.basiclands.Mountain",forest="mage.cards.basiclands.Forest",island="mage.cards.basiclands.Island";
        phyrexianThenOrdinary();
        String[] artifacts={"mage.cards.s.SeatOfTheSynod","mage.cards.g.GreatFurnace","mage.cards.v.VaultOfWhispers",mountain};
        scenario("artifact-flying","{U}",new String[]{island,island},false,false,false,false);
        scenario("affinity-enforcer","{7}",artifacts,false,false,false,false);
        scenario("affinity-thoughtcast","{4}{U}",artifacts,false,false,false,false);
        scenario("affinity-zero","{4}",artifacts,false,false,false,false);
        scenario("artifact-null-rod","{C}",new String[]{"mage.cards.s.SolRing"},true,false,false,false);
        scenario("artifact-null-rod-basic","{U}",new String[]{"mage.cards.s.SeatOfTheSynod",island},false,false,false,false);
        scenario("denizen","{R}",new String[]{mountain,mountain},false,false,false,false);
        scenario("double-red","{R}{R}",new String[]{mountain,mountain},false,false,false,false);
        scenario("chosen-x","{X}{R}",new String[]{mountain,mountain,mountain},false,false,false,false);
        scenario("phyrexian-mana","{R/P}",new String[]{mountain},false,false,false,false);
        scenario("cost-reducer","{1}{R}",new String[]{mountain},false,false,false,false);
        scenario("cost-increase","{R}",new String[]{mountain,mountain},false,false,false,false);
        scenario("commander-tower","{R}",new String[]{"mage.cards.c.CommandTower"},false,false,false,false);
        scenario("commander-signet","{G}",new String[]{"mage.cards.a.ArcaneSignet"},false,false,false,false);
        scenario("commander-tower-wrong-color","{U}",new String[]{"mage.cards.c.CommandTower"},true,false,false,false);
        scenario("commander-tax","{R}",new String[]{mountain,mountain,mountain},false,false,false,false);
        scenario("counters","{R}",new String[]{mountain},false,false,true,false);
        scenario("hybrid","{R/G}",new String[]{forest},false,false,false,false);
        scenario("snow","{S}",new String[]{"mage.cards.basiclands.SnowCoveredMountain"},false,false,false,false);
        scenario("wrong-snow-source","{S}",new String[]{mountain},true,false,false,false);
        scenario("rock-colorless","{C}",new String[]{"mage.cards.s.SolRing"},false,false,false,false);
        scenario("sick-mana-creature","{G}",new String[]{"mage.cards.l.LlanowarElves"},true,false,false,false);
        scenario("tapped-source","{R}",new String[]{mountain},true,false,false,false);
        scenario("mana-creature","{G}",new String[]{"mage.cards.l.LlanowarElves"},false,false,false,false);
        scenario("variable-mana","{G}{G}",new String[]{"mage.cards.p.PriestOfTitania","mage.cards.l.LlanowarElves"},false,false,false,false);
        scenario("safe-before-life","{R}",new String[]{"mage.cards.c.CityOfBrass",mountain},false,false,false,false);
        scenario("filter","{U}",new String[]{mountain,"mage.cards.s.ShimmeringGrotto"},false,false,false,false);
        scenario("dualland","{U}",new String[]{"mage.cards.t.TropicalIsland"},false,false,false,false);
        scenario("mana-doubler","{R}{R}",new String[]{mountain},false,false,false,true);
        scenario("activation","{1}{U}",new String[]{mountain,island},false,true,false,false);
        scenario("nonstack-activation","{R}",new String[]{mountain},false,true,false,false);
        scenario("stale-before-submit","{R}",new String[]{mountain},false,false,false,false);
        scenario("manual-mode","{R}",new String[]{mountain},true,false,false,false);
        scenario("full-control-mode","{R}",new String[]{mountain},true,false,false,false);
        scenario("insufficient","{R}{R}",new String[]{mountain},true,false,false,false);
        scenario("manabarbs","{R}",new String[]{mountain},true,false,false,false);
        scenario("life-source","{R}",new String[]{"mage.cards.c.CityOfBrass"},true,false,false,false);
        scenario("sacrifice-source","{B}{B}",new String[]{"mage.cards.p.PeatBog"},true,false,false,false);
        Random generated=new Random(20261110L);
        for(int seed=0;seed<12;seed++) {
            int red=1+generated.nextInt(2),green=1+generated.nextInt(2);String[] sources=new String[red+green];Arrays.fill(sources,0,red,mountain);Arrays.fill(sources,red,sources.length,forest);
            scenario("generated-20261110-"+seed,"{R}{G}",sources,false,false,seed%2==0,false);
        }
    }
}

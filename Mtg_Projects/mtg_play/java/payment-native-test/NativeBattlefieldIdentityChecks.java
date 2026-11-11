import java.util.*;
import java.util.concurrent.TimeUnit;
import mage.game.events.PlayerQueryEvent;
import mage.cards.Card;
import mage.constants.*;
import mage.game.permanent.Permanent;
import mage.game.permanent.token.SoldierToken;
import mage.view.GameView;

/** Hosted-only real native lifecycle proof. No manually assigned zone counters. */
public final class NativeBattlefieldIdentityChecks {
    static void check(boolean value,String code){if(!value)throw new AssertionError(code);}
    interface Checked {void run() throws Exception;}
    static void rejects(Checked action,String code) throws Exception {
        try{action.run();}catch(IllegalArgumentException | IllegalStateException expected){return;}throw new AssertionError(code);
    }
    static void pause(NativePaymentAcceptanceChecks.Engine e,Runnable change) throws Exception {
        check(e.running==null || e.running.isDone(),"PREVIOUS_IDENTITY_WORKER_ACTIVE");
        check(e.queries.isEmpty(),"PREVIOUS_IDENTITY_QUERY_PENDING");
        e.running=e.thread.submit(()->{change.run();e.game.applyEffects();
            for(Permanent object:e.game.getBattlefield().getAllPermanents())System.out.println("IDENTITY_FIXTURE after-effects id="+object.getId()+" zone="+e.game.getState().getZone(object.getId())+" generation="+object.getZoneChangeCounter(e.game)+" present=true");
            e.game.saveState(false);e.payer.chooseUse(Outcome.Benefit,"Identity snapshot",null,e.game);});
        // Wait for either the expected native query or the worker failure, rather
        // than hiding a failed transition behind the payment fixture's timeout.
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);
        PlayerQueryEvent query=null;
        while(query==null && System.nanoTime()<deadline){
            if(e.running.isDone())e.running.get();
            query=e.queries.poll(20,TimeUnit.MILLISECONDS);
        }
        check(query!=null && query.getQueryType()==PlayerQueryEvent.QueryType.ASK && query.getPlayerId().equals(e.payer.getId()),"IDENTITY_CHECKPOINT_QUERY");
        Object monitor=e.response.get(e.payer);
        while(System.nanoTime()<deadline){
            if(e.running.isDone())e.running.get();
            synchronized(monitor){if(Boolean.TRUE.equals(e.opened.get(e.payer))){e.view=new GameView(e.game.getState(),e.game,e.payer.getId(),null);return;}}
            Thread.yield();
        }
        throw new AssertionError("IDENTITY_CHECKPOINT_NOT_OPEN");
    }
    static void resume(NativePaymentAcceptanceChecks.Engine e) throws Exception {
        e.payer.setResponseBoolean(false);e.running.get(5,TimeUnit.SECONDS);
        synchronized(e.response.get(e.payer)){check(!Boolean.TRUE.equals(e.opened.get(e.payer)),"IDENTITY_RESPONSE_STILL_OPEN");}
        check(e.queries.isEmpty(),"IDENTITY_QUERY_NOT_CONSUMED");
    }
    static Permanent permanent(NativePaymentAcceptanceChecks.Engine e,Card card){
        Permanent result=e.game.getPermanent(card.getId());check(result!=null,"FIXTURE_PERMANENT_MISSING_"+card.getName());return result;
    }
    static BattlefieldIdentityRegistry.Snapshot snapshot(NativePaymentAcceptanceChecks.Engine e,UUID viewer) throws Exception {
        return NativeBattlefieldIdentity.capturePaused(e.game,viewer,e.game.getState().getApplyEffectsCounter(),()->new GameView(e.game.getState(),e.game,viewer,null));
    }
    static BattlefieldIdentityRegistry.Member member(List<BattlefieldIdentityRegistry.Member> list,UUID id){return list.stream().filter(m->m.objectReference.equals(id.toString())).findFirst().orElseThrow(()->new AssertionError("MEMBER_MISSING"));}
    static final class Fixture implements AutoCloseable {
        final NativePaymentAcceptanceChecks.Engine e=new NativePaymentAcceptanceChecks.Engine();
        final BattlefieldIdentityRegistry registry=new BattlefieldIdentityRegistry(e.game.getId());
        Fixture() throws Exception {}
        Card load(Card original){
            e.load(original,Zone.HAND);Card registered=e.game.getCard(original.getId());
            check(registered!=null,"REGISTERED_CARD_MISSING");trace("registered",registered);return registered;
        }
        Card forest(){return load(new mage.cards.basiclands.Forest(e.payer.getId(),NativePaymentAcceptanceChecks.info("Forest")));}
        Card bear(){return load(new mage.cards.g.GrizzlyBears(e.payer.getId(),NativePaymentAcceptanceChecks.info("Grizzly Bears")));}
        Card battlefieldCard(Card registered){
            // ZonesHandler changes a DoubleFacedCard entry event's target to its
            // left half. The composite ID never denotes its live permanent.
            return registered instanceof mage.cards.DoubleFacedCard?((mage.cards.DoubleFacedCard)registered).getLeftHalfCard():registered;
        }
        void enter(Card registered){
            check(registered.putOntoBattlefield(e.game,Zone.HAND,registered.getSpellAbility(),e.payer.getId()),"NATIVE_ENTRY");
            Card active=battlefieldCard(registered);trace("entered",active);permanent(e,active);
        }
        void trace(String stage,Card card){
            System.out.println("IDENTITY_FIXTURE "+stage+" id="+card.getId()+" zone="+e.game.getState().getZone(card.getId())+" generation="+card.getZoneChangeCounter(e.game)+" present="+(e.game.getPermanent(card.getId())!=null));
        }
        void observe(Card... cards) throws Exception {
            for(Card card:cards){trace("checkpoint",card);permanent(e,card);}
            registry.reconcile(snapshot(e,e.payer.getId()));
            for(Card card:cards)check(registry.incarnation(card.getId())!=null,"INITIAL_INCARNATION_MISSING");
        }
        public void close() throws Exception {try{e.close();}finally{registry.close();}}
    }
    static void ordinaryChanges() throws Exception {
        try(Fixture f=new Fixture()){
            Card creature=f.bear(),equipment=f.load(new mage.cards.b.Bonesplitter(f.e.payer.getId(),NativePaymentAcceptanceChecks.info("Bonesplitter")));
            pause(f.e,()->{f.enter(creature);f.enter(equipment);});f.observe(creature,equipment);
            String before=f.registry.incarnation(creature.getId());resume(f.e);
            pause(f.e,()->{
                Permanent current=permanent(f.e,creature);check(current.tap(equipment.getSpellAbility(),f.e.game),"NATIVE_TAP");
                current.getCounters(f.e.game).addCounter(mage.counters.CounterType.P1P1.createInstance());
                current.damage(1,equipment.getId(),equipment.getSpellAbility(),f.e.game);
                permanent(f.e,equipment).attachTo(creature.getId(),equipment.getSpellAbility(),f.e.game);
            });f.observe(creature,equipment);
            Permanent current=permanent(f.e,creature);
            check(current.isTapped() && current.getDamage()==1 && current.getCounters(f.e.game).getCount(mage.counters.CounterType.P1P1)==1 && permanent(f.e,equipment).getAttachedTo().equals(creature.getId()),"NATIVE_CHARACTERISTIC_CHANGES");
            check(before.equals(f.registry.incarnation(creature.getId())),"ORDINARY_UPDATE_IDENTITY");resume(f.e);
        }
    }
    static void transformation() throws Exception {
        try(Fixture f=new Fixture()){
            Card composite=f.load(new mage.cards.d.DelverOfSecrets(f.e.payer.getId(),NativePaymentAcceptanceChecks.info("Delver of Secrets")));
            Card front=f.battlefieldCard(composite);check(!front.getId().equals(composite.getId()),"DFC_DISTINCT_NATIVE_IDS");
            pause(f.e,()->f.enter(composite));f.observe(front);
            check(f.e.game.getPermanent(composite.getId())==null,"COMPOSITE_IS_NOT_PERMANENT");
            String before=f.registry.incarnation(front.getId());int generation=permanent(f.e,front).getZoneChangeCounter(f.e.game);resume(f.e);
            pause(f.e,()->check(permanent(f.e,front).transform(front.getSpellAbility(),f.e.game),"NATIVE_TRANSFORM"));f.observe(front);
            check(permanent(f.e,front).isTransformed(),"NATIVE_TRANSFORMED_FACE");
            check(generation==permanent(f.e,front).getZoneChangeCounter(f.e.game) && before.equals(f.registry.incarnation(front.getId())),"TRANSFORM_INCARNATION");resume(f.e);
        }
    }
    static void blink() throws Exception {
        try(Fixture f=new Fixture()){
            Card land=f.forest();pause(f.e,()->f.enter(land));f.observe(land);
            String before=f.registry.incarnation(land.getId());int generation=permanent(f.e,land).getZoneChangeCounter(f.e.game);
            String handle=member(f.registry.project(snapshot(f.e,f.e.payer.getId())),land.getId()).handle;resume(f.e);
            pause(f.e,()->{check(permanent(f.e,land).moveToZone(Zone.EXILED,land.getSpellAbility(),f.e.game,false),"NATIVE_LEAVE");check(f.e.game.getPermanent(land.getId())==null,"NATIVE_ABSENCE");check(f.e.game.getCard(land.getId()).putOntoBattlefield(f.e.game,Zone.EXILED,land.getSpellAbility(),f.e.payer.getId()),"NATIVE_REENTER");});
            check(permanent(f.e,land).getZoneChangeCounter(f.e.game)>generation,"NATIVE_GENERATION_NOT_ADVANCED");
            BattlefieldIdentityRegistry.Result result=f.registry.reconcile(snapshot(f.e,f.e.payer.getId()));
            check(result.removed.contains(before) && !before.equals(f.registry.incarnation(land.getId())),"COALESCED_BLINK");
            check(f.registry.resolve(f.e.payer.getId(),handle)==null,"STALE_BLINK_HANDLE");resume(f.e);
        }
    }
    static void transfer(NativePaymentAcceptanceChecks.Engine e,Card land) {
        // A direct changeControllerId is reset by the next native control-layer pass.
        // Install the same continuous effect used by native control-changing cards.
        mage.abilities.effects.common.continuous.GainControlTargetEffect effect=new mage.abilities.effects.common.continuous.GainControlTargetEffect(Duration.Custom,e.opponent.getId());
        effect.setTargetPointer(new mage.target.targetpointer.FixedTarget(permanent(e,land),e.game));
        mage.abilities.Ability source=new mage.abilities.common.SimpleActivatedAbility(Zone.BATTLEFIELD,effect,new mage.abilities.costs.mana.ManaCostsImpl<>("0"));
        source.setSourceId(land.getId());source.setControllerId(e.payer.getId());
        e.game.addEffect(effect,source);
    }
    static void control() throws Exception {
        try(Fixture f=new Fixture()){
            Card land=f.forest();pause(f.e,()->f.enter(land));f.observe(land);
            String before=f.registry.incarnation(land.getId()),handle=member(f.registry.project(snapshot(f.e,f.e.payer.getId())),land.getId()).handle;resume(f.e);
            System.out.println("IDENTITY_CONTROL before controller="+permanent(f.e,land).getControllerId()+" generation="+permanent(f.e,land).getZoneChangeCounter(f.e.game)+" handle="+handle);
            pause(f.e,()->transfer(f.e,land));f.observe(land);
            check(permanent(f.e,land).getControllerId().equals(f.e.opponent.getId()),"CONTROL_NATIVE_CONTROLLER");
            System.out.println("IDENTITY_CONTROL after controller="+permanent(f.e,land).getControllerId()+" generation="+permanent(f.e,land).getZoneChangeCounter(f.e.game)+" oldHandleResolved="+(f.registry.resolve(f.e.payer.getId(),handle)!=null));
            check(before.equals(f.registry.incarnation(land.getId())),"CONTROL_INCARNATION");check(f.registry.resolve(f.e.payer.getId(),handle)==null,"CONTROL_HANDLE");
            check(member(f.registry.project(snapshot(f.e,f.e.payer.getId())),land.getId()).seat.equals(f.registry.seat(f.e.opponent.getId())),"CONTROL_SEAT");resume(f.e);
        }
    }
    static void concealment() throws Exception {
        try(Fixture f=new Fixture()){
            Card creature=f.bear();pause(f.e,()->f.enter(creature));f.observe(creature);
            String handle=member(f.registry.project(snapshot(f.e,f.e.payer.getId())),creature.getId()).handle;resume(f.e);
            pause(f.e,()->permanent(f.e,creature).setFaceDown(true,f.e.game));f.observe(creature);
            check(permanent(f.e,creature).isFaceDown(f.e.game),"NATIVE_FACE_DOWN");
            check(f.registry.project(snapshot(f.e,f.e.payer.getId())).isEmpty() && f.registry.resolve(f.e.payer.getId(),handle)==null,"CONCEALED_HANDLE");resume(f.e);
            pause(f.e,()->permanent(f.e,creature).setFaceDown(false,f.e.game));
            check(!member(f.registry.project(snapshot(f.e,f.e.payer.getId())),creature.getId()).handle.equals(handle),"REVEAL_REUSED_HANDLE");resume(f.e);
        }
    }
    static void tokens() throws Exception {
        try(Fixture f=new Fixture()){
            Card source=f.forest();SoldierToken token=new SoldierToken();
            pause(f.e,()->{f.enter(source);check(token.putOntoBattlefield(1,f.e.game,source.getSpellAbility(),f.e.payer.getId(),false,false,null,null,false,Collections.emptyList()),"TOKEN_ENTER");});
            UUID first=token.getLastAddedTokenIds().get(0);f.registry.reconcile(snapshot(f.e,f.e.payer.getId()));String before=f.registry.incarnation(first);check(before!=null,"TOKEN_IDENTITY");resume(f.e);
            pause(f.e,()->{check(f.e.game.getPermanent(first).moveToZone(Zone.EXILED,source.getSpellAbility(),f.e.game,false),"TOKEN_LEAVE");check(token.putOntoBattlefield(1,f.e.game,source.getSpellAbility(),f.e.payer.getId(),false,false,null,null,false,Collections.emptyList()),"TOKEN_RECREATE");});
            UUID second=token.getLastAddedTokenIds().get(0);BattlefieldIdentityRegistry.Result result=f.registry.reconcile(snapshot(f.e,f.e.payer.getId()));
            check(result.removed.contains(before) && f.registry.incarnation(first)==null,"TOKEN_REMOVAL");check(!first.equals(second) && f.registry.incarnation(second)!=null && !before.equals(f.registry.incarnation(second)),"TOKEN_REPLACEMENT_IDENTITY");resume(f.e);
        }
    }
    static void viewersRejectionAndDisposal() throws Exception {
        try(Fixture f=new Fixture()){
            Card land=f.forest();pause(f.e,()->f.enter(land));f.observe(land);
            BattlefieldIdentityRegistry.Snapshot first=snapshot(f.e,f.e.payer.getId());
            String before=f.registry.incarnation(land.getId());
            BattlefieldIdentityRegistry.Member a=member(f.registry.project(first),land.getId()),b=member(f.registry.project(snapshot(f.e,f.e.opponent.getId())),land.getId());
            check(!a.handle.equals(b.handle) && a.seat.equals(b.seat),"VIEWER_ISOLATION");check(f.registry.resolve(f.e.opponent.getId(),a.handle)==null,"FOREIGN_HANDLE");
            rejects(()->NativeBattlefieldIdentity.capturePaused(f.e.game,f.e.payer.getId(),first.cycle-1,()->f.e.view),"STALE_CAPTURE");
            rejects(()->f.registry.reconcile(new BattlefieldIdentityRegistry.Snapshot(UUID.randomUUID(),first.viewer,first.cycle,first.seats,first.permanents,first.admitted)),"FOREIGN_GAME");
            rejects(()->f.registry.reconcile(new BattlefieldIdentityRegistry.Snapshot(first.game,first.viewer,first.cycle-1,first.seats,first.permanents,first.admitted)),"STALE_RECONCILE");
            rejects(()->f.registry.reconcile(new BattlefieldIdentityRegistry.Snapshot(first.game,first.viewer,first.cycle,first.seats,Collections.singletonList(new BattlefieldIdentityRegistry.Observation(land.getId(),-1,f.e.payer.getId())),Collections.emptyMap())),"MISSING_GENERATION");
            check(before.equals(f.registry.incarnation(land.getId())) && f.registry.resolve(f.e.payer.getId(),a.handle)!=null,"REJECTION_MUTATED_STATE");resume(f.e);
            rejects(()->NativeBattlefieldIdentity.capturePaused(f.e.game,f.e.payer.getId(),first.cycle,()->f.e.view),"UNPAUSED_READ");
            f.registry.close();check(f.registry.incarnation(land.getId())==null && f.registry.seat(f.e.payer.getId())==null && f.registry.resolve(f.e.payer.getId(),a.handle)==null,"DISPOSE_LEAK");rejects(()->f.registry.project(first),"CLOSED_REOPEN");
        }
    }
    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("GAME-identity-acceptance-owner");
        String[] names={"ordinary changes","transformation","coalesced blink","control transfer","concealment","tokens","viewer rejection and disposal"};
        Checked[] scenarios={NativeBattlefieldIdentityChecks::ordinaryChanges,NativeBattlefieldIdentityChecks::transformation,NativeBattlefieldIdentityChecks::blink,NativeBattlefieldIdentityChecks::control,NativeBattlefieldIdentityChecks::concealment,NativeBattlefieldIdentityChecks::tokens,NativeBattlefieldIdentityChecks::viewersRejectionAndDisposal};
        for(int i=0;i<scenarios.length;i++){scenarios[i].run();System.out.println("Battlefield identity passed: "+names[i]);}
    }
}

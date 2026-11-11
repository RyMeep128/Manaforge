import java.util.*;
import java.util.concurrent.TimeUnit;
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
        e.running=e.thread.submit(()->{change.run();e.game.applyEffects();e.payer.chooseUse(Outcome.Benefit,"Identity snapshot",null,e.game);});e.advance(0);
    }
    static void resume(NativePaymentAcceptanceChecks.Engine e) throws Exception {e.payer.setResponseBoolean(false);e.running.get(5,TimeUnit.SECONDS);}
    static BattlefieldIdentityRegistry.Snapshot snapshot(NativePaymentAcceptanceChecks.Engine e,UUID viewer) throws Exception {
        return NativeBattlefieldIdentity.capturePaused(e.game,viewer,e.game.getState().getApplyEffectsCounter(),()->new GameView(e.game.getState(),e.game,viewer,null));
    }
    static BattlefieldIdentityRegistry.Member member(List<BattlefieldIdentityRegistry.Member> list,UUID id){return list.stream().filter(m->m.objectReference.equals(id.toString())).findFirst().orElseThrow(()->new AssertionError("MEMBER_MISSING"));}
    public static void main(String[] args) throws Exception {
        Thread.currentThread().setName("GAME-identity-acceptance-owner");
        try(NativePaymentAcceptanceChecks.Engine e=new NativePaymentAcceptanceChecks.Engine();BattlefieldIdentityRegistry registry=new BattlefieldIdentityRegistry(e.game.getId())){
            Card land=e.load(new mage.cards.basiclands.Forest(e.payer.getId(),NativePaymentAcceptanceChecks.info("Forest")),Zone.HAND);
            Card delver=e.load(new mage.cards.d.DelverOfSecrets(e.payer.getId(),NativePaymentAcceptanceChecks.info("Delver of Secrets")),Zone.HAND);
            Card equipment=e.load(new mage.cards.b.Bonesplitter(e.payer.getId(),NativePaymentAcceptanceChecks.info("Bonesplitter")),Zone.HAND);
            pause(e,()->{check(equipment.putOntoBattlefield(e.game,Zone.HAND,equipment.getSpellAbility(),e.payer.getId()),"EQUIPMENT_ENTER");check(land.putOntoBattlefield(e.game,Zone.HAND,land.getSpellAbility(),e.payer.getId()),"LAND_ENTER");check(delver.putOntoBattlefield(e.game,Zone.HAND,delver.getSpellAbility(),e.payer.getId()),"DELVER_ENTER");});
            BattlefieldIdentityRegistry.Snapshot first=snapshot(e,e.payer.getId());registry.reconcile(first);
            String incarnation=registry.incarnation(land.getId()),transformed=registry.incarnation(delver.getId());int generation=e.game.getPermanent(land.getId()).getZoneChangeCounter(e.game);
            BattlefieldIdentityRegistry.Member a=member(registry.project(first),land.getId()),b=member(registry.project(snapshot(e,e.opponent.getId())),land.getId());
            check(!a.handle.equals(b.handle) && a.seat.equals(b.seat),"VIEWER_ISOLATION");check(registry.resolve(e.opponent.getId(),a.handle)==null,"FOREIGN_HANDLE");
            rejects(()->NativeBattlefieldIdentity.capturePaused(e.game,e.payer.getId(),first.cycle-1,()->e.view),"STALE_CAPTURE");
            rejects(()->registry.reconcile(new BattlefieldIdentityRegistry.Snapshot(UUID.randomUUID(),first.viewer,first.cycle,first.seats,first.permanents,first.admitted)),"FOREIGN_GAME");
            rejects(()->registry.reconcile(new BattlefieldIdentityRegistry.Snapshot(first.game,first.viewer,first.cycle-1,first.seats,first.permanents,first.admitted)),"STALE_RECONCILE");
            rejects(()->registry.reconcile(new BattlefieldIdentityRegistry.Snapshot(first.game,first.viewer,first.cycle,first.seats,Collections.singletonList(new BattlefieldIdentityRegistry.Observation(land.getId(),-1,e.payer.getId())),Collections.emptyMap())),"MISSING_GENERATION");
            check(incarnation.equals(registry.incarnation(land.getId())) && registry.resolve(e.payer.getId(),a.handle)!=null,"REJECTION_MUTATED_STATE");resume(e);
            rejects(()->NativeBattlefieldIdentity.capturePaused(e.game,e.payer.getId(),first.cycle,()->e.view),"UNPAUSED_READ");
            pause(e,()->{
                Permanent permanent=e.game.getPermanent(delver.getId());permanent.tap(land.getSpellAbility(),e.game);
                permanent.getCounters(e.game).addCounter(mage.counters.CounterType.P1P1.createInstance());
                permanent.damage(1,land.getId(),land.getSpellAbility(),e.game);
                check(permanent.transform(land.getSpellAbility(),e.game),"NATIVE_TRANSFORM");
                e.game.getPermanent(equipment.getId()).attachTo(delver.getId(),equipment.getSpellAbility(),e.game);
            });registry.reconcile(snapshot(e,e.payer.getId()));
            check(e.game.getPermanent(delver.getId()).isTransformed() && e.game.getPermanent(delver.getId()).isTapped() && e.game.getPermanent(delver.getId()).getDamage()==1 && e.game.getPermanent(equipment.getId()).getAttachedTo().equals(delver.getId()),"NATIVE_CHARACTERISTIC_CHANGES");
            check(transformed.equals(registry.incarnation(delver.getId())) && incarnation.equals(registry.incarnation(land.getId())),"ORDINARY_UPDATE_IDENTITY");resume(e);
            pause(e,()->{e.game.getPermanent(equipment.getId()).unattach(e.game);check(e.game.getPermanent(land.getId()).moveToZone(Zone.EXILED,land.getSpellAbility(),e.game,false),"NATIVE_LEAVE");check(land.putOntoBattlefield(e.game,Zone.EXILED,land.getSpellAbility(),e.payer.getId()),"NATIVE_REENTER");});
            check(e.game.getPermanent(land.getId()).getZoneChangeCounter(e.game)>generation,"NATIVE_GENERATION_NOT_ADVANCED");
            BattlefieldIdentityRegistry.Result blink=registry.reconcile(snapshot(e,e.payer.getId()));
            check(!incarnation.equals(registry.incarnation(land.getId())) && blink.removed.contains(incarnation),"COALESCED_BLINK");check(registry.resolve(e.payer.getId(),a.handle)==null,"STALE_BLINK_HANDLE");
            String beforeControl=registry.incarnation(land.getId()),oldHandle=member(registry.project(snapshot(e,e.payer.getId())),land.getId()).handle;resume(e);
            pause(e,()->check(e.game.getPermanent(land.getId()).changeControllerId(e.opponent.getId(),e.game,land.getSpellAbility()),"CONTROL_TRANSFER"));
            registry.reconcile(snapshot(e,e.payer.getId()));check(beforeControl.equals(registry.incarnation(land.getId())),"CONTROL_INCARNATION");check(registry.resolve(e.payer.getId(),oldHandle)==null,"CONTROL_HANDLE");
            check(member(registry.project(snapshot(e,e.payer.getId())),land.getId()).seat.equals(registry.seat(e.opponent.getId())),"CONTROL_SEAT");
            String visibleDelver=member(registry.project(snapshot(e,e.payer.getId())),delver.getId()).handle;
            resume(e);
            pause(e,()->e.game.getPermanent(delver.getId()).setFaceDown(true,e.game));registry.reconcile(snapshot(e,e.payer.getId()));
            check(registry.project(snapshot(e,e.payer.getId())).stream().noneMatch(m->m.objectReference.equals(delver.getId().toString())),"CONCEALED_PROJECTION");check(registry.resolve(e.payer.getId(),visibleDelver)==null,"CONCEALED_HANDLE");resume(e);
            pause(e,()->e.game.getPermanent(delver.getId()).setFaceDown(false,e.game));
            check(!member(registry.project(snapshot(e,e.payer.getId())),delver.getId()).handle.equals(visibleDelver),"REVEAL_REUSED_HANDLE");resume(e);
            SoldierToken token=new SoldierToken();
            pause(e,()->check(token.putOntoBattlefield(1,e.game,land.getSpellAbility(),e.payer.getId(),false,false,null,null,false,Collections.emptyList()),"TOKEN_ENTER"));
            UUID tokenId=token.getLastAddedTokenIds().get(0);registry.reconcile(snapshot(e,e.payer.getId()));String tokenIdentity=registry.incarnation(tokenId);check(tokenIdentity!=null,"TOKEN_IDENTITY");resume(e);
            pause(e,()->{check(e.game.getPermanent(tokenId).moveToZone(Zone.EXILED,land.getSpellAbility(),e.game,false),"TOKEN_LEAVE");check(token.putOntoBattlefield(1,e.game,land.getSpellAbility(),e.payer.getId(),false,false,null,null,false,Collections.emptyList()),"TOKEN_RECREATE");});
            BattlefieldIdentityRegistry.Result tokens=registry.reconcile(snapshot(e,e.payer.getId()));check(tokens.removed.contains(tokenIdentity) && registry.incarnation(tokenId)==null,"TOKEN_REMOVAL");
            check(!tokenIdentity.equals(registry.incarnation(token.getLastAddedTokenIds().get(0))),"TOKEN_REPLACEMENT_IDENTITY");
            registry.close();check(registry.incarnation(land.getId())==null && registry.seat(e.payer.getId())==null && registry.resolve(e.payer.getId(),oldHandle)==null,"DISPOSE_LEAK");
            rejects(()->registry.project(first),"CLOSED_REOPEN");resume(e);
            System.out.println("Battlefield identity native lifecycle, viewer isolation, rejection and cleanup passed");
        }
    }
}

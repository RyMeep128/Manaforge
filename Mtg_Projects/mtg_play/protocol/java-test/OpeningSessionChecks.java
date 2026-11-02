import com.google.gson.*;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

/** Engine-free public fixture over real authenticated sockets and production admission. */
public final class OpeningSessionChecks {
    static void confirmationChecks(JsonObject before,JsonObject prompt,NativeCastCorrelation correlation,JsonObject after,JsonObject metadata) throws Exception {
        byte[] key=new byte[32];String hash=String.join("",java.util.Collections.nCopies(64,"0"));
        JsonObject client=ManaforgeOpeningLoopback.hello("session","human","synthetic-engine",hash,"client");
        JsonObject gateway=ManaforgeOpeningLoopback.hello("session","human","synthetic-engine",hash,"gateway");
        try(java.net.ServerSocket listener=new java.net.ServerSocket(0,1,java.net.InetAddress.getByName("127.0.0.1"));
            java.net.Socket peer=new java.net.Socket("127.0.0.1",listener.getLocalPort());
            manaforge.protocol.LoopbackFrameReader frames=new manaforge.protocol.LoopbackFrameReader(listener.accept())) {
            peer.setSoTimeout(5000);JsonObject signed=client.deepCopy();
            signed.getAsJsonObject("body").addProperty("proof",manaforge.protocol.ViewerAuthentication.computeProof(signed.toString(),key));
            manaforge.protocol.TextFrame.write(peer.getOutputStream(),signed.toString());peer.getOutputStream().flush();
            manaforge.protocol.GatewayHandshake.ViewerContext context=manaforge.protocol.GatewayHandshake.accept(frames,client.toString(),gateway.toString(),key,5000);
            manaforge.protocol.TextFrame.read(peer.getInputStream());
            ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();JsonObject snapshot=projection.project(before,prompt,false,true);
            String wire=OpeningProjectionChecks.choose(snapshot,0),id="public-choice";
            try(ManaforgeOpeningSession owner=new ManaforgeOpeningSession(context,projection,envelope(snapshot).toString())) {
                if(!owner.dispatch(wire,"raw-game","raw-human",42,8).shouldSubmit)throw new AssertionError("ABILITY_NOT_SUBMITTED");
                JsonObject command=owner.pollNative();NativeCastCorrelation.AbilityEvidence proof=correlation.abilityEvidence(before,prompt,command,after,metadata);
                if(proof==null)throw new AssertionError("ABILITY_PROOF_MISSING");
                for(int mode=0;mode<3;mode++) {
                    JsonObject other=command.deepCopy();other.addProperty("request_id","other-command");
                    try{owner.confirmAbility(mode==0?"wrong-id":id,mode==1?null:mode==2?correlation.abilityEvidence(before,prompt,other,after,metadata):proof);throw new AssertionError("BAD_PROOF_ACCEPTED");}
                    catch(IOException expected){if(!"CAST_EVIDENCE_MISMATCH".equals(expected.getMessage()))throw expected;}
                }
                JsonObject nextPrompt=OpeningProjectionChecks.priorityPrompt();nextPrompt.addProperty("decision_id",43);
                JsonObject followup=projection.projectPriorityWithoutStack(after,nextPrompt),update=envelope(followup);update.addProperty("message_id","next-priority");owner.observe(update.toString());
                JsonObject pass=JsonParser.parseString(OpeningProjectionChecks.perform(followup)).getAsJsonObject();pass.addProperty("message_id","early-pass");
                manaforge.protocol.SubmissionLedger.Prepared blocked=owner.dispatch(pass.toString(),"raw-game","raw-human",43,8);
                if(blocked.shouldSubmit || !"COMMAND_PENDING".equals(blocked.receipt().getAsJsonObject("body").get("code").getAsString()) || owner.pollNative()!=null)throw new AssertionError("UNRESOLVED_FOLLOWUP_ACCEPTED");
                JsonObject confirmed=owner.confirmAbility(id,proof);
                if(!"confirmed".equals(confirmed.getAsJsonObject("body").get("outcome").getAsString()) || !confirmed.equals(owner.confirmAbility(id,proof)))throw new AssertionError("CONFIRMATION_NOT_IDEMPOTENT");
                manaforge.protocol.SubmissionLedger.Prepared duplicate=owner.dispatch(wire,"raw-game","raw-human",42,8);
                if(duplicate.shouldSubmit || !confirmed.equals(duplicate.receipt()) || owner.pollNative()!=null)throw new AssertionError("CONFIRMED_COMMAND_REPLAYED");
                JsonObject stale=JsonParser.parseString(wire).getAsJsonObject();stale.addProperty("message_id","stale-ability");
                if(owner.dispatch(stale.toString(),"raw-game","raw-human",43,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("STALE_ABILITY_ACCEPTED");
                pass.addProperty("message_id","followup-pass");
                if(!owner.dispatch(pass.toString(),"raw-game","raw-human",43,8).shouldSubmit)throw new AssertionError("FOLLOWUP_NOT_ADMITTED");
                JsonObject nativePass=owner.pollNative();if(nativePass==null || !new JsonPrimitive(false).equals(nativePass.get("value")))throw new AssertionError("FOLLOWUP_NOT_NATIVE_PASS");
                if(owner.dispatch(pass.toString(),"raw-game","raw-human",43,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("FOLLOWUP_REPLAYED");
                owner.uncertain("followup-pass");
                JsonObject observation=envelope(projection.projectReadOnlyPriority(after,nextPrompt));observation.addProperty("message_id","post-pass-readonly");owner.observe(observation.toString());
                if(!"uncertain".equals(owner.receiptFor("followup-pass").getAsJsonObject("body").get("outcome").getAsString()) || owner.pollNative()!=null)throw new AssertionError("OBSERVATION_SETTLED_PASS");
                JsonObject resolved=after.deepCopy();resolved.add("stack",new JsonArray());
                JsonObject source=before.getAsJsonArray("hand").get(0).getAsJsonObject();resolved.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").add(source.deepCopy());
                String sourceId=source.get("id").getAsString(),stackId=after.getAsJsonArray("stack").get(0).getAsJsonObject().get("id").getAsString();
                JsonObject beforeMeta=metadata.deepCopy(),afterMeta=new JsonObject(),objects=new JsonObject(),entry=new JsonObject(),accepted=new JsonObject(),later=nextPrompt.deepCopy();
                beforeMeta.addProperty("priority_open",true);afterMeta.addProperty("priority_open",true);afterMeta.addProperty("status","ok");afterMeta.addProperty("cycle",8);
                entry.addProperty("incarnation",metadata.getAsJsonObject("objects").getAsJsonObject(stackId).get("source_incarnation").getAsLong()+1);entry.addProperty("owner","raw-human");entry.addProperty("controller","raw-human");objects.add(sourceId,entry);afterMeta.add("objects",objects);
                accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.addProperty("request_id","followup-pass");later.addProperty("decision_id",44);
                NativeCastCorrelation.PriorityEvidence passProof=proof.priorityEvidence(after,nextPrompt,nativePass,beforeMeta,accepted,resolved,later,afterMeta);
                if(passProof==null)throw new AssertionError("PRIORITY_PROOF_MISSING");
                for(int mode=0;mode<2;mode++)try{owner.confirmPriority(mode==0?"wrong":"followup-pass",mode==0?passProof:null);throw new AssertionError("WRONG_PRIORITY_PROOF_ACCEPTED");}
                    catch(IOException expected){if(!"PRIORITY_EVIDENCE_MISMATCH".equals(expected.getMessage()))throw expected;}
                JsonObject passReceipt=owner.confirmPriority("followup-pass",passProof);
                if(!"confirmed".equals(passReceipt.getAsJsonObject("body").get("outcome").getAsString()) || !passReceipt.equals(owner.confirmPriority("followup-pass",passProof)))throw new AssertionError("PRIORITY_NOT_CONFIRMED");
                manaforge.protocol.SubmissionLedger.Prepared passRetry=owner.dispatch(pass.toString(),"raw-game","raw-human",43,8);
                if(passRetry.shouldSubmit || !passReceipt.equals(passRetry.receipt()) || owner.pollNative()!=null)throw new AssertionError("CONFIRMED_PRIORITY_REPLAYED");
                JsonObject permanent=resolved.getAsJsonArray("players").get(0).getAsJsonObject().getAsJsonArray("battlefield").get(0).getAsJsonObject();permanent.addProperty("controller_name","raw-name");permanent.addProperty("owner_name","raw-name");
                resolved.addProperty("turn",1);resolved.addProperty("phase","PRECOMBAT_MAIN");resolved.addProperty("step","PRECOMBAT_MAIN");
                JsonObject postSnapshot=projection.project(resolved,later,true),postUpdate=envelope(postSnapshot);postUpdate.addProperty("message_id","post-resolution-priority");owner.observe(postUpdate.toString());
                JsonObject postCommand=JsonParser.parseString(OpeningProjectionChecks.perform(postSnapshot)).getAsJsonObject();postCommand.addProperty("message_id","post-resolution-pass");
                if(!owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8).shouldSubmit)throw new AssertionError("POST_RESOLUTION_PASS_NOT_ADMITTED");
                JsonObject nativePost=owner.pollNative();if(nativePost==null || nativePost.get("decision_id").getAsLong()!=44 || !new JsonPrimitive(false).equals(nativePost.get("value")))throw new AssertionError("WRONG_POST_RESOLUTION_PASS");
                if(owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("POST_RESOLUTION_PASS_REPLAYED");
                owner.uncertain("post-resolution-pass");postCommand.addProperty("message_id","blocked-fourth-command");
                manaforge.protocol.SubmissionLedger.Prepared fourth=owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8);
                if(fourth.shouldSubmit || !"COMMAND_PENDING".equals(fourth.receipt().getAsJsonObject("body").get("code").getAsString()) || owner.pollNative()!=null)throw new AssertionError("UNCERTAIN_POST_PASS_RELEASED");
                JsonObject phaseAfter=resolved.deepCopy(),phasePrompt=later.deepCopy(),phaseAccepted=accepted.deepCopy();phaseAfter.addProperty("phase","COMBAT");phaseAfter.addProperty("step","BEGIN_COMBAT");phasePrompt.addProperty("decision_id",45);phaseAccepted.addProperty("request_id","post-resolution-pass");
                NativeCastCorrelation.PriorityEvidence phaseProof=proof.phasePriorityEvidence(resolved,later,nativePost,afterMeta,phaseAccepted,phaseAfter,phasePrompt,afterMeta);
                if(phaseProof==null)throw new AssertionError("PHASE_PROOF_MISSING");
                JsonObject phaseReceipt=owner.confirmPriority("post-resolution-pass",phaseProof);
                if(!"confirmed".equals(phaseReceipt.getAsJsonObject("body").get("outcome").getAsString()) || !phaseReceipt.equals(owner.confirmPriority("post-resolution-pass",phaseProof)))throw new AssertionError("PHASE_CONFIRMATION_FAILED");
                postCommand.addProperty("message_id","post-resolution-pass");
                if(owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("CONFIRMED_PHASE_PASS_REPLAYED");
                JsonObject phaseUpdate=envelope(projection.projectReadOnlyPriority(phaseAfter,phasePrompt));phaseUpdate.addProperty("message_id","phase-observation");owner.observe(phaseUpdate.toString());
                owner.disconnected();if(!confirmed.equals(owner.receiptFor(id)))throw new AssertionError("CONFIRMATION_LOST_ON_DISCONNECT");
                if(!passReceipt.equals(owner.receiptFor("followup-pass")))throw new AssertionError("PRIORITY_CONFIRMATION_LOST");
                if(!phaseReceipt.equals(owner.receiptFor("post-resolution-pass")))throw new AssertionError("PHASE_CONFIRMATION_LOST");
            }
            attackConfirmationChecks(context);attackerConfirmationChecks(context);declaredAttackConfirmationChecks(context);
        }finally{java.util.Arrays.fill(key,(byte)0);}
    }
    static void declaredAttackConfirmationChecks(manaforge.protocol.GatewayHandshake.ViewerContext context) throws Exception {
        JsonObject before=OpeningProjectionChecks.attackState(),prompt=OpeningProjectionChecks.attackPrompt(),next=OpeningProjectionChecks.priorityPrompt();prompt.addProperty("decision_id",42);next.addProperty("decision_id",43);
        before.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));JsonObject after=before.deepCopy();after.addProperty("priority_player","raw-name");
        ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();JsonObject snapshot=projection.projectSelectedAttackFinish(before,prompt);String wire=OpeningProjectionChecks.perform(snapshot);
        try(ManaforgeOpeningSession owner=new ManaforgeOpeningSession(context,projection,envelope(snapshot).toString())) {
            if(!owner.dispatch(wire,"raw-game","raw-human",42,8).shouldSubmit)throw new AssertionError("DECLARATION_NOT_ADMITTED");JsonObject command=owner.pollNative(),accepted=new JsonObject();accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id"));
            NativeCastCorrelation.DeclaredAttackEvidence proof=NativeCastCorrelation.declaredAttackEvidence(before,prompt,command,OpeningProjectionChecks.attackMetadata(false),accepted,after,next,OpeningProjectionChecks.attackMetadata(true),"raw-card");
            JsonObject other=command.deepCopy(),otherPrompt=prompt.deepCopy();other.addProperty("decision_id",41);otherPrompt.addProperty("decision_id",41);
            NativeCastCorrelation.DeclaredAttackEvidence different=NativeCastCorrelation.declaredAttackEvidence(before,otherPrompt,other,OpeningProjectionChecks.attackMetadata(false),accepted,after,next,OpeningProjectionChecks.attackMetadata(true),"raw-card");
            if(proof==null || different==null)throw new AssertionError("DECLARATION_PROOF_MISSING");
            for(int mode=0;mode<3;mode++)try{owner.confirmDeclaredAttack(mode==0?"wrong":"land-action",mode==1?null:mode==2?different:proof);throw new AssertionError("BAD_DECLARATION_PROOF_ACCEPTED");}catch(IOException expected){if(!"DECLARED_ATTACK_EVIDENCE_MISMATCH".equals(expected.getMessage()))throw expected;}
            JsonObject receipt=owner.confirmDeclaredAttack("land-action",proof);if(!"confirmed".equals(receipt.getAsJsonObject("body").get("outcome").getAsString()) || !receipt.equals(owner.confirmDeclaredAttack("land-action",proof)))throw new AssertionError("DECLARATION_NOT_CONFIRMED");
            if(owner.dispatch(wire,"raw-game","raw-human",42,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("DECLARATION_REPLAYED");
            JsonObject update=envelope(projection.projectReadOnlyDeclaredAttack(after,next));update.addProperty("message_id","declared-attack-result");new ManaforgeUnityOpening.VerifiedDeclaredAttackResult(proof,update);owner.observe(update.toString());
            try{new ManaforgeUnityOpening.VerifiedDeclaredAttackResult(proof,envelope(snapshot));throw new AssertionError("ACTIONABLE_DECLARATION_ACCEPTED");}catch(IllegalArgumentException expected){}
            owner.disconnected();if(!receipt.equals(owner.receiptFor("land-action")))throw new AssertionError("DECLARATION_CONFIRMATION_LOST");
        }
    }
    static void attackerConfirmationChecks(manaforge.protocol.GatewayHandshake.ViewerContext context) throws Exception {
        JsonObject before=OpeningProjectionChecks.attackState(),prompt=OpeningProjectionChecks.attackPrompt(),after=before.deepCopy(),next=OpeningProjectionChecks.attackPrompt();next.addProperty("decision_id",42);
        after.add("combat",JsonParser.parseString("[{\"attackers\":[\"raw-card\"],\"blockers\":[],\"defender\":\"raw-ai\",\"blocked\":false}]"));
        ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();JsonObject snapshot=projection.projectAttackSelection(before,prompt);String wire=OpeningProjectionChecks.perform(snapshot);
        try(ManaforgeOpeningSession owner=new ManaforgeOpeningSession(context,projection,envelope(snapshot).toString())) {
            if(!owner.dispatch(wire,"raw-game","raw-human",41,8).shouldSubmit)throw new AssertionError("ATTACKER_NOT_ADMITTED");JsonObject command=owner.pollNative(),accepted=new JsonObject();
            accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id").deepCopy());
            NativeCastCorrelation.AttackerSelectionEvidence proof=NativeCastCorrelation.attackerSelectionEvidence(before,prompt,command,OpeningProjectionChecks.attackMetadata(false),accepted,after,next,OpeningProjectionChecks.attackMetadata(false),"raw-card");
            if(proof==null)throw new AssertionError("ATTACKER_PROOF_MISSING");
            JsonObject other=command.deepCopy(),otherAccepted=accepted.deepCopy();other.addProperty("request_id","other");otherAccepted.addProperty("request_id","other");
            NativeCastCorrelation.AttackerSelectionEvidence otherProof=NativeCastCorrelation.attackerSelectionEvidence(before,prompt,other,OpeningProjectionChecks.attackMetadata(false),otherAccepted,after,next,OpeningProjectionChecks.attackMetadata(false),"raw-card");
            JsonObject otherDecision=command.deepCopy(),otherPrompt=prompt.deepCopy();otherDecision.addProperty("decision_id",40);otherPrompt.addProperty("decision_id",40);
            NativeCastCorrelation.AttackerSelectionEvidence decisionProof=NativeCastCorrelation.attackerSelectionEvidence(before,otherPrompt,otherDecision,OpeningProjectionChecks.attackMetadata(false),accepted,after,next,OpeningProjectionChecks.attackMetadata(false),"raw-card");
            if(otherProof==null || decisionProof==null)throw new AssertionError("ALTERNATE_ATTACKER_PROOF_MISSING");
            for(int mode=0;mode<4;mode++)try{owner.confirmAttackerSelection(mode==0?"wrong-id":"land-action",mode==1?null:mode==2?otherProof:mode==3?decisionProof:proof);throw new AssertionError("BAD_ATTACKER_PROOF_ACCEPTED");}
                catch(IOException expected){if(!"ATTACKER_EVIDENCE_MISMATCH".equals(expected.getMessage()))throw expected;}
            JsonObject original=command.deepCopy();command.addProperty("value","mutated");
            if(!proof.matchesCommand(original) || proof.matchesCommand(command))throw new AssertionError("MUTABLE_ATTACKER_EVIDENCE");
            JsonObject receipt=owner.confirmAttackerSelection("land-action",proof);
            if(!"confirmed".equals(receipt.getAsJsonObject("body").get("outcome").getAsString()) || !receipt.equals(owner.confirmAttackerSelection("land-action",proof)))throw new AssertionError("ATTACKER_CONFIRMATION_FAILED");
            manaforge.protocol.SubmissionLedger.Prepared duplicate=owner.dispatch(wire,"raw-game","raw-human",41,8);
            if(duplicate.shouldSubmit || !receipt.equals(duplicate.receipt()) || owner.pollNative()!=null)throw new AssertionError("CONFIRMED_ATTACKER_REPLAYED");
            JsonObject observation=envelope(projection.projectReadOnlyAttackAssignment(after,next));observation.addProperty("message_id","attack-assignment");new ManaforgeUnityOpening.VerifiedAttackerResult(proof,observation);owner.observe(observation.toString());
            try{new ManaforgeUnityOpening.VerifiedAttackerResult(proof,envelope(snapshot));throw new AssertionError("ACTIONABLE_ATTACKER_RESULT_ACCEPTED");}catch(IllegalArgumentException expected){}
            if(owner.dispatch(wire,"raw-game","raw-human",42,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("OBSERVED_ATTACKER_REPLAYED");
            owner.disconnected();if(!receipt.equals(owner.receiptFor("land-action")))throw new AssertionError("ATTACKER_DISCONNECT_LOST_CONFIRMATION");
            JsonObject finishSnapshot=envelope(projection.projectSelectedAttackFinish(after,next));
            new ManaforgeUnityOpening.VerifiedAttackerResult(proof,new ManaforgeUnityOpening.DeclaredAttackOffer(finishSnapshot,42,8,value->null));
            try{new ManaforgeUnityOpening.VerifiedAttackerResult(proof,new ManaforgeUnityOpening.DeclaredAttackOffer(envelope(snapshot),41,8,value->null));throw new AssertionError("NON_FINISH_ATTACKER_FOLLOWUP_ACCEPTED");}catch(IllegalArgumentException expected){}

        }
    }
    static void attackConfirmationChecks(manaforge.protocol.GatewayHandshake.ViewerContext context) throws Exception {
        JsonObject before=OpeningProjectionChecks.attackState(),prompt=OpeningProjectionChecks.attackPrompt(),after=before.deepCopy(),next=OpeningProjectionChecks.priorityPrompt();next.addProperty("decision_id",42);after.addProperty("priority_player","raw-name");
        ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();JsonObject snapshot=projection.projectAttackFinish(before,prompt);String wire=OpeningProjectionChecks.perform(snapshot);
        try(ManaforgeOpeningSession owner=new ManaforgeOpeningSession(context,projection,envelope(snapshot).toString())) {
            if(!owner.dispatch(wire,"raw-game","raw-human",41,8).shouldSubmit)throw new AssertionError("ATTACK_NOT_ADMITTED");JsonObject command=owner.pollNative(),accepted=new JsonObject();
            accepted.addProperty("event","response_sent");accepted.addProperty("accepted",true);accepted.add("request_id",command.get("request_id").deepCopy());
            NativeCastCorrelation.AttackFinishEvidence proof=NativeCastCorrelation.attackFinishEvidence(before,prompt,command,OpeningProjectionChecks.attackMetadata(false),accepted,after,next,OpeningProjectionChecks.attackMetadata(true),"raw-card");
            if(proof==null)throw new AssertionError("ATTACK_PROOF_MISSING");
            for(int mode=0;mode<2;mode++)try{owner.confirmAttackFinish(mode==0?"wrong-id":"land-action",mode==0?proof:null);throw new AssertionError("BAD_ATTACK_PROOF_ACCEPTED");}
                catch(IOException expected){if(!"ATTACK_EVIDENCE_MISMATCH".equals(expected.getMessage()))throw expected;}
            owner.uncertain("land-action");JsonObject receipt=owner.confirmAttackFinish("land-action",proof);
            if(!"confirmed".equals(receipt.getAsJsonObject("body").get("outcome").getAsString()) || !receipt.equals(owner.confirmAttackFinish("land-action",proof)))throw new AssertionError("ATTACK_CONFIRMATION_FAILED");
            manaforge.protocol.SubmissionLedger.Prepared duplicate=owner.dispatch(wire,"raw-game","raw-human",41,8);
            if(duplicate.shouldSubmit || !receipt.equals(duplicate.receipt()) || owner.pollNative()!=null)throw new AssertionError("CONFIRMED_ATTACK_REPLAYED");
            JsonObject observed=envelope(projection.projectReadOnlyPriority(after,next));observed.addProperty("message_id","post-combat-priority");
            new ManaforgeUnityOpening.VerifiedAttackResult(proof,observed);
            try{new ManaforgeUnityOpening.VerifiedAttackResult(proof,envelope(snapshot));throw new AssertionError("ACTIONABLE_COMBAT_RESULT_ACCEPTED");}
            catch(IllegalArgumentException expected){if(!"COMBAT_RESULT_NOT_READ_ONLY".equals(expected.getMessage()))throw expected;}
            owner.observe(observed.toString());JsonObject stale=JsonParser.parseString(wire).getAsJsonObject();stale.addProperty("message_id","stale-attack-finish");
            if(owner.dispatch(stale.toString(),"raw-game","raw-human",42,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("READ_ONLY_COMBAT_ACCEPTED_ACTION");
            manaforge.protocol.SubmissionLedger.Prepared replay=owner.dispatch(wire,"raw-game","raw-human",42,8);
            if(replay.shouldSubmit || !receipt.equals(replay.receipt()) || owner.pollNative()!=null)throw new AssertionError("COMBAT_RESULT_CHANGED_RECEIPT");
            JsonObject priority=projection.project(after,next,true),priorityUpdate=envelope(priority);priorityUpdate.addProperty("message_id","combat-priority");
            new ManaforgeUnityOpening.VerifiedAttackResult(proof,new ManaforgeUnityOpening.PriorityOffer(priorityUpdate,42,8,commandValue->{}));
            try{new ManaforgeUnityOpening.VerifiedAttackResult(proof,new ManaforgeUnityOpening.PriorityOffer(envelope(snapshot),41,8,commandValue->{}));throw new AssertionError("NON_PRIORITY_COMBAT_FOLLOWUP_ACCEPTED");}
            catch(IllegalArgumentException expected){if(!"COMBAT_RESULT_NOT_PASS_ONLY".equals(expected.getMessage()))throw expected;}
            owner.observe(priorityUpdate.toString());JsonObject pass=JsonParser.parseString(OpeningProjectionChecks.perform(priority)).getAsJsonObject();pass.addProperty("message_id","after-combat-pass");
            if(!owner.dispatch(pass.toString(),"raw-game","raw-human",42,8).shouldSubmit)throw new AssertionError("COMBAT_PRIORITY_NOT_ADMITTED");
            JsonObject nativePass=owner.pollNative();if(nativePass==null || nativePass.get("decision_id").getAsLong()!=42 || !new JsonPrimitive(false).equals(nativePass.get("value")))throw new AssertionError("BAD_COMBAT_PRIORITY");
            owner.uncertain("after-combat-pass");
            if(owner.dispatch(pass.toString(),"raw-game","raw-human",42,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("COMBAT_PRIORITY_REPLAYED");
            owner.dispatch(wire,"raw-game","raw-human",42,8);pass.addProperty("message_id","blocked-next");
            manaforge.protocol.SubmissionLedger.Prepared blocked=owner.dispatch(pass.toString(),"raw-game","raw-human",42,8);
            if(blocked.shouldSubmit || !"COMMAND_PENDING".equals(blocked.receipt().getAsJsonObject("body").get("code").getAsString()) || owner.pollNative()!=null)throw new AssertionError("OLD_ATTACK_RECEIPT_RELEASED_PASS");
            JsonObject phaseBefore=after.deepCopy(),phaseAfter=after.deepCopy(),phaseNext=next.deepCopy(),passAccepted=accepted.deepCopy();
            phaseBefore.addProperty("phase","COMBAT");phaseBefore.addProperty("step","END_COMBAT");phaseAfter.addProperty("phase","POSTCOMBAT_MAIN");phaseAfter.addProperty("step","POSTCOMBAT_MAIN");phaseNext.addProperty("decision_id",43);passAccepted.addProperty("request_id","after-combat-pass");
            NativeCastCorrelation.PriorityEvidence phaseProof=proof.phasePriorityEvidence(phaseBefore,next,nativePass,OpeningProjectionChecks.attackMetadata(true),passAccepted,phaseAfter,phaseNext,OpeningProjectionChecks.attackMetadata(true));
            if(phaseProof==null)throw new AssertionError("COMBAT_PASS_PROOF_MISSING");
            JsonObject passReceipt=owner.confirmPriority("after-combat-pass",phaseProof);if(!"confirmed".equals(passReceipt.getAsJsonObject("body").get("outcome").getAsString()) || !passReceipt.equals(owner.confirmPriority("after-combat-pass",phaseProof)))throw new AssertionError("COMBAT_PASS_CONFIRMATION_FAILED");
            JsonObject phaseUpdate=envelope(projection.projectReadOnlyPriority(phaseAfter,phaseNext));phaseUpdate.addProperty("message_id","combat-priority-result");owner.observe(phaseUpdate.toString());pass.addProperty("message_id","after-combat-pass");
            manaforge.protocol.SubmissionLedger.Prepared passRetry=owner.dispatch(pass.toString(),"raw-game","raw-human",43,8);
            if(passRetry.shouldSubmit || !passReceipt.equals(passRetry.receipt()) || owner.pollNative()!=null)throw new AssertionError("CONFIRMED_COMBAT_PASS_REPLAYED");
            owner.disconnected();if(!receipt.equals(owner.receiptFor("land-action")))throw new AssertionError("ATTACK_CONFIRMATION_LOST");
            if(!passReceipt.equals(owner.receiptFor("after-combat-pass")))throw new AssertionError("COMBAT_PRIORITY_CONFIRMATION_LOST");
        }
    }
    static JsonObject envelope(JsonObject snapshot) {
        JsonObject envelope=new JsonObject(),body=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","snapshot");envelope.addProperty("message_id","opening");
        body.addProperty("fixture_only",false);body.add("snapshot",snapshot);envelope.add("body",body);return envelope;
    }
    public static void main(String[] args) throws Exception {
        String keyText=String.join("",java.util.Collections.nCopies(64,"a"));
        for(String bootstrap:new String[]{"{\"live_opening_bootstrap_version\":1,\"viewer_key_hex\":\""+keyText+"\"}","{}","{\"live_opening_bootstrap_version\":true,\"viewer_key_hex\":\""+keyText+"\"}","{\"live_opening_bootstrap_version\":1,\"viewer_key_hex\":[\""+keyText+"\"]}"}) {
            java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();manaforge.protocol.TextFrame.write(out,bootstrap);
            try{byte[] key=ManaforgeUnityOpening.readBootstrap(new java.io.ByteArrayInputStream(out.toByteArray()));if(!bootstrap.startsWith("{\"live_opening_bootstrap_version\":1,\"viewer_key_hex\":\""))throw new AssertionError("BAD_BOOTSTRAP_ACCEPTED");if(key.length!=32 || key[0]!=(byte)0xaa)throw new AssertionError("BAD_KEY");java.util.Arrays.fill(key,(byte)0);}
            catch(IOException failure){if(bootstrap.startsWith("{\"live_opening_bootstrap_version\":1,\"viewer_key_hex\":\""))throw failure;if(!failure.getMessage().equals("LIVE_OPENING_BOOTSTRAP_FAILED"))throw failure;}
        }
        AtomicInteger calls=new AtomicInteger();String hash=String.join("",java.util.Collections.nCopies(64,"0"));
        ManaforgeOpeningProjection projection=OpeningProjectionChecks.projection();
        JsonObject snapshot=projection.project(OpeningProjectionChecks.state(),OpeningProjectionChecks.prompt());
        ManaforgeOpeningLoopback.exchange(envelope(snapshot),projection,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->{
            if(!command.get("value").getAsBoolean() || !command.get("game_id").getAsString().equals("raw-game") || command.get("decision_id").getAsInt()!=41)throw new AssertionError("BAD_NATIVE_BINDING");
            calls.incrementAndGet();
        },()->false);
        if(calls.get()!=1)throw new AssertionError("DUPLICATE_NATIVE_IO");
        try{OpeningProjectionChecks.claim(projection,OpeningProjectionChecks.choose(snapshot,0));throw new AssertionError("DISCONNECTED_CHOICE_ACCEPTED");}
        catch(IOException expected){if(!expected.getMessage().equals("STALE_DECISION"))throw expected;}
        ManaforgeOpeningProjection cancelled=OpeningProjectionChecks.projection();
        JsonObject offered=cancelled.project(OpeningProjectionChecks.state(),OpeningProjectionChecks.prompt());
        try {
            ManaforgeOpeningLoopback.exchange(envelope(offered),cancelled,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->calls.incrementAndGet(),()->true);
            throw new AssertionError("CANCELLED_AUTH_ACCEPTED");
        }catch(IOException failure){if(!failure.getMessage().equals("AUTH_CANCELLED"))throw failure;}
        if(calls.get()!=1)throw new AssertionError("CANCELLED_NATIVE_IO");
        try{OpeningProjectionChecks.claim(cancelled,OpeningProjectionChecks.choose(offered,0));throw new AssertionError("CANCELLED_CHOICE_RETAINED");}
        catch(IOException expected){if(!expected.getMessage().equals("STALE_DECISION"))throw expected;}
        ManaforgeOpeningProjection priority=OpeningProjectionChecks.projection();
        JsonObject prioritySnapshot=priority.project(OpeningProjectionChecks.landState(),OpeningProjectionChecks.priorityPrompt(),true);
        ManaforgeOpeningLoopback.exchangeChoice(envelope(prioritySnapshot),priority,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->{
            if(!command.get("kind").getAsString().equals("boolean") || command.get("value").getAsBoolean())throw new AssertionError("BAD_NATIVE_PASS");
            calls.incrementAndGet();
        },()->false,false);
        if(calls.get()!=2)throw new AssertionError("DUPLICATE_PASS_IO");
        String abilityId="12345678-abcd-1234-abcd-123456789abc";
        JsonObject abilityPrompt=OpeningProjectionChecks.priorityPrompt();abilityPrompt.addProperty("kind","GAME_CHOOSE_ABILITY");abilityPrompt.addProperty("is_priority",false);
        JsonObject choices=new JsonObject();choices.addProperty(abilityId,"Cast creature");abilityPrompt.add("key_choices",choices);
        ManaforgeOpeningProjection ability=OpeningProjectionChecks.projection();
        JsonObject abilitySnapshot=ability.project(OpeningProjectionChecks.landState(),abilityPrompt,false,true);
        ManaforgeOpeningLoopback.exchangeChoice(envelope(abilitySnapshot),ability,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->{
            if(!command.get("kind").getAsString().equals("object") || !command.get("value").getAsString().equals(abilityId))throw new AssertionError("BAD_NATIVE_ABILITY");
            calls.incrementAndGet();
        },()->false,true,"cast_spell");
        if(calls.get()!=3)throw new AssertionError("DUPLICATE_ABILITY_IO");
        ManaforgeOpeningProjection combat=OpeningProjectionChecks.projection();JsonObject combatSnapshot=combat.projectAttackFinish(OpeningProjectionChecks.attackState(),OpeningProjectionChecks.attackPrompt());
        ManaforgeOpeningLoopback.exchangeChoice(envelope(combatSnapshot),combat,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->{
            if(!"boolean".equals(command.get("kind").getAsString()) || !new JsonPrimitive(false).equals(command.get("value")))throw new AssertionError("BAD_NATIVE_ATTACK_FINISH");calls.incrementAndGet();
        },()->false,false);
        if(calls.get()!=4)throw new AssertionError("DUPLICATE_ATTACK_FINISH_IO");
        ManaforgeOpeningProjection attacker=OpeningProjectionChecks.projection();JsonObject attackerSnapshot=attacker.projectAttackSelection(OpeningProjectionChecks.attackState(),OpeningProjectionChecks.attackPrompt());
        ManaforgeOpeningLoopback.exchangeChoice(envelope(attackerSnapshot),attacker,"raw-game","raw-human",41,8,"synthetic-engine",hash,command->{
            if(!"object".equals(command.get("kind").getAsString()) || !"raw-card".equals(command.get("value").getAsString()))throw new AssertionError("BAD_NATIVE_ATTACKER");calls.incrementAndGet();
        },()->false,true,"declare_attacker");
        if(calls.get()!=5)throw new AssertionError("DUPLICATE_ATTACKER_IO");
        System.out.println("Opening session: authenticated snapshot/choice/pass/ability/attack finish, duplicate receipt, one native enqueue, disconnect uncertainty and cancelled-auth checks passed");
    }
}

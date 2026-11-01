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
                JsonObject postSnapshot=projection.project(resolved,later,true),postUpdate=envelope(postSnapshot);postUpdate.addProperty("message_id","post-resolution-priority");owner.observe(postUpdate.toString());
                JsonObject postCommand=JsonParser.parseString(OpeningProjectionChecks.perform(postSnapshot)).getAsJsonObject();postCommand.addProperty("message_id","post-resolution-pass");
                if(!owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8).shouldSubmit)throw new AssertionError("POST_RESOLUTION_PASS_NOT_ADMITTED");
                JsonObject nativePost=owner.pollNative();if(nativePost==null || nativePost.get("decision_id").getAsLong()!=44 || !new JsonPrimitive(false).equals(nativePost.get("value")))throw new AssertionError("WRONG_POST_RESOLUTION_PASS");
                if(owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8).shouldSubmit || owner.pollNative()!=null)throw new AssertionError("POST_RESOLUTION_PASS_REPLAYED");
                owner.uncertain("post-resolution-pass");postCommand.addProperty("message_id","blocked-fourth-command");
                manaforge.protocol.SubmissionLedger.Prepared fourth=owner.dispatch(postCommand.toString(),"raw-game","raw-human",44,8);
                if(fourth.shouldSubmit || !"COMMAND_PENDING".equals(fourth.receipt().getAsJsonObject("body").get("code").getAsString()) || owner.pollNative()!=null)throw new AssertionError("UNCERTAIN_POST_PASS_RELEASED");
                owner.disconnected();if(!confirmed.equals(owner.receiptFor(id)))throw new AssertionError("CONFIRMATION_LOST_ON_DISCONNECT");
                if(!passReceipt.equals(owner.receiptFor("followup-pass")))throw new AssertionError("PRIORITY_CONFIRMATION_LOST");
                if(!"uncertain".equals(owner.receiptFor("post-resolution-pass").getAsJsonObject("body").get("outcome").getAsString()))throw new AssertionError("POST_PASS_UNCERTAINTY_LOST");
            }
        }finally{java.util.Arrays.fill(key,(byte)0);}
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
        System.out.println("Opening session: authenticated snapshot/choice/pass/ability, duplicate receipt, one native enqueue, disconnect uncertainty and cancelled-auth checks passed");
    }
}

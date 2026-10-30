package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

public final class LedgerFixtureConsumer {
    private static void check(boolean value) {if(!value)throw new AssertionError("Submission ledger mismatch");}
    private static JsonObject command(JsonObject original,String id) {JsonObject copy=original.deepCopy();copy.addProperty("message_id",id);return copy;}
    private static String outcome(SubmissionLedger.Prepared value) {return value.receipt().getAsJsonObject("body").get("outcome").getAsString();}
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        JsonObject original=corpus.getAsJsonArray("positive").get(0).getAsJsonObject().getAsJsonObject("envelope");
        String first=command(original,"first").toString(),second=command(original,"second").toString();
        try(SubmissionLedger ledger=new SubmissionLedger("session","seat-one",16)) {
            for(String field:new String[]{"session_id","viewer_id"}) {
                JsonObject wrong=command(original,"wrong-context");wrong.getAsJsonObject("body").addProperty(field,"other");
                try {ledger.prepare(wrong.toString(),null);throw new AssertionError("Wrong context accepted");}
                catch(WireEnvelope.EnvelopeException error) {check(error.code.equals("COMMAND_CONTEXT"));}
            }
            SubmissionLedger.Prepared submitted=ledger.prepare(first,null);check(submitted.shouldSubmit && outcome(submitted).equals("submitted"));
            submitted.receipt().getAsJsonObject("body").addProperty("outcome","confirmed"); // external copies cannot change history
            check(!ledger.prepare(first,"STALE_REVISION").shouldSubmit && outcome(ledger.prepare(first,null)).equals("submitted"));
            JsonObject reordered=new JsonObject();reordered.add("body",original.get("body"));reordered.addProperty("message_id","first");reordered.addProperty("message_type","command");reordered.addProperty("wire_version",1);
            check(!ledger.prepare(reordered.toString(),null).shouldSubmit);
            JsonObject changed=command(original,"first");changed.getAsJsonObject("body").addProperty("action_id","different");
            try {ledger.prepare(changed.toString(),null);throw new AssertionError("ID conflict accepted");}
            catch(WireEnvelope.EnvelopeException error) {check(error.code.equals("COMMAND_ID_CONFLICT"));}
            SubmissionLedger.Prepared pending=ledger.prepare(second,null);check(!pending.shouldSubmit && outcome(pending).equals("rejected"));
            check(pending.receipt().getAsJsonObject("body").get("code").getAsString().equals("COMMAND_PENDING"));
            try {ledger.recordOutcome("first","confirmed","ENGINE_REJECTED");throw new AssertionError("Malformed outcome accepted");}
            catch(WireEnvelope.EnvelopeException error) {check(error.code.equals("MESSAGE_INVALID"));}
            check(outcome(ledger.prepare(first,null)).equals("submitted"));
            ledger.disconnected();check(outcome(ledger.prepare(first,null)).equals("uncertain"));
            ledger.recordOutcome("first","submitted",null);check(outcome(ledger.prepare(first,null)).equals("uncertain"));
            ledger.recordOutcome("first","confirmed",null);check(!ledger.prepare(first,null).shouldSubmit && outcome(ledger.prepare(first,null)).equals("confirmed"));
            String third=command(original,"third").toString();check(ledger.prepare(third,null).shouldSubmit);
            ledger.recordOutcome("first","confirmed",null);
            check(!ledger.prepare(command(original,"fourth").toString(),null).shouldSubmit); // old receipt cannot release third
            ledger.recordOutcome("third","rejected","ENGINE_REJECTED");
            SubmissionLedger.Prepared stale=ledger.prepare(command(original,"stale").toString(),"STALE_REVISION");check(!stale.shouldSubmit);
            check(!ledger.prepare(command(original,"stale").toString(),null).shouldSubmit);
            try {ledger.recordOutcome("first","rejected","ENGINE_REJECTED");throw new AssertionError("Conflicting outcome accepted");}
            catch(WireEnvelope.EnvelopeException error) {check(error.code.equals("ACK_CONFLICT"));}
        }
        try(SubmissionLedger ledger=new SubmissionLedger("session","seat-one",1)) {
            ledger.prepare(first,null);ledger.recordOutcome("first","confirmed",null);
            try {ledger.prepare(second,null);throw new AssertionError("Capacity silently evicted ID");}
            catch(WireEnvelope.EnvelopeException error) {check(error.code.equals("COMMAND_HISTORY_FULL"));}
            check(!ledger.prepare(first,null).shouldSubmit);
            ledger.close();try {ledger.prepare(first,null);throw new AssertionError("Closed ledger accepted");}
            catch(WireEnvelope.EnvelopeException error) {check(error.code.equals("LEDGER_CLOSED"));}
        }
        try(SubmissionLedger ledger=new SubmissionLedger("session","seat-one",16)) {
            java.util.concurrent.atomic.AtomicInteger reservations=new java.util.concurrent.atomic.AtomicInteger();
            java.util.concurrent.atomic.AtomicReference<Throwable> failure=new java.util.concurrent.atomic.AtomicReference<>();
            Runnable attempt=()->{try {if(ledger.prepare(first,null).shouldSubmit)reservations.incrementAndGet();}catch(Throwable error){failure.set(error);}};
            Thread a=new Thread(attempt),b=new Thread(attempt);a.start();b.start();a.join(2000);b.join(2000);
            check(!a.isAlive() && !b.isAlive() && failure.get()==null && reservations.get()==1);
        }
        System.out.println("Java submission ledger: duplicate/conflict, pending, uncertainty, outcome and capacity checks passed");
    }
}

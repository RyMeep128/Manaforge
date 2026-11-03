package manaforge.protocol;

import com.google.gson.*;
import java.io.IOException;
import java.util.*;

/** Session/viewer-owned receipt history. No engine rules, retries or automatic reconciliation. */
public final class SubmissionLedger implements AutoCloseable {
    private static final class Record {
        final JsonObject request;
        final long revision;
        String outcome,code;
        Record(JsonObject request,String outcome,String code) {
            this.request=request.deepCopy();this.revision=request.getAsJsonObject("body").get("revision").getAsLong();
            this.outcome=outcome;this.code=code;
        }
    }
    public static final class Prepared {
        public final boolean shouldSubmit;
        private final JsonObject receipt;
        private Prepared(boolean shouldSubmit,JsonObject receipt) {this.shouldSubmit=shouldSubmit;this.receipt=receipt.deepCopy();}
        public JsonObject receipt() {return receipt.deepCopy();}
    }
    private final String session,viewer;
    private final int capacity;
    private final Map<String,Record> records=new HashMap<>();
    private Record active;
    private boolean closed;
    public SubmissionLedger(String session,String viewer,int capacity) {
        if(session==null || session.isEmpty() || viewer==null || viewer.isEmpty() || capacity<1 || capacity>65536)
            throw new IllegalArgumentException("LEDGER_CONTEXT_INVALID");
        this.session=session;this.viewer=viewer;this.capacity=capacity;
    }
    private void open() throws WireEnvelope.EnvelopeException {if(closed)fail("LEDGER_CLOSED");}
    synchronized boolean hasUnresolved(){return active!=null;}
    private static void fail(String code) throws WireEnvelope.EnvelopeException {throw new WireEnvelope.EnvelopeException(code);}
    private JsonObject receipt(Record record) throws IOException {
        JsonObject body=new JsonObject();body.addProperty("session_id",session);body.addProperty("viewer_id",viewer);
        body.addProperty("command_id",record.request.get("message_id").getAsString());body.addProperty("request_revision",record.revision);
        body.addProperty("outcome",record.outcome);if(record.code==null)body.add("code",JsonNull.INSTANCE);else body.addProperty("code",record.code);
        JsonObject envelope=new JsonObject();envelope.addProperty("wire_version",1);envelope.addProperty("message_type","ack");
        envelope.addProperty("message_id","ledger-receipt");envelope.add("body",body);
        return WireMessages.parse(envelope.toString());
    }
    /** Admission is a pure current-state check already performed on the serialized gateway worker.
     * It must not execute anything. A true shouldSubmit reserves one engine submission, not confirmation. */
    public synchronized Prepared prepare(String text,String admissionRejection) throws IOException {
        open();JsonObject request=WireMessages.parse(text),body=request.getAsJsonObject("body");
        if(!request.get("message_type").getAsString().equals("command"))fail("MESSAGE_UNSUPPORTED");
        if(!body.get("session_id").getAsString().equals(session) || !body.get("viewer_id").getAsString().equals(viewer))fail("COMMAND_CONTEXT");
        String id=request.get("message_id").getAsString();Record existing=records.get(id);
        if(existing!=null) {
            if(!existing.request.equals(request))fail("COMMAND_ID_CONFLICT");
            return new Prepared(false,receipt(existing));
        }
        if(records.size()>=capacity)fail("COMMAND_HISTORY_FULL");
        String rejection=admissionRejection!=null?admissionRejection:active==null?null:"COMMAND_PENDING";
        Record record=new Record(request,rejection==null?"submitted":"rejected",rejection);
        JsonObject acknowledgement=receipt(record); // reject invalid admission codes before reserving
        records.put(id,record);
        if(rejection==null)active=record;
        return new Prepared(rejection==null,acknowledgement);
    }
    /** Trusted engine-correlated outcome only; never call because a write or game result looked successful. */
    public synchronized JsonObject recordOutcome(String id,String outcome,String code) throws IOException {
        open();Record record=records.get(id);if(record==null) {fail("ACK_UNKNOWN");return null;}
        Record candidate=new Record(record.request,outcome,code);JsonObject acknowledgement=receipt(candidate);
        if(record.outcome.equals("confirmed") || record.outcome.equals("rejected")) {
            if(!record.outcome.equals(outcome) || !Objects.equals(record.code,code))fail("ACK_CONFLICT");
            return receipt(record);
        }
        if(record.outcome.equals("uncertain") && outcome.equals("submitted"))return receipt(record);
        record.outcome=outcome;record.code=code;
        if(outcome.equals("confirmed") || outcome.equals("rejected")) {if(active==record)active=null;}
        return acknowledgement;
    }
    public synchronized void disconnected() throws IOException {
        open();if(active!=null) {active.outcome="uncertain";active.code="COMMAND_UNCERTAIN";}
    }
    /** Owner-only observation; does not reserve or replay an engine submission. */
    public synchronized JsonObject receiptFor(String id) throws IOException {
        open();Record record=records.get(id);if(record==null)fail("ACK_UNKNOWN");return receipt(record);
    }
    public synchronized void close() {closed=true;active=null;records.clear();}
}

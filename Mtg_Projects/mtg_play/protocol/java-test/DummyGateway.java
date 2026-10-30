package manaforge.protocol;

import com.google.gson.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.atomic.*;

/** Test-only owned loopback peer. Never starts XMage or accepts real decks. */
public final class DummyGateway {
    private static JsonObject envelope(String type, String id, JsonObject body) {
        JsonObject e=new JsonObject(); e.addProperty("wire_version",1); e.addProperty("message_type",type);
        e.addProperty("message_id",id); e.add("body",body); return e;
    }
    private static JsonObject object(String text) throws IOException {
        return WireEnvelope.parse("{\"wire_version\":1,\"message_type\":\"hello\",\"message_id\":\"bootstrap\",\"body\":"+text+"}").getAsJsonObject("body");
    }
    private static void require(boolean condition) throws IOException { if(!condition) throw new IOException("DUMMY_INVALID"); }
    private static byte[] hex(String value) throws IOException {
        require(value.matches("[0-9a-f]{64}")); byte[] key=new byte[32];
        for(int i=0;i<32;i++) key[i]=(byte)Integer.parseInt(value.substring(i*2,i*2+2),16); return key;
    }
    private static String nonce() {
        byte[] bytes=new byte[32]; new SecureRandom().nextBytes(bytes); StringBuilder text=new StringBuilder();
        for(byte b:bytes) text.append(String.format(Locale.ROOT,"%02x",b&255)); return text.toString();
    }
    private static JsonObject hello(JsonObject boot,String serverNonce,String role) {
        JsonObject b=new JsonObject(); b.addProperty("protocol_version",1);
        for(String key:new String[]{"engine_version","artifact_manifest_sha256","session_id","viewer_id","client_nonce"}) b.add(key,boot.get(key));
        b.addProperty("server_nonce",serverNonce); b.addProperty("role",role); b.addProperty("proof",String.join("",Collections.nCopies(64,"0")));
        return envelope("hello","auth-"+role,b);
    }
    private static void send(OutputStream out,JsonObject value) throws IOException { TextFrame.write(out,value.toString()); out.flush(); }
    public static void main(String[] args) {
        AtomicBoolean ownerGone=new AtomicBoolean(); AtomicReference<Socket> active=new AtomicReference<>();
        byte[] key=null;
        try(ServerSocket listener=new ServerSocket()) {
            InputStream owner=new BufferedInputStream(System.in);
            JsonObject boot=object(TextFrame.read(owner));
            require(boot.size()==7 && boot.keySet().containsAll(Arrays.asList("viewer_key_hex","engine_version","artifact_manifest_sha256","session_id","viewer_id","client_nonce","fixture_only")));
            require(boot.get("fixture_only").isJsonPrimitive() && boot.get("fixture_only").getAsJsonPrimitive().isBoolean() && boot.get("fixture_only").getAsBoolean());
            key=hex(boot.get("viewer_key_hex").getAsString()); String serverNonce=nonce();
            String session=boot.get("session_id").getAsString(),viewer=boot.get("viewer_id").getAsString();
            JsonObject clientHello=hello(boot,serverNonce,"client"),gatewayHello=hello(boot,serverNonce,"gateway");
            ViewerAuthentication.parse(clientHello.toString());
            JsonObject snapshot=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonObject("snapshot");
            require(session.equals(snapshot.get("session_id").getAsString()) && viewer.equals(snapshot.get("viewer_id").getAsString()));
            listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0),1); listener.setSoTimeout(8000);
            Thread lifeline=new Thread(()->{ try { owner.read(); } catch(IOException ignored){} ownerGone.set(true);
                try { listener.close(); Socket s=active.get(); if(s!=null)s.close(); } catch(IOException ignored){} },"dummy-owner-lifeline");
            lifeline.setDaemon(true); lifeline.start();
            JsonObject ready=new JsonObject(); ready.addProperty("host","127.0.0.1"); ready.addProperty("port",listener.getLocalPort()); ready.addProperty("server_nonce",serverNonce);
            send(System.out,ready);
            try(Socket socket=listener.accept()) {
                active.set(socket); if(ownerGone.get())throw new IOException("OWNER_GONE"); socket.setSoTimeout(5000);
                InputStream in=socket.getInputStream(); OutputStream out=socket.getOutputStream();
                try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(clientHello.toString(),key)) {
                    require(verifier.verify(TextFrame.read(in)));
                }
                gatewayHello.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(gatewayHello.toString(),key));
                send(out,gatewayHello);
                JsonObject body=new JsonObject(); body.addProperty("fixture_only",true); body.add("snapshot",snapshot);
                JsonObject snapshotMessage=envelope("snapshot","fixture-snapshot",body);
                ReceiveMessages.parse(snapshotMessage.toString(),session,viewer,0,true);send(out,snapshotMessage);
                JsonObject event=new JsonObject();event.addProperty("kind","fixture-event");event.addProperty("player_id","two");
                event.add("revision",snapshot.get("revision"));event.add("code",JsonNull.INSTANCE);event.add("observations",new JsonArray());
                JsonObject eventBody=new JsonObject();eventBody.addProperty("fixture_only",true);eventBody.addProperty("session_id",session);eventBody.addProperty("viewer_id",viewer);eventBody.add("event",event);
                JsonObject eventMessage=envelope("event","fixture-event",eventBody);
                ReceiveMessages.parse(eventMessage.toString(),session,viewer,0,true);send(out,eventMessage);
                long revision=snapshot.get("revision").getAsLong();
                String decision=snapshot.getAsJsonObject("decision").get("decision_id").getAsString();
                List<String> actions=new ArrayList<>(); for(JsonElement a:snapshot.getAsJsonArray("actions"))actions.add(a.getAsJsonObject().get("action_id").getAsString());
                try(SubmissionLedger ledger=new SubmissionLedger(session,viewer,4096)) {
                for(int count=0;count<8;count++) {
                    String text=TextFrame.read(in); require(text!=null);
                    JsonObject message=WireMessages.parse(text),request=message.getAsJsonObject("body");
                    String type=message.get("message_type").getAsString();
                    if(type.equals("shutdown")) {
                        require(request.get("session_id").getAsString().equals(session) && request.get("viewer_id").getAsString().equals(viewer));
                        send(out,envelope("shutdown","shutdown-ok",request)); return;
                    }
                    require(type.equals("command"));
                    String rejection=WireMessages.checkCurrent(text,session,viewer,revision,decision,actions);
                    SubmissionLedger.Prepared prepared=ledger.prepare(text,rejection);
                    JsonObject acknowledgement=prepared.receipt();acknowledgement.addProperty("message_id","ack-"+count);
                    send(out,acknowledgement);
                    if(prepared.shouldSubmit) {
                        JsonObject result=new JsonObject();result.addProperty("fixture_only",true);
                        JsonObject terminal=snapshot.deepCopy();terminal.addProperty("status","finished");terminal.addProperty("result","fixture_complete");
                        terminal.addProperty("revision",revision+1);terminal.add("decision",JsonNull.INSTANCE);terminal.add("actions",new JsonArray());
                        result.add("snapshot",terminal);JsonObject resultMessage=envelope("result","fixture-result",result);
                        ReceiveMessages.parse(resultMessage.toString(),session,viewer,revision,true);send(out,resultMessage);
                    }
                }
                throw new IOException("DUMMY_LIMIT");
                }
            }
        } catch(Exception error) { if(!ownerGone.get()) { System.err.println("DUMMY_FAILED");System.exit(2); } }
        finally { if(key!=null)Arrays.fill(key,(byte)0); }
    }
}

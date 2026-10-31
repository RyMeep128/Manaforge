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
    private static void send(LoopbackFrameReader frames,JsonObject value) throws IOException { frames.write(value.toString(),5000); }
    public static void main(String[] args) {
        AtomicBoolean ownerGone=new AtomicBoolean(); AtomicReference<LoopbackFrameReader> active=new AtomicReference<>();
        byte[] key=null;
        try(ServerSocket listener=new ServerSocket()) {
            InputStream owner=new BufferedInputStream(System.in);
            boolean sceneMode=args.length==2 && args[1].startsWith("scene-fixture:");
            JsonObject boot=object(TextFrame.read(owner));
            require(boot.size()==7 && boot.keySet().containsAll(Arrays.asList("viewer_key_hex","engine_version","artifact_manifest_sha256","session_id","viewer_id","client_nonce","fixture_only")));
            require(boot.get("fixture_only").isJsonPrimitive() && boot.get("fixture_only").getAsJsonPrimitive().isBoolean() && boot.get("fixture_only").getAsBoolean());
            key=hex(boot.get("viewer_key_hex").getAsString()); String serverNonce=nonce();
            String session=boot.get("session_id").getAsString(),viewer=boot.get("viewer_id").getAsString();
            JsonObject clientHello=hello(boot,serverNonce,"client"),gatewayHello=hello(boot,serverNonce,"gateway");
            ViewerAuthentication.parse(clientHello.toString());
            JsonObject snapshot=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject().getAsJsonObject("snapshot");
            require(session.equals(snapshot.get("session_id").getAsString()) && viewer.equals(snapshot.get("viewer_id").getAsString()));
            boolean numberMode=args.length==2 && args[1].equals("number");
            boolean amountsMode=args.length==2 && args[1].equals("amounts");
            boolean manaMode=args.length==2 && args[1].equals("mana");
            boolean choiceMode=args.length==2 && args[1].equals("choice") || numberMode || amountsMode || manaMode;
            if(choiceMode) {
                snapshot.add("actions",new JsonArray());JsonObject request=snapshot.getAsJsonObject("decision");
                request.addProperty("family","selection");request.addProperty("is_priority",false);request.addProperty("can_finish",true);request.addProperty("cancellable",true);
                JsonObject option=new JsonObject();option.addProperty("option_id","fixture-option");option.addProperty("label","Public fixture option");
                option.add("object_id",JsonNull.INSTANCE);option.add("player_id",JsonNull.INSTANCE);option.addProperty("selected",false);
                JsonArray options=new JsonArray();options.add(option);request.add("options",options);
                if(manaMode) {
                    request.addProperty("family","mana");request.add("options",new JsonArray());request.addProperty("can_finish",false);request.addProperty("cancellable",false);
                    JsonObject source=snapshot.getAsJsonArray("objects").get(0).getAsJsonObject().deepCopy();
                    source.addProperty("object_id","fixture-mana-object");source.addProperty("zone","battlefield");source.addProperty("hidden",false);source.addProperty("face_down",false);
                    snapshot.getAsJsonArray("objects").add(source);
                }
                if(numberMode || amountsMode) {
                    request.addProperty("family",numberMode?"number":"amounts");request.add("options",new JsonArray());
                    request.addProperty("can_finish",false);request.addProperty("cancellable",false);
                    request.addProperty("minimum",numberMode?-3:1);request.addProperty("maximum",numberMode?3:1);
                    if(amountsMode) {
                        JsonArray constraints=new JsonArray();
                        for(int i=0;i<2;i++) {JsonObject range=new JsonObject();range.addProperty("label","Public fixture amount");
                            range.addProperty("minimum",i==0?-3:0);range.addProperty("maximum",i==0?0:5);range.add("default",JsonNull.INSTANCE);constraints.add(range);}
                        request.add("amounts",constraints);
                    }
                }
            }
            listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0),1); listener.setSoTimeout(8000);
            Thread lifeline=new Thread(()->{ try { owner.read(); } catch(IOException ignored){} ownerGone.set(true);
                try { listener.close(); } catch(IOException ignored){}
                LoopbackFrameReader s=active.get();if(s!=null)try { s.close(); } catch(IOException ignored){} },"dummy-owner-lifeline");
            lifeline.setDaemon(true); lifeline.start();
            JsonObject ready=new JsonObject(); ready.addProperty("host","127.0.0.1"); ready.addProperty("port",listener.getLocalPort()); ready.addProperty("server_nonce",serverNonce);
            if(sceneMode) {
                JsonObject address=new JsonObject();address.addProperty("host","127.0.0.1");address.addProperty("port",listener.getLocalPort());
                Path path=Paths.get(args[1].substring("scene-fixture:".length())),temporary=Paths.get(path.toString()+".tmp");Files.write(temporary,address.toString().getBytes(StandardCharsets.UTF_8));Files.move(temporary,path,StandardCopyOption.ATOMIC_MOVE);
            }else send(System.out,ready);
            try(Socket socket=listener.accept();LoopbackFrameReader frames=new LoopbackFrameReader(socket)) {
                active.set(frames); if(ownerGone.get())throw new IOException("OWNER_GONE");
                OutputStream out=socket.getOutputStream();
                if(args.length==2 && args[1].equals("blocked-client"))socket.setSendBufferSize(1024);
                GatewayHandshake.ViewerContext authenticated=null;
                if(args.length==2 && args[1].equals("delayed-proof")) {
                    // Deliberate negative client-deadline fixture; normal paths use the bounded gateway helper.
                    try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(clientHello.toString(),key)) {require(verifier.verify(frames.read(5000)));}
                    Thread.sleep(350);gatewayHello.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(gatewayHello.toString(),key));send(frames,gatewayHello);
                } else if(args.length==2 && args[1].equals("server-auth-timeout")) {
                    try{GatewayHandshake.accept(frames,clientHello.toString(),gatewayHello.toString(),key,150);throw new IOException("DUMMY_EXPECTED_AUTH_TIMEOUT");}
                    catch(WireEnvelope.EnvelopeException error){require(error.code.equals("AUTH_TIMEOUT"));return;}
                } else {
                    authenticated=sceneMode || args.length==2 && args[1].equals("fresh-challenge")
                        ?ViewerChallengeHandshake.accept(frames,clientHello.toString(),gatewayHello.toString(),key,5000,ownerGone::get)
                        :GatewayHandshake.accept(frames,clientHello.toString(),gatewayHello.toString(),key,5000);
                    require(authenticated.sessionId.equals(session) && authenticated.viewerId.equals(viewer));
                }
                if(args.length==2 && args[1].equals("blocked-client")) {
                    char[] text=new char[TextFrame.MAX_BYTES];Arrays.fill(text,'x');
                    try{frames.write(new String(text),150);throw new IOException("DUMMY_EXPECTED_WRITE_TIMEOUT");}
                    catch(TextFrame.FrameException error){require(error.code.equals("FRAME_WRITE_TIMEOUT"));return;}
                }
                if(args.length==2 && args[1].equals("partial-frame")) {
                    out.write(new byte[]{0,0});out.flush();
                    while(!ownerGone.get())Thread.sleep(20);
                    return;
                }
                require(authenticated!=null);
                try(GatewaySessionBoundary boundary=new GatewaySessionBoundary(authenticated,true,4096)) {
                JsonObject body=new JsonObject(); body.addProperty("fixture_only",true); body.add("snapshot",snapshot);
                JsonObject snapshotMessage=envelope("snapshot","fixture-snapshot",body);
                boundary.observe(snapshotMessage.toString());send(frames,snapshotMessage);send(frames,snapshotMessage);
                JsonObject event=new JsonObject();event.addProperty("kind","fixture-event");event.addProperty("player_id","two");
                event.add("revision",snapshot.get("revision"));event.add("code",JsonNull.INSTANCE);event.add("observations",new JsonArray());
                JsonObject eventBody=new JsonObject();eventBody.addProperty("fixture_only",true);eventBody.addProperty("session_id",session);eventBody.addProperty("viewer_id",viewer);eventBody.add("event",event);
                JsonObject eventMessage=envelope("event","fixture-event",eventBody);
                boundary.observe(eventMessage.toString());send(frames,eventMessage);
                if(sceneMode) {
                    int heartbeat=0;while(!ownerGone.get() && heartbeat<1800){Thread.sleep(1000);if(ownerGone.get())break;
                        JsonObject pulse=eventMessage.deepCopy();pulse.addProperty("message_id","fixture-heartbeat-"+(heartbeat++));pulse.getAsJsonObject("body").getAsJsonObject("event").addProperty("kind","fixture-heartbeat");
                        try{boundary.observe(pulse.toString());send(frames,pulse);}catch(IOException closed){while(!ownerGone.get())Thread.sleep(20);return;}}
                    return;
                }
                long revision=snapshot.get("revision").getAsLong();
                Set<String> fixtureSubmissions=new HashSet<>(); // Explicit synthetic enqueue recorder; no engine.
                for(int count=0;count<8;count++) {
                    String text=frames.read(args.length==2 && args[1].equals("client-partial-frame")?500:5000); require(text!=null);
                    JsonObject message=WireMessages.parse(text),request=message.getAsJsonObject("body");
                    String type=message.get("message_type").getAsString();
                    if(type.equals("shutdown")) {
                        require(request.get("session_id").getAsString().equals(session) && request.get("viewer_id").getAsString().equals(viewer));
                        send(frames,envelope("shutdown","shutdown-ok",request)); return;
                    }
                    require(type.equals("command"));
                    SubmissionLedger.Prepared prepared=boundary.dispatch(text,value->require(fixtureSubmissions.add(value.get("message_id").getAsString())));
                    JsonObject acknowledgement=prepared.receipt();acknowledgement.addProperty("message_id","ack-"+count);
                    send(frames,acknowledgement);
                    if(prepared.shouldSubmit) {
                        if(choiceMode) {
                            // Explicitly simulated fixture confirmation, never an engine-backed claim.
                            JsonObject confirmed=boundary.recordOutcome(message.get("message_id").getAsString(),"confirmed",null);
                            confirmed.addProperty("message_id","fixture-confirmed");send(frames,confirmed);
                        }
                        if(args.length==2 && args[1].equals("session-error")) {
                            JsonObject failed=new JsonObject();failed.addProperty("session_id",session);failed.addProperty("viewer_id",viewer);
                            failed.addProperty("terminal",true);failed.addProperty("code","SESSION_FAILED");
                            JsonObject error=envelope("error","fixture-session-error",failed);
                            SessionErrors.parse(error.toString(),session,viewer);send(frames,error);return;
                        }
                        JsonObject result=new JsonObject();result.addProperty("fixture_only",true);
                        JsonObject terminal=snapshot.deepCopy();terminal.addProperty("status","finished");terminal.addProperty("result","fixture_complete");
                        terminal.addProperty("revision",revision+1);terminal.add("decision",JsonNull.INSTANCE);terminal.add("actions",new JsonArray());
                        result.add("snapshot",terminal);JsonObject resultMessage=envelope("result","fixture-result",result);
                        boundary.observe(resultMessage.toString());send(frames,resultMessage);
                    }
                }
                throw new IOException("DUMMY_LIMIT");
                }
            }
        } catch(Exception error) { if(!ownerGone.get()) { System.err.println("DUMMY_FAILED");System.exit(2); } }
        finally { if(key!=null)Arrays.fill(key,(byte)0); }
    }
}

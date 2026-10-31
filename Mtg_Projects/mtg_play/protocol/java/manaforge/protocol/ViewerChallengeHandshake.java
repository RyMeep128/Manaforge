package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

/** Pre-auth hello exchange; copies no peer-supplied identity or compatibility fields. */
public final class ViewerChallengeHandshake {
    private static final SecureRandom RANDOM=new SecureRandom();
    private static void fail() throws IOException {throw new WireEnvelope.EnvelopeException("AUTH_FAILED");}
    private static String nonce(JsonElement value) throws IOException {
        if(value==null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString() || !value.getAsString().matches("[0-9a-f]{64}"))fail();return value.getAsString();
    }
    private static JsonObject body(String text,boolean response) throws IOException {
        if(text==null || text.getBytes(StandardCharsets.UTF_8).length>4096)fail();
        JsonObject value=WireEnvelope.parse(text),body=value.getAsJsonObject("body");
        if(!value.get("message_type").getAsString().equals("hello") || !value.get("message_id").getAsString().equals(response?"auth-nonce":"auth-challenge") || body.size()!=(response?4:3)
            || !body.has("auth_exchange_version") || !body.get("auth_exchange_version").isJsonPrimitive() || !body.get("auth_exchange_version").getAsJsonPrimitive().isNumber() || !body.get("auth_exchange_version").getAsString().equals("1")
            || !body.has("stage") || !body.get("stage").isJsonPrimitive() || !body.get("stage").getAsJsonPrimitive().isString() || !body.get("stage").getAsString().equals(response?"client_nonce":"gateway_challenge"))fail();
        nonce(body.get("server_nonce"));if(response)nonce(body.get("client_nonce"));return body;
    }
    private static String message(String server,String client) throws IOException {
        nonce(new JsonPrimitive(server));if(client!=null)nonce(new JsonPrimitive(client));
        JsonObject value=new JsonObject(),body=new JsonObject();value.addProperty("wire_version",1);value.addProperty("message_type","hello");value.addProperty("message_id",client==null?"auth-challenge":"auth-nonce");
        body.addProperty("auth_exchange_version",1);body.addProperty("stage",client==null?"gateway_challenge":"client_nonce");body.addProperty("server_nonce",server);if(client!=null)body.addProperty("client_nonce",client);value.add("body",body);return value.toString();
    }
    public static String challenge(String server) throws IOException{return message(server,null);}
    public static String response(String server,String client) throws IOException{if(client==null)fail();return message(server,client);}
    public static String readChallenge(String text) throws IOException{return nonce(body(text,false).get("server_nonce"));}
    public static String readResponse(String text,String expectedServer) throws IOException{JsonObject body=body(text,true);if(!nonce(body.get("server_nonce")).equals(expectedServer))fail();return nonce(body.get("client_nonce"));}
    private static String fresh(){byte[] bytes=new byte[32];RANDOM.nextBytes(bytes);StringBuilder text=new StringBuilder();for(byte b:bytes)text.append(String.format("%02x",b&255));Arrays.fill(bytes,(byte)0);return text.toString();}
    private static int remaining(long started,int budget,BooleanSupplier cancel) throws IOException {
        if(cancel.getAsBoolean() || Thread.currentThread().isInterrupted())throw new WireEnvelope.EnvelopeException("AUTH_CANCELLED");long left=TimeUnit.MILLISECONDS.toNanos(budget)-(System.nanoTime()-started);if(left<=0)throw new WireEnvelope.EnvelopeException("AUTH_TIMEOUT");return (int)Math.max(1,(left+999999)/1000000);
    }
    public static GatewayHandshake.ViewerContext accept(LoopbackFrameReader owned,String trustedClient,String trustedGateway,byte[] viewerKey,int milliseconds,BooleanSupplier cancel) throws IOException {
        if(owned==null || milliseconds<1 || milliseconds>60000 || cancel==null)throw new IllegalArgumentException("AUTH_CONTEXT");
        long started=System.nanoTime();byte[] key=null;
        try {
            if(!owned.beginViewerChallenge())fail();remaining(started,milliseconds,cancel);
            if(viewerKey==null || viewerKey.length!=32)fail();key=viewerKey.clone();
            JsonObject client=ViewerAuthentication.parse(trustedClient),gateway=ViewerAuthentication.parse(trustedGateway);
            if(!client.get("message_id").getAsString().equals("auth-client") || !gateway.get("message_id").getAsString().equals("auth-gateway"))fail();
            if(!client.getAsJsonObject("body").get("role").getAsString().equals("client") || !gateway.getAsJsonObject("body").get("role").getAsString().equals("gateway"))fail();
            for(String field:new String[]{"protocol_version","engine_version","artifact_manifest_sha256","session_id","viewer_id"})if(!client.getAsJsonObject("body").get(field).equals(gateway.getAsJsonObject("body").get(field)))fail();
            String server=fresh();owned.write(challenge(server),remaining(started,milliseconds,cancel),cancel);
            String clientNonce=readResponse(owned.read(remaining(started,milliseconds,cancel),cancel),server);
            for(JsonObject hello:new JsonObject[]{client,gateway}){JsonObject body=hello.getAsJsonObject("body");body.addProperty("server_nonce",server);body.addProperty("client_nonce",clientNonce);body.addProperty("proof",new String(new char[64]).replace('\0','0'));}
            GatewayHandshake.ViewerContext context=GatewayHandshake.accept(owned,client.toString(),gateway.toString(),key,remaining(started,milliseconds,cancel),cancel);remaining(started,milliseconds,cancel);return context;
        }catch(IOException | RuntimeException error){try{owned.close();}catch(IOException ignored){}String code="AUTH_FAILED";
            boolean cancelled=Thread.currentThread().isInterrupted();try{cancelled|=cancel.getAsBoolean();}catch(RuntimeException ignored){}
            if(cancelled)code="AUTH_CANCELLED";
            else if(error instanceof TextFrame.FrameException && ((TextFrame.FrameException)error).code.contains("TIMEOUT"))code="AUTH_TIMEOUT";
            else if(error instanceof WireEnvelope.EnvelopeException){String value=((WireEnvelope.EnvelopeException)error).code;if(value.equals("AUTH_TIMEOUT") || value.equals("AUTH_CANCELLED"))code=value;}
            throw new WireEnvelope.EnvelopeException(code);
        }finally{if(key!=null)Arrays.fill(key,(byte)0);}
    }
}

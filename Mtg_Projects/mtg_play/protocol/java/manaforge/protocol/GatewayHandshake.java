package manaforge.protocol;
import com.google.gson.*;
import java.io.IOException;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

/** Trusted expectations only. Does not create listeners, keys, nonces, decks or engine sessions. */
public final class GatewayHandshake {
    public static final class ViewerContext {
        public final String sessionId,viewerId,engineVersion,artifactManifestSha256;
        private ViewerContext(JsonObject trusted) {
            sessionId=trusted.get("session_id").getAsString();viewerId=trusted.get("viewer_id").getAsString();
            engineVersion=trusted.get("engine_version").getAsString();artifactManifestSha256=trusted.get("artifact_manifest_sha256").getAsString();
        }
    }
    public static ViewerContext accept(LoopbackFrameReader owned,String expectedClient,String gatewayTemplate,byte[] viewerKey,int milliseconds) throws IOException {
        return accept(owned,expectedClient,gatewayTemplate,viewerKey,milliseconds,()->false);
    }
    // Invalid budget arguments precede transfer. Failure thereafter closes the socket; success leaves it with the caller.
    public static ViewerContext accept(LoopbackFrameReader owned,String expectedClient,String gatewayTemplate,byte[] viewerKey,int milliseconds,BooleanSupplier cancellation) throws IOException {
        if(owned==null || milliseconds<1 || milliseconds>60000 || cancellation==null)throw new IllegalArgumentException("AUTH_CONTEXT");
        long started=System.nanoTime();byte[] key=null;
        try {
            if(!owned.beginViewerHandshake())fail("AUTH_FAILED");
            remaining(started,milliseconds,cancellation);
            if(viewerKey==null || viewerKey.length!=32)fail("AUTH_FAILED");key=viewerKey.clone();
            JsonObject client=ViewerAuthentication.parse(expectedClient).getAsJsonObject("body");
            JsonObject gateway=ViewerAuthentication.parse(gatewayTemplate);
            if(!client.get("role").getAsString().equals("client") || !gateway.getAsJsonObject("body").get("role").getAsString().equals("gateway"))fail("AUTH_FAILED");
            for(String field:new String[]{"protocol_version","engine_version","artifact_manifest_sha256","session_id","viewer_id","server_nonce","client_nonce"})
                if(!client.get(field).equals(gateway.getAsJsonObject("body").get(field)))fail("AUTH_FAILED");
            try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(expectedClient,key)) {
                if(!verifier.verify(owned.read(remaining(started,milliseconds,cancellation),cancellation)))fail("AUTH_FAILED");
                gateway.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(gatewayTemplate,key));
                owned.write(gateway.toString(),remaining(started,milliseconds,cancellation),cancellation);
                remaining(started,milliseconds,cancellation);return new ViewerContext(client);
            }
        }catch(TextFrame.FrameException error) {
            close(owned);String code=error.code.equals("FRAME_CANCELLED") || error.code.equals("FRAME_WRITE_CANCELLED")?"AUTH_CANCELLED":
                error.code.equals("FRAME_TIMEOUT") || error.code.equals("FRAME_WRITE_TIMEOUT")?"AUTH_TIMEOUT":"AUTH_FAILED";
            throw new WireEnvelope.EnvelopeException(code);
        }catch(WireEnvelope.EnvelopeException error) {
            close(owned);throw new WireEnvelope.EnvelopeException(error.code.equals("AUTH_CANCELLED") || error.code.equals("AUTH_TIMEOUT")?error.code:"AUTH_FAILED");
        }catch(IOException | RuntimeException error){close(owned);throw new WireEnvelope.EnvelopeException("AUTH_FAILED");}
        finally{if(key!=null)Arrays.fill(key,(byte)0);}
    }
    private static int remaining(long started,int milliseconds,BooleanSupplier cancellation) throws IOException {
        if(cancellation.getAsBoolean() || Thread.currentThread().isInterrupted())fail("AUTH_CANCELLED");
        long nanos=TimeUnit.MILLISECONDS.toNanos(milliseconds)-(System.nanoTime()-started);
        if(nanos<=0)fail("AUTH_TIMEOUT");return (int)Math.max(1,(nanos+999999)/1000000);
    }
    private static void fail(String code) throws WireEnvelope.EnvelopeException {throw new WireEnvelope.EnvelopeException(code);}
    private static void close(LoopbackFrameReader owned){try{owned.close();}catch(IOException ignored){/* Preserve safe authentication failure. */}}
}

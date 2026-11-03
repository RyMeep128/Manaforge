package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.net.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Public challenge corpus and real-loopback negative/freshness checks. */
public final class ChallengeFixtureConsumer {
    private static void require(boolean value){if(!value)throw new AssertionError("Challenge fixture failed");}
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        for(JsonElement item:corpus.getAsJsonArray("positive")){JsonObject c=item.getAsJsonObject();String value=c.get("response").getAsBoolean()?ViewerChallengeHandshake.readResponse(c.get("envelope").toString(),new String(new char[64]).replace('\0','1')):ViewerChallengeHandshake.readChallenge(c.get("envelope").toString());require(value.length()==64);}
        for(JsonElement item:corpus.getAsJsonArray("negative")){JsonObject c=item.getAsJsonObject();boolean rejected=false;try{if(c.get("response").getAsBoolean())ViewerChallengeHandshake.readResponse(c.get("envelope").toString(),new String(new char[64]).replace('\0','1'));else ViewerChallengeHandshake.readChallenge(c.get("envelope").toString());}catch(IOException expected){rejected=true;}require(rejected);}
        JsonObject auth=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[1])),StandardCharsets.UTF_8)).getAsJsonObject();String client=auth.getAsJsonArray("positive").get(0).getAsJsonObject().get("envelope").toString(),gateway=auth.getAsJsonArray("positive").get(1).getAsJsonObject().get("envelope").toString();
        byte[] key=new byte[32];for(int i=0;i<32;i++)key[i]=(byte)i;Set<String> nonces=new HashSet<>();ExecutorService pool=Executors.newSingleThreadExecutor();
        try {
            for(int mode=0;mode<4;mode++) {
                try(ServerSocket listener=new ServerSocket(0,1,InetAddress.getByName("127.0.0.1"));Socket peer=new Socket("127.0.0.1",listener.getLocalPort());LoopbackFrameReader owned=new LoopbackFrameReader(listener.accept())) {
                    peer.setSoTimeout(2000);final int selected=mode;
                    Future<String> attempt=pool.submit(()->{try{ViewerChallengeHandshake.accept(owned,client,gateway,key,selected==2?80:1000,()->selected==3);return "accepted";}catch(WireEnvelope.EnvelopeException error){return error.code;}});
                    if(mode<2) {
                        String nonce=ViewerChallengeHandshake.readChallenge(TextFrame.read(peer.getInputStream()));require(nonces.add(nonce));
                        // A response copied from another connection/challenge must not reach the proof stage.
                        TextFrame.write(peer.getOutputStream(),ViewerChallengeHandshake.response(new String(new char[64]).replace('\0','0'),new String(new char[64]).replace('\0','2')));peer.getOutputStream().flush();
                    }
                    require(attempt.get(3,TimeUnit.SECONDS).equals(mode==2?"AUTH_TIMEOUT":mode==3?"AUTH_CANCELLED":"AUTH_FAILED"));require(owned.isClosed());
                }
            }
            for(int i=0;i<32;i++)require(key[i]==(byte)i);
        }finally{pool.shutdownNow();require(pool.awaitTermination(3,TimeUnit.SECONDS));}
        System.out.println("Java fresh challenges: 2 positive/10 negative fixtures and 4 real loopback cases passed");
    }
}

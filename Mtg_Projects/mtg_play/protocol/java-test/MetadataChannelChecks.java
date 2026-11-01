import com.google.gson.*;
import manaforge.protocol.*;
import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Engine-free private transport checks. No engine, filesystem metadata or product listener. */
public final class MetadataChannelChecks {
    static final String GAME="12345678-abcd-1234-abcd-123456789abc",VIEWER="87654321-abcd-1234-abcd-123456789abc",HASH=String.join("",Collections.nCopies(64,"0"));
    static int checks;
    static void check(boolean value){checks++;if(!value)throw new AssertionError("METADATA_CHANNEL_CHECK");}
    static JsonObject request(){JsonObject out=new JsonObject();out.addProperty("command","metadata");out.addProperty("game",GAME);out.addProperty("player",VIEWER);out.addProperty("cycle",8);JsonArray ids=new JsonArray();ids.add(GAME);out.add("object_ids",ids);out.add("identified_ids",ids.deepCopy());return out;}
    static LoopbackFrameReader connect(ManaforgeMetadataChannel server,byte[] key) throws Exception {
        Socket socket=new Socket();socket.connect(new InetSocketAddress("127.0.0.1",server.port()),1000);LoopbackFrameReader frames=new LoopbackFrameReader(socket);
        try {
            String nonce=ViewerChallengeHandshake.readChallenge(frames.read(3000)),clientNonce=String.join("",Collections.nCopies(64,"b"));
            frames.write(ViewerChallengeHandshake.response(nonce,clientNonce),3000);
            JsonObject client=ManaforgeOpeningLoopback.hello(server.session(),VIEWER,"synthetic-engine",HASH,"client"),gateway=ManaforgeOpeningLoopback.hello(server.session(),VIEWER,"synthetic-engine",HASH,"gateway");
            for(JsonObject hello:new JsonObject[]{client,gateway}){hello.getAsJsonObject("body").addProperty("server_nonce",nonce);hello.getAsJsonObject("body").addProperty("client_nonce",clientNonce);}
            client.getAsJsonObject("body").addProperty("proof",ViewerAuthentication.computeProof(client.toString(),key));frames.write(client.toString(),3000);
            try(ViewerAuthentication.Verifier verifier=new ViewerAuthentication.Verifier(gateway.toString(),key)){if(!verifier.verify(frames.read(3000)))throw new IOException("AUTH_FAILED");}
            return frames;
        }catch(Exception failure){frames.close();throw failure;}
    }
    public static void main(String[] args) throws Exception {
        check(ManaforgeMetadataChannel.validate(request().toString(),GAME,VIEWER).equals(request()));
        for(int mode=0;mode<12;mode++) {
            JsonObject bad=request();
            if(mode==0)bad.addProperty("command","respond");
            if(mode==1)bad.addProperty("game",VIEWER);
            if(mode==2)bad.addProperty("player",GAME);
            if(mode==3)bad.addProperty("cycle",-1);
            if(mode==4)bad.addProperty("cycle",true);
            if(mode==5)bad.addProperty("cycle",2147483648L);
            if(mode==6)bad.addProperty("path","PRIVATE_PATH");
            if(mode==7)bad.getAsJsonArray("object_ids").add(GAME);
            if(mode==8)bad.getAsJsonArray("identified_ids").add(VIEWER);
            if(mode==9)bad.getAsJsonArray("object_ids").add("invalid");
            if(mode==10)bad.remove("object_ids");
            if(mode==11)for(int i=0;i<256;i++)bad.getAsJsonArray("object_ids").add(UUID.randomUUID().toString());
            try{ManaforgeMetadataChannel.validate(bad.toString(),GAME,VIEWER);throw new AssertionError("BAD_METADATA_ACCEPTED");}
            catch(IOException failure){check(failure.getMessage().equals("METADATA_REQUEST_INVALID") && failure.getCause()==null);}
        }
        String duplicate=request().toString().replace("\"cycle\":8","\"cycle\":8,\"cycle\":9");
        try{ManaforgeMetadataChannel.validate(duplicate,GAME,VIEWER);throw new AssertionError("DUPLICATE_ACCEPTED");}catch(IOException expected){check(true);}
        JsonObject boundary=request();for(int i=0;i<255;i++)boundary.getAsJsonArray("object_ids").add(UUID.randomUUID().toString());check(ManaforgeMetadataChannel.validate(boundary.toString(),GAME,VIEWER).getAsJsonArray("object_ids").size()==256);
        byte[] key=new byte[32];new java.security.SecureRandom().nextBytes(key);byte[] original=key.clone();AtomicInteger calls=new AtomicInteger();
        try(ManaforgeMetadataChannel server=new ManaforgeMetadataChannel(key,GAME,VIEWER,"synthetic-engine",HASH,command->{calls.incrementAndGet();check(command.equals(request()));JsonObject result=new JsonObject();result.addProperty("status","ok");result.addProperty("private_marker","PRIVATE_METADATA_CANARY");return result;});LoopbackFrameReader client=connect(server,key)) {
            check(calls.get()==0);client.write(request().toString(),3000);JsonObject result=WireEnvelope.parseObject(client.read(3000));check(result.get("private_marker").getAsString().equals("PRIVATE_METADATA_CANARY") && calls.get()==1);
            JsonObject wrong=request();wrong.addProperty("player",GAME);client.write(wrong.toString(),3000);
            try{check(client.read(3000)==null && calls.get()==1);}catch(IOException expected){check(calls.get()==1);}
        }
        check(Arrays.equals(key,original));
        try(ManaforgeMetadataChannel server=new ManaforgeMetadataChannel(key,GAME,VIEWER,"synthetic-engine",HASH,command->{calls.incrementAndGet();throw new IOException("PRIVATE_NATIVE_FAILURE");});LoopbackFrameReader client=connect(server,key)) {
            client.write(request().toString(),3000);String result=client.read(3000);check(result.contains("METADATA_READ_FAILED") && !result.contains("PRIVATE_NATIVE_FAILURE"));
        }
        int before=calls.get();
        try(ManaforgeMetadataChannel server=new ManaforgeMetadataChannel(key,GAME,VIEWER,"synthetic-engine",HASH,command->{calls.incrementAndGet();return request();})) {
            byte[] wrong=key.clone();wrong[0]^=1;try(LoopbackFrameReader client=connect(server,wrong)){throw new AssertionError("WRONG_KEY_ACCEPTED");}catch(IOException expected){check(calls.get()==before);}
        }
        try(ManaforgeMetadataChannel server=new ManaforgeMetadataChannel(key,GAME,VIEWER,"synthetic-engine",HASH,command->{calls.incrementAndGet();return request();});Socket socket=new Socket("127.0.0.1",server.port());LoopbackFrameReader client=new LoopbackFrameReader(socket)) {
            client.read(3000);client.write(request().toString(),3000);try{check(client.read(3000)==null && calls.get()==before);}catch(IOException expected){check(calls.get()==before);}
        }
        ManaforgeMetadataChannel idle=new ManaforgeMetadataChannel(key,GAME,VIEWER,"synthetic-engine",HASH,command->request());
        try(LoopbackFrameReader client=connect(idle,key)){idle.close();try{check(client.read(3000)==null);}catch(IOException expected){check(true);}}finally{idle.close();}
        java.util.concurrent.CountDownLatch entered=new java.util.concurrent.CountDownLatch(1),release=new java.util.concurrent.CountDownLatch(1);
        ManaforgeMetadataChannel blocked=new ManaforgeMetadataChannel(key,GAME,VIEWER,"synthetic-engine",HASH,command->{entered.countDown();while(true)try{release.await();break;}catch(InterruptedException ignored){}return request();});
        try(LoopbackFrameReader client=connect(blocked,key)) {
            client.write(request().toString(),3000);check(entered.await(3,java.util.concurrent.TimeUnit.SECONDS));
            try{blocked.close();throw new AssertionError("BLOCKED_READER_CLEANUP_CLAIMED");}catch(IOException expected){check(expected.getMessage().equals("METADATA_CLEANUP_UNCERTAIN"));}
        }finally{release.countDown();blocked.close();Arrays.fill(key,(byte)0);Arrays.fill(original,(byte)0);}
        System.out.println("Private metadata channel: "+checks+" bounded request/authentication/privacy/lifecycle checks passed; no XMage binding");
    }
}

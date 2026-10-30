package manaforge.protocol;
import java.io.*;
import java.net.*;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Real owned socket checks for writes, without engine/deck data. */
public final class WriteDeadlineFixtureConsumer {
    private static final ExecutorService POOL=Executors.newFixedThreadPool(4);
    private interface Write {void run() throws IOException;}
    private static void require(boolean value){if(!value)throw new AssertionError("Write deadline fixture failed");}
    private static String failure(Write write) throws IOException {
        try{write.run();throw new AssertionError("Accepted failed write");}
        catch(TextFrame.FrameException error){require(error.getMessage().equals(error.code));return error.code;}
    }
    private static String large(){char[] text=new char[TextFrame.MAX_BYTES];Arrays.fill(text,'x');return new String(text);}
    private static final class Pair implements AutoCloseable {
        final Socket peer;final LoopbackFrameReader channel;
        Pair() throws IOException {
            Socket client=new Socket();Socket accepted=null;
            try(ServerSocket listener=new ServerSocket()) {
                listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0));listener.setSoTimeout(2000);
                client.setReceiveBufferSize(1024);client.setSoTimeout(2000);
                client.connect(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),listener.getLocalPort()),2000);
                accepted=listener.accept();accepted.setSendBufferSize(1024);channel=new LoopbackFrameReader(accepted);peer=client;
            }catch(IOException | RuntimeException error){client.close();if(accepted!=null)accepted.close();throw error;}
        }
        public void close() throws IOException{try{channel.close();}finally{peer.close();}}
    }
    private static void started(LoopbackFrameReader channel) throws InterruptedException {
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(1);
        while(!channel.writeInProgress() && System.nanoTime()<until)Thread.sleep(1);
        require(channel.writeInProgress());
    }
    public static void main(String[] args) throws Exception {
        int passed=0;
        try {
            try(Pair p=new Pair()) {
                Future<?> write=POOL.submit(()->{p.channel.write("one",1000);p.channel.write("two",1000);return null;});
                require("one".equals(TextFrame.read(p.peer.getInputStream())) && "two".equals(TextFrame.read(p.peer.getInputStream())));
                TextFrame.write(p.peer.getOutputStream(),"reply");require("reply".equals(p.channel.read(1000)));write.get(2,TimeUnit.SECONDS);passed++;
            }
            try(Pair p=new Pair()) {
                Future<String> write=POOL.submit(()->failure(()->p.channel.write(large(),150)));
                require("FRAME_WRITE_TIMEOUT".equals(write.get(2,TimeUnit.SECONDS)) && p.channel.isClosed());passed++;
            }
            try(Pair p=new Pair()) {
                AtomicBoolean cancel=new AtomicBoolean();Future<String> write=POOL.submit(()->failure(()->p.channel.write(large(),5000,cancel::get)));
                started(p.channel);cancel.set(true);require("FRAME_WRITE_CANCELLED".equals(write.get(2,TimeUnit.SECONDS)) && p.channel.isClosed());passed++;
            }
            try(Pair p=new Pair()) {
                Future<String> write=POOL.submit(()->failure(()->p.channel.write(large(),5000)));started(p.channel);p.channel.close();
                require("FRAME_CLOSED".equals(write.get(2,TimeUnit.SECONDS)));passed++;
            }
            try(Pair p=new Pair()) {
                Future<String> first=POOL.submit(()->failure(()->p.channel.write(large(),5000)));started(p.channel);
                require("FRAME_CONCURRENT_WRITE".equals(failure(()->p.channel.write("other",1000))));
                require("FRAME_CLOSED".equals(first.get(2,TimeUnit.SECONDS)));passed++;
            }
            String[] invalid={null,"","\ufeffbad",new String(new char[]{(char)0xd800})};
            String[] codes={"FRAME_SIZE","FRAME_SIZE","FRAME_BOM","FRAME_UTF8"};
            for(int i=0;i<invalid.length;i++)try(Pair p=new Pair()) {
                final String text=invalid[i];require(codes[i].equals(failure(()->p.channel.write(text,1000))) && !p.channel.isClosed());
                p.channel.write("valid",1000);require("valid".equals(TextFrame.read(p.peer.getInputStream())));passed++;
            }
            for(int budget:new int[]{0,60001})try(Pair p=new Pair()) {
                try{p.channel.write("bad",budget);throw new AssertionError("Invalid budget accepted");}catch(IllegalArgumentException expected){}
                p.channel.write("valid",1000);require("valid".equals(TextFrame.read(p.peer.getInputStream())));passed++;
            }
            try(Pair p=new Pair();SubmissionLedger ledger=new SubmissionLedger("session","one",4096)) {
                String command="{\"wire_version\":1,\"message_type\":\"command\",\"message_id\":\"c1\",\"body\":{\"session_id\":\"session\",\"viewer_id\":\"one\",\"revision\":7,\"decision_id\":\"decision\",\"operation\":\"perform\",\"action_id\":\"action\"}}";
                require(ledger.prepare(command,null).shouldSubmit);
                require("FRAME_WRITE_CANCELLED".equals(failure(()->p.channel.write(command,1000,()->true))));ledger.disconnected();
                SubmissionLedger.Prepared receipt=ledger.prepare(command,null);require(!receipt.shouldSubmit && receipt.receipt().getAsJsonObject("body").get("outcome").getAsString().equals("uncertain"));passed++;
            }
            try(Pair p=new Pair()) {
                AtomicReference<Thread> writer=new AtomicReference<>();
                Future<String> write=POOL.submit(()->{writer.set(Thread.currentThread());try{return failure(()->p.channel.write(large(),5000));}finally{Thread.interrupted();}});
                started(p.channel);writer.get().interrupt();require("FRAME_WRITE_CANCELLED".equals(write.get(2,TimeUnit.SECONDS)));passed++;
            }
            try(Pair p=new Pair()) {
                p.channel.write("first",120);require("first".equals(TextFrame.read(p.peer.getInputStream())));
                Thread.sleep(180);require(!p.channel.isClosed());p.channel.write("later",1000);
                require("later".equals(TextFrame.read(p.peer.getInputStream())));passed++;
            }
            require(passed==14);
        }finally{POOL.shutdownNow();require(POOL.awaitTermination(3,TimeUnit.SECONDS));}
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
        while(watchers()>0 && System.nanoTime()<until)Thread.sleep(1);
        require(watchers()==0);System.out.println("Java frame writes: 14 real loopback checks plus watchdog cleanup passed");
    }
    private static long watchers(){return Thread.getAllStackTraces().keySet().stream().filter(t->t.isAlive() && t.getName().equals("manaforge-frame-write-watch")).count();}
}

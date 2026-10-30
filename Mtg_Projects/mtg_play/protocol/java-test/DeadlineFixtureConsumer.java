package manaforge.protocol;
import java.io.*;
import java.net.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Real owned IPv4 loopback checks. No XMage, decks or external service. */
public final class DeadlineFixtureConsumer {
    private static final ExecutorService POOL=Executors.newFixedThreadPool(4);
    private interface Read {String get() throws IOException;}
    private static void require(boolean value){if(!value)throw new AssertionError("Deadline fixture failed");}
    private static String failure(Read read) throws IOException {
        try{read.get();throw new AssertionError("Accepted failed read");}
        catch(TextFrame.FrameException error){require(error.getMessage().equals(error.code));return error.code;}
    }
    private static final class Pair implements AutoCloseable {
        final Socket sender;final LoopbackFrameReader reader;
        Pair() throws IOException {
            Socket client=new Socket();Socket accepted=null;
            try(ServerSocket listener=new ServerSocket()) {
                listener.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0));listener.setSoTimeout(2000);
                client.connect(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),listener.getLocalPort()),2000);
                accepted=listener.accept();accepted.setSoLinger(true,5);reader=new LoopbackFrameReader(accepted);
                require(accepted.getSoLinger()==-1);sender=client;
            } catch(IOException | RuntimeException error){client.close();if(accepted!=null)accepted.close();throw error;}
        }
        void send(byte[] bytes) throws IOException{sender.getOutputStream().write(bytes);}
        public void close() throws IOException{try{reader.close();}finally{sender.close();}}
    }
    private static void started(LoopbackFrameReader reader) throws InterruptedException {
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(1);
        while(!reader.readInProgress() && System.nanoTime()<until)Thread.sleep(1);
        require(reader.readInProgress());
    }
    public static void main(String[] args) throws Exception {
        int passed=0;
        try {
            try(Pair p=new Pair()) {
                TextFrame.write(p.sender.getOutputStream(),"one");TextFrame.write(p.sender.getOutputStream(),"two");p.sender.shutdownOutput();
                require("one".equals(p.reader.read(1000)) && "two".equals(p.reader.read(1000)) && p.reader.read(1000)==null && !p.reader.isClosed());passed++;
            }
            byte[] partial=new byte[]{0,0,0,4,97};
            for(int size:new int[]{0,2,5})try(Pair p=new Pair()) {
                byte[] bytes=new byte[size];System.arraycopy(partial,0,bytes,0,size);if(size>0)p.send(bytes);
                long start=System.nanoTime();require("FRAME_TIMEOUT".equals(failure(()->p.reader.read(120))));
                long elapsed=TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start);
                require(elapsed>=80 && elapsed<2000 && p.reader.isClosed());require("FRAME_CLOSED".equals(failure(()->p.reader.read(1000))));passed++;
            }
            try(Pair p=new Pair()) {
                AtomicBoolean stop=new AtomicBoolean();
                Future<?> writer=POOL.submit(()->{
                    try{byte[] frame=new byte[36];frame[3]=32;for(byte value:frame){Thread.sleep(30);if(stop.get())break;p.send(new byte[]{value});}}
                    catch(IOException expected){}catch(InterruptedException interrupted){Thread.currentThread().interrupt();}
                });
                try{long start=System.nanoTime();require("FRAME_TIMEOUT".equals(failure(()->p.reader.read(180))));require(TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-start)<1500 && p.reader.isClosed());}
                finally{stop.set(true);writer.get(2,TimeUnit.SECONDS);}passed++;
            }
            for(int size:new int[]{2,5})try(Pair p=new Pair()) {
                byte[] bytes=new byte[size];System.arraycopy(partial,0,bytes,0,size);p.send(bytes);AtomicBoolean cancel=new AtomicBoolean();
                Future<String> read=POOL.submit(()->failure(()->p.reader.read(5000,cancel::get)));started(p.reader);cancel.set(true);
                require("FRAME_CANCELLED".equals(read.get(2,TimeUnit.SECONDS)) && p.reader.isClosed());passed++;
            }
            try(Pair p=new Pair()) {
                Future<String> read=POOL.submit(()->failure(()->p.reader.read(5000)));started(p.reader);p.reader.close();
                require("FRAME_CLOSED".equals(read.get(2,TimeUnit.SECONDS)));passed++;
            }
            String[] codes={"FRAME_SIZE","FRAME_TRUNCATED","FRAME_UTF8"};
            byte[][] malformed={new byte[4],new byte[]{0,0,0,4,1},new byte[]{0,0,0,1,(byte)255}};
            for(int i=0;i<codes.length;i++)try(Pair p=new Pair()) {
                p.send(malformed[i]);p.sender.shutdownOutput();require(codes[i].equals(failure(()->p.reader.read(1000))) && p.reader.isClosed());passed++;
            }
            for(int invalid:new int[]{0,60001})try(Pair p=new Pair()) {
                TextFrame.write(p.sender.getOutputStream(),"still-owned");
                try{p.reader.read(invalid);throw new AssertionError("Accepted invalid budget");}catch(IllegalArgumentException expected){}
                require("still-owned".equals(p.reader.read(1000)));passed++;
            }
            try(Pair p=new Pair()) {
                Future<String> first=POOL.submit(()->failure(()->p.reader.read(5000)));started(p.reader);
                require("FRAME_CONCURRENT".equals(failure(()->p.reader.read(1000))));require("FRAME_CLOSED".equals(first.get(2,TimeUnit.SECONDS)));passed++;
            }
            try(Pair p=new Pair()) {require("FRAME_CANCELLED".equals(failure(()->p.reader.read(1000,()->true))) && p.reader.isClosed());passed++;}
            try(Pair p=new Pair()) {
                Future<String> read=POOL.submit(()->{Thread.currentThread().interrupt();try{return failure(()->p.reader.read(1000));}finally{Thread.interrupted();}});
                require("FRAME_CANCELLED".equals(read.get(2,TimeUnit.SECONDS)) && p.reader.isClosed());passed++;
            }
            require(passed==16);System.out.println("Java owned frame deadlines: 16 real loopback checks passed");
        } finally{POOL.shutdownNow();require(POOL.awaitTermination(3,TimeUnit.SECONDS));}
    }
}

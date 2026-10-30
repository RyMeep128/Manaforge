package manaforge.protocol;

import java.io.*;
import java.net.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;

/** Owns one connected loopback socket. Worker-side, one reader; no write/handshake policy. */
public final class LoopbackFrameReader implements AutoCloseable {
    private final Socket socket;
    private final AtomicBoolean closed=new AtomicBoolean(),reading=new AtomicBoolean();
    public LoopbackFrameReader(Socket ownedSocket) throws IOException {
        if(ownedSocket==null || !ownedSocket.isConnected() || ownedSocket.isClosed()
            || !ownedSocket.getLocalAddress().isLoopbackAddress() || !ownedSocket.getInetAddress().isLoopbackAddress())
            throw new IllegalArgumentException("FRAME_SOCKET_CONTEXT");
        ownedSocket.setSoLinger(false,0);ownedSocket.setSoTimeout(25);socket=ownedSocket;
    }
    public boolean isClosed(){return closed.get();}
    public boolean readInProgress(){return reading.get();}
    public String read(int milliseconds) throws IOException{return read(milliseconds,()->false);}
    public String read(int milliseconds,BooleanSupplier cancellation) throws IOException {
        if(milliseconds<1 || milliseconds>60000 || cancellation==null)throw new IllegalArgumentException("FRAME_READ_CONTEXT");
        if(closed.get())throw new TextFrame.FrameException("FRAME_CLOSED");
        if(!reading.compareAndSet(false,true)){abort();throw new TextFrame.FrameException("FRAME_CONCURRENT");}
        try {
            DeadlineInput input=new DeadlineInput(milliseconds,cancellation);input.check();
            String text=TextFrame.read(input);input.check();return text;
        } catch(TextFrame.FrameException error){abort();throw error;}
        catch(IOException error){String code=closed.get()?"FRAME_CLOSED":"FRAME_IO";abort();throw new TextFrame.FrameException(code);}
        catch(RuntimeException error){abort();throw new TextFrame.FrameException("FRAME_IO");}
        finally{reading.set(false);}
    }
    private void abort(){try{close();}catch(IOException ignored){/* Preserve the safe primary failure. Owner still owns lifecycle cleanup. */}}
    public void close() throws IOException{if(closed.compareAndSet(false,true))socket.close();}
    private final class DeadlineInput extends InputStream {
        private final long started=System.nanoTime(),budget;
        private final BooleanSupplier cancellation;
        private final InputStream input;
        DeadlineInput(int milliseconds,BooleanSupplier cancellation) throws IOException {
            budget=TimeUnit.MILLISECONDS.toNanos(milliseconds);this.cancellation=cancellation;input=socket.getInputStream();
        }
        void check() throws IOException {
            if(cancellation.getAsBoolean() || Thread.currentThread().isInterrupted())throw new TextFrame.FrameException("FRAME_CANCELLED");
            if(closed.get())throw new TextFrame.FrameException("FRAME_CLOSED");
            if(System.nanoTime()-started>=budget)throw new TextFrame.FrameException("FRAME_TIMEOUT");
        }
        public int read() throws IOException{byte[] value=new byte[1];return read(value,0,1)<0?-1:value[0]&255;}
        public int read(byte[] bytes,int offset,int count) throws IOException {
            if(bytes==null)throw new NullPointerException();
            if(offset<0 || count<0 || offset>bytes.length-count)throw new IndexOutOfBoundsException();
            if(count==0)return 0;
            while(true) {
                check();long remaining=budget-(System.nanoTime()-started);
                int wait=(int)Math.max(1,Math.min(25,(remaining+999999)/1000000));
                socket.setSoTimeout(wait);
                try{return input.read(bytes,offset,count);}catch(SocketTimeoutException timeout){/* Recheck total budget/cancellation. */}
            }
        }
    }
}

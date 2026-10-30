package manaforge.protocol;

import java.io.*;
import java.net.*;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;

/** Owns one connected loopback socket. Worker-side, one reader and one writer; session/handshake policy stays outside. */
public final class LoopbackFrameReader implements AutoCloseable {
    private final Socket socket;
    private final AtomicBoolean closed=new AtomicBoolean(),reading=new AtomicBoolean(),writing=new AtomicBoolean();
    private final ScheduledThreadPoolExecutor watchdog;
    public LoopbackFrameReader(Socket ownedSocket) throws IOException {
        if(ownedSocket==null || !ownedSocket.isConnected() || ownedSocket.isClosed()
            || !ownedSocket.getLocalAddress().isLoopbackAddress() || !ownedSocket.getInetAddress().isLoopbackAddress())
            throw new IllegalArgumentException("FRAME_SOCKET_CONTEXT");
        ownedSocket.setSoLinger(false,0);ownedSocket.setSoTimeout(25);socket=ownedSocket;
        watchdog=new ScheduledThreadPoolExecutor(1,task->{Thread thread=new Thread(task,"manaforge-frame-write-watch");thread.setDaemon(true);return thread;});
        watchdog.setRemoveOnCancelPolicy(true);watchdog.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
    }
    public boolean isClosed(){return closed.get();}
    public boolean writeInProgress(){return writing.get();}
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
    public void write(String text,int milliseconds) throws IOException{write(text,milliseconds,()->false);}
    /** Success is local socket acceptance, never an engine acknowledgement. */
    public void write(String text,int milliseconds,BooleanSupplier cancellation) throws IOException {
        if(milliseconds<1 || milliseconds>60000 || cancellation==null)throw new IllegalArgumentException("FRAME_WRITE_CONTEXT");
        if(closed.get())throw new TextFrame.FrameException("FRAME_CLOSED");
        if(!writing.compareAndSet(false,true)){abort();throw new TextFrame.FrameException("FRAME_CONCURRENT_WRITE");}
        long started=System.nanoTime();WipeBuffer buffer=new WipeBuffer();
        WriteAttempt attempt=null;ScheduledFuture<?> watch=null;
        try {
            TextFrame.write(buffer,text); // preflight is complete before socket output
            attempt=new WriteAttempt(started,milliseconds,cancellation);
            try {
                attempt.check();watch=watchdog.scheduleAtFixedRate(attempt,0,10,TimeUnit.MILLISECONDS);
                OutputStream output=socket.getOutputStream();
                for(int offset=0;offset<buffer.size();) {
                    attempt.check();int count=Math.min(16384,buffer.size()-offset);
                    output.write(buffer.bytes(),offset,count);offset+=count;
                }
                attempt.finish();
            } catch(TextFrame.FrameException error){abort();throw error;}
            catch(IOException | RuntimeException error){String code=attempt.failureCode();abort();throw new TextFrame.FrameException(code);}
        } finally {
            if(attempt!=null)attempt.seal();if(watch!=null)watch.cancel(false);
            buffer.clear();writing.set(false);
        }
    }
    private static final class WipeBuffer extends ByteArrayOutputStream {
        byte[] bytes(){return buf;}
        void clear(){Arrays.fill(buf,0,count,(byte)0);reset();}
    }
    private final class WriteAttempt implements Runnable {
        private final long started,budget;
        private final BooleanSupplier cancellation;
        private final Thread writer=Thread.currentThread();
        private String reason;
        private boolean finished;
        WriteAttempt(long started,int milliseconds,BooleanSupplier cancellation) {
            this.started=started;budget=TimeUnit.MILLISECONDS.toNanos(milliseconds);this.cancellation=cancellation;
        }
        synchronized void check() throws IOException {
            if(reason==null && !finished) {
                try {
                    if(cancellation.getAsBoolean() || writer.isInterrupted())reason="FRAME_WRITE_CANCELLED";
                    else if(closed.get())reason="FRAME_CLOSED";
                    else if(System.nanoTime()-started>=budget)reason="FRAME_WRITE_TIMEOUT";
                } catch(RuntimeException error){reason="FRAME_WRITE_IO";}
            }
            if(reason!=null){abort();throw new TextFrame.FrameException(reason);}
        }
        public synchronized void run(){if(finished)return;try{check();}catch(IOException ignored){/* Socket closure releases the writer. */}}
        synchronized void finish() throws IOException{check();finished=true;}
        synchronized void seal(){finished=true;}
        synchronized String failureCode(){return reason!=null?reason:closed.get()?"FRAME_CLOSED":"FRAME_WRITE_IO";}
    }
    private void abort(){try{close();}catch(IOException ignored){/* Preserve the safe primary failure. Owner still owns lifecycle cleanup. */}}
    public void close() throws IOException{if(closed.compareAndSet(false,true))try{socket.close();}finally{watchdog.shutdownNow();}}
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

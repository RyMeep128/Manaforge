import java.util.Objects;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** Application-level XMage ping, independent of gameplay decisions and viewer activity. */
final class ManaforgeHeartbeat implements AutoCloseable {
    private final Runnable ping, failed;
    private final long periodMillis;
    private ScheduledExecutorService worker;

    ManaforgeHeartbeat(Runnable ping,Runnable failed) {this(ping,failed,30000);}
    ManaforgeHeartbeat(Runnable ping,Runnable failed,long periodMillis) {
        this.ping=Objects.requireNonNull(ping);this.failed=Objects.requireNonNull(failed);
        if(periodMillis<=0)throw new IllegalArgumentException("HEARTBEAT_PERIOD");
        this.periodMillis=periodMillis;
    }
    synchronized void start() {
        if(worker!=null)return;
        worker=Executors.newSingleThreadScheduledExecutor(task->{
            Thread thread=new Thread(task,"manaforge-engine-heartbeat");thread.setDaemon(true);return thread;
        });
        worker.scheduleWithFixedDelay(()->{
            try{ping.run();}catch(RuntimeException error){close();failed.run();}
        },periodMillis,periodMillis,TimeUnit.MILLISECONDS);
    }
    @Override public synchronized void close() {
        if(worker==null)return;
        worker.shutdownNow();worker=null;
    }
}

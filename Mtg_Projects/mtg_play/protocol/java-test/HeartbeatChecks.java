import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class HeartbeatChecks {
    public static void main(String[] args) throws Exception {
        AtomicInteger calls=new AtomicInteger(),failures=new AtomicInteger();
        CountDownLatch repeated=new CountDownLatch(3);
        ManaforgeHeartbeat heartbeat=new ManaforgeHeartbeat(()->{calls.incrementAndGet();repeated.countDown();},failures::incrementAndGet,10);
        heartbeat.start();heartbeat.start();
        if(!repeated.await(3,TimeUnit.SECONDS))throw new AssertionError("NO_IDLE_HEARTBEATS");
        heartbeat.close();heartbeat.close();Thread.sleep(50);int stopped=calls.get();
        Thread.sleep(80);
        if(calls.get()!=stopped || failures.get()!=0)throw new AssertionError("HEARTBEAT_AFTER_CLOSE");
        CountDownLatch failed=new CountDownLatch(1);
        try(ManaforgeHeartbeat broken=new ManaforgeHeartbeat(()->{throw new IllegalStateException("fixture");},()->{failures.incrementAndGet();failed.countDown();},10)){
            broken.start();if(!failed.await(3,TimeUnit.SECONDS))throw new AssertionError("HEARTBEAT_FAILURE_HIDDEN");
            Thread.sleep(50);if(failures.get()!=1)throw new AssertionError("HEARTBEAT_FAILURE_RETRIED");
        }
        heartbeat.start();long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);while(calls.get()<=stopped && System.nanoTime()<until)Thread.sleep(10);heartbeat.close();
        if(calls.get()<=stopped)throw new AssertionError("HEARTBEAT_RECONNECT_NOT_STARTED");
        System.out.println("Heartbeat: repeated idle pings, shutdown, reconnect and failure lifecycle passed");
    }
}

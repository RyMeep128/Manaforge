import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/** Gives the owned server a stdin shutdown channel, allowing normal JVM shutdown hooks. */
public final class ManaforgeServerHost {
    public static void main(String[] args) throws Exception {
        Thread control = new Thread(() -> {
            try {
                BufferedReader input = new BufferedReader(
                    new InputStreamReader(System.in, StandardCharsets.UTF_8));
                String line;
                while ((line = input.readLine()) != null) {
                    if (line.equals("shutdown")) System.exit(0);
                }
                System.exit(0); // The owning Python process closed its pipe.
            } catch (Exception error) {
                error.printStackTrace(System.err);
                System.exit(1);
            }
        }, "manaforge-server-control");
        control.setDaemon(true);
        control.start();
        mage.server.Main.main(args);
    }
}

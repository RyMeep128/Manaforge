import com.google.gson.*;

/** Public fixture setup/assertions only. Never consulted by ordinary gameplay decisions. */
public interface NativeAcceptanceCase {
    interface Metadata {JsonObject read(JsonObject state,String... ids) throws Exception;}
    String key();
    JsonArray deck(boolean ai);
    boolean openingMatches(JsonArray hand);
    void before(JsonObject state,JsonObject prompt,JsonObject command);
    boolean observe(JsonObject state,JsonObject prompt,Metadata metadata) throws Exception;
    void terminal(String outcome) throws Exception;
    JsonObject report();
}

/** Optional normal-launch extension. Every call runs on the existing gameplay owner. */
public interface OrganizationEndpoint extends AutoCloseable {
    void observe(String gameplay) throws Exception;
    boolean receive(String packet) throws Exception;
    void close() throws Exception;
}

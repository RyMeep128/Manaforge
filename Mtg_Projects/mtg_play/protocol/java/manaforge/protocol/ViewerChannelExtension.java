package manaforge.protocol;

/** Trusted opt-in owner callbacks; no organization model or native SDK dependency. */
public interface ViewerChannelExtension extends AutoCloseable {
    int MAX_BYTES=262144;
    enum Kind { CONTROL, RECEIPT, SNAPSHOT }
    interface Sender {
        boolean send(String trustedSeat,Kind kind,String validatedWire) throws Exception;
    }
    interface Factory {ViewerChannelExtension create(Sender sender) throws Exception;}
    interface OwnerAction {void run(ViewerChannelExtension extension) throws Exception;}
    void connected(String trustedSeat) throws Exception;
    void receive(String trustedSeat,String wire) throws Exception;
    void disconnected(String trustedSeat);
    void close() throws Exception;
}

# Shared organization channel (CT-11A)

Opt-in integration work only. The ordinary launcher and its authentication hello
are unchanged. A registration must explicitly allow the extension, and the owner
must install a factory before starting channels. Default registrations retain the
read-only behavior. No capability probe is sent to a legacy receiver.

## Transport extension boundary

`ViewerChannelExtension` is a protocol-level callback interface without organization
model or native SDK dependencies. Its factory and all callbacks execute on the
coordinator owner. The authenticated listener registration supplies the canonical
seat; packet identity fields cannot replace it. Trusted `updateExtension` actions
allow later basis updates on that same serialized owner, never from socket workers.

Each enabled reader has at most 32 pending input packets, each bounded to 256 KiB.
The single socket writer owns one initial control slot, one replacement gameplay
snapshot, a 32-item receipt FIFO, and one replacement organization snapshot. Initial
control precedes publication; gameplay snapshots otherwise precede organization
traffic. Overflow or write failure disconnects only that viewer. No sibling ACK is
required. Disconnect clears outgoing organization queues. Match shutdown closes
the extension on the owner before disposing the shared match resource.

`ExtensionPlumbingChecks` uses actual authenticated sockets with explicitly synthetic
transport packets to verify owner binding, opt-in isolation, one-writer delivery,
and cleanup. It is not organization or native-game acceptance. Existing read-only
coordinator tests remain in the protocol suite. Local checks are compile/static
only; no suites are run locally.

The native helper now includes game-plugin JARs for both real-game modes. Previously
multi-view mode compiled fixtures without TwoPlayerDuel/TwoPlayerMatch available.
This fixes a source-assembly condition, not a change to native rules or identity
assertions. The native identity/control-transfer failure remains a separate gate.

Host admission, retry handling, viewer-safe fanout, and their end-to-end evidence
follow in the next review steps. Live shared organization remains disabled.

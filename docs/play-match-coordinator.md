# Read-only two-viewer match coordinator (CT-10A)

`ManaforgeMatchCoordinator` is an opt-in Java owner for up to two local viewer
registrations. It is not used by the existing single-viewer launcher. No remote
binding, discovery, peer-to-peer connectivity, organization admission, or gameplay
command routing is added. Transport-only checks are not native multiplayer proof.

## Ownership and channels

Construction transfers one AutoCloseable match resource to the coordinator. A
dedicated serialized owner handles registration, projection/publication, and final
resource disposal. The native rules thread remains native; socket workers never
read mutable game state. Closing is idempotent and disposes the match once, after
closing channels and joining bounded workers. Parent cancellation requests the same
owner shutdown. An individual socket disconnect never invokes match disposal or
concession. An immutable status reports only connection state, safe reason code,
sent revision, and pending snapshot count.

Register canonical seat/native player plus trusted session/viewer IDs and a 32-byte
key before start. Seats, native players, session/viewer IDs, and keys must be distinct.
Each registration gets a private 127.0.0.1 listener and copied key. Registration is
host capability data; no native player/seat is selected from a client's hello. Each
socket uses the unchanged challenge/proof handshake, artifact/engine pins, and frame
owner. Active duplicate attachments close immediately. An unauthenticated A can
hold only A's listener up to its authentication budget; B has an independent worker.
Keys are erased during coordinator shutdown and never printed or sent as data.

Each connection has one reader and one writer. Any incoming post-auth frame closes
that read-only channel with READ_ONLY_TRAFFIC; there is no native submission port.
The writer has a bounded deadline and one pending replacement snapshot. A later
unsent snapshot replaces the previous one; an in-flight write is not interleaved.
One latest immutable payload is retained for an authenticated read-only attachment.
This is not gameplay reconnect/resume support or a retry ledger. The worker queue
is bounded; write/auth failures close only their channel. No sibling acknowledgement
is required. Coordinator shutdown releases payloads, projections, keys, and sockets.

## Publication and tests

The trusted fixture publication port validates an entire batch before publishing
any payload, checks per-viewer session/revision/mode, and rejects decisions/actions.
It is not a client endpoint. Native publication accepts deep-copied observations,
requires the same native game/cycle and the correct viewer/native player mapping,
uses one existing read-only projection per viewer, and revalidates the resulting
receive messages. No raw native observation or private prompt is serialized directly.
The native integration proof is the next review step.

The hosted Java protocol suite runs actual sockets and authentication with explicitly
fixture-only snapshots. It covers distinct registrations, wrong key/seat/pins,
duplicate attachment, A stalled during auth while B connects, atomic batch rejection,
independent disconnects, slow A while B receives, one-slot bounds, forbidden commands,
parent cancellation, and exactly-once resource cleanup. No suite is run locally;
compile-only and lint checks do not establish hosted or native acceptance.

Existing gameplay serving, offer admission, receipt ledgers, authentication transcript,
Unity UI, and Python ownership remain unchanged. Native identity/control-transfer
acceptance and interactive production integration remain separate gates.

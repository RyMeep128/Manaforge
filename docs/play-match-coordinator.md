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
The native integration proof is described below.

The hosted Java protocol suite runs actual sockets and authentication with explicitly
fixture-only snapshots. It covers distinct registrations, wrong key/seat/pins,
duplicate attachment, A stalled during auth while B connects, atomic batch rejection,
independent disconnects, slow A while B receives, one-slot bounds, forbidden commands,
parent cancellation, and exactly-once resource cleanup. No suite is run locally;
compile-only and lint checks do not establish hosted or native acceptance.

Existing gameplay serving, offer admission, receipt ledgers, authentication transcript,
Unity UI, and Python ownership remain unchanged. Native identity/control-transfer
acceptance and interactive production integration remain separate gates.

## Native two-seat proof and evidence

`NativeMultiViewerChecks` owns one real native game via the existing pinned fixture.
It loads distinct actual cards into each seat's hand, enters a real native priority
query, and captures both GameViews while holding that live response monitor. Both
views must retain the same GameState/cycle. The original query is passed through
the existing bridge and read-only projection; no decision or actionable offer is
manufactured or serialized. Socket workers receive only projected immutable strings.

Both authenticated clients must see their own private hand canary and not the
other's. A real native tap reaches both; A's forbidden command then closes only A
while the native priority response remains unconsumed and native submission count
stays zero. A subsequent native untap reaches B with A disconnected and the match
still alive. Parent cancellation at the next paused priority must dispose the
native resource exactly once and close all channel workers.

The test uses synthetic credential/pin labels over the same authentication code;
the surrounding job separately verifies the real stock/delivery artifact hashes.
It is not a production bootstrap or a human-versus-AI full-game certificate.
`Play native two-viewer coordinator` runs this proof independently of the inherited
native identity/control-transfer failure. The helper's `--real-game-multiview` flag
requires the existing pinned-helper/provenance checks but does not run or skip the
separate native payment acceptance flag. Transport fixtures remain in the Java
protocol workflow. Its first run on `bb4b29c` passed; final-SHA native and transport
results are still required. No local suite was executed, only compile/static checks.

CT-10A is implemented as an opt-in harness boundary. Production single-viewer
serving has not been replaced, organization packets remain unrouted, and full
CT-10/11 acceptance is not claimed. Interactive admission, authenticated launch
handoff, replay/deduplication, reconnect policy, and Unity composition remain later
work. No Unity source changes or new local player rebuild are needed in this slice;
unrelated existing Unity rollout edits were preserved outside these commits.

### Non-priority observer projection boundary

Final integration review found that the existing projectReadOnlyPriority port still
requires its viewer to own priority. The coordinator therefore uses a new explicit
projectObserverPriority port. It accepts only a real, known priority observation
and preserves that actual public priority player. After projecting the authorized
viewer's cards/players it returns before constructing any choice, action, native
submission mapping, or private prompt text. It invalidates previous authority and
marks unsupported observation/stack details explicitly. Ordinary gameplay and the
older read-only port retain their original priority-owner guard unchanged. Focused
protocol checks require the old port to reject foreign priority, the observer port
to produce a valid decision-free snapshot, and previously offered commands to fail.
This narrow follow-up is a separate versioned commit; no pushed history is rewritten.

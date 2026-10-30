# Bounded client receive inbox — P1.2/G1

Status: client worker handoff implemented and locally exercised. This is not a
production socket pump, renderer projection, Java gateway or G1 completion.
No wire fields or shared schemas change in this increment.

## Ownership and routing

Create a C# ReceiveInbox only after authentication, using the trusted expected
session/viewer and explicit fixture permission. Each viewer/session owns its own
inbox and ReceiveHistory. The default fixture permission remains false. Never
route another seat's data through it or log packet JSON.

The producer calls Enqueue in wire order on a worker. Existing ReceiveMessages
and ReceiveHistory validate schema, context, explicit concealment, revision and
ID replay before admitting data. Duplicate data returns false and consumes no
queue capacity. Only snapshot/event/result belong here. ACKs, session errors,
hello and shutdown keep their separate validated control routes; this queue does
not reinterpret command receipts or game results.

A projection worker calls nonblocking TryTake. On success it owns a ReceivePacket
and must dispose it. ReadJson decodes the packet on that worker, before producing
an immutable rendering projection. Do not parse/decode these packets on Unity's
render thread or treat the encoded packet as a second game model. The existing
dummy worker validates/deserializes after dequeue as a test oracle; no actual
scene is wired to this inbox yet.

## Bounds and private data

Default limits are 128 queued packets and 8 MiB normalized UTF-8 bytes. Allowed
configuration is 1–1024 packets and 1 byte–64 MiB. Those are transport allocation
limits, not player/card/seat limits. The existing 1 MiB frame and receive-history
limits remain independent. There is no silent eviction, coalescing or dropped
private reveal to make room. Overflow faults and clears the whole inbox.

Queued payloads are privately owned byte arrays. The producer never exposes an
alias, and ReadJson returns an immutable string rather than the backing array.
QueuedBytes counts the retained normalized UTF-8 arrays, not total managed heap
or transient parsing/tree/string allocations. Each original frame still passes
the existing framing/JSON bounds before this handoff.

Taking a packet removes it from queue accounting and transfers ownership. Packet
Dispose zeroes its owned bytes and refuses later reads. Inbox cancellation,
failure and disposal zero all still-queued packet bytes and clear replay history.
They cannot revoke a packet already taken or erase strings/trees retained by a
consumer. Viewer handoff must join/stop projection work, dispose taken packets,
clear their projections and destroy private renderer resources before displaying
the next viewer. This increment alone does not prove P3.5's handoff acceptance.

## Completion, cancellation and failure

State is Open, Completed, Cancelled, Faulted or Disposed. Completion is a task
carrying an immutable first-termination state and safe code; continuations run
asynchronously so owner callbacks cannot execute under the inbox lock. It signals
input termination, not that all queued packets have drained.

- FinishInput is an explicit owner decision for normal input completion. It admits
  no more packets but permits existing validated packets to drain. Unexpected EOF
  is not automatically a normal game outcome or proof of action rejection.
- Cancel revokes queued packets, including a completed queue still awaiting drain.
- Validation failure or overflow clears the queue and faults admission. Later
  reads/writes fail closed. The completion code preserves the initial safe cause.
- Dispose clears owned data and closes admission idempotently. It does not replace
  an already published completion cause. State may therefore be Disposed while
  Completion still reports the earlier failure/cancellation/completion.

The transport/session owner must observe failure immediately, stop/gate further
submissions, mark pending commands uncertain, close its owned socket and cancel
receive/projection work. Checking CommandTracker.CanSubmit alone is insufficient
if the owner has not yet handled inbox termination. The test demonstrates an owner
completion continuation disconnecting the tracker while preserving uncertainty;
the inbox does not own that tracker or a socket.

Cancel is a state transition under a lock; it does not interrupt an OS read
already blocked in TextFrame.Read. TryTake does not wait for incoming data. Socket deadlines,
partial-frame cancellation, normal-versus-unexpected EOF policy, production pump
coordination, recovery and immutable renderer projection remain separate work.
The implementation must run on workers; bounded parsing still does work while
holding the inbox's serialization lock.

## Evidence

Fifteen focused checks cover FIFO, duplicate admission at capacity, packet-count
and exact multibyte UTF-8 budgets, clearing on overflow, owner command uncertainty,
explicit cancellation, completion/draining, wrong-viewer/concealed-identity/mode
rejection, concurrent consumers, safe malformed-input errors, invalid bounds and
ownership transfer/disposal. All five authenticated Java-dummy scenarios now
route data through the inbox before worker-side validation/deserialization.

Local result: 101 focused Unity EditMode checks and Java protocol preflight passed.
No full application suite ran. There is no new Java wire contract or queue in this
client-only increment. Licensed Unity CI, product transport/lifecycle integration,
real engine visibility and G0/G1 acceptance remain open. CI review stays on the
owner's third-commit cadence; no new CI pass is claimed here and Qt CI was not
investigated.


### Socket-read deadline follow-up

The separate [owned loopback reader](frame-read-deadlines.md) now bounds complete
C# socket frame reads and observes lifetime cancellation without abandoning a
read task. It closes on partial-frame failure; ReceiveInbox still does not own
that socket. A product coordinator must couple reader failure, inbox cancellation
and command uncertainty. Explicit inbox cancellation alone does not interrupt an
unrelated socket read.

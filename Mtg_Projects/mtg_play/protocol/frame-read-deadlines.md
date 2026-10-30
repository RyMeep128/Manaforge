# Owned loopback frame read deadlines — P1.2/P1.4/G1

Status: C# worker-side socket framing validated locally, including an authenticated
partial-frame Java-dummy failure. This is not a production transport coordinator,
Java gameplay gateway or completed G1 gate. The wire format is unchanged.

## Read and ownership contract

LoopbackFrameReader takes ownership of one connected socket after successfully
validating both local and remote endpoints as loopback. The caller remains
responsible for a socket if construction fails. This does not prove that an
upstream listener was bound privately; listener creation must still bind loopback
explicitly, as the current dummy/test listeners do. No remote-network transport
is enabled by this class.

Call Read on a transport worker with a total per-frame budget from 1–60,000 ms
(default 5,000) and an optional lifetime cancellation token. A monotonic Stopwatch
covers the first byte, complete four-byte header, payload and observed completion.
It is not a timeout reset after every fragment. A peer sending occasional bytes
cannot indefinitely extend the frame budget.

Socket readiness is polled in intervals of at most 25 ms, with cancellation and
the absolute deadline rechecked. A defensive 25 ms socket receive timeout handles
readiness races. There is no abandoned read task continuing to consume bytes after
a timeout. OS scheduling can delay observation; these are bounded engineering
checks rather than real-time guarantees. This worker does not use Unity APIs.

The existing TextFrame implementation still owns length/strict UTF-8/BOM checks.
No partial payload is returned. Observed timeout, cancellation, malformed framing,
I/O failure or concurrent reader misuse closes the owned socket; subsequent reads
cannot resume the abandoned frame. A completed frame is checked once more against
cancellation/deadline before being returned. Invalid budget arguments fail before
reading and do not consume input.

Only one reader may consume this socket. All read routes must use this owner;
using another NetworkStream/reader concurrently would bypass the guard. Misuse
through this class fails FRAME_CONCURRENT and closes the socket rather than
splitting a frame between workers. Owner Dispose is idempotent and unblocks an
active read. Diagnostics ReadInProgress/IsClosed are observations, not external
synchronization primitives.

## Failure categories and owner obligations

Fixed categories added here are FRAME_TIMEOUT, FRAME_CANCELLED, FRAME_CLOSED,
FRAME_CONCURRENT and FRAME_IO. Existing FRAME_SIZE, FRAME_TRUNCATED, FRAME_UTF8
and FRAME_BOM categories are preserved. Exceptions do not echo payloads, socket
addresses or underlying exception text.

An EOF between complete frames remains null. EOF within a header/payload remains
FRAME_TRUNCATED. Neither proves an engine result, acknowledgement or rejected
action. The session owner must distinguish expected shutdown from unexpected EOF,
stop further writes, disconnect/fault command tracking, cancel/clear ReceiveInbox,
join projection work and clean up its owned runtime. A write/submission may have
executed even when its receipt times out; never replay it blindly. This class does
not own command tracking, inboxes, decks, renderer state or engine processes.

Connect/accept budgets, complete authentication/session deadlines, write budgets,
private bootstrap pipes and recovery remain separate responsibilities. Writers
must be serialized and bounded by their owner. ReceiveTimeout is deliberately
configured on the transferred socket; do not depend on unrelated readers using
a previous timeout. Java's existing dummy inbound read timeout is not upgraded
to an absolute frame deadline by this client-only class. Product duplex transport
and Java-side deadline parity remain pending.

## Actual validation

Fifteen focused real IPv4 loopback checks cover:

- Two complete frames followed by between-frame EOF.
- Idle peer, partial header and partial payload deadlines.
- Trickle traffic that cannot reset the total budget.
- Cancellation during header/payload waits and a pre-cancelled operation.
- Explicit owner disposal and concurrent-reader failure closing the socket.
- Size, truncation and UTF-8 errors closing rather than resuming the channel.
- Invalid budgets preserving unread input.

Tests use owned ephemeral loopback listeners/clients, bounded task joins and no
engine or private deck data. They assert generous scheduling bounds, not precise
input latency or networking throughput. IPv6 is accepted by endpoint validation
but has not been exercised in this Windows test set.

All existing authenticated Java-dummy socket reads now use LoopbackFrameReader;
private owner bootstrap pipes retain the test harness's existing outer timeout.
A sixth Java mode authenticates successfully, sends two header bytes and waits
for owner EOF. The C# client observes FRAME_TIMEOUT, confirms socket closure,
closes its private owner pipe and checks clean child exit. No snapshot/result or
real XMage action is involved in that mode.

Local evidence: 117 focused Unity EditMode checks, including six owned Java process
scenarios and the existing Java protocol preflight, passed. No full application
suite ran. Licensed Unity CI, owner coordination and actual engine lifecycle still
need evidence. CI review follows the owner's third-commit cadence; no new CI pass
is claimed for this increment and Qt CI was not investigated.

# Owned loopback frame read deadlines — P1.2/P1.4/G1

Status: matching C#/Java worker-side socket framing validated locally, including
authenticated partial-frame failures in both directions. This is not a production
transport coordinator,
Java gameplay gateway or completed G1 gate. The wire format is unchanged.

## Read and ownership contract

Both LoopbackFrameReader implementations take ownership of one connected socket
after successfully
validating both local and remote endpoints as loopback. The caller remains
responsible for a socket if construction fails. This does not prove that an
upstream listener was bound privately; listener creation must still bind loopback
explicitly, as the current dummy/test listeners do. No remote-network transport
is enabled by this class.

Call Read on a transport worker with a total per-frame budget from 1–60,000 ms
(default 5,000) and an optional lifetime cancellation token (C#) or BooleanSupplier
(Java). A monotonic Stopwatch (C#) or System.nanoTime budget (Java)
covers the first byte, complete four-byte header, payload and observed completion.
It is not a timeout reset after every fragment. A peer sending occasional bytes
cannot indefinitely extend the frame budget.

C# polls socket readiness in intervals of at most 25 ms, with cancellation and
the absolute deadline rechecked. A defensive 25 ms receive timeout handles
readiness races. Java caps each Socket input read to the smaller of 25 ms and the
remaining total budget, then rechecks the monotonic deadline/cancellation flag.
There is no abandoned read task continuing to consume bytes after
a timeout. OS scheduling can delay observation; these are bounded engineering
checks rather than real-time guarantees. This worker does not use Unity APIs.

The existing TextFrame implementation still owns length/strict UTF-8/BOM checks.
Both readers disable configured blocking socket linger before accepting ownership,
so failure cleanup does not wait on a previously enabled linger option. Real
loopback tests deliberately enable linger before transfer and verify it is
disabled by construction. No partial payload is returned. Observed timeout,
cancellation, malformed framing,
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
a previous timeout. Java now uses the matching whole-frame reader for inbound
dummy TCP frames;
private bootstrap pipes retain their existing test harness ownership. Product
duplex coordination, complete conversation budgets and write deadlines remain pending.

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

All existing authenticated Java-dummy socket reads in both directions now use
LoopbackFrameReader; private owner bootstrap pipes retain the test harness's existing outer timeout.
A sixth Java mode authenticates successfully, sends two header bytes and waits
for owner EOF. The C# client observes FRAME_TIMEOUT, confirms socket closure,
closes its private owner pipe and checks clean child exit. No snapshot/result or
real XMage action is involved in that mode.

Java adds 16 real-loopback checks covering the same completion/idle/partial/trickle,
cancellation, ownership, framing and invalid-budget boundaries, plus Java thread
interruption. BooleanSupplier cancellation and interruption are observed between
bounded socket reads; the reader does not clear the caller's interrupt flag.
IOException/callback failures are mapped to safe categories without raw exception
text. Aborting preserves the primary frame failure if socket close also throws;
the session owner still owns final lifecycle cleanup.

A seventh authenticated process scenario sends a partial client command header.
The Java reader's short test budget expires, closes the socket and exits the dummy
with its expected fixed failure status. C# observes EOF and checks child exit.
This does not mean a real pending action was rejected; there is no XMage action
or command reservation in that scenario.

Local evidence: 118 focused Unity EditMode checks, including seven owned Java process
scenarios, all Java corpora and 16 new Java loopback checks passed. Model drift
and Python helper lint also passed. No full application suite ran. Licensed Unity CI, owner coordination and actual engine lifecycle still
need evidence. CI review follows the owner's third-commit cadence; no new CI pass
is claimed for this increment and Qt CI was not investigated.


Scheduled third-commit CI snapshot: protocol runs for `96fd05f`
(https://github.com/RyMeep128/Manaforge/actions/runs/41124171111), `a86511d`
(https://github.com/RyMeep128/Manaforge/actions/runs/41123204310) and `671c43e`
(https://github.com/RyMeep128/Manaforge/actions/runs/41108455868) passed. These are
hosted Java/model checks for earlier increments, not licensed Unity evidence or a
CI result for the new Java reader. No running job was waited on.


### C# write boundary follow-up

The same C# socket owner now also supports [bounded frame writes](frame-write-deadlines.md),
with a separate single-writer guard and failure closure. Normal dummy client
sends use that path while a reader may run alongside it. Java write deadlines and
product session coordination remain pending. Local focused EditMode count is 130;
read-deadline behavior and all seven process scenarios remain covered.

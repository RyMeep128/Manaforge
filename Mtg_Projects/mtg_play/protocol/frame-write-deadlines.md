# Bounded C# frame writes — P1.2/P1.4/G1

Status: C# socket-write boundary exercised locally. Java write deadlines, product
session coordination and G1 freeze remain pending. No wire fields change.

## One socket owner

The existing C# LoopbackFrameReader socket owner now also exposes Write; its type
name is retained for compatibility. One read and one write may run concurrently,
but two writers fail FRAME_CONCURRENT_WRITE and close the channel. All production
writes for that socket must use this owner rather than bypassing its guard through
another NetworkStream. The protocol fixture's deliberate two-byte malformed probes
are test-only exceptions, not gameplay submission paths.

Call Write on a transport worker with a 1–60,000 ms total budget (default 5,000)
and optional lifetime cancellation token. Framing validates/encodes the complete
payload before any socket byte is sent. Invalid payload/budget arguments consume
no wire input and leave an otherwise unused channel available. If the session
owner already registered a command, it must still handle that failure explicitly;
argument rejection is not an engine ACK.

A monotonic budget covers preflight and socket progress. Readiness polls last at
most 25 ms; each send chunk is at most 16 KiB with a defensive 25 ms native send
timeout on the owned socket. That native timeout may conservatively fail earlier
than the total budget. The writer checks cancellation/deadline before sending and
after observed completion. It does not start an abandoned asynchronous write task.
OS scheduling can delay observation; no real-time guarantee is made.

The backing frame buffer is bounded by the existing 1 MiB payload plus four-byte
header. Its used bytes are cleared in finally and the writer guard is released.
This does not erase caller strings or all temporary encoder allocations. Encoding
and socket work must remain off Unity's rendering thread.

## Failure and command safety

FRAME_WRITE_TIMEOUT, FRAME_WRITE_CANCELLED, FRAME_WRITE_IO, FRAME_CLOSED and
FRAME_CONCURRENT_WRITE are fixed local transport categories, without payload or
underlying exception text. Invalid preflight retains existing FRAME_SIZE,
FRAME_BOM and FRAME_UTF8 categories. No new public session-error code is introduced.

Timeout, cancellation, failed sends and concurrent-writer misuse close the owned
socket. A send exception can occur after bytes have already transferred, so a
failed chunk is never retried. Even cancellation observed after the final send
leaves the action outcome uncertain. Success means only local socket acceptance;
it is neither remote receipt nor engine confirmation.

The session owner must stop new submissions, disconnect/fault CommandTracker,
cancel ReceiveInbox/projection work, close/join owned transport workers and perform
lifecycle cleanup. It must register each command before the first write and never
blindly replay it after failure. A correlated engine-confirmed ACK is still the
only route from a pending command to a confirmed/rejected outcome. This transport
does not choose actions, decide legality or infer game results.

## Actual evidence

Twelve new focused checks use real owned IPv4 loopback sockets with constrained
buffers, including a peer that deliberately does not read. They cover complete
framing, a concurrent reader, bounded backpressure failure, cancellation, explicit
owner disposal, concurrent-writer exclusion, invalid payloads/budgets writing no
header, and preservation of pending-command uncertainty. The malformed-surrogate
input is constructed inside the test so test-runner attribute serialization cannot
replace it with valid replacement characters.

All seven authenticated Java-dummy scenarios now use the bounded C# writer for
normal TCP hello/command/shutdown sends. SendTracked still registers before Write
and disconnects tracking on any thrown write failure. Private owner bootstrap pipes
retain their separate existing harness path. Java outbound fixture writes remain
synchronous without a whole-frame write deadline; that parity is not claimed.

Local validation: 130 focused Unity EditMode checks, all Java corpora including
16 Java read-deadline socket checks, and seven actual Java process scenarios pass.
No full application suite ran. No new UI, engine startup, saved-deck path or
installer behavior changes. Product command-admission/stop coordination, Java write
deadlines, complete handshake/session budgets, recovery and licensed Unity CI still
need evidence. G0/G1 stay open; CI review follows the owner's third-commit cadence
and no new CI result is claimed here. Qt CI was not investigated.

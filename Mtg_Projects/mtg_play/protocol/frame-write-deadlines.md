# Bounded frame writes — C#/Java — P1.2/P1.4/G1

Status: C#/Java socket-write boundaries exercised locally. Product session
coordination and G1 freeze remain pending. No wire fields change.

## One socket owner

Both LoopbackFrameReader socket owners now expose Write/write; the existing type
name is retained for compatibility. One read and one write may run concurrently,
but two writers fail FRAME_CONCURRENT_WRITE and close the channel. All production
writes for that socket must use this owner rather than bypassing its guard through
another NetworkStream. The protocol fixture's deliberate two-byte malformed probes
are test-only exceptions, not gameplay submission paths.

Call Write on a transport worker with a 1–60,000 ms total budget (default 5,000)
and optional lifetime cancellation token. Framing validates/encodes the complete
payload before any socket byte is sent. Invalid payload/budget arguments emit
no bytes and leave an otherwise unused channel available. If the session
owner already registered a command, it must still handle that failure explicitly;
argument rejection is not an engine ACK.

In C#, a monotonic budget covers preflight and socket progress. Readiness polls last at
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

## Java watchdog ownership

Java's plain Socket output API has no send-timeout setting. Each owner therefore
has one lazy daemon ScheduledThreadPoolExecutor used only to watch its current
write. A monotonic deadline and cancellation flag are checked before each chunk,
at completion and by the watcher at 10 ms intervals. Java thread interruption is
also observed without clearing the caller's flag. On failure the watcher closes
the same owned socket, releasing the blocking output call; no second worker task
continues writing a timed-out frame.

A synchronized attempt seals successful completion before its watcher is canceled.
A stale watcher cannot close a later frame. Canceled tasks are removed from the
scheduler queue; closing the socket owner shuts down its scheduler. There is at
most one writer and one watcher thread per live socket owner, and no frame backlog
is retained by this mechanism. Reads and writes may operate together.

Observed cancellation, total-budget expiry, concurrent writers and I/O failure use
the same fixed categories as C#. The backing frame buffer is cleared on exit;
a failed partial write is never retried. Callback failures map to a safe local
category without raw exception text. Socket close is the interruption mechanism;
OS scheduling/close behavior still requires platform acceptance rather than a
hard real-time claim. Private bootstrap pipes and complete conversation/session
budgets are separate responsibilities.

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
retain their separate existing harness path. Java normal outbound TCP frames now also use its bounded writer. Deliberate raw
malformed probes and private readiness/bootstrap pipes remain separate test paths.

Java adds 14 real-loopback write checks: completion/duplex behavior, blocked
receiver deadline, cancellation, owner close, writer exclusion, invalid frame and
budget preflight, pending ledger uncertainty, active thread interruption and a
successful frame whose expired watcher must not affect a later write. The helper
also checks that all owned watchdog threads terminate after their sockets close.

An eighth authenticated process scenario stops consuming data after gateway proof.
The Java dummy sends a bounded maximum-sized public stress frame, verifies its own
FRAME_WRITE_TIMEOUT and exits cleanly; C# checks child exit and disposes its owned
socket without parsing the deliberately incomplete data. It is not an engine
result or proof of a rejected gameplay command.

Local validation: 131 focused Unity EditMode checks, all Java corpora including
16 Java read and 14 Java write socket checks, and eight actual Java process
scenarios pass.
No full application suite ran. No new UI, engine startup, saved-deck path or
installer behavior changes. Product command-admission/stop coordination, complete handshake/session budgets,
recovery and licensed Unity CI still
need evidence. G0/G1 stay open; CI review follows the owner's third-commit cadence
and no new CI result is claimed here. Qt CI was not investigated.

# Owned C# client session channel — P1.2/P1.4/G1

Status: first coordinator slice validated locally against fixtures and the actual
Java dummy. G1 remains open. This is not a product launcher, engine gateway or
live match. The Qt/Python fallback and persistent deck model are unchanged.

## Trusted construction and ownership

ClientSessionChannel is constructed only after gateway authentication using the
owner's trusted session/viewer/pin context. It does not authenticate a socket by
itself. The authenticated process tests construct it after the gateway proof
passes, never from untrusted snapshot context. Successful construction transfers
ownership of the connected LoopbackFrameReader; failed construction leaves that
transport with its caller.

The channel privately owns command tracking, receive inbox/history and the socket
owner. Callers cannot bypass its command state through a public tracker/inbox.
It starts no background thread or process. A caller-owned worker drives
ReceiveNext with an explicit read budget; submission/shutdown writes also belong
on workers. Do not put a permanent five-second read loop around normal human
thinking without a designed idle/heartbeat policy. Whole conversation deadlines,
worker scheduling and product bootstrap remain separate work.

## Admission and receive routing

Submission admission, receipt application, token changes and termination serialize
under one lock. Blocking socket reads/writes run outside that lock so termination
can close the socket and release a sibling worker. Calls admitted before a stop
may already have sent bytes; cancellation cannot undo them. No new submission is
admitted after the coordinator observes termination, and a stopped socket cannot
be reused for transmission.

This first slice supports **perform only**. It requires an active viewer snapshot,
a nonempty engine-provided decision token, the current revision and an exact
engine-provided action ID. Same-revision duplicates do not refresh tokens. A
higher-revision event revokes old decision/action tokens until fresh state arrives.
Non-active/unknown status and empty decisions do not enable submissions. Local
stale/unoffered/unsupported commands are rejected before writing; they do not
poison an otherwise healthy session. This is token/context comparison, not a
second legality engine or strategic decision maker.

Choose, mana source, amounts, numbers, finish and cancellation families remain
supported by the shared protocol readers, but this coordinator explicitly refuses
them with SESSION_COMMAND_UNSUPPORTED until their admission/receipt handling is
implemented. It does not silently invent a choice or retire the existing adapter.

Commands are registered before writing. Data messages go through the existing
receive inbox and history; duplicates are dropped. ACKs go to the exact pending
command tracker. Results block further submissions but do not confirm a pending
command; a later correlated ACK can still resolve that receipt. Terminal errors
validate viewer/session and enter the same stop path. Unexpected types, malformed
messages, wrong receipts, overflow, read/write failure and cancellation also stop.

ReceiveNext returns immutable type/applied/receipt metadata. Packet contents are
taken separately by a projection worker with explicit disposal. It is not an
immutable renderer model, and no Unity scene consumes this channel yet.

## Termination and final packet drain

State is Active, Completed, Stopped or Disposed. The first termination task record
is immutable and runs continuations asynchronously. It reports the protocol stop
cause, not proof of OS/runtime containment or a game outcome.

- Failure/cancellation stops admission, clears tokens, marks an active command
  uncertain, clears queued data/history and closes the socket together.
- EOF without the expected shutdown response is SESSION_EOF, never an inferred
  rejection, concession or successful game result. Queued data is revoked.
- RequestShutdown sends a validated lifecycle request, blocks further submissions
  and expects matching session/viewer/reason. An unsolicited/mismatched shutdown
  fails closed. This control never concedes the game.
- A matching shutdown completes gracefully and leaves already validated final
  packets available to drain. Pending actions still become uncertain unless their
  correlated terminal ACK was received. A result alone does not make EOF graceful.
- Explicit Cancel or Dispose can revoke a completed queue awaiting drain. They do
  not replace the first termination metadata. Dispose clears in-memory receipts;
  capture any needed pending receipt before ending the owner. No durable recovery
  or automatic reconnect/reset is provided.

Already dequeued packets, caller-owned strings/projections and private rendering
resources must still be disposed/cleared by their owners. Stop/Dispose closes the
socket to release IO but does not join caller-created workers or prove private
seat handoff. Product integration must join them and finish renderer cleanup before
showing another viewer. No process termination, deck export or LaunchOwner
transition is performed by this coordinator.

## Evidence and open gates

Eighteen focused loopback checks exercise token admission, duplicate delivery,
correlated receipts, malformed/wrong-viewer input, overflow, cancellation during
an active read, unexpected EOF, terminal error, unsolicited/matched shutdown,
final packet draining, results versus ACKs, disposal, canceled writes, revision
advance, unsupported choice families and inactive/empty-decision state.

Two new authenticated Java-dummy scenarios use the owner end to end. The normal
path consumes snapshot/duplicate/event, rejects stale input locally, submits an
exact action, observes submitted ACK and fixture-only result, then completes a
matching shutdown and drains the result packet. The failure path consumes a
terminal error, revokes queued data and preserves the submitted command as
uncertain. Existing eight lower-level scenarios remain for independent regression
coverage. These are ten actual process scenarios, not real engine games.

Local evidence: 151 focused Unity EditMode checks, all Java corpora including
16 read and 14 write loopback checks, passed. No full application suite ran.
Complete choice dispatch, authentication/session deadline coordination, Java
session ownership, immutable renderer projection, product lifecycle containment
and licensed Unity CI remain pending. G0/G1 stay open; bulk P2 is not started.

Scheduled CI snapshot: earlier protocol runs for `32f7a87`
(https://github.com/RyMeep128/Manaforge/actions/runs/41127042507), `c9ebefe`
(https://github.com/RyMeep128/Manaforge/actions/runs/41126130630) and `14b44ce`
(https://github.com/RyMeep128/Manaforge/actions/runs/41125133229) passed. These are
Java/model checks, not licensed Unity or this new coordinator's CI result.
Review remains every third commit with running checks deferred; Qt CI was not
investigated.

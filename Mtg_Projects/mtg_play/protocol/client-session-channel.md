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

The coordinator now supports **perform, choose, finish_selection, cancel, choose_number, choose_amounts
and select_mana_source**.
It requires an active viewer snapshot, a nonempty engine-provided decision token
and the current revision. Perform uses exact offered action IDs; choose uses exact
offered option IDs. Finish/cancel require the explicit can_finish/cancellable flag.
No labels, prompts, printed text, selected-option counts or guessed game rules
authorize a command. Generic option IDs/flags are consumed as protocol facts;
this does not interpret or claim UI support for an unknown decision family.

Same-revision duplicates do not refresh tokens. A higher-revision event revokes
all old decision/action/option/control permissions until fresh state arrives.
Every new snapshot replaces them. Non-active/unknown status and empty decisions
do not enable submissions. Local stale/unoffered/unsupported commands are rejected
before writing; they do not poison an otherwise healthy session. This is current
viewer/token admission, not a second legality engine or strategic decision maker.

[Numeric admission](numeric-choices.md) uses only supplied number/amount ranges,
exact vector length and overflow-safe mathematical totals. It does not select,
clamp or infer values. Missing/unsupported constraints do not enable numeric
submission. [Mana source admission](mana-source-admission.md) requires the current
mana decision and an exact current viewer object ID; the engine still determines
usability. No land/type/tap/controller inference or automatic source choice occurs.

No operation is selected automatically. Submit(operation=cancel) is an engine
decision command bound to its token/flag; the owner's Cancel() closes the local
channel. Neither substitutes for concession. Existing Qt/Python behavior remains
the regression reference.

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

Sixty-three focused loopback checks exercise token admission, duplicate delivery,
correlated receipts, malformed/wrong-viewer input, overflow, cancellation during
an active read, unexpected EOF, terminal error, unsolicited/matched shutdown,
final packet draining, results versus ACKs, disposal, canceled writes, revision
advance, control-message rejection and inactive/empty-decision state. New cases cover
offered options, absent finish/cancel flags, controls without an option list,
replacement permissions and revision-based choice revocation.

Two new authenticated Java-dummy scenarios use the owner end to end. The normal
path consumes snapshot/duplicate/event, rejects stale input locally, submits an
exact action, observes submitted ACK and fixture-only result, then completes a
matching shutdown and drains the result packet. The failure path consumes a
terminal error, revokes queued data and preserves the submitted command as
uncertain. Existing eight lower-level scenarios remain for independent regression
coverage. Three further authenticated cases use choose/finish/cancel against an
explicitly simulated Java choice decision. They observe submitted and simulated
confirmed receipts, a fixture-only result and matched shutdown. There are thirteen
actual process scenarios in that slice, not real engine games or choice-parity evidence.
Two more authenticated numeric scenarios now bring the total to fifteen; see
[numeric admission](numeric-choices.md).

Local evidence: 202 focused Unity EditMode checks, all Java corpora including
16 read and 14 write loopback checks, passed. No full application suite ran.
Authentication/session deadline coordination, Java
session ownership, immutable renderer projection, product lifecycle containment
and licensed Unity CI remain pending. G0/G1 stay open; bulk P2 is not started.

Scheduled CI snapshot: earlier protocol runs for `32f7a87`
(https://github.com/RyMeep128/Manaforge/actions/runs/41127042507), `c9ebefe`
(https://github.com/RyMeep128/Manaforge/actions/runs/41126130630) and `14b44ce`
(https://github.com/RyMeep128/Manaforge/actions/runs/41125133229) passed. These are
Java/model checks, not licensed Unity or this new coordinator's CI result.
Review remains every third commit with running checks deferred; Qt CI was not
investigated.


Shared receive validation now rejects empty/duplicate option IDs in both Java and
C# (eight positive/26 negative receive cases). Eight focused Python schema checks
pass; identity/context constraints remain distinct from JSON shape. No fields or
schema versions change and no real engine gateway dispatcher is enabled.


The mana follow-up adds a sixteenth authenticated process scenario; all seven
specified command families now have client admission coverage. The owner retains
only current viewer-scoped object IDs, not a computed list of legal mana sources.
Fifteen new checks cover that distinction and permission lifetime. See
[mana admission](mana-source-admission.md) for current evidence and limits.


## Bounded authenticated construction

[ClientHandshake.Open](client-handshake.md) now provides the preferred worker-side
entry point: one total proof-exchange budget, trusted-context verification and
failure closure before returning this owner. The low-level constructor still
requires prior authentication. Local validation is now 220 focused EditMode
checks with eighteen process scenarios; product bootstrap/renderer integration
and licensed CI remain pending.

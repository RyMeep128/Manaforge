# Java viewer session boundary

GatewaySessionBoundary owns a GatewayCommandGate and SubmissionLedger for one
successfully authenticated ViewerContext. Trusted fixture mode is explicit. One
monitor serializes viewer observations, current-decision admission and one-time
submission reservation. Callers cannot access the owned gate or ledger directly.
The normal authenticated dummy paths now use this owner.

prepare returns the existing defensive-copy Prepared receipt. shouldSubmit is
true only for a newly reserved request. Semantic duplicate command IDs return the
original receipt without resubmission, even after current state advances; changed
content with the same ID faults the boundary. A game result revokes offered
permissions but does not confirm an outstanding command. Engine-correlated
recordOutcome is the only trusted outcome path.

States are ACTIVE, DISCONNECTED, FAULTED and CLOSED. Disconnect/fault closes the
gate, revokes permissions and marks a pending reservation uncertain. Further
observations and preparations are refused; there is no reconnect or retry path.
Repeated disconnect does not overwrite a confirmed outcome. Late trusted engine
outcomes may resolve retained uncertainty while disconnected/faulted, but never
reactivate the owner. Malformed observations, command conflicts and capacity
failures fault the owner. Close is idempotent and clears gate and receipt history.

receiptFor is a private owner diagnostic/reconciliation API that returns a copy
without reserving anything. It must not be exposed to another viewer. Retained
history is bounded by the configured capacity; it contains command IDs, opaque
arguments and receipts, rather than card text or artwork. Java strings are not
guaranteed to be securely erased. Session exceptions must remain sanitized by
the future transport/lifecycle owner.

This is an admission/reservation owner, not a running Java/XMage gameplay session.
It starts no worker, socket, process, engine or deck import. The lock does not
extend beyond prepare: the future worker must serialize actual engine dispatch
with observations and cancellation, avoid replaying reserved/uncertain commands,
and report failures after reservation as uncertain. Sending a receipt or a result
never proves an engine submission succeeded. Process cleanup and transport-close
notification are caller responsibilities until product lifecycle integration.

Thirty focused Java checks cover duplicate/conflicting requests, pending
reservations, defensive receipt copies, result-without-confirmation, disconnect,
late outcomes, idempotent disposal, malformed observations, bounded capacity and
concurrent duplicate admission. They run after a real loopback authentication,
with synthetic snapshots; no engine rules or gameplay parity are simulated.
No rendered UI changes or hands-on UI verification are required. G0/G1 remain
open, with private bootstrap, full worker/transport/process ownership, renderer
handoff and licensed CI still required. Bulk P2 remains gated.


Local validation passed: 30 new Java owner checks, 37 admission checks, 22
authentication cases and the other Java protocol corpora. All 227 focused Unity
EditMode checks passed, including 19 Java process scenarios. No full application
suite ran. CI checking follows the owner's third-commit cadence; the next commit
is the next checkpoint. No CI pass is claimed for this increment.

# Java viewer command admission

`GatewayCommandGate` requires a context returned by successful GatewayHandshake
and an explicit trusted fixture-mode setting. It consumes trusted viewer-filtered
snapshot/event/result envelopes through bounded ReceiveHistory validation. It is
not a root all-seats session and must never receive unfiltered engine state.

The gate retains only current action/option/object IDs, decision ID/family/flags,
numeric bounds, and bounded stream IDs/digests. It retains no card artwork,
printing data, prompt text, option labels or original snapshots. Replacing the
current snapshot clears earlier permissions. Higher-revision events revoke them
until a fresh snapshot arrives; semantic duplicates cannot restore revoked IDs.
Results, nonactive snapshots and missing decisions leave no usable permissions.
Invalid observations fault the gate and clear retained permissions. Close clears
its history and current decision. Java immutable strings are not securely erased.

`check` parses all seven command families and compares the authenticated session,
viewer, current revision and decision. It then compares offered action/option IDs,
finish/cancel flags, mana family and current viewer object IDs, or supplied numeric
bounds. Amount totals use BigInteger so signed 64-bit overflow cannot admit an
invalid total. Missing/inverted bounds, wrong vector length, wrong family and
unoffered IDs fail closed with existing wire rejection codes.

A null rejection means the request addresses the current offered decision. It is
not proof that a mana object is usable, a choice is strategically appropriate, or
an action is legal. XMage retains authority over rules, costs and outcomes. The
gate does not execute, reserve, retry or confirm submissions. SubmissionLedger
still owns duplicate receipts and pending/uncertain command state. The future
session owner must serialize observation, admission, reservation and engine
submission on one worker; separate synchronized method calls do not make the
whole dispatch atomic. Shutdown remains a separate owner/lifecycle operation.

The authenticated Java dummy now uses this gate in all normal fixture paths.
Numeric fixture admission compares offered ranges rather than hardcoded sample
answers. Confirmations remain explicitly simulated and do not claim engine parity.
The deliberately delayed-proof negative mode never enters this gate.

The result now advances the dummy gateway's current revision, so a new request at
the old revision is rejected as STALE_REVISION before ledger pending admission.
The exchange assertion was updated explicitly for that behavior; independent
pending/duplicate/uncertain ledger tests and local client pending checks remain.

Validation passed: 37 Java admission checks, the existing Java protocol corpora,
and 227 focused Unity EditMode checks including 19 Java process scenarios.
No full application suite ran. CI checking is deferred to the next scheduled
third-commit checkpoint; this increment has no claimed CI pass. No rendered UI changed and
no hands-on UI verification is required. Product bootstrap, session/worker/process
ownership, engine dispatch/parity, renderer handoff and licensed CI remain open.
G0/G1 are not complete; this is protocol infrastructure, not the bulk P2 port.


The [viewer session boundary](gateway-session-boundary.md) now owns the gate and
ledger together, serializing observation/admission/reservation. Actual engine
dispatch remains future worker integration and is not covered by this monitor.

# First wire command boundary — P1.2/G1 increment

Status: shared command/ack/shutdown schema, Java/C# readers and current-decision
comparison tests implemented. Follow-ups add [viewer authentication](viewer-authentication.md),
a [dummy exchange](dummy-exchange.md), [receive validation](receive-boundary.md)
and [client ACK tracking](command-tracking.md). No actual engine execution is
implemented by this wire boundary; G1 stays open.

## Supported vertical slice

The body schema is `wire-messages-v1.schema.json`. `WireMessages.Parse/parse`
first runs strict envelope validation, then accepts only these message types:

- `command`: exactly session_id, viewer_id, revision, operation (`perform`),
  decision_id and action_id. The envelope message_id is the command correlation
  ID. IDs remain opaque; wire ID fields currently allow 1–128 ASCII letters,
  digits, underscore, hyphen, period and colon. Revision is a nonnegative signed
  64-bit integer. There is no client-inferred action or free-form rules request.
- `ack`: exactly session_id, viewer_id, command_id, request_revision, outcome and
  code. command_id follows the envelope ID alphabet; it must later match an
  actual outstanding command. request_revision binds the reply to its request,
  not an invented newer engine revision. It is not a snapshot update.
- `shutdown`: exactly session_id, viewer_id and reason (`client_close`, `cancel`
  or `startup_failed`). This is a viewer shutdown request, not authorization to
  kill a process or end another seat's game. Ownership policy remains required.

Other header types fail MESSAGE_UNSUPPORTED in this reader; malformed/unknown
body fields fail MESSAGE_INVALID. Valid snapshots/hello/results still need their
own validators and routing. Other existing adapter command families (choices,
amounts, mana sources, cancellation and concession) are deliberately not exposed
yet. No installed application path uses these new bodies.

## Outcomes stay distinct

| Outcome | Code | Meaning required from future dispatcher |
| --- | --- | --- |
| submitted | null | Accepted for processing; no confirmed game effect |
| confirmed | null | Correlated engine evidence establishes the outcome |
| rejected | Fixed rejection code | Command refused; never infer an outcome from an exception |
| uncertain | COMMAND_UNCERTAIN | Effect is unresolved; never blindly replay |

Rejection codes in this first schema are SESSION_MISMATCH, VIEWER_MISMATCH,
STALE_REVISION, STALE_DECISION, ACTION_UNAVAILABLE, COMMAND_PENDING and
ENGINE_REJECTED. These are safe enumerated categories, not raw engine messages.
Existing adapter CommandResult contracts/error meanings remain unchanged. The
confirmed fixture is only DTO data, not proof of engine confirmation.

## Current-decision comparison

`CheckCurrent/checkCurrent` takes immutable command text plus caller-supplied
current session ID, authenticated viewer, revision, decision ID and the actual
viewer-authorized action IDs. It parses/validates the request and compares those
opaque values in that order, returning a rejection code or null for no mismatch.
It calculates no Magic legality and never submits, retries or confirms anything.

The future gateway must supply a trusted, viewer-scoped current decision after
peer authentication, and serialize comparison with execution so state cannot
change between them. These helpers alone cannot authenticate the caller, prove
ownership, enforce one outstanding submission, deduplicate IDs or make replay
safe. A structurally valid body may still be stale or unauthorized. ACK routing
must independently bind command/session/viewer/request revision and ignore/reject
uncorrelated or contradictory replies. Parsing an ACK never establishes that its
sender is the engine or that a claimed confirmation is true.

## Evidence and remaining work

Shared `fixtures/wire-messages-v1.json` covers six positive bodies, 19 malformed
or unsupported bodies, and six current-context comparisons: valid, wrong session,
wrong viewer, stale revision, stale decision and unknown action. Java and C# run
the same cases. Python schema checks also establish that current-context rejection
cases are structurally valid, so freshness cannot be confused with shape checks.
No user decks or real hidden state are included.

Local Java checks passed; 33 focused Unity EditMode tests and two focused Python
schema checks passed. The existing hosted protocol helper now compiles/runs this
corpus. No full local suite was run. Relevant CI for this commit is pending.

Scheduled CI snapshot: hosted Java protocol runs for `428543c`
([framing](https://github.com/RyMeep128/Manaforge/actions/runs/41092829995)) and
`758fa4a` ([envelopes](https://github.com/RyMeep128/Manaforge/actions/runs/41093633808))
passed. Desktop Tests passed for `9813d30`, `712cef8` and `547e30b`. Desktop runs
for `428543c`, `758fa4a`, `84fa6d5` and `7501539` were still running and deferred
without waiting. No licensed Unity CI result is claimed.

Next add compatibility/authentication bootstrap and the remaining dummy-exchange
message bodies, then demonstrate Java/Unity exchange and clean shutdown using
synthetic sessions. Bounded cancellation/timeouts, pending/uncertain command
tracking, authenticated snapshot visibility and OS process containment remain
required. Do not start the bulk engine migration or mark G1 complete here.

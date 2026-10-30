# Choice-family command bodies — P1.2/G1 increment

Status: Java/C# parsers and shared schemas cover the current decision families.
This adds transport shapes, not engine execution, choice UI or a completed Java
port. Existing Python contracts, decisions and rules behavior remain unchanged.

Every supported command carries exactly session_id, viewer_id, revision,
operation and decision_id, plus its operation-specific argument below. IDs are
opaque and must originate from the authenticated viewer's current engine decision.

| Operation | Additional field | Existing GameSession method |
| --- | --- | --- |
| perform | action_id | perform |
| choose | option_id | choose |
| select_mana_source | object_id | select_mana_source |
| choose_number | value | choose_number |
| choose_amounts | values | choose_amounts |
| finish_selection | none | finish_selection |
| cancel | none | cancel |

Unknown operations, missing/wrong/extra arguments, null IDs, boolean numeric
values and malformed vectors fail closed. Number/amount entries are signed
64-bit integers, with no decimal/exponent spelling. Negative values are
preserved rather than inventing gameplay restrictions; the engine decides
whether a supplied value is permitted. Amount-vector order is preserved.

`values` permits at most 1024 entries, including an empty vector where the engine
allows it. This is an explicit allocation/transport limit, not a Magic rule,
validated card limit or accepted Commander capacity. Both consumers test exactly
1024 and reject 1025; no truncation or automatic distribution occurs. A future
larger supported decision needs a deliberate compatible contract change.

## Shape and binding are not legality

`CheckBinding/checkBinding` compares session, authenticated viewer, revision and
decision ID for all seven families. A null result means those context values
match, not that the choice/source/value is legal. The gateway must still verify
the engine-provided option/object IDs and constraints, cancellation/finish flags
and current decision family, then submit through XMage. Do not implement those
rules in Unity or infer choices from card text.

The existing `CheckCurrent/checkCurrent` action-ID helper remains **perform-only**
and rejects every other operation with MESSAGE_UNSUPPORTED. This prevents a
caller from silently treating an otherwise current choice as an authorized
perform action. Comparison and execution still require serialized current engine
state. No gateway dispatcher for the new choice shapes is introduced here.

The C# `CommandTracker` accepts these validated shapes without inventing new
outcome semantics. The same correlated ACK, pending/uncertain and no-replay
behavior applies. One focused test verifies a choice remains uncertain after
disconnect/reconnect. The live dummy peer remains a perform-only scenario and
refuses to execute other families; it is not real choice integration evidence.

Concession is still unsupported by the new wire parser. Its existing Python
method has no decision argument and requires a separately specified authorization
boundary; this increment does not fabricate an engine action/token for it.
Shutdown is process/session-lifecycle traffic, not a substitute for concession or
cancelling an engine decision. Both continue to require their distinct ownership
policies.

## Evidence

Shared body fixtures now cover 12 positives and 37 negatives, six perform-context
checks and 12 choice-binding checks, plus exact amount-vector bounds. Fixtures
include signed integer extremes, wrong types, stale decisions, unknown/extra
arguments, overflow/fraction rejection and unsupported concession. Existing ACK
and shutdown checks remain unchanged. Python schema checks also confirm that
context-stale bodies can be structurally valid.

Local Java checks passed; 56 focused Unity EditMode tests and six Python schema
checks passed. The three owned Java-process scenarios still pass. No full suite,
real engine, screenshot or new packaged UX is claimed. Hosted protocol CI includes
the shared corpus; this commit's CI remains unverified until the scheduled
third-commit review. Qt CI is outside this Unity/Java work at owner direction.

Remaining G1 work includes actual compatibility pin validation, product private
bootstrap/lifecycle, gateway deduplication and authoritative reconciliation,
choice dispatch/engine parity, immutable viewer scene projection, transport
queue/cancellation handling and licensed Unity CI. G0/G1 remain open; the bulk
P2 engine migration has not started.

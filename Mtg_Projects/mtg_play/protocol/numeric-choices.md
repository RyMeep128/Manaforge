# Client numeric decision admission — P1.2/G1

Status: C# number/amount admission exercised against supplied fixtures and the
owned Java dummy. This is not a real-engine choice port or G1 completion.
The existing wire schema/DTOs and native persistent decks are unchanged.

## Existing engine boundary

The Python adapter's choose_number compares the current number-family decision
and its supplied minimum/maximum. choose_amounts checks vector length, each
AmountConstraint range and the supplied total range; Python sums do not wrap.
The new NumericDecisionBounds projection preserves that boundary using the
already viewer-validated ChoiceRequest fields. It retains family/bounds only,
not labels, prompts, printed information or defaults.

The client session owner now admits choose_number and choose_amounts alongside
perform/choose/finish/cancel. All commands still require current authenticated
session/viewer/revision/decision binding and registration before write. XMage/the
gateway must revalidate against current engine state before executing anything.
Comparing engine-provided bounds is not a second Magic rules engine.

## Exact values, no inferred choices

Number values remain signed 64-bit integers and must lie within the supplied
range. Amount vectors preserve order and exact length; each value must satisfy
its corresponding engine-provided range, and the mathematical total must satisfy
the supplied total range. C# uses BigInteger for that total so both overflowing
partial sums and cancellation back into range match Python's arithmetic. No
larger integer type is added to the wire format.

Negative values and an empty vector remain supported when the request permits
them. No value is chosen automatically, padded, clamped, truncated, redistributed
or replaced by a default. A single out-of-range value, wrong vector length or
out-of-range total is rejected locally as AMOUNT_OUT_OF_RANGE before writing.
A different request family returns DECISION_FAMILY_MISMATCH. These are local
admission failures, not new ACK codes or engine-confirmed rejections.

Missing total bounds, inverted total/component bounds or an amount dimension
above the existing 1024-value wire cap make numeric admission unavailable
(SESSION_NUMERIC_UNAVAILABLE). The request remains inspectable; it is not filled
with invented bounds. The cap is an allocation/transport limit, not a Magic card
or Commander capacity rule. No silent truncation occurs. Non-numeric controls may
still be available if the engine explicitly supplies them; CanSubmit is not a
promise that every user-entered vector is valid or that the constraint system
has a feasible solution.

A fresh snapshot replaces the numeric projection. Higher-revision events, results,
non-active state and channel failure revoke it with other decision permissions.
The same correlated ACK, uncertainty, cancellation and no-replay handling applies.
The later [mana-source path](mana-source-admission.md) uses current viewer object
IDs and a mana decision; it does not infer source eligibility from numeric payment
data.

## Actual evidence

Twenty new client-owner loopback checks cover signed integer extrema, negative
values, empty vectors, exact mathematical totals, overflow that must not wrap into
range, per-entry/total/count rejection, missing/inverted/oversized constraints,
exact 1024-entry preservation, replacement/revocation and wrong request families.
Malformed/noninteger wire values remain covered by the shared body corpus.

Two further authenticated Java-dummy cases submit an explicit signed number and
amount vector, then observe submitted and explicitly simulated confirmed receipts,
a fixture-only result and matched shutdown. The dummy accepts only the fixed
public values for these cases; it is not an engine dispatcher or general rules
implementation. No real Magic choice or natural game result is claimed.

Local validation: 186 focused Unity EditMode checks, including 48 owner checks and
15 actual Java-process scenarios, plus all Java corpora/16 read/14 write socket
checks passed. Model-generation drift check passed. No full application suite ran.
No new numeric UI or live session is exposed by this increment.

Boundary work still includes complete authentication/session
budgets, Java session ownership, immutable renderer projection, product launch/
containment and licensed Unity CI. G0/G1 remain open. Java/XMage behavior parity
belongs to Phase 2/G2 acceptance after those gates. CI review
stays on the owner's third-commit cadence; no new CI pass is claimed here and Qt
CI was not investigated.

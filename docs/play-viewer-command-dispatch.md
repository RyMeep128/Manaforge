# Bound viewer command dispatch

Status: backend boundary through 0.5.104-alpha.1. No new scene controls or live-game
claim. Packaged fixture owner review and G0/G1 remain pending.

ViewerSessionHost exposes PerformAsync, ChooseAsync, FinishSelectionAsync and
CancelChoiceAsync. Callers supply the current opaque ViewerDecisionOffer and,
where applicable, the exact action/option object from that offer. Matching ID
strings from another projection do not authorize submission. Finish and cancel
require the engine-provided flags. ChooseNumberAsync accepts an explicit signed 64-bit value. ChooseAmountsAsync
accepts an explicitly ordered array and copies it before worker scheduling, with
the existing protocol length cap. The channel checks engine-provided per-value
and aggregate bounds using its existing overflow-safe validation. No labels,
printed text or defaults supply values. SelectManaSourceAsync accepts an exact ProjectedManaSource reference from the
current offer. No defaults, strategic choices, auto-pass or retry are introduced.

A CPU-only reservation disables CanSubmit before scheduling a worker. The worker
constructs context and token fields from the captured frame, rechecks the offer
at channel admission, and performs the bounded socket write outside binding locks.
The channel retains final shape, family, token and pending-state validation.
Concurrent clicks admit at most one command. Local command IDs correlate receipts;
they do not invent legal actions. JSON construction and network IO stay off Unity's
rendering thread. UI controls must still honor the surface handoff barrier.

Task success means the local write returned AwaitingAck, not gateway acceptance or
engine confirmation. Ordered receiver notifications carry submitted, confirmed or
rejected outcomes. Cancellation or lost transport after admission preserves the
existing conservative uncertainty evidence; uncertain commands are never replayed.
The host cancels IO and awaits outgoing worker retirement before completing cleanup.
Previously captured strings remain caller-owned; no secure erasure is promised.

Validation: Java preflight, 362 EditMode and 71 graphics-enabled PlayMode checks
passed with no skips. Six new real authenticated-loopback tests cover exact wire
tokens, distinct receipts, choose/finish/cancel, foreign same-ID objects, stale and
replacement epochs, cancellation, ended ownership and sixteen concurrent clicks.
The full application suite was not run. No UI behavior changed in this increment.

Numeric follow-up evidence: 362 EditMode and 75 graphics-enabled PlayMode checks
passed without skips. Four additional authenticated-loopback tests cover signed
extremes, ordered copied arrays, length/count/range and family errors, overflow,
and stale numeric offers. Rejected local input writes no command, consumes no
pending tracker slot, and leaves a current offer available for corrected input.
There is no new number-entry widget or visible fixture change. CI is next checked
at 0.5.105 under the every-third-commit cadence; no CI success is inferred here.

Mana references are created only for mana-family decisions, from the snapshot's
viewer-filtered object set, and contain only context, decision ID and opaque
object ID. The read-only collection expresses addressability, not legal mana
eligibility. It does not filter by printed card text, zone, controller, tapped
state, concealed identity or inferred abilities. The gateway must validate every
attempt against the engine. No hidden identity or printing field is added.

The dispatcher requires reference membership in the exact current offer, then
uses the existing reservation, final channel admission, bounded worker write and
receipt/uncertainty lifecycle. A separately parsed object with the same ID is not
accepted. New snapshots replace all references even if IDs are unchanged; old
offers or incarnations cannot be rebound to fresh state. Non-mana decisions have
no source references. This adds no mana-source UI, automatic payment or game rules.

Mana follow-up evidence: 364 EditMode and 79 graphics-enabled PlayMode checks
passed with no skips, plus Java preflight. New checks cover the immutable
routing-only reference shape, independent snapshots, empty/non-mana collections,
exact tokens on authenticated loopback, foreign/null references, replaced
incarnations, non-mana offers and uncertainty on shutdown after a write.
No full application suite or visible scene change. The next CI check remains
0.5.105; fixture owner review and real-engine/G0/G1 acceptance remain pending.

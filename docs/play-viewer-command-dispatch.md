# Bound viewer command dispatch

Status: backend boundary through 0.5.103-alpha.1. No new scene controls or live-game
claim. Packaged fixture owner review and G0/G1 remain pending.

ViewerSessionHost exposes PerformAsync, ChooseAsync, FinishSelectionAsync and
CancelChoiceAsync. Callers supply the current opaque ViewerDecisionOffer and,
where applicable, the exact action/option object from that offer. Matching ID
strings from another projection do not authorize submission. Finish and cancel
require the engine-provided flags. ChooseNumberAsync accepts an explicit signed 64-bit value. ChooseAmountsAsync
accepts an explicitly ordered array and copies it before worker scheduling, with
the existing protocol length cap. The channel checks engine-provided per-value
and aggregate bounds using its existing overflow-safe validation. No labels,
printed text or defaults supply values. Mana selection dispatch remains future
work; no defaults, strategic choices, auto-pass or retry are introduced.

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

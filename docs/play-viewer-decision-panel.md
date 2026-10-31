# Viewer decision panel

Status: reusable presentation component through 0.5.107-alpha.1. Not mounted in the
product launcher or packaged session fixture. Owner visual review is pending.

ViewerDecisionPanel renders the engine prompt and exact action/option labels,
plus finish/cancel only when the decision flags allow them. Labels disable rich
text interpretation. Actions/options share pages of sixteen entries; navigation
never submits a command and all entries remain individually reachable. Number and amount decisions have explicit text entry described below. Mana
decisions still state that their source-selection widget is not available. No default choice, inferred legality or smart pass is implemented.

The owning UI calls host.Tick followed by panel.Tick each frame. The panel reads
host.PresentedDecision, which requires the current offer's revision to match the
card snapshot actually presented by the same surface epoch. This includes the
empty-frame handoff barrier and mailbox watermark. Until then the panel clears
its prompt, controls and cached offer. Owner loss, replacement epoch, terminal
state and retired offers likewise clear on the next UI tick. The host/dispatcher
also reject stale callbacks even if a detached button is retained elsewhere.
The application must continue pumping or dispose the panel on close; it cannot
promise UI-thread destruction while the application stops pumping.

Clicks recheck the presented offer and use the existing bound dispatcher. A
pending task disables the decision controls. Local write success alone says only
"Command sent. Waiting for gateway state." Typed receipt feedback from its own
host can subsequently distinguish submitted, confirmed, rejected or uncertain.
These labels report gateway command status, not a game result. The panel does
not consume the ordered receive queue, parse ACKs, retry uncertainty or choose
strategic actions. A retired task's
exception is observed without a worker touching Unity UI. Disposing the panel
removes its subtree; host/process ownership remains with the existing owner.

The graphics PlayMode test writes a public synthetic capture to
Mtg_Projects/mtg_play_unity/Artifacts/DecisionPanelProof.png. It uses the same panel,
real authenticated loopback and UI navigation-submit events. It is a component
review image, not an Arena battlefield or live XMage acceptance build. The
existing artwork and packaged session galleries remain unchanged.

Local validation: Java preflight, 364 EditMode and 84 graphics-enabled PlayMode
checks passed without skips. Five new panel tests use actual UI navigation-submit
events and authenticated sockets to verify exact option/action/finish/cancel
commands, page reachability without automatic input, literal labels, presentation
barrier, snapshot replacement and owner/epoch revocation. The synthetic pending
state capture was visually inspected. Disabled buttons deliberately remain visible
while awaiting gateway state. No full application suite or packaged build ran for
this increment. Owner review is still required before mounting the panel in the
session fixture; neither screenshots nor automated checks record owner approval.

Numeric input follow-up (0.5.106): number fields start empty and never adopt zero,
a range endpoint or the engine's optional default. They accept an explicit signed
64-bit integer using invariant syntax without decimal/group separators or silent
truncation. Every amount must be entered, including an intentional zero. The
panel displays engine-supplied per-value and total bounds, then delegates range
and aggregate/overflow validation to the existing channel admission. Invalid
ranges produce a fixed recoverable message and preserve editable values; no
command is written or pending slot consumed. Corrected input requires another
explicit submit. Local write success still does not mean engine confirmation.

Amount fields are paginated sixteen at a time, with earlier entries retained in
original engine order. At most the protocol's 1024 values are supported; missing,
inverted or unsupported bounds do not produce guessed controls. UI parsing checks
do not allocate value arrays each frame. Snapshot replacement, owner loss and
panel disposal discard input state and remove fields; old callbacks cannot alter
the next offer. This is scoped reference cleanup, not secure string erasure.

Evidence: 89 graphics-enabled PlayMode checks passed without skips. Five new
real authenticated-loopback UI checks cover blank/malformed input, explicit zero
and signed extremes, ignored defaults, pagination, aggregate rejection followed
by correction, stale callback isolation, missing limits and over-capacity arrays.
The synthetic DecisionNumbersProof.png capture was visually inspected. No full
application suite, EditMode rerun or packaged build was needed for this UI-only
increment. Owner review remains pending and the panel stays unmounted in existing
scenes. CI is next checked at 0.5.108 under the third-commit cadence; no new CI
success is inferred from these local results.

Receipt-feedback follow-up (0.5.107): CommandTracker.Find returns an immutable
snapshot of a record already owned by that authenticated tracker. Unknown IDs or
disposed history return null. Observation never advances a receipt, releases a
pending command or performs IO. The channel exposes that lookup internally only
while active. The host additionally requires the exact currently presented offer
and matching revision/decision metadata before returning its own command record.
A caller-supplied receipt never becomes the source of displayed confirmation.

The panel retains the locally returned submission only for its current offer.
It samples the latest validated tracker state, which is updated by the existing
ordered receive worker. Intermediate states may pass between rendered frames;
the ordered notification queue remains intact for its separate owner to consume.
A repeated receipt for an old command cannot overwrite a new command's display.
A new offer, owner loss or surface epoch replacement drops cached feedback. No
receipt history is shown after revocation; stopped-session uncertainty remains
in the existing host stop summary for a future recovery view.

Submitted remains disabled while waiting for confirmation. An explicit uncertain
receipt says "Command outcome is uncertain. Do not retry." and leaves submission
blocked. Gateway-confirmed/rejected terminal receipts retain the existing channel
availability behavior; they do not invent a new decision or automatically play.

Receipt feedback evidence: Java preflight, 366 EditMode and 93 graphics-enabled
PlayMode checks passed without skips. Two new tracker checks verify immutable,
non-mutating lookups and old-terminal isolation. Four new authenticated-loopback
panel checks verify submitted/confirmed distinctions even when ACKs precede UI
polling, queue preservation, rejection and repeated-old-receipt isolation, late
confirmation after a new decision, uncertain/late-submitted blocking, and owner
loss cleanup. No full application suite or packaged build ran. CI is next checked
at 0.5.108; product mounting and owner visual acceptance remain pending.

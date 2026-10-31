# Viewer decision panel

Status: reusable presentation component at 0.5.105-alpha.1. Not mounted in the
product launcher or packaged session fixture. Owner visual review is pending.

ViewerDecisionPanel renders the engine prompt and exact action/option labels,
plus finish/cancel only when the decision flags allow them. Labels disable rich
text interpretation. Actions/options share pages of sixteen entries; navigation
never submits a command and all entries remain individually reachable. Number,
amount and mana decisions explicitly say their input widgets are not available
in this panel. No default choice, inferred legality or smart pass is implemented.

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
pending task disables the decision controls. Local write success says only
"Command sent. Waiting for gateway state." It is not displayed as confirmed,
submitted or a game result. The panel does not consume the ordered receive queue,
interpret ACKs, retry uncertainty or choose strategic actions. A retired task's
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

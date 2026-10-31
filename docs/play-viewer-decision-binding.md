# Viewer decision offer binding

Status: lifecycle/availability boundary at 0.5.101-alpha.1. No controls, command
builder, auto-pass or outgoing-action API are enabled. The fixture UI review and
real-engine/G0/G1 acceptance remain pending.

Each ViewerSessionReceiver owns a ViewerDecisionBinding. An applied active
snapshot with a decision creates a new opaque ViewerDecisionOffer. The offer
exposes only its own current immutable Frame and a dynamic CanSubmit indication.
An offer never starts referring to another snapshot's data. No UI/token identities
are fabricated from card names, labels, families or numeric defaults.

Current lookup checks the captured viewer mailbox, minimum revision and the
channel's exact live session/viewer/revision/decision binding. The channel checks
these fields and submission availability together under its lock. An availability
read is still only a snapshot: final command shape, token membership, family,
numeric limits, pending/uncertain state and transport admission remain the
channel's responsibility when a future dispatcher submits.

A pending/submitted/uncertain command keeps the current prompt readable while
CanSubmit is false. Receipts are not interpreted as game-state snapshots or
implicit results. Confirmed/rejected terminal receipts release the existing
channel tracker as before. Explicit stale-revision/decision, unavailable-action,
session-mismatch or viewer-mismatch rejections retire a matching offer until a
new snapshot arrives. Local TrackedCommand now retains the submitted decision ID
alongside request revision, so late rejections for another decision do not retire
the new one. This metadata comes from the locally admitted command, not a new ACK
field or protocol change.

New applied snapshots replace the offer even when engine context strings and
tokens are unchanged. Duplicate receive notifications do not. Newer event revisions
retire old offers; same-revision events preserve them. Terminal/missing-decision
snapshots, channel stop, queue overflow and viewer/owner revocation remove the
binding. Old offers expose null data and false submission availability. A receiver
for a replacement epoch does not recognize an old offer even if every engine
context string happens to match.

The host's CurrentDecision property supplies its receiver's current offer and
checks owner-lifeline completion before returning it. Binding operations are CPU
only and thread-safe; no socket reads, JSON parsing, Unity objects or waits occur
there. UI bindings must still respect the surface's empty-frame handoff barrier
before showing controls, clear their cached labels/references on revocation, and
revalidate the captured offer at dispatch. An offer is neither rendering permission
nor authority to skip engine validation. Previously extracted immutable frames
remain caller-owned; this does not promise secure erasure of saved strings.

Local evidence: 362 EditMode checks including Java preflight and 65 graphics-enabled
PlayMode checks passed with no graphics skips. New real-loopback checks cover
matching context versus pending submission, ordered submitted/confirmed receipts,
same-token replacement snapshots, higher/same-revision events, identical-context
replacement epochs, missing/failed/result snapshots, channel stop/overflow,
matching stale rejection, and late rejection for another decision at the same or
newer revision. The authenticated host revokes an offer on owner loss before Tick.
No full application suite or visible UI change. CI review remains every third
commit, next at 0.5.102.

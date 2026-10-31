# Bounded viewer presentation pump

Status: G1/P3 integration seam at 0.5.90-alpha.1. Product scene mounting, private
launcher bootstrap, live engine integration and G0/G1 acceptance remain open.

After creating a ViewerCardSurface, begin its viewer epoch with a private
ViewerArtworkScope and create its artwork jobs using the pinned Core provider.
The future authenticated receive worker posts immutable card projections to that
ticket's mailbox. The UI host calls `surface.Pump(ticket)` once per update.

Pump drains the newest snapshot before uploading images or admitting artwork
jobs. The existing whole-empty-frame handoff barrier remains enforced. Defaults
are two completion uploads and four artwork admissions per update, independently
configurable from zero to sixteen. Invalid limits fail before any mailbox mutation.
The return value counts consumed mailbox items plus accepted jobs, not successful
images, engine acknowledgements or completed gameplay actions.

Applying a snapshot builds a FIFO of eligible unbound object IDs, bounded by the
projection's 4096-object limit. Each update examines only its configured number
of requests, rather than rescanning the board. Hidden, unknown-face and already
bound objects do not enter the FIFO. Requests are issued through the existing
current-viewer/revision checks; providers run on workers. Queue capacity refusal
retains the head for a later update, preserving eventual admission when capacity
becomes available. No waiting, file reads, decoding or database access occur in
the pump. Snapshot application and texture uploads retain their existing costs;
this is a count budget rather than a measured frame-time guarantee.

Once a job is accepted, the pump removes it from that revision's FIFO. Missing,
failed or mailbox-dropped results stay unavailable without automatic replay.
An applied newer snapshot rebuilds the FIFO for current unbound objects; retained
valid bindings avoid redundant reads. A watermark ahead of displayed state
invalidates pending admission until a current snapshot arrives; a watermark
behind or equal to that state preserves valid requests. New snapshots replace old admission
state. Clearing a viewer stops jobs and clears the FIFO; retired tickets cannot
drive the next viewer's pump. Stopped mailboxes clear the surface on its next tick.

Choose pump-managed admission or explicit manual RequestArtwork/TryQueue for an
epoch. Do not mix manual admission with the pump: the lower-level coordinator's
pending-request deduplication is not a completed-attempt history or retry policy.
DrainMailbox remains available for callers that manage scheduling themselves.
Receive events, command receipts and uncertainty retain their separate protocol
owners; Pump coalesces no event history and submits no game commands.

Local validation: 321 EditMode checks including Java protocol preflight and 37
graphics-enabled PlayMode checks passed with zero graphics skips. New checks
cover the empty-frame barrier, independent admission/upload budgets, retained
backpressure, no repeated failed requests, newer snapshot cursor replacement,
retired ticks, stopped mailbox cleanup, concealed objects, watermark invalidation
preservation of valid requests under a lagging watermark, and invalid limits
without mutation. The public fixture scene is unchanged and
no new owner UI verification is needed. No full application test suite ran.

Third-commit CI checkpoint: no newer relevant run was present during review. The
latest observed protocol success remains commit 0e8f028, [run 41170567675](https://github.com/RyMeep128/Manaforge/actions/runs/41170567675).
That is historical protocol evidence, not validation of this renderer increment.
The protocol workflow's path filters exclude these presentation-only changes;
licensed Unity CI remains manually dispatched. No unfinished run was awaited.

The subsequent [session receiver](play-viewer-session-receiver.md) now feeds
validated card projections and event watermarks into this pump while preserving
ordered worker notifications separately. It revokes the captured mailbox on
channel/owner cancellation; the UI host must keep pumping to perform visual cleanup.

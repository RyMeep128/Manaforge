# Bounded render mailbox and UI drain

Status: tested worker-to-UI foundation. Core cache jobs, bounded active-worker
scheduling and production session-scene mounting remain open. See the
[viewer surface](play-viewer-surface.md) and [artwork boundary](play-viewer-artwork.md).

Each opaque `ViewerSurfaceTicket` owns one `ViewerRenderMailbox`. Producers must
capture that exact ticket/mailbox when work starts; never route an old completion
to whatever viewer happens to be current after an await. Returning to the same
session/viewer creates a different ticket and retires the old mailbox.

The mailbox is CPU-only, thread-safe and bounded. It retains at most one complete
immutable projected snapshot, replacing it only with a strictly newer revision
in the same session/viewer context. This coalesces rendering state, not wire game
events, decisions, command receipts or replay history. The authenticated channel
and receive history must still process those in order and validate conflicts.
The mailbox neither parses nor authenticates arbitrary network data.

Artwork completions are limited independently by count and decoded byte size:
32 entries and 8 MiB by default, with validated maxima of 64 entries and 64 MiB.
The existing preparation boundary caps each image at 1024 per edge. Duplicate
queued request tokens, wrong epochs, obsolete revisions and overflow are refused;
refused prepared buffers are disposed/cleared. Reposting the exact already-owned
queued instance does not clear that accepted instance. An accepted post transfers
ownership: the producer must not mutate, dispose or repost the payload.

Newer snapshots and revision watermarks discard obsolete pending images. No
queued image may bypass a pending snapshot. Worker-side mailbox disposal clears
all queued pixels and releases the pending frame reference; late arrivals are
also consumed and cleared. This bounds queued completion retention, not the
number or memory footprint of active decoder jobs outside this mailbox. The host
still needs bounded job scheduling, cooperative cancellation and disposal of
inputs/completions that never reach a post operation.

`ViewerCardSurface.DrainMailbox(ticket, maximumArtworkUploads=2)` runs on the
creating UI thread once per update. It advances the trusted minimum revision,
tries the newest full frame first and processes only a bounded number of image
completions. Peek retains the frame while the viewer-switch empty-frame barrier
is closed. A stopped mailbox clears the current surface on its next drain.
Every new viewer, clear, fault or disposal closes the old mailbox before private
texture-scope disposal. Retired drains cannot clear the new viewer.

The surface also checks mailbox watermarks during direct frame/artwork/inspection
admission. A worker receiving newer state can therefore revoke obsolete artwork
work before the UI presents the next frame. Visibility revocation/disconnect must
stop the captured mailbox (or clear the matching UI ticket), not merely raise a
revision watermark. Existing already-visible state is changed only by the UI
owner; a background producer never calls Unity UI or graphics APIs.

Applied images still go through exact printing/face policy, current request
identity and private texture budgets. No new decoder, downloader, database, deck
format, wire schema or Python gameplay relay was introduced. The mailbox does
not provide a live engine session, seat layout or action dispatch.

Validation at 0.5.87-alpha.1: 321 EditMode checks and 22 graphics-enabled PlayMode
checks passed, including existing Java preflight and the real GPU pixel-copy
check with zero skips. New checks cover concurrent revision coalescing, wrong
contexts, immutable latest-frame peeking, monotonic watermarks, epoch retirement,
invalid-budget safety, the empty UI handoff frame, bounded drain/queue work,
rejected and obsolete pixel disposal, duplicate ownership, concurrent completion
budgets, and shutdown. No full application suite ran. The public fixture is
unchanged; no new owner UX review or live-game acceptance is claimed.

A subsequent [artwork coordinator](play-artwork-jobs.md) now provides bounded
per-epoch active/queued jobs and asynchronous lifetime cancellation. The concrete
Core provider, provider deadlines/global retirement policy and live mounting
remain separate work.

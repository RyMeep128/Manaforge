# Bounded artwork job coordinator

Status: tested per-viewer-epoch worker scheduling. A concrete Core cache provider,
provider deadlines/global retirement policy and production scene mounting remain
open. This extends the [mailbox](play-render-mailbox.md) and
[artwork binding](play-viewer-artwork.md), without a new database or decoder.

`ViewerCardSurface.CreateArtworkJobs(ticket, provider, concurrency=2,
maximumQueued=32)` creates at most one coordinator for the active viewer epoch
and requires its private artwork scope. Construction does not call the provider.
Queued/running work deduplicates request instances. Limits are validated up to
eight active provider calls and 128 queued requests per coordinator. Stale queued
revisions are pruned before admission and checked again before execution. The
worker retirement path restarts pending work so a concurrent admission cannot
strand a queue behind an exiting idle worker.

The provider signature is `Func<ViewerArtworkRequest, CancellationToken,
Task<PreparedCardArtwork>>`. Invocation occurs inside Task.Run, outside the
coordinator lock, and awaits do not capture the Unity synchronization context.
The host must implement the provider with existing Core cache mapping/decoding,
honor cancellation, bound input allocation, clear its owned private decode
buffers and return the exact request's prepared result. No engine rule,
name-based artwork lookup, downloader or Python gameplay relay is supplied here.

A returned prepared result transfers ownership to the coordinator. A matching
live completion is transferred to the captured mailbox; null, mismatched, stale,
failed or stopped results are discarded and owned pixel buffers are disposed.
Mailbox refusal also consumes the completion. Provider exceptions never escape
as private filenames/card names: LastCode records only fixed ARTWORK_JOB codes.
A completed job is not an engine command acknowledgement or gameplay outcome.
There is no automatic retry; a later cache change/new state or explicit host
policy determines any retry, still through current request admission.

Surface clear, viewer switch, fault or disposal stops its owned coordinator.
Dispose invalidates admission and clears queued requests synchronously, then
signals cancellation on a worker. User cancellation callbacks therefore cannot
block the Unity caller or run under the coordinator lock. Callback exceptions
are contained with a fixed diagnostic. The UI never waits for providers.
Completion means the stopped coordinator's workers and cancellation callbacks
have finished and its cancellation source is released; it is not a per-job
success result or an idle notification.

Cancellation is cooperative, not forced thread termination. A provider that
ignores it may finish later; its result is still disposed and cannot enter the
retired or next viewer's mailbox. The host must track retiring Completion tasks
and apply provider deadlines/global resource policy; per-epoch bounds do not
promise a bound on arbitrarily many noncooperating retired providers. This
increment does not create a process killer, global job pool or live asset pump.
Already-posted valid pixels remain owned by the mailbox; viewer revocation closes
that mailbox separately, as the surface cleanup already does.

Local validation at 0.5.88-alpha.1: 321 EditMode and 28 graphics-enabled PlayMode
checks passed with no graphics skips, including existing Java preflight and GPU
pixel-copy evidence. New checks cover concurrent/queued limits, duplicate
admission, worker-only callbacks, pruning obsolete work, late-result disposal
across viewer changes, provider failure/null/mismatched results, asynchronous
cancellation callback containment, and 64 concurrent admissions with fast
providers and no stranded accepted work. No full application suite ran. The
public fixture remains unchanged and no owner UX review is needed for this
scheduler-only increment. Core provider integration and G0/G1 remain open.

The subsequent [offline Core provider](play-core-artwork-provider.md) now supplies
pinned launch-sidecar pixels to these jobs. Product launcher/scene mounting and
general face contracts remain open.

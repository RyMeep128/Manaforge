# Viewer session receive-to-presentation bridge

Status: worker/UI integration seam at 0.5.96-alpha.1. Production scene mounting,
full choice/event UI projection, installed-artifact verification and OS containment
remain open. This is not a real-engine gameplay or G0/G1 acceptance claim.

Create ViewerSessionReceiver immediately after obtaining an authenticated
ClientSessionChannel, with a current matching ViewerSurfaceTicket and no existing
queued channel packets. Identity mismatch or invalid budgets reject construction
before taking any receive rights. The channel owner retains its lifetime and
command-submission API; the receiver becomes its exclusive receive consumer.
Never construct the channel from an unauthenticated socket in production. Tests
may construct fixture channels directly; authentication has separate Java/C# proof.

The connection worker calls ReceiveOnce with an explicit bounded read budget.
There is no new automatic read loop, heartbeat, idle policy or reconnection.
The method uses existing channel admission/history, then projects snapshots or
results into immutable card frames for the captured viewer's mailbox. Events
advance its minimum revision without inventing a snapshot. Snapshot coalescing
occurs only in the render mailbox. New fields retain the existing projection's
privacy/unknown-value rules; no raw packet is passed to a card scene.

Every receive notification is also retained in a bounded ordered queue, including
events, results, duplicate indications and command receipts. Packet ownership
transfers from the channel inbox without copying another byte buffer. TryTake
transfers a ViewerSessionUpdate to a worker consumer, which must Dispose it.
That worker must build suitable immutable choice/event UI projections before any
scene use. Receipt-only updates have no packet; their immutable tracked receipt
preserves submitted/confirmed/rejected/uncertain distinctions. These notifications
are not coalesced or silently dropped while the receiver is active.

Default limits are 128 updates and 8 MiB of retained packet bytes, configurable
to 1–1024 updates and 1–64 MiB. The byte budget counts packet buffers; the update
count also bounds small receipt/duplicate metadata. Overflow fails closed,
cancelling the channel and revoking the viewer instead of losing ordered work.
Projection failures, bad privacy/context, concurrent readers and channel stop
likewise revoke. A stopped receiver returns false, admits no late packets and
does not retry. Invalid read budgets fail before changing receiver state.

Cancel/Dispose revoke only the captured ticket's mailbox and clear receiver-owned
packets. The UI host must call ViewerCardSurface.Pump on each update: a stopped
mailbox clears its cards/inspection/pending artwork and releases owned textures on
the UI thread. Workers never manipulate Unity objects. Cancel the old receiver
when switching seats or losing the owner lifeline, before starting a new channel.
An old receiver cannot clear or populate a new epoch. A generic game event is not
interpreted as an authorization revocation; the trusted host must explicitly cancel
on seat/owner revocation. Choice/event UI not yet mounted must adopt this same policy.

The first bridge stop reason wins. The channel's own Completion retains its more
specific protocol cause. Bridge Completion preserves a small viewer-scoped stop
summary: pending command (after cancellation), last accepted receipt, graceful
transport flag, and the last authoritative result's context/status/result only.
It retains no result cards, reveal observations or raw packets. This summary is
for its retired viewer, never another seat, and must not be dumped into logs.
Graceful shutdown is not a game outcome; only a received result supplies one.
Completion records revocation and its summary, not receive-worker quiescence.
The host must also await any outstanding ReceiveOnce task off the UI thread
before final channel disposal or resource cleanup.
Submitted pending actions become uncertain on disconnect; confirmed receipts do
not become uncertain. The bridge cancels but does not dispose the borrowed channel,
so its owner can inspect tracker evidence before final disposal.

Transferred updates remain caller-owned; cancellation cannot erase a caller's
saved strings or projections. Managed-memory erasure limitations still apply.
Cancellation revokes admission immediately; visual destruction occurs on the next
UI pump and Unity's existing deferred-destruction frame, not on the network worker.

Local evidence: 44 graphics-enabled PlayMode checks passed with zero skips. New
real-loopback/panel checks cover ordered packets through render coalescing, event
watermarks, result summary after graceful shutdown, receipts in order, pending
uncertainty, confirmed-state preservation, count/byte overflow, cancellation while
blocked on a socket, concurrent readers, malformed hidden state, and retired-seat
isolation. A private texture is released after UI cleanup. Existing GPU-copy and
surface lifecycle checks remain active. No full application suite ran. Public
gallery UI is unchanged; no new owner UI review needed. Relevant CI is checked at
this third-commit checkpoint without waiting for unfinished runs.

Recovery note: after the owner-reported power cut, the saved report was confirmed
as Passed, 44/44 with no skips, and source changes were intact. A recovery rerun
exited before tests with Unity exit 198: its licensing client had no access token
or valid Editor entitlement. That rerun is blocked by local license restoration,
not recorded as a new passing run. No source test failure or license workaround
is inferred; the existing Hub sign-in/license must be restored by the owner.

After the owner reopened Hub, the recovery rerun passed all 44 graphics checks;
that local license interruption is resolved. The later
[session host](play-viewer-session-host.md) coordinates the authenticated connector,
receiver and UI pump, and observes owner loss across their lifetime.

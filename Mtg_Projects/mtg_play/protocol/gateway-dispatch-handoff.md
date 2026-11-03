# Java reservation-to-enqueue handoff

GatewaySessionBoundary.dispatch combines current viewer admission, one-time
reservation and a trusted Submission.enqueue callback under the owner's monitor.
The callback receives its own parsed command tree. Rejected and duplicate
requests return their receipts without invoking it. Callback mutation cannot
change the ledger's retained request or make an identical retry a new command.
A successful callback returns a submitted receipt; it does not confirm gameplay.

Enqueue exceptions fault the owner, revoke decisions and mark the reservation
uncertain. The caller receives only SESSION_DISPATCH_FAILED, without callback
messages or causes. InterruptedException preserves the thread interrupt flag.
Fatal Java Errors also fault the owner and mark uncertainty, then propagate to
the local worker; the future transport owner must never serialize their details.
The callback may have taken effect before failing, so no automatic retry occurs.
Late trusted engine outcomes can still resolve the retained uncertain receipt.

This callback must promptly enqueue to an owned engine worker. It must not wait
for engine work, perform socket IO, or reenter the boundary. Reentrant observation,
preparation, dispatch, receipt/outcome access, disconnect and close are rejected;
state inspection is harmless. Callbacks from other threads serialize behind the
handoff. A hung callback would block those callers, so bounded worker admission
and watchdog/process containment remain product integration requirements. This
API itself provides no callback timeout, queue, worker or process ownership.

The lower-level prepare API remains for fixtures/integration but does not provide
an enqueue handoff. Product dispatch should use dispatch. Neither API replaces
XMage legality, viewer-filtering, revision/decision validation or authoritative
outcome correlation. The Java dummy now uses an explicitly synthetic enqueue-ID
recorder; simulated confirmations remain fixture-only behavior.

Thirty-six focused Java checks cover one-time/duplicate/rejected invocation,
callback mutation, side-effect-then-exception uncertainty, refusal to retry,
late trusted confirmation, interruption, null callbacks, reentry, fatal-error
cleanup and concurrent duplicate handoffs. No rendered UI changes or hands-on
Unity verification are required. G0/G1 remain open; this is not a live-engine game
or the bulk P2 gateway migration.


Local validation passed: the 36 new dispatch checks, all existing Java protocol
corpora and socket/owner checks, and 227 focused Unity EditMode checks including
19 Java process scenarios. Ruff passed for the updated Python runner. No full
application suite ran. CI is checked at this third-commit checkpoint after push;
unfinished runs will be deferred rather than awaited.

# Authenticated viewer session host

Status: UI/worker lifetime coordinator at 0.5.97-alpha.1. It is exercised on an
attached test panel, not mounted in the public gallery or product launcher. Live
XMage gameplay, G0/G1 acceptance and hands-on UX acceptance remain open.

Create ViewerSessionHost on the card surface's UI thread with an owned private
ViewerBootstrap and the owner's lifeline task. The host begins a fresh viewer
epoch with its existing empty-frame barrier. Bootstrap ownership transfers only
after BeginViewer succeeds. The parent retains ownership of the bootstrap pipe
and its lifeline monitoring task; any completion, failure or cancellation of that
task means the owner has ended.

The default connection path runs entirely on workers. ViewerSessionConnection
connects to literal IPv4 loopback without DNS, then runs the fresh Java/C# nonce
and signed-hello exchange. One budget covers connection and authentication;
timeouts/cancellation close the attempt and late completions cannot mount a view.
The host installs ViewerSessionReceiver only after successful authentication and
matching context. No unverified socket can post a card frame through this path.
Expected pin agreement does not verify installed engine/gateway artifacts.

Once authenticated, a connection worker receives under explicit bounded read
budgets. Tick on the UI thread calls the existing presentation pump; it does not
read sockets, parse JSON, decode artwork or wait for workers. Inspect delegates to
the captured viewer's inspection boundary and submits no gameplay action. The
Authenticated property means peer proof succeeded, not that an opening snapshot
arrived, a deck was engine-resolved or a match is playable.

Owner loss is checked before every Tick/Inspect as well as observed asynchronously.
Stop revokes the captured mailbox, cancels its receiver/channel and prevents late
authentication or snapshots from mounting. The next UI pump clears cards,
inspection and private assets. UI Dispose cancels and clears synchronously without
waiting. An old host's stop, Tick or disposal cannot clear a replacement epoch.
Cancel can be called from any thread; Tick/Inspect/Dispose enforce their UI thread.

Completion means the host's connection/receive work has retired, its channel and
bootstrap have been disposed, and a small stop summary is available. CleanupConfirmed
refers only to those owned managed/transport resources, not processes, descendant
containment, transferred updates, or deferred Unity texture destruction. The
receiver captures command uncertainty/result/receipt evidence before the host
disposes the channel. Parent code must await Completion away from the UI thread
and separately manage its pipe, artwork jobs/workspace and process containment.

Ordered notifications remain available through TryTake for a worker consumer,
which owns/disposes transferred updates and builds future choice/event UI models.
The host never silently drains/discards this queue while active. Failure to consume
it eventually reaches the existing explicit queue limit and revokes the session.
Only card snapshots coalesce in the rendering mailbox.

Current limits: this host does not load bootstrap artwork sidecars or submit game
commands yet. Engine fields and unavailable-artwork/rules placeholders use the
existing shared renderer. Core provider mounting and full decision/event UI follow
separately. The existing read API has a maximum/default 60-second per-read budget;
real-session idle/heartbeat policy is not accepted yet, and read timeouts are not
automatically retried. There is no reconnection, automatic play or inferred legality.

Local validation: 50 graphics-enabled PlayMode checks passed with zero skips.
New real-loopback/panel cases exercise connect + fresh proof + visible snapshot,
ordered update transfer, owner-loss card/inspection clearing, cancellation during
authentication, a valid proof for the wrong pin followed by an untrusted snapshot,
replacement-epoch isolation, already-ended owners with no connection attempt, and
refused connections with resource cleanup. Previous protocol interop proves the
same handshake against Java; these host peers are public synthetic C# fixtures.
No full application suite or public scene change. No new owner UI review needed.
Relevant CI is next checked at 0.5.99 under the third-commit cadence.

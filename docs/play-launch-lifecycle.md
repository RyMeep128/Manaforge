# Play launch ownership and lifecycle — P1.4 foundation

Status: owned-child coordinator and failure tests implemented. Private IPC,
OS containment, orphan recovery and the real launcher are not yet implemented.
See the [roadmap](play-unity-java-roadmap.md) and [manifest boundary](play-launch-boundary.md).

## Ownership contract

| Resource | Owner | Required shutdown evidence |
| --- | --- | --- |
| Gateway and Unity root processes | Desktop launch worker | Owned handles reaped; exit/forced status retained |
| XMage and gateway-created descendants | Java gateway plus platform containment | Verified descendant cleanup, not just gateway exit |
| Viewer snapshots, assets and pending interactions | Unity viewer projection | Invalidate on seat change/disconnect/shutdown |
| Private launch bytes and owner bootstrap credentials | Trusted Desktop/gateway bootstrap | Never sent to Unity, logs, command lines or remote seats |
| Per-launch workspace | Launch owner | Delete only verified launch-owned content after confirmed cleanup |
| Native decks/library/preferences | Existing Manaforge modules | Never overwritten or removed by Play cleanup |

Python may coordinate startup/shutdown and monitor child health. It does not
relay per-action gameplay. Java owns engine processing; Unity owns presentation.

## Implemented coordinator

`mtg_play.launch_lifecycle.LaunchOwner` creates direct child processes without a
shell, retains their handles and reuses the existing bounded `stop_process` helper.
It never adopts saved PIDs, scans process names, kills an occupied port or deletes
a directory. Windows child windows are hidden. This foundation discards stdout/
stderr rather than storing unfiltered output; bounded redacted diagnostics and
verified handshake readers must be connected before it runs actual product binaries.

```text
new → starting_gateway → gateway_ready → starting_client → active
                         any started state → stopping
stopping → closed                       (all cleanup confirmed)
stopping → cleanup_blocked → stopping    (retry, with new evidence)
```

Starting Unity requires gateway readiness and a living gateway. Readiness methods
are lifecycle events for a future verified handshake; they do not authenticate a
peer or infer readiness from time, process existence or a listening port.

The launch worker calls `check_health` during startup and the active session.
Startup has a monotonic deadline; active games do not inherit that startup limit.
Blocking methods are serialized, while `request_cancel()` is thread-safe and
nonblocking. Cancellation is checked before and after process creation so a child
created during cancellation is still registered and stopped.

Close stops Unity before the gateway, attempts every owned child even if another
cleanup or status check fails, and retains immutable reports. Missing process
evidence is explicitly unconfirmed; unknown forced status is null. Forced-stop
history survives retries. Exit codes are lifecycle facts, never Magic results.

Root exit does not prove XMage stopped. `runtime_cleanup` must be a trusted,
bounded callback reading verified gateway/OS ownership evidence. The default is
unconfirmed if a gateway was created. A constant true callback is used only for
test children known to have no descendants; it is not valid runtime evidence.

`cleanup_blocked` rejects a new launch on the same owner. The future application
controller must retain that owner and block replacement launches until cleanup
is confirmed. `closed` is terminal; a successful new match uses a fresh owner.
Context exit always attempts cleanup. It raises an explicit cleanup error on
otherwise normal exit, or preserves an existing exception with a safe cleanup note.

## Planned private delivery

The proposed transport split is inherited anonymous pipes for one-time bootstrap
and an authenticated loopback stream for Java/Unity gameplay. This avoids passing
every action through Python and supports asynchronous decisions and cancellation.
It is a design proposal, not an implemented or accepted protocol.

- Send the owner-only manifest and fresh owner credential to the gateway through
  its inherited pipe, not a public deck file, command argument or environment variable.
- Give Unity only its viewer credential and compatible loopback endpoint through
  a separate inherited channel. It must never receive all seats' decks/credentials.
- Bind loopback only to localhost; frame and cap messages. Verify versions,
  engine/artifact pins, ownership proof and seat authorization before readiness.
- Keep the owner pipe as a lifeline after bootstrap. EOF requests graceful shutdown;
  Unity must marshal quit onto its main thread, and Java must stop/reap its runtime.
- Resolve unknown, malformed, stale or uncertain messages safely. Do not replay
  uncertain actions or treat a bootstrap acknowledgement as a completed game.
- Retain no manifest file by default. RAM lifetime is bounded by launch ownership;
  Python's immutable bytes/garbage collector do not promise secure memory erasure.

These schemas/readers must be proven with dummy-process exchanges under G1 before
connecting this coordinator to the real client. Current readiness calls and child
EOF fixtures do not substitute for that evidence.

## Crashes, workspaces and orphan recovery

Before P4, add containment that proves descendant ownership and survives owner
crashes. On Windows, evaluate Job Objects with kill-on-close and appropriate child
inheritance/no-breakaway behavior, including Unity/compiler compatibility. Attach
containment before a child can create untracked descendants. Microsoft documents
these controls in [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
They are not implemented by the current Popen-based coordinator.

Use unique private workspaces and opaque launch ownership records without cards,
tokens or raw command lines. Treat leftover records as recovery candidates, never
authority to kill a reused PID. Verify live ownership or fail closed. Unknown
descendants or uncertain cleanup keep Play blocked. Never remove user data, adopt
an unrelated engine or recursively delete a path inferred solely from an old record.

## Validation and remaining gate

Focused tests exercise transitions, deadlines, cancellation during creation,
partial startup, child death, failed cleanup/poll, proof failures, context exit,
forced history and private diagnostic exclusion. Tiny real Python child tests
verify graceful EOF, forced shutdown, and an unrelated process remaining alive.
They start neither Unity nor XMage; the module also imports without Qt or Core.

The existing Qt runtime remains the fallback. No installed Play gate, installer,
engine pin, saved deck or live gameplay path changes here. Complete real bootstrap,
bounded diagnostics, platform containment/orphan checks and lifecycle acceptance
before treating P1.4 or G1 as complete. CI is reviewed every third commit; a running
check is deferred to the next scheduled review without waiting.


### G1 stream-boundary progress

The shared [text framing foundation](../Mtg_Projects/mtg_play/protocol/text-framing.md)
now provides matching Java/C# length caps, strict UTF-8 and fragmented/truncated
stream checks. No bootstrap pipes or loopback service use it yet. JSON envelopes,
authentication, cancellation/deadlines, acknowledgements and the actual dummy
exchange are still required; P1.4/G1 remain open.


The subsequent strict JSON envelope increment adds the shared header schema,
duplicate-key/depth/Unicode checks and an explicit header-only type vocabulary.
See the [protocol guide](../Mtg_Projects/mtg_play/protocol/README.md#strict-json-envelope-foundation--g1-remains-open).
Bodies, peer authentication, live command safety and dummy exchange remain pending;
this does not mark G1 complete or begin the XMage gateway port.


The [first command-body slice](../Mtg_Projects/mtg_play/protocol/command-boundary.md)
adds perform/ack/viewer-shutdown validation and opaque current-decision comparison.
It does not execute actions, authenticate a viewer, wire the launch owner or prove
shutdown. The dummy exchange and P1.4/G1 gates remain pending.


The [viewer-authentication primitive](../Mtg_Projects/mtg_play/protocol/viewer-authentication.md)
now specifies a separate per-seat key and role/nonce/session/pin-bound hello
proof, with single-use Java/C# verifiers. Credential generation/delivery,
challenge exchange, verified readiness and owner lifeline remain unimplemented.
No process lifecycle transition uses proof success yet.


The [owned dummy exchange](../Mtg_Projects/mtg_play/protocol/dummy-exchange.md)
now proves private test bootstrap, actual loopback Java↔Unity EditMode messages,
wrong-key exclusion and owner-EOF listener cleanup locally. This fixture starts
no descendants and is separate from LaunchOwner. Product bootstrap/containment,
packaged client integration and CI evidence remain open.


The [receive-body follow-up](../Mtg_Projects/mtg_play/protocol/receive-boundary.md)
now validates generated existing DTO shapes and authenticated viewer/session,
revision and fixture mode before dummy client deserialization. It does not wire
product launch ownership or prove real engine visibility. G1 remains open.


### Client frame-read deadline follow-up

An [owned C# loopback reader](../Mtg_Projects/mtg_play/protocol/frame-read-deadlines.md)
now stops partial-frame waits using a total monotonic deadline/cancellation check,
closes its socket on failure and permits explicit owner disposal to unblock a
worker. The authenticated Java dummy proves timeout followed by owner-EOF child
cleanup. This remains separate from LaunchOwner; product bootstrap, complete
session/handshake deadlines, Java-side parity and containment remain pending.


### Java frame-read parity follow-up

The [owned frame reader](../Mtg_Projects/mtg_play/protocol/frame-read-deadlines.md)
now also bounds Java authentication/command frames with a monotonic total budget.
Its owner lifeline closes through the reader rather than bypassing ownership.
An authenticated partial-client-frame scenario verifies Java timeout and child
exit; 16 Java socket cases and 118 focused EditMode checks pass locally. This
still does not connect LaunchOwner, bound writes or prove product containment.


### Client write deadline follow-up

The C# socket owner now provides [bounded writes](../Mtg_Projects/mtg_play/protocol/frame-write-deadlines.md)
and closes after partial/uncertain failure rather than retrying. The authenticated
fixture uses it for normal outbound TCP frames; 130 focused EditMode checks pass.
Product orchestration must still couple failure with command admission, inbox
cancellation and process cleanup. This does not connect LaunchOwner or implement
Java outbound deadlines.


### Java write deadline follow-up

The Java [socket writer](../Mtg_Projects/mtg_play/protocol/frame-write-deadlines.md)
now closes stalled output via an owner-scoped, canceled-on-completion watchdog.
Tests cover cancellation/interruption, stale watcher safety and watchdog-thread
cleanup. The eighth authenticated process case proves timeout against a
non-reading client; 131 focused EditMode checks and Java protocol preflight pass.
This still does not connect LaunchOwner or implement product stop/admission
coordination, durable reconciliation or containment.


### First client session owner follow-up

The [C# client channel](../Mtg_Projects/mtg_play/protocol/client-session-channel.md)
now couples perform admission, pending receipts, bounded receive data and socket
closure under one owner. Cancellation releases an active read, and matching
shutdown preserves final packets to drain. Two new authenticated fixture scenarios
pass within 151 focused EditMode checks. This starts no processes and does not yet
connect LaunchOwner, join product workers or prove private renderer handoff.

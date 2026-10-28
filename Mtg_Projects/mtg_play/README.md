# XMage connection proof

Standalone feasibility experiment for Python → Java bridge → local XMage server →
real server callback → disconnection and normal JVM shutdown. This does not enable
Play in Manaforge or implement deck loading, game actions, or rendering.

## Run on Windows

From the repository root:

```powershell
python Mtg_Projects/mtg_play/connection_proof.py
```

Requires Python 3.11+ and defaults to these existing installations:

- Bundle: `Mtg_Projects/mtg_play/mage-full_1.4.62-dev_2026-10-03_20-47`
- Compiler: `C:\Program Files\Java\jdk-23\bin\javac.exe`
- Runtime: the bundle's `java/jre1.8.0_201/bin/java.exe`

Override locations if needed:

```powershell
python Mtg_Projects/mtg_play/connection_proof.py --xmage-root "D:\XMage\mage-full_1.4.62-dev_2026-10-03_20-47" --jdk-path "C:\Program Files\Java\jdk-23"
```

The bundle argument is the directory containing **both** `xmage/` and `java/`.
`--port 17171` optionally selects a primary port; otherwise an available port is
chosen. An occupied port causes a failure without connecting to its occupant.
No toolchain downloads or installations occur.

Success prints `"success": true` and exits 0. Failure exits nonzero and identifies
the relevant log or missing artifact. Startup allows 120 seconds; connection,
status, and callback receipt share a 30-second deadline. Each process has 10 seconds
to stop normally before the harness kills and reaps that specific owned process.
A forced shutdown makes the proof fail.

## What runs

1. Validate SHA-256 hashes in `artifacts.json`: all 86 server dependency/plugin
   JARs, the Java executable, and the original server configuration. Reject changed
   artifacts rather than silently updating the engine pin.
2. Create a unique ignored `.runtime/<run>/` workspace. Copy configuration and
   server messages; hard-link read-only JARs where possible, copying otherwise.
   Configure a loopback server with anonymous local login. All engine-generated
   databases, extensions, logs, and bridge output stay in that workspace. H2's
   auxiliary database listener is also explicitly bound to `127.0.0.1`.
3. Compile the two small Java hosts using `javac --release 8`, against the server
   JARs. No Maven build, engine changes, or desktop-client JAR is needed.
4. Run `ManaforgeServerHost` with the bundled JVM. Wait for the server's own
   listening announcement, not merely an open TCP port.
5. Run `ManaforgeBridge` headlessly with a temporary username. It implements
   `MageClient` and reuses `SessionImpl`; XMage internally uses `SwingWorker`, but
   no `MageFrame` or desktop UI is created.
6. Request the main room and available game types, then join its local lobby chat.
   Require an actual `ClientCallback`, independently of connection notifications.
7. Disconnect the session, acknowledge shutdown, and request a normal server JVM
   exit over stdin. EOF also shuts down either host if its parent disappears.

Each run retains `compile.log`, `server.log`, `bridge.log`, `events.jsonl`, and
`result.json`, including process IDs, exit codes, forced-cleanup flags, callback
method/message ID, and queried engine version. The runner never kills by process
name or port. The original download is preserved; generated files and downloads
are ignored by Git. Workspaces are retained for diagnosis and are not auto-deleted.

## Experimental bridge protocol

UTF-8 newline-delimited JSON, protocol version 1. This is a connection experiment,
not the future Manaforge game protocol. Commands require string `request_id` and
one of `connect`, `status`, or `shutdown`:

```json
{"protocol":1,"request_id":"connect-1","command":"connect","port":17171,"username":"mf_test"}
{"protocol":1,"request_id":"status-1","command":"status"}
{"protocol":1,"request_id":"shutdown-1","command":"shutdown"}
```

Responses include `protocol`, `event`, and the originating `request_id` for command
completion/errors. Asynchronous events omit request IDs. `callback` events contain
`method` and integer `message_id`; arbitrary engine payloads are deliberately not
serialized. `transport_connected` and `connection` never count as callbacks.
`status` includes `connected`, `engine_version`, `game_types`, and `room_id`.
`shutdown` must confirm `connected: false`. Engine diagnostics go to stderr;
bridge stdout is reserved for protocol JSON.

## Verification and limits

Run the isolated tests with an interpreter that already has pytest installed:

```powershell
Mtg_Projects/mtg_proxy/venv/Scripts/python.exe -m pytest -q Mtg_Projects/mtg_play/tests
python -m ruff check --isolated --select E4,E7,E9,F Mtg_Projects/mtg_play/connection_proof.py Mtg_Projects/mtg_play/tests/test_connection_proof.py
python -m ruff format --isolated --check Mtg_Projects/mtg_play/connection_proof.py Mtg_Projects/mtg_play/tests/test_connection_proof.py
```

Controlled subprocess tests cover invalid protocol, request correlation, genuine
callback versus connection notification, callback timeout, unexpected exit, engine
errors, normal/forced cleanup, unrelated-process preservation, artifact mismatch,
missing tools, occupied ports, startup timeout, and original-config preservation.

Static inspection of the downloaded JAR interfaces confirmed `MageClient`,
`SessionImpl`, and `ClientCallback`; JDK 23 successfully compiles their Java 8
bridge. The source reference is upstream tag
[`xmage_1.4.62V1`](https://github.com/magefree/mage/tree/xmage_1.4.62V1), with binary
hashes providing the actual compatibility pin.

Verified October 28, 2026: 22 focused tests pass, Ruff lint/format checks pass,
and two consecutive runs of the final harness received `CHATMESSAGE` callbacks
and queried engine `1.4.62-V1` with 17 game types. Both runs confirmed
disconnection and normal exit code 0 for both JVMs, without forced cleanup.
The final run's three observed server listeners (primary, secondary, and H2)
were all bound to `127.0.0.1`. Missing-runtime and occupied-port CLI checks also
failed as intended without disturbing the occupied listener.

This proves headless transport reuse. It does **not**
yet prove deck conversion, game creation, legal-action coverage, game-state
translation, dynamic characteristics, or hidden-information correctness. Those are
the next feasibility milestones.

XMage's bundled license is MIT. No XMage source is copied here; distribution still
requires preserving applicable engine/dependency notices and a separate packaging
review. Forge remains untouched and is not a dependency of this experiment.

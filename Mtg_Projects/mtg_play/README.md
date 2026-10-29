# XMage integration and connection proof

For the current public gameplay API, acceptance scenarios, capabilities, and
remaining verification gate, read [ADAPTER.md](ADAPTER.md). The connection and
Milestone A sections below document the historical experiment; current gameplay
consumers must use the public adapter.

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


## Gameplay feasibility (adapter epic, historical Milestone A)

The current public adapter and capability status are documented in [ADAPTER.md](ADAPTER.md).
The following describes the original feasibility milestone.

Run the same pinned, isolated engine with two independent human sessions:

```powershell
python Mtg_Projects/mtg_play/gameplay_proof.py
```

The CLI accepts the same `--xmage-root` and `--jdk-path` overrides. It reuses
`run_proof` for artifact verification, compilation, loopback listeners, process
ownership, deadlines, diagnostics, and shutdown. No download or installation
changes occur. The original connection-only CLI remains available.

The scenario creates a **Two Player Duel** table using the engine's
**Constructed - Freeform Unlimited** validator. Each fixture deck contains 30
M10/248 Forests and 30 SOM/174 Memnites. These deliberately simple, engine-supported
fixture decks are not yet Manaforge `DeckDocument` conversion. XMage shuffles and
deals them normally; the harness never fixes opening hands or implements rules.

Acceptance requires both sessions to join the same game, receive seven distinct
opening objects and mulligan prompts, keep their hands, submit engine-provided
playable objects, observe a Forest on the battlefield, observe Memnite on the
stack and then on the battlefield, reject a replayed decision, and receive
`GAME_OVER` for both seats after an explicit concession. A submission acknowledgement
alone never establishes a land play, cast, resolution, or game completion.
The scenario deadline is 90 seconds after starting the match. Unexpected prompts
fail explicitly. Choosing an offered starting player and ability, keeping hands,
passing priority, and conceding are scripted **harness** decisions, not adapter
automation or opponent strategy.

### Confirmed binary API mappings

Inspected using JDK `javap` against the SHA-256-pinned server JARs; upstream
[`CallbackClientImpl`](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage.Client/src/main/java/mage/client/remote/CallbackClientImpl.java)
and [`Deck`](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage/src/main/java/mage/cards/decks/Deck.java)
provide source context. The pinned binaries remain the compatibility authority.

| Operation | Actual engine interface |
|---|---|
| Create table | `SessionImpl.createTable(roomId, MatchOptions)` |
| Join seat with deck | `SessionImpl.joinTable(..., PlayerType.HUMAN, ..., DeckCardLists, ...)` |
| Start match | `SessionImpl.startMatch(roomId, tableId)` |
| Enter game | `START_GAME` contains `TableClientMessage`; then `joinGame(gameId)` |
| Authoritative player view | `GAME_INIT` carries `GameView`; gameplay messages carry `GameClientMessage.getGameView()` |
| Mulligan | `GAME_ASK`, answered with `sendPlayerBoolean` |
| Priority/object selection | `GAME_SELECT`, answered with `sendPlayerUUID` or `sendPlayerBoolean(false)` |
| Starting player | `GAME_TARGET` with permitted player UUIDs |
| Cast/ability selection | `GAME_CHOOSE_ABILITY` carries `AbilityPickerView`; answer with `sendPlayerUUID` |
| Concession | `sendPlayerAction(PlayerAction.CONCEDE, gameId, null)` |

Important observed pitfalls: `DeckCardInfo` constructor order is **name, number,
set, quantity**. Its name does not establish Oracle identity: `Deck.load` resolves
set and number. An unknown deck-validator label can create a table whose later
join fails with a server-side null-pointer error; use the exact configured label.
Neither finding justifies inventing a permanent deck-resolution contract yet.

### Experimental wire extension and privacy

This is still experimental bridge protocol **1**, not a stable public game API.
New operations: `create_game`, `join_table`, `start_game`, `respond`, `concede`.
`respond` requires the current `game_id`, `decision_id`, response `kind`, and
`value`. Responses are consumed before the remote call, preventing replay and
avoiding overwriting a newer callback's pending decision. Invalid response kinds
leave the decision available. Duplicate/older decision callbacks are ignored;
complete view updates advance by callback message ID. Failed submissions require
explicit recovery; they are never silently retried.

Gameplay events include `game_started`, `game_state`, `decision`, `response_sent`,
and `game_over`. Per-session state includes only that player's engine-provided
hand, public battlefield/stack information and player counts. Face-down or
engine-hidden cards omit names and characteristics. No arbitrary Java payload
is serialized. Protocol transcripts retain only event/routing metadata, omitting
hands, prompts, targets, rules, and other gameplay data. JVM logs remain local
engine diagnostics and must not be distributed as visibility-safe public events.

### Capability status and remaining epic work

**At Milestone A:** two-player fixture-deck gameplay was demonstrated with
the pinned engine. A game ending by concession is verified; representative combat
and a game ending through damage are not yet acceptance scenarios.

At that milestone the remaining work in Stories 2?12 included: a stable
Manaforge-owned API, Core deck/Oracle and selected-printing resolution, object
identity across zone changes, comprehensive state/dynamic characteristics,
validated legal-action and decision contracts, exhaustive visibility scenarios,
Commander and actual 2/3/4/5-seat verification, interruption/recovery semantics,
and integration acceptance exclusively through the public adapter. Engine IDs and
callback names here are private experimental transport details; future consumers
must not depend on them. No Commander or multiplayer capability is claimed from
plugin presence alone.

`view_rules` is engine view text; it is **not** a guarantee of complete current
abilities or authoritative dynamic Oracle text. Unsupported fields are omitted in
this experiment, not filled with printed data. Amount/mana/general-choice interfaces have binary API evidence but no live
scenario coverage or response implementation yet.
Unsupported decision families emit `UNSUPPORTED_DECISION` and fail the harness.
The current protocol is unsuitable as a production visibility or authorization
boundary until those later stories pass.

Ordinary adapter tests run in the existing Windows test job. The existing CI workflow now prepares explicitly SHA-256-pinned engine/runtime
archives in an isolated directory and runs the public adapter acceptance suite.
See ADAPTER.md for the current verification process.
No test-suite result should be inferred from the live harness result.


Verified October 28, 2026: final gameplay scenario
`.runtime/20261028-183731-050afcd6/result.json` reported both player starts, both
opening hands and mulligan prompts, independent opening-object identities, nine
submitted decisions, a land on the battlefield, a spell on the stack and then
resolved, stale-response rejection, and game-over callbacks for both seats.
All three owned JVMs exited 0 without forced cleanup. The original connection
harness also passed in `.runtime/20261028-183837-e3826419/result.json`, with both
JVMs exiting 0 normally. Ruff checks passed. The two new privacy regression tests
were added to CI but were not executed locally; CI has not run for this unpushed
branch. These results establish Milestone A, not completion of the epic.

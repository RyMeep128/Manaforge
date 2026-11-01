# Live Unity / Java / XMage integration

Owner priority: move into live integration while retaining the fallback. Formal
G0/G1 acceptance remains open; this direction does not certify those gates.
Start with human versus XMage AI, keeping seat count independent of controller
and future multiplayer layouts. Automatic mana work remains parked.

## First real Java-owned opening (0.5.128)

ManaforgeLiveOpening now creates an actual pinned-XMage freeform match through
the existing ManaforgeBridge in the same Java process. A bounded internal event
sink replaces JSON/stdout round trips for this diagnostic only. The default
bridge CLI is preserved; its connect/status/shutdown path is also exercised.
No engine source fork, rules reimplementation or Python gameplay session is used.

The public fixture contains 30 M10/248 Forest and 30 SOM/174 Memnite for each of
two seats, one human and one engine_ai. Java connects, checks the engine version,
creates the table, joins the AI through XMage's table-owner API, joins the human,
and starts the match. The diagnostic chooses only engine-offered pregame options
and player target IDs, stops at a real seven-card hand plus pending decision,
then disconnects. Its tiny pregame policy is diagnostic code, not product passing
or strategic automation. Unknown prompts fail; it never auto-plays a normal game.
The queue, pregame response count and wall-clock runtime are bounded. Parent EOF
requests cancellation and the parent retains the subprocess handle for timeout
cleanup. This is direct-root ownership, not production OS containment.

Run from the repository root:

```powershell
python tools/check_play_live_opening.py
```

Use --xmage-root and --jdk-path for alternate installed paths. Hash validation,
workspace preparation, compile and server lifecycle reuse connection_proof.
Python coordinates the isolated server and diagnostic processes; all match
creation and pregame response commands execute in Java. An existing idle proof
client performs only connection/status checks, not match actions.

The local focused live proof passed after correcting the diagnostic username
length and adding the engine's pregame player-target decision. It confirmed an
actual opening hand and pending decision, then normal cleanup of the diagnostic,
reference client and XMage server. No full application suite ran. Dedicated
Play live Java opening CI prepares the hash-pinned runtime and runs the same
proof, uploading only Artifacts/LiveOpening/report.json. CI is next checked at
.129; no CI success is claimed for this increment yet.

The report contains fixed evidence booleans, opening-hand count and source commit,
without cards, engine UUIDs, player names or prompt contents. Runtime bridge logs
remain local diagnostics for this public fixture and are not uploaded. Never use
this harness as a user-deck exporter or send its raw engine callback JSON to Unity.

## Remaining live vertical slice

1. Translate the live human view and outstanding decision into the existing
   viewer-filtered public snapshot/choice contracts. Preserve opaque incarnations,
   exact identities, decision/revision binding and unknown/unsupported fields.
2. Route explicit Unity choices through the authenticated Java session boundary
   to the current XMage decision. Python must stay outside per-action exchange.
3. Mount that live source in the existing Unity session scene, then stop for owner
   UI verification of the real opening hand, keep/mulligan and priority controls.
4. Extend to land, creature, mana, stack, combat and a natural authoritative result.
   Compare meaningful behavior against the existing Python adapter as reference.
5. Integrate saved-deck launch manifests, complete readiness/descendant cleanup,
   privacy acceptance and packaged lifecycle before enabling installed Play.

Unity is not connected by this first increment. No full match, public protocol
parity, AI UX, hidden-information boundary or live Unity gameplay is claimed.
Existing fixture UI reviews remain pending; this increment changes no Unity UI.


## Opening public projection (0.5.129)

ManaforgeOpeningProjection now converts the real human opening view and its
GAME_ASK decision to the generated PlayContracts DTO model. The live Java proof
validates its resulting envelope with the same ReceiveMessages/schema used by
the Unity channel, in non-synthetic protocol mode. The diagnostic still reports
public_fixture_only because its decks are public fixtures; it does not relabel a
live engine state as a fake engine snapshot.

This read-only opening scope requires the bound engine viewer, matching state/
decision cycle, a numeric engine decision ID, empty board/stack/exile/combat and
an engine boolean decision. Unsupported states fail with a fixed error. It does
not omit a live occupied zone and pretend the rest is complete. Player seats are
mapped without a fixed maximum. Opponents expose counts/public life only; the
projection reads only the bound local hand. Concealed/face-down cards have no
characteristics or printing identities. Engine IDs/names and unknown raw fields
are not copied. UUIDs inside permitted display text are redacted.

Selected-printing bindings come from trusted host mappings by set/collector pair;
there is no name fallback or invented printing. Unknown bindings remain null.
The public fixture supplies its existing selected-forest/selected-memnite IDs.
Metadata requiring the server's full physical-incarnation information remains
unfinished. Object/choice IDs are fresh per projection, with incarnation support
explicitly unavailable; this opening-only helper must not be used for animated
live board transitions. It returns fresh DTO JSON without retaining caller-mutated
output or shared binding objects. actions_complete is false, actions are empty,
and unavailable characteristics and session fields are marked unsupported.

Boolean options reflect the engine's yes/no prompt, with fresh public tokens.
No Unity command endpoint or token-to-native submission map is connected yet;
these tokens must not be accepted by an executable gateway until that mapping
and current revision/decision validation are implemented. No raw engine view
is sent to Unity or persisted as a snapshot artifact.

Validation passed: 30 isolated Java checks (shared receive shape, concealed/
face-down cards, opponent canaries, raw IDs, unknown printing, source/output
isolation, mismatched viewer/cycle, occupied zones, malformed numbers and
unsupported decisions); the Java protocol preflight; 28 focused process-runtime
checks; and the actual human/AI opening with its public snapshot schema check
and normal cleanup. No full application suite or Unity UI ran. CI now includes
the projection checks and reruns the live proof for protocol-runtime changes.

Scheduled CI check: [.127 protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41257622899),
[.127 preview](https://github.com/RyMeep128/Manaforge/actions/runs/41257622905) and
[.126 dependency fix](https://github.com/RyMeep128/Manaforge/actions/runs/41257263652)
passed. [.128 live opening](https://github.com/RyMeep128/Manaforge/actions/runs/41260532957)
and [.128 preview](https://github.com/RyMeep128/Manaforge/actions/runs/41260532996)
were still running and were deferred. Check the next increment at .132 without
waiting on unfinished work. No G0/G1 gate or full gameplay acceptance is implied.

Next: bind the engine boolean decision to authenticated public choice submission,
then mount the live source in Unity and request owner UI verification.


## One-shot opening choice binding (0.5.130)

The opening projection now retains a private mapping from its two public option
IDs to the native boolean decision. claimBoolean parses the existing command
schema and reuses WireMessages.checkBinding. It checks trusted host session/
viewer context, public revision/decision/option, engine viewer/game/decision and
cycle before producing a private respond command for the existing bridge.

The claim is synchronized and consumed before native IO, so two simultaneous
submissions or a retry after uncertain IO cannot create a second native command.
Rejected bad bindings do not consume a valid choice. Reprojection invalidates old
tokens before validation, including when the new state is unsupported; explicit
invalidation supports disconnect/shutdown. Public DTO/output mutation cannot
change the retained token/value mapping. Native IDs remain in the trusted adapter
only, never in the public snapshot.

The host-context arguments are trusted internal inputs, not authentication. This
helper must be called by the future authenticated session worker using its verified
viewer context and current engine state, never using caller-supplied identity or
current-state assertions. The existing GatewaySessionBoundary and submission ledger
still need wiring around enqueue, receipt/uncertainty handling and this native claim.
This increment creates no network listener or unauthenticated command endpoint.

The public diagnostic now chooses Yes through a complete public command envelope,
claims the corresponding native boolean, submits it to XMage, checks accepted
transport submission, rejects replay, and observes a newer engine decision/state.
The fixture's explicit answer is not product automation. Engine advancement is
recorded separately from transport acceptance; it is not a claim that every outcome
or complete match has been confirmed. The existing bridge checks game/decision
again immediately before native IO. Python performs no gameplay actions.

Local validation passed: 63 projection/privacy/binding checks, including both
boolean values, incorrect sessions/viewers/options/revisions/decisions, changed
native game/viewer/decision/cycle, reprojection, invalidation and simultaneous claims;
the Java protocol preflight (60 checks before the final concurrent/native-viewer
cases were added, with all 63 then rerun in isolation); and the real public-choice
submission/replay rejection/engine-advancement scenario with clean root shutdown.
No full application suite or Unity UI ran. CI remains scheduled for .132; no new
CI success is claimed. Owner visual review is not needed for this Java-only change.

Next: compose this binding with authenticated Java session admission and receipts,
then connect the live source to Unity's existing session/decision scene and stop
for owner UI verification. Manual engine actions, board/stack/combat normalization,
full parity, saved-deck runtime resolution and natural game completion remain open.


## Authenticated live opening admission (0.5.131)

ManaforgeOpeningSession composes the verified GatewayHandshake.ViewerContext,
existing GatewaySessionBoundary/SubmissionLedger, opening projection and a bounded
one-command native queue. Admission observes the public snapshot, reserves a
receipt, and claims/enqueues the matching private native response. Socket writes,
engine IO and waits occur only after admission returns, on the serialized owner
worker. It never calls back into the session boundary from its enqueue callback.
Native polling is owner-only; no raw command enters a client channel.

The public diagnostic ManaforgeOpeningLoopback now supplies a real Java client
on authenticated localhost sockets. Fresh viewer keys and client/server nonces
stay in memory. Existing challenge/proof verification precedes ViewerContext
creation, snapshot delivery and choice admission. The client validates the shared
receive shape, submits an explicit Yes command, gets submitted, retries that same
command ID and gets the cached receipt. Only one private native command is polled
and sent to XMage. Engine advancement remains a separate observation.

No confirmed receipt is fabricated. Because exact semantic reconciliation of this
opening answer is unfinished, disconnect leaves its unresolved receipt uncertain.
The diagnostic checks that state before final disposal. Disconnect/cancellation
invalidates choice tokens and clears queued work; socket/worker ownership and key
clearing are handled even on failure. This is serialized-worker coordination,
not production thread joining, persistence or XMage descendant containment.

The loopback client is a public fixture tool, not a production listener, launch
credential API or Unity UI. It does not authenticate an arbitrary external client
or accept user decks. The live adapter session worker is reusable; the next step
is replacing the diagnostic client with the existing Unity authenticated channel.
No public interface or installed Play feature has been enabled.

Local validation passed: the actual XMage authenticated opening choice, duplicate
receipt/one native submission, subsequent engine advancement and normal cleanup;
full focused Java protocol preflight including all 63 projection/binding checks;
and new engine-free real-socket tests for authenticated delivery, cached receipts,
disconnect uncertainty and cancellation before native submission. Cleanup-only
changes were recompiled and those socket tests passed again in isolation. No
full application suite or Unity build/UI ran. CI next check remains .132.

Sanitized live report version 2 adds authenticated_choice, duplicate_receipt_reused
and disconnect_uncertainty_retained. duplicate_native_submission_prevented replaces
the earlier choice_replay_rejected label: retrying the same command returns its
stored receipt rather than a rejection, while still preventing duplicate execution.
No credentials, native IDs, cards or prompts are included in uploaded evidence.

Next: attach Unity's existing session scene and decision panel to this live
opening source, then stop for owner visual/interaction review. Broader actions,
board translation, saved-deck resolution and natural match completion remain open.


## Packaged Unity live opening — owner review required (0.5.132)

The opt-in LiveOpeningScene now uses the existing ViewerSessionHost with
fixtureMode=false, ViewerCardSurface/CardView inspection and ViewerDecisionPanel.
A new -manaforgeLiveOpening route leaves default Play/preview/fixture routes intact.
No new renderer or deck model was introduced. All parsing/networking remains on
existing workers; scene code ticks presentation and counts sanitized evidence.

Run the packaged public-deck slice from the repository root:

```powershell
python tools/check_play_unity_live.py --interactive
```

Allow roughly a minute for pinned-engine validation, compilation and startup.
The player opens without Unity Editor. Inspect the seven-card human opening with
the Inspect buttons and read the engine's mulligan question. Choose Yes or No
within 60 seconds. After submission, the viewer clears and the spike closes.
Yes is an actual engine response, not a simulated UI response; No can keep the
opening hand where that is the offered mulligan question. This is not a playable
full match: land/spell/stack/combat and later decisions remain disconnected.

The headless form `python tools/check_play_unity_live.py` drives the actual mounted
Yes button for public-fixture acceptance and captures connected.png/choice.png
under a fresh Unity Artifacts/UnityLive-* directory. The local packaged proof passed:
real seven-card snapshot, challenge/proof authentication, native response, engine
advancement, submitted then uncertain receipts, renderer clearing and normal owned
root cleanup. The existing synthetic packaged decision fixture also passed against
the same new build. No full application suite ran. The player build succeeded.

Do not interpret uncertain as a confirmed result: advancement is not yet mapped
to full semantic reconciliation. The new live endpoint does not fabricate confirmed
or game-result packets. Scene cancellation clears stale opening cards at the end
of the supported slice. The renderer currently has no artwork bundle for this
fixture. Known review limitations include fallback art, raw engine font markup in
the question and default land P/T display; these are not polished UX acceptance.
The owner must review actual interaction before further UI work proceeds.

The gateway's diagnostic Unity mode receives a fresh viewer key in one private
bounded stdin frame, before its EOF lifeline starts. Only a nonsecret loopback
address marker is written to disk. Unity receives its bootstrap privately through
its separately owned stdin. No viewer keys, manifests or native IDs enter argv,
public reports or screenshot metadata. Bootstrap rejects malformed versions and
non-string/invalid keys; focused protocol checks include these cases. Parent owns
startup deadlines, cancellation and cleanup; blocking initial Java reads rely on
that owned-process deadline rather than claiming independent read cancellation.

ManaforgeUnityOpening reuses the existing auth/session/projection and hands native
IO to the serialized worker outside admission. The diagnostic accepts one opening
choice, emits submitted, waits for native transport acceptance and observed engine
advancement, emits conservative uncertainty, then waits for the owner lifeline.
It has finite accept/action/lifetime bounds. Saved-deck launch integration,
production listener lifecycle/containment and privacy acceptance remain pending.
The live report accurately leaves duplicate-test booleans false in Unity mode:
that run submits one choice, while the separate Java peer exercises duplicates.

The .132 scheduled CI check confirmed [.131 protocol](https://github.com/RyMeep128/Manaforge/actions/runs/41261559681)
and [.131 preview](https://github.com/RyMeep128/Manaforge/actions/runs/41261559702)
success, plus prior live-opening success. The [.131 live job](https://github.com/RyMeep128/Manaforge/actions/runs/41261559717)
was still running and was deferred. Older native-helper CI failed because its
compiler glob pulled in the new gateway/protocol consumers without their classpath.
Its source list is now explicitly the three original bridge/server/metadata files;
focused local validation passed 147 native object checks, 11 pinned API inspections
and bridge compilation. This fixes shared build infrastructure without enabling
or changing mana policy. New CI evidence remains pending; next check is .135.

Principal files: ManaforgeUnityOpening.java and the diagnostic Java entry point;
LiveOpeningScene.cs and FoundationTable routing; the additive surface inspection-ID
accessor; tools/check_play_unity_live.py; bootstrap checks and native compile scope.
Generated Unity build-setting/scene rewrites are excluded. The Python/Qt fallback
and the owner's unrelated working-tree edits remain intact. G0/G1 and full-game
acceptance are still open. Stop here for owner UI review.

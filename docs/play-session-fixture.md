# Authenticated packaged session fixture

Status: explicit diagnostic scene at 0.5.98-alpha.1. Automated packaged proof
passed; owner UI review is pending. Product launch, real XMage games, artwork
binding, decision controls, OS containment and G0/G1 acceptance remain open.

The opt-in `-manaforgeSessionFixture <output>` entry point receives its bootstrap
through inherited stdin, starts the real authenticated session host, and renders
its immutable viewer-filtered card projection through the shared card surface.
It creates no separate card renderer or deck model. The normal artwork gallery
and existing Qt Play path are unchanged.

The scene refuses any bootstrap that differs from the public synthetic fixture
identity, engine pin, key or unsupported artwork path. Its validated dynamic
loopback port is retained. A worker checks/consumes the input key, disposes the
original bootstrap, then reissues only the known public test key to the host.
This diagnostic-only reissue is not a production credential-delivery API and
cannot enable this fixture for ordinary user credentials.

The fixture Java gateway uses the fresh challenge handshake, then emits one
public card, one concealed object, a harmless repeated snapshot and ordered
fixture events. Diagnostic-only heartbeat events keep this review connection
alive for up to 30 minutes; they establish no production idle policy. The scene's
worker counts and disposes these explicit fixture notifications and refuses
unexpected message families. It submits no gameplay command or strategic choice.
The source is generated solely from committed public fixture corpora, never decks.

The public card is inspectable using the fixture button. Artwork and complete
rules are unavailable here; those placeholders are deliberate and are not a new
replacement for the existing artwork renderer. The concealed object has no name,
printing, rules or statistics in its view. The UI is a simple integration layout,
not an Arena-style battlefield acceptance build.

Owner EOF revokes the mailbox, clears the surface/inspection on Unity's UI thread,
awaits host and fixture-consumer retirement, removes the viewer surface, records
sanitized cleanup evidence and quits. The parent stops the owned Java root after
the player. No root exit is claimed as OS descendant containment or a game result.

## Reproduce and review

From the repository root, if rebuilding/preparing is necessary:

```powershell
./tools/unity-play.ps1 -Mode EditMode
./tools/unity-play.ps1 -Mode Build
```

Run the automatic graphics capture and cleanup proof:

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_unity_session.py
```

For the owner UI review, the prepared build is ready:

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_unity_session.py --interactive
```

Inspect the public card, confirm the concealed object reveals no identity, and
check that the connected status and fixture limitations are understandable. Close
the Unity window or press Ctrl+C in the launching terminal to finish. The runner
retains owned cleanup and never records human approval automatically. A new output
directory is created under Unity Artifacts for each run.

Local evidence: 350 EditMode checks including Java preflight passed; the Windows
build succeeded; the actual Java-process + packaged graphics player completed
authentication, ordered fixture consumption, scene mounting, inspection and owner
EOF cleanup with both roots exiting 0 and no forced termination. The runner checks
that the synthetic key/key field do not appear in player logs. Artifacts record
the managed assembly hash and source HEAD, not live credentials or proofs. Reports
made before commit retain that earlier source HEAD; no clean-source provenance
is inferred from the working-tree build.

Initial review artifacts:
`Mtg_Projects/mtg_play_unity/Artifacts/SessionFixtureProof-098/connected.png`,
`cleared.png`, and `report.json`. Connected and cleared captures were visually
inspected locally. The report explicitly leaves `human_ui_approved` false and
`descendant_containment_proven` false. No full application suite ran. Relevant CI
review is next at 0.5.99; no current CI success or UX acceptance is claimed.


## Packaged explicit decisions (0.5.122)

Status: packaged automated interaction and original read-only control passed
locally; licensed CI and owner visual acceptance remain pending. This is G1/P3.4
synthetic client integration, not real XMage, AI gameplay or a completed game.
Automatic mana work is parked and unchanged by this increment.

The existing ViewerDecisionPanel is now optionally mounted beside the shared
ViewerCardSurface in the authenticated packaged scene. It uses the existing
ViewerSessionHost, decision offers, dispatcher, tracker and channel. There is no
second renderer, command model, rules engine or direct UI socket write. The
original inspection-only scene remains the default.

Run the interactive review from the repository root (a current packaged player
and Java dummy preparation must already exist):

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_unity_session.py --decisions --interactive
```

The current local build and test-only Java classes are prepared. On another
checkout, run `python tools/check_play_java_protocol.py --dummy-output
Mtg_Projects/mtg_play_unity/Artifacts/JavaDummy` and
`./tools/unity-play.ps1 -Mode Build` first. The peer uses pinned Gson; it does not
start XMage or read user decks. No Unity Editor is needed to open the player.

Owner review:

1. Confirm the authenticated fixture title and public synthetic-data warning.
2. Inspect the public card; the other object must remain concealed.
3. Within 60 seconds, deliberately choose the public option in the right panel.
4. Verify the fixture reports completion, removes its choice controls and sends
   no further action automatically. Confirmation may advance between rendered
   frames; the ordered submitted/confirmed updates remain separately counted.
5. Close the window or press Ctrl+C in the launcher. Confirm both owned roots
   exit cleanly. No visual approval is recorded merely by running this command.

The 60-second read budget is a fixture limitation, not an accepted product
heartbeat/reconnection policy. Initial UI shows the public option plus native
fixture finish/cancel controls. No gameplay legality is inferred from labels.
Multiple decisions, numeric UX, art-sidecar mounting, actual human-vs-AI gameplay
and complete product launch remain follow-up work.

### Automated public-fixture proof

`python tools/check_play_unity_session.py --decisions` runs a deliberately
scripted PUBLIC diagnostic. After the initial screenshot it dispatches a UI
navigation-submit event to the actual mounted option button. The desktop/product
launch path never sets this fixture-only script switch, and the scene first
requires the existing known-public bootstrap gate. The helper constructs only
public test data and exposes no real-deck or credential input.

DummyGateway's separate decision-scene mode retains fresh authenticated
handshakes and GatewaySessionBoundary admission. It records a synthetic enqueue,
then sends distinct submitted/confirmed receipts and a fixture-only terminal
snapshot. A queued write is not accepted as proof of completion. The peer stays
owned until parent EOF; no engine outcome is claimed.

The scene's notification consumer now recognizes ACK/result updates only in this
explicit mode. It retains their ordering/counts, waits for the result to revoke
the displayed decision, and verifies all controls are gone. Owner loss disposes
the panel before the host/surface. The original read-only report schema stays
unchanged; decision mode adds strict ACK/result counts and panel-clear evidence.
No receipt or hidden card contents are copied into those reports.

Local evidence: Java protocol preflight passed; ten focused Python report checks
passed; the Windows Unity player built successfully. Packaged decision proof and
read-only control both passed, with two initial snapshot notifications, one event,
zero ACKs/results at readiness, then two ACKs and one synthetic result after the
explicit choice. The decision panel cleared, owner EOF cleared all CardViews, and
client/gateway both exited 0 without forced cleanup. Decision assembly SHA-256:
`f45f8b417f1fdd4910549203103c053d3b3e5325843c92787a8057d9ea5a69fd`.
The packaged proof is rerun after the implementation commit to record its exact
source revision in `Artifacts/SessionFixture-Decisions122/report.json`.

The licensed Unity workflow now runs this packaged decision scenario and uploads
only its public screenshots/report. The automatic desktop-preview workflow also
runs the ten report-contract tests. No licensed CI result is claimed for this
increment; routine status is next checked at 0.5.123. No full application suite
ran, and no owner visual approval, G0/G1 completion or real-engine integration is
inferred. Existing Qt Play, deck preview, artwork gallery and automatic-payment
production gate remain unchanged.

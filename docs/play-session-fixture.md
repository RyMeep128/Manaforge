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

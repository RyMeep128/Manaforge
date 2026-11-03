# Packaged Unity private-bootstrap proof

Status: headless Windows fixture proof at 0.5.94-alpha.1. Authenticated gateway
challenge exchange, real session mounting/private-view cleanup and OS containment
remain open. This does not close G0/G1 or demonstrate a Magic game.

The Foundation player has an explicit `-manaforgeBootstrapDiagnostic <output>`
mode. It bypasses the card gallery, creates no game/artwork provider, and accepts
only the committed public synthetic bootstrap context/key with no artwork path.
Ordinary gallery launch behavior is unchanged. All report files contain fixed
status codes and fixture markers, never viewer credentials or game state.

The diagnostic reads inherited stdin using the Windows private pipe primitive.
After validating the public fixture it reports receipt and watches the owner
lifeline. EOF is observed on a worker, then the scene calls Application.Quit on
Unity's main thread. Invalid input/context and startup timeout report fixed codes
and quit with status 1. Pending read/lifeline tasks are cancelled/observed and
owned resources are disposed during destruction. No gameplay outcome is inferred.

Reproduce with the installed licensed editor and Python environment:

```powershell
./tools/unity-play.ps1 -Mode Build
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_unity_bootstrap.py
```

The runner creates a fresh diagnostic output under Unity Artifacts. A dummy Python
gateway with no descendants supplies only lifecycle readiness for the fixture;
it is not XMage and performs no authentication. LaunchOwner starts the actual
packaged Unity player headlessly and delivers public synthetic bootstrap bytes
over stdin. It never marks the client ready merely because delivery succeeded.

Four cases passed locally:

| Case | Evidence |
| --- | --- |
| Valid frame then owner EOF | Receipt, OWNER_EOF report, player exit 0 |
| Malformed framed payload | BOOTSTRAP_PIPE_PAYLOAD, player exit 1 |
| No frame with owner still alive | BOOTSTRAP_PIPE_TIMEOUT, player exit 1 |
| Non-fixture viewer context | BOOTSTRAP_DIAGNOSTIC_CONTEXT, player exit 1 |

Every case reaped its two owned roots without forced termination. Reports also
record executable and Manaforge.Play.dll SHA-256 hashes, source HEAD/dirty state,
and `descendant_containment_proven: false`. The managed assembly hash identifies
code that the Unity executable wrapper alone cannot identify. Reports made before
commit explicitly retain their earlier HEAD/dirty provenance. The runner checks
player logs for the synthetic key/key field to guard accidental credential logging.

Other local evidence: Windows player build succeeded and 338 Unity EditMode
checks passed, including Java protocol preflight and public-fixture-only gating.
No full application suite ran. The diagnostic uses -nographics: it provides no
graphics benchmark, visual acceptance or new licensed CI evidence. The installed
editor remains the existing pinned version, not a new approved LTS decision.

Initial sanitized evidence is under
`Mtg_Projects/mtg_play_unity/Artifacts/BootstrapPlayerProof-094/report.json`.
The matching managed assembly hash is
`92ac0ac8bfa5e8a4d7c366d0225816bac50eb6bed47127a4d476618e362929d2`.
Artifacts and built binaries stay ignored. No public UI changed and no new owner
visual review is needed. CI review remains every third commit, next at 0.5.96.

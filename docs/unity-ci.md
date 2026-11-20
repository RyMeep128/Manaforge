# Local Unity validation

Unity validation runs directly on the owner's Windows machine. GitHub Actions
continues to run Python/Core, Java/XMage, protocol, and other non-Unity suites.
The former Unity Actions workflow and license activation helpers are retired.
No GitHub runner registration or Unity Actions secrets are needed.

## Run

Close the Unity editor for this project, sign in to Unity Hub, and activate the
editor pinned in `Mtg_Projects/mtg_play_unity/ProjectSettings/ProjectVersion.txt`.
Install Python 3.12 or 3.13, JDK 23.0.2+7, and Node.js 22 or newer with npm. Then run from
PowerShell 7 in the repository root:

```powershell
./tools/validate_unity_local.ps1
```

The defaults use the existing Python 3.13 and JDK installations on the owner's
PC. Override them with `-Python <python.exe> -Jdk <jdk-directory>` if needed.
`MANAFORGE_UNITY_EDITOR` can select another installation of the pinned editor.
The script installs Python dependencies into an isolated environment for this
run and uses `npm ci` for the repository's multiplayer relay. It downloads the
hash-pinned engine into that run's directory. It does not export Unity licenses
or install a persistent runner service.

The Java fixture peer is compiled for Unity exchange tests without running the
standalone Java protocol suite locally. All Unity validation stages from the
former Unity workflow are retained: EditMode,
graphics-enabled PlayMode, Windows build, player smoke, theme captures, payment
modes, pile and other choices, public artwork preview, a normal shuffled human
versus AI match, concession, authenticated decision UI, and multiplayer in
freeform and Commander. A failed stage stops the run and records failure.
PlayMode graphics checks require all tests to execute without skips.

Logs and the stage report are under `Artifacts/UnityLocal/<run-id>/`.
Unity test XML and screenshots remain under
`Mtg_Projects/mtg_play_unity/Artifacts/`. A modified workspace can be validated,
but release packaging requires a fresh successful run on a clean committed
revision. Source changes during a run make its evidence ineligible for release.
Do not reuse a validation report after modifying the player or its source.

A standalone rebuild remains available:

```powershell
./tools/unity-play.ps1 -Mode Build
```

## Windows packaging and release evidence

A successful clean run produces `unity-local-<commit>.zip` and its SHA256 in the
run directory. The archive contains the player, selected test/visual evidence,
and a manifest with the tested commit, completed stages, and file checksums.
It is owner-provided local evidence, not a hosted Unity test result.

For hosted Windows packaging, make that ZIP available at a downloadable HTTPS
URL using storage you control, then manually dispatch the **Tests** workflow on
the same source revision with `build_windows`, `unity_player_url`, and
`unity_player_sha256`. Uploading evidence does not authorize creating a tag or
release. The workflow does not upload local files automatically.

Packaging verifies the archive SHA256, clean source revision, all required local
stages, payload checksums, and safe extraction paths before importing the player.
Missing or mismatched evidence fails packaging; there is no hosted Unity build
fallback. Python application startup, Java bridge, installer, and non-Unity
checks remain hosted. Unity gameplay checks run locally against the standalone
player; the final combined installer does not receive a hosted Unity match run.
Publication additionally requires the existing exact-revision protocol, native
payment, live-opening, and broad XMage engine checks, plus the verified local
Unity receipt. Successful compilation alone never establishes gameplay acceptance.

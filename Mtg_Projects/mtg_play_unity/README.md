# Manaforge Play Unity foundation

Current scope: P0.1/P0.2 feasibility increment only. Gameplay and multiplayer
are future design targets, not implementation scope for this increment. **Fixture rendering only**, without a game engine,
deck import, card artwork, gameplay actions or AI integration. First playable
target is one human versus XMage AI; design for up to five players. The shared
protocol must not hardcode a five-seat maximum. Existing Qt/Python remains intact.

## Pinned toolchain

- Installed/editor pin: `6000.6.7f1`, revision `b22767f04f04`.
- URP `17.6.0`; test framework `1.8.0`. Track manifest and resolved package lock.
- Official Newtonsoft JSON package `3.2.2` supports generated fixture DTOs. See
  the [protocol guide](../mtg_play/protocol/README.md); these do not connect the scene to gameplay.
- Windows x64 development player, Mono, .NET Standard, text serialization and
  visible tracked `.meta` files. No XMage, Python or database calls in Unity.
- Project starts from the editor's official blank URP template. `FoundationBuild`
  creates a deterministic saved scene, shared fixture material and build settings.
- **LTS decision remains open:** the installed 6.6 editor is a current/update
  release, not LTS. Use it for this reversible feasibility spike; do not claim
  the roadmap's approved LTS selection is complete.

## Reproduce on the licensed Windows host

Close this project in interactive Unity before running batch commands. Other
Unity projects can remain open. From the repository root in PowerShell 7:

```powershell
./tools/unity-play.ps1 -Mode Prepare
./tools/unity-play.ps1 -Mode EditMode
./tools/unity-play.ps1 -Mode PlayMode
./tools/unity-play.ps1 -Mode Build
./tools/unity-play.ps1 -Mode Smoke
```

Override `MANAFORGE_UNITY_EDITOR` or pass `-EditorPath` for a different installation
path of the exact pinned editor. The script rejects mismatched versions, nonzero
exits, missing/failed test results, empty test runs and stale smoke evidence. It
times out and terminates only its owned process tree. Generated logs, tests,
screenshots and binaries stay in ignored `Artifacts/` and `Builds/`.

The player is `Builds/Windows/ManaforgePlay.exe`; keep its full containing directory.
Running it without smoke arguments leaves a fixture window open for manual review.
Smoke mode renders 20 placeholder quads in URP at 1280×720, captures a camera render-target PNG (without the OnGUI labels) and
records device/version/count/resolution. It must use a graphics device, not
`-nographics`. This is neither an artwork benchmark nor an Arena-quality UX claim.

## CI and licensing

`Unity Play feasibility` is a manual-only workflow on an owner-controlled Windows
runner labelled `manaforge-unity`. The host needs PowerShell 7, the pinned editor,
Windows build support, an independently valid license and a usable graphics
session. Do not assume a license activated for one interactive account works for
a service account. A logged-in desktop runner may be necessary for screenshot
capture; establish this before claiming CI viability.

No Unity serial, password, activation file or account token is stored in the repo,
workflow or uploaded artifacts. This workflow does not activate or return licenses.
Use Unity's supported activation for the actual runner account; installation on
the owner's desktop does not prove CI licensing. Do not schedule untrusted PR
code on this persistent host. Registration and a successful workflow run remain
required before P0.2 is complete. Logs remain local because licensing/runtime logs
can contain host/account information; CI uploads synthetic screenshots, reports,
source revision and player output only.

## Local evidence — October 30, 2026

On the owner-licensed host: Prepare/import and Windows build exited 0; six focused
EditMode tests and one PlayMode scene test passed. The packaged smoke passed on
AMD Radeon RX 6600 at 1280×720 with 20 fixture cards and 102,340 colored card
pixels. The camera PNG was visually inspected. Reports are in ignored Artifacts;
these are local results, not CI evidence or integrated-GPU benchmarks.

No Unity-specific connector was exposed in this session. Automation uses the
official installed editor command-line interface and Unity Test Framework.

The protocol-consumer increment passed eight EditMode tests: six layout checks
plus two checks covering 14 positive and 12 negative shared fixtures.

## Remaining acceptance

G0 remains open: approved LTS choice, executed CI/license evidence, real-artwork
20/70/200-object interactions, packaged timing/memory/integrated-GPU measurements
and distribution review. G1/shared protocol and human-versus-AI integration also
remain open. No installer or installed Play gate changes are made here.

Owner checks: launch the whole player folder, verify two rows of cards and readable
labels, resize the window and close it. This does not exercise real gameplay.

References: [roadmap](../../docs/play-unity-java-roadmap.md),
[editor release](https://unity.com/releases/editor/whats-new/6000.6.7f1),
[official command-line reference](https://docs.unity.com/en-us/engine/6000.6/manual/unity-editor/command-line-arguments/editor).

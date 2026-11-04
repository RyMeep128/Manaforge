# Manaforge Play — Unity

Unity is the gameplay UI, with Java/XMage providing the rules engine. The desktop
launcher prepares saved decks, artwork, and owned process lifetime. See the
[current Play guide](../../docs/play.md) for launch behavior and acceptance limits.

## Build and validation

The editor pin is recorded in [ProjectVersion.txt](ProjectSettings/ProjectVersion.txt);
package pins are in [manifest.json](Packages/manifest.json) and
[packages-lock.json](Packages/packages-lock.json). Use the exact pinned editor
with Windows build support and a valid license for the executing account.
`MANAFORGE_UNITY_EDITOR` can override its installation path.

From the repository root, build the player with:

```powershell
./tools/unity-play.ps1 -Mode Build
```

The player is `Builds/Windows/ManaforgePlay.exe`; retain its entire containing
folder. Generated logs and reports belong in ignored `Artifacts/` and `Builds/`.
Test suites run through GitHub Actions. The manual
[Unity workflow](../../.github/workflows/unity-play.yml) uses the owner-controlled
Windows runner labelled `manaforge-unity`, with a licensed editor and graphics
session. Local installation does not establish runner readiness or CI success.

[Shared protocol](../mtg_play/protocol/README.md),
[renderer and session references](../../docs/README.md), and the
[archived foundation journal](../../docs/archive/unity-foundation-history.md)
provide implementation detail. Historical test totals and screenshots are evidence
for their original revisions only.

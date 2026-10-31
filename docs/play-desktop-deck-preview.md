# Desktop-to-Unity deck preview

Implementation: 0.5.117-alpha.1, codex/play-desktop-deck-preview.
Status: implemented and Windows player built locally; CI and owner UI acceptance
are pending. This is P3.5 preview integration, not P4.1 or a live game.
Owner requirements: [launch story](play-desktop-deck-preview-story.md).

## Open it without Unity Editor or a terminal

1. Close any existing development Manaforge window so the new Python code loads.
2. Double-click `Launch Manaforge.cmd` in the repository root.
3. Open Play, choose Offline Play, select Freeform or Commander, then Continue to Lobby.
4. Select your saved deck in the human seat. The AI deck is optional for preview.
5. Click **Start Play Preview**. The packaged player opens in a separate window.
6. Confirm **Deck Preview — Not a Live Game**, your deck name and format. Hover,
   click or keyboard-focus compact cards to inspect them. Quantities and deck
   sections are labels, not simulated game zones or drawn cards.
7. Close the Unity window or use **Close Preview / Cancel** in Manaforge. Confirm
   the same deck selections remain and the desktop is still responsive.
8. Select another deck and repeat. Include a deck with missing cached artwork,
   a full-art printing and Commander cards. Missing artwork must be explicit.

The development launcher uses the existing local Play gate. Frozen/installed
Play remains gated; no installer or general release activation changed.

The current local player is at
`Mtg_Projects/mtg_play_unity/Builds/Windows/ManaforgePlay.exe`.
For another checkout, build once with `./tools/unity-play.ps1 -Mode Build` on a
licensed machine. A missing player produces a lobby error. An outdated player
must be rebuilt; no Java runtime or Unity Editor is needed to launch preview.

## Handoff and components

The existing PlayWorkspace selectors supply one saved native DeckDocument.
File-backed selections are re-read on the worker so deleted/corrupt/replaced
files cannot silently preview stale in-memory contents. Cached shared selections
use their existing local snapshot. The selected document is never modified.
The AI deck and all-seats launch manifest never enter this handoff.

A quiet JobQueue worker projects at most 24 deterministic deck entries (out of at
most 2048), retaining entry IDs, quantities, sections, exact printing/Oracle IDs
and available printed display fields. Entries are not expanded into game objects.
The version-1 deck_preview contract contains no decisions, legal actions,
priority, engine zones, shuffling, results or credentials. It is read-only ephemeral
render input, not another persistent deck model or card database.

Existing collect_visual_candidates, cached_rgba and export_artwork_bundle prepare
only offline assets. Compatible cached standard presentation is preferred when
available; the selected printing ID stays intact and the artwork printing ID is
separate. Otherwise verified selected special-frame artwork stays authentic.
Missing or mismatched assets remain unavailable. The preview-only bundle reader
accepts authentic faces; the original viewer/game bundle rules stay strict.
There are no downloads or preference/cache changes. Initial preview inspects
only the first face; unsupported treatments are not reconstructed.

LaunchOwner now has an explicit preview start from NEW with no gateway process
or fabricated gateway readiness. The one-time versioned startup frame uses its
existing bounded inherited stdin writer. ViewerBootstrapPipe shares framing,
timeouts/cancellation and the owner-EOF lifeline with a separate preview codec.
Only mode/window flags enter argv. Deck contents, local bundle paths and pins go
through the inherited pipe; hashes pin the ephemeral deck and artwork manifests.
The player validates before displaying and writes a tiny ready marker. Desktop
health monitoring checks actual child exit, ready data, startup deadline and
cancellation. No per-frame Python/Unity communication is introduced.

DeckPreviewScene reuses CardView, CardDisplayValues, VisualPrintingPolicy,
CardCompactProfile, existing typography, mana symbols and card frames. The
scene adds a scrollable playmat collection and a full inspection panel; it never
constructs viewer snapshots or bypasses the future authenticated Java session.
The CoreArtworkBundle index and pixel reads run on workers. Pixels are bounded,
textures shared per artwork printing, GPU budget capped at 64 MiB, and at most
one texture is uploaded per rendered frame. Views clear before textures are
destroyed. Late worker completions dispose their CPU buffers/indexes.

Only the child handle created by LaunchOwner is stopped. PreviewLaunch retains
that owner and its fresh temporary asset directory for cleanup retries; a failure
blocks new previews and navigation until cleanup succeeds. Cleanup verifies the
resolved generated temporary target before recursive removal. Decks, Core cache,
preferences and unrelated Unity windows are never cleanup targets. This proves
root-child ownership, not general OS descendant containment.

## Validation and evidence

Local Unity 6000.6.7f1 Windows build succeeded with the new preview path.
Built Manaforge.Play.dll SHA-256:
`be4710e62a6e90de62f2b38b83016f70c9231e178ebc9265680a89fb1ce5e18f`. Changed
Python sources parsed successfully. Per this story's policy, no routine local
Python/C# tests or packaged smoke tests were executed. No claim of owner visual
acceptance, natural gameplay, Java parity or completed roadmap gates is made.

CI coverage added:

- Play desktop preview: projection, bounds, duplicates/quantities, exact identity,
  read-only data, missing/authentic/fallback artwork, child-only launch, repeated
  owned children, cancel/startup failure, cleanup retries and navigation regression.
- C# EditMode: shared Python projection fixture, strict preview mode/version,
  invalid quantities/duplicates/oversize/injected game state and separate bootstrap.
- Existing licensed Unity workflow: compile/tests/build plus packaged preview
  smoke and screenshot using generated public artwork only. It exercises the
  actual product preview startup/scene, not ArtworkFixtureScene. The smoke
  command is `python tools/check_play_deck_preview.py`; it requires a built player.
  Desktop never supplies the optional screenshot switch, and private decks are
  never used as CI artifacts.

Python checks: [Play desktop preview workflow](https://github.com/RyMeep128/Manaforge/actions/workflows/play-preview.yml).
Licensed graphics checks: [Unity Play feasibility](https://github.com/RyMeep128/Manaforge/actions/workflows/unity-play.yml).
The latter is manually dispatched to the owner-controlled manaforge-unity runner;
no new licensed-runner result is available for this commit. Check the exact commit
run before treating an increment as validated. Owner UI review above remains
required before this story can be accepted.

Primary files: workspace.py, deck_preview.py, artwork_bundle.py,
launch_lifecycle.py; Unity DeckPreview.cs, DeckPreviewScene.cs,
CoreArtworkBundle.cs, ViewerBootstrapPipe.cs and FoundationTable.cs; dedicated
Python/C# tests, shared fixture, preview CI, licensed smoke helper/workflow.

P4.1 follow-up remains authoritative Java gateway/XMage launch, viewer-filtered
state/actions/results, actual human-vs-AI integration and all associated acceptance.
Preview mode must remain separate until those boundaries are proven.


## CI cleanup correction (0.5.121)

The 0.5.120 CI checkpoint found that the dedicated preview job failed three
cleanup cases on Windows. The actual job log showed a temporary path under
`C:/Users/RUNNER~1/...`; resolve() expands that valid 8.3 spelling to the same
`runneradmin` directory. Comparing the original spelling with the resolved path
incorrectly rejected the owned directory. The other 88 checks passed in that run:
[failed evidence](https://github.com/RyMeep128/Manaforge/actions/runs/41254073829).

PreviewLaunch now canonicalizes a newly adopted generated directory once, checks
its resolved temporary parent/prefix, rejects symlink/junction roots and records
its filesystem device/inode identity. Cleanup requires the same canonical path,
parent and directory identity before recursive deletion. This accepts valid
Windows aliases without allowing replacement directories or linked targets to be
removed. Failure still retains the existing owner/assets for explicit retry.
No process names, user data/cache folders or unrelated Unity processes are used.

The original three assertions remain intact. Added CI regressions exercise
Windows GetShortPathNameW (normal canonical ownership on other platforms),
replacement-directory preservation and refusal to adopt unrelated directories.
Changed Python files parse successfully; no routine local tests, Unity build or
UI verification were run for this correction, following the preview story policy.
CI is pending for the fix; do not call the preview story accepted. The next routine
status checkpoint remains 0.5.123. Owner visual review is still required.

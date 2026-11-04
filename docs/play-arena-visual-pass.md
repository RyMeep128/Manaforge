# Arena-inspired live table visual pass

Status: implementation in progress; owner visual review and final story acceptance pending.

## Investigation and visual gaps

Baseline: `4e75f9b`, `codex/play-live-first-land`, 215 commits ahead of local main
(the requested 214-commit sequence plus the latest shared Commander presentation).
Reviewed branch history and change inventory, the Unity roadmap, composable card
rendering story, specialized layout gallery, live integration notes, asset inventory,
local handoff and Downloads Unity Asset Catalog. Existing unrelated uncommitted
Java, launch, acceptance and Unity settings work was present before this pass.

The prior normal TableGameplayPresentation put every projected object in one
wrapping grid, forced all cards to compact mode, permanently reserved inspection
and decision columns, and showed life/phase as a status line. The stronger opening
fan, focus, mulligan controls and supplied backdrop lived in LiveOpeningScene,
which is a diagnostic acceptance scene and is not the normal saved-deck client.
Normal bootstrap also omitted the existing artwork sidecar entirely.

| Area | Reference target | This implementation |
| --- | --- | --- |
| Environment | supplied SOS tutorial battlefield, blue/gold divider and opposing halves | reuses existing local imported backdrop; dark source-only fallback |
| Seats | opponent above, player below, visible life/priority | separate life plaques and projected decision-owner highlight |
| Board | distinct land and permanent ranks across central field | controller/zone-driven ranks; type only separates already-projected permanents |
| Hand | full-card fan, overlap, readable focus | separate bottom fan, generous mulligan fan, hover/keyboard lift |
| Commands | contextual choices near lower right | existing authenticated panel in bounded scroll region; engine pagination retained |
| Inspection | full view on demand | right-click or focus card and Space; Esc/close dismisses |
| Combat | visible attack/block/selection states | immutable combat object IDs, colored borders, counters/damage badges |
| Result | authoritative outcome, prominent finish | Victory/Defeat/Draw only from supplied result; brief terminal display |

Local source evidence: Downloads/Assets from Wizards, given with permission;
Downloads/Unity Asset Catalog; ignored UNITY_ASSETS_AI_HANDOFF.local.md;
Artifacts/ReferenceVisuals/SOS_BF_NoInteractables.png and supplied button textures.
Original Downloads files were not changed or extracted again. No proprietary
binary is added to Git. Existing imported fonts, buttons and playmat remain local.
The available floor is a decorative reference, not a full screenshot demonstrating
visual parity. Earlier owner references are documented in play-live-integration.md.

## View architecture

Current architectural direction: the Arena table is the default **1v1 composition**.
Its reusable elements must also work in other compositions. See
[shared elements and view ownership](play.md#reusable-visual-elements-and-views)
for the current extraction plan; the implementation journal below records its
original increment and does not establish that extraction is complete.

`ArenaGameplayPresentation` is one implementation of `IGameplayPresentation`.
It is the default normal-game view through LiveGameScene's existing presentation
factory. The original `TableGameplayPresentation` is retained, and callers can
supply other views with SetPresentationFactory before scene startup. No format
or game rules are encoded in the view selection. ArenaTable.uss is scoped to
this presentation; other views keep their own layout and theme.

ViewerCardSurface retains all card objects, artwork tickets, revision validation,
texture ownership, concealment and disposal. Its UI-thread visitor exposes only
currently admitted projection/view pairs and stops after revocation. CardView,
CardCompactProfile, CardTypography and BattlefieldFrame remain the shared renderer.
CardView owns and clears its new live marker label during concealment. Combat
IDs are copied into the existing immutable decision slice, not looked up by name.

ViewerDecisionPanel keeps its offer binding and dispatch mechanisms. Selected
options receive visible text, zero-only mana pools are omitted, and current
choices remain bounded and scrollable. No action, strategic choice or decision
token is synthesized by production presentation. The existing explicit acceptance
driver remains opt-in and makes fixture choices only during public-deck checks.

Normal launch now prepares an ephemeral pinned artwork bundle from the local
player's own deck using the existing offline Core exporter. AI deck entries are
not supplied to the asset exporter. Unity still binds textures only for current
viewer-permitted printing/oracle identities. No network retrieval, catalog/model
change, alternate artwork cache or gameplay adapter is introduced.

## Evidence and reproduction

Use the installed Unity 6000.6.7f1 editor. Build:

```powershell
./tools/unity-play.ps1 -Mode Build
python tools/capture_play_visuals.py
```

The capture command launches a real packaged public saved-deck XMage match using
the existing opt-in acceptance driver. It resolves exact fixture set/collector
printing IDs through offline Core and copies PNGs out before owned temporary
session cleanup. Results go to a unique ignored Artifacts/ArenaVisualReview-*
directory. These are real gameplay captures, not fabricated projection fixtures.
Do not use that driver's strategic policy for normal gameplay.

Focused Python checks:

```powershell
python -m pytest Mtg_Projects/mtg_play/tests/test_live_artwork.py Mtg_Projects/mtg_play/tests/test_artwork_bundle.py Mtg_Projects/mtg_play/tests/test_live_game.py -q
python -m ruff check tools/capture_play_visuals.py Mtg_Projects/mtg_play/tests/test_live_artwork.py Mtg_Projects/mtg_play/live_game.py
```

Focused Unity test filters (pass to editor -runTests -testPlatform):

- EditMode: Manaforge.Play.Tests.ViewerDecisionProjectionTests;Manaforge.Play.Tests.CardViewTests
- PlayMode: Manaforge.Play.Tests.ArenaTablePresentationTests;Manaforge.Play.Tests.ViewerCardSurfaceTests

The table test covers 1280x720, 1366x768, 1920x1080 and 2560x1440,
identically named objects in different zones/controllers, tapped rotation and
viewer clearing. Existing surface tests cover inspection clearing and concealment;
a live marker is explicitly added before the hidden-card clearing assertion.

Initial packaged match evidence: Artifacts/ArenaVisualLive/report.json, native loss,
203 snapshots, 202 confirmed inputs, zero uncertainty, viewer cleared and cleanup
confirmed. The first captures exposed missing artwork and label overflow and were
used to iterate; they are not final acceptance images. The historical
Artifacts/UnityLive-febcdd2fee/battlefield.png shows the earlier diagnostic grid,
not a saved-deck normal-game baseline.

Latest validation and final captures are recorded below after final rebuild.
GitHub's connected commit-workflow query returned no PR-triggered runs for baseline
4e75f9b. This uncommitted work has no CI result. Required Actions validation is pending;
no full application suite was run locally.

## Remaining limitations and owner checklist

- [ ] Review the packaged saved-deck view in an actual human-controlled match.
- [ ] Compare opening/mulligan, battlefield, focus/inspection, decisions, combat
      and terminal screenshots to the owner's complete Arena references.
- [ ] Confirm readability and scaling visually at all four desktop sizes; current
      automated geometry coverage is not a substitute for visual review.
- [ ] Review very large hands and crowded boards. Board ranks page rather than compressing cards indefinitely; verify paging
      and keyboard focus on larger boards.
- [ ] Review manual mana, targeting, modes and numeric prompts with larger offers.
- [ ] Verify optional textures/fonts absent in a source-only build.
- [ ] Verify final CI checks after changes are committed/pushed.
- [ ] Record explicit owner visual approval. It is currently PENDING.

The existing live artwork provider accepts exact cached single-face standard
printings. Unsupported specialized/multiface printings and missing exact images
retain fallbacks; the richer offline gallery does not establish live support.
Opponent artwork is not preloaded from its private deck. Current rules text,
mana costs and some advanced relationships are still limited by the established
live projection/provider; no Oracle text or mechanics are invented from names.
Combat borders do not yet draw assignment arrows. Avatar art, environment effects,
polished tap animation and exact Arena materials are not implemented.
These limitations mean this increment does not complete the entire visual story
or assert Arena parity.

During implementation another session advanced the shared workspace to b62017a
(0.5.216-alpha.1) and added --presentation table / --no-capture acceptance
switches. Those changes are preserved. Some shared artwork/projection additions
were included in that concurrent commit; this pass does not claim authorship of
the Commander work or modify its release version. The Arena view remains the
normal default; the classic table can be selected through the existing factory.

## Final local evidence

- Windows development player rebuild succeeded with Unity 6000.6.7f1;
  local executable: Mtg_Projects/mtg_play_unity/Builds/Windows/ManaforgePlay.exe.
- 65 focused EditMode checks passed (projection/CardView); 7 focused PlayMode
  checks passed (table geometry/paging and surface lifetime/concealment).
- 19 focused Python checks passed; scoped Ruff and diff whitespace checks passed.
- Final real packaged saved-deck public acceptance: native win, 131 snapshots,
  130 confirmed inputs, zero uncertainty, viewer cleared, cleanup confirmed.
- Captures: Artifacts/ArenaVisualReview-3f922285/{opening,battlefield,hover,
  inspection,priority,combat,result}.png; report.json records the native outcome.
  These captures were visually inspected. They demonstrate the live vertical slice,
  including the current missing-art fallbacks, not finished Arena parity.
- Earlier artwork-enabled run: Artifacts/ArenaVisualReview-4dfb22c6/report.json,
  native win, 235 confirmed inputs, zero uncertainty and successful cleanup.
- Connected GitHub commit-workflow query also returned no PR-triggered runs for
  concurrent baseline b62017a. No CI success is asserted for these working changes.
- Packaged captures are 1280x720. All four requested sizes have focused layout
  tests; packaged visual captures at the other three sizes remain pending.

Owner visual review: **PENDING**. The full story remains open for artwork coverage,
additional packaged resolution evidence, CI and visual acceptance.

## Exact-deck artwork loading correction

The initial live exporter and Unity loader both rejected cached printings unless
classified as ordinary 2015 frames. This incorrectly excluded real cached deck
images such as the selected SOM Memnite. Normal launch now opts into exact
single-face normal-layout images regardless of frame age. The pinned Unity loader
and worker accept those records, preserve their standard/authentic classification,
and reuse the shared profile/card renderer. Multiface identity is still not guessed.

No artwork preference, alternate printing selection or deck mutation was added.
The exporter still requires the exact requested printing and Oracle identity;
regressions verify that a cached alternative is never substituted when the
selected image is missing. All six exact selected printings in the public test
deck exported successfully, including three older frames, with no unavailable
records. Focused Python checks: 21 passed. Focused Unity artwork/surface tests:
18 passed with graphics enabled, no skips; includes GPU upload, pinned older-frame
loading, inspection, revocation and concealment. Windows player rebuild succeeded.

This fixes local-player cached single-face artwork. The preexisting Java projection
still omits opponent printing identities, and no opponent private deck artwork
is exposed as part of this fix. Truly missing exact images and unprojected
multiface identities continue to show unavailable artwork.

Packaged verification for the artwork correction: Artifacts/ArenaVisualReview-4e1f1122.
The opening screenshot was inspected and shows the exact Forest, Scryb Sprites
and Walking Ballista deck artwork loaded. report.json records the native match
outcome and cleanup; this remains live gameplay evidence, not visual parity approval.

## Spatial decisions and library motion

The Arena view now mounts reusable ViewerBoardInput over the existing authenticated
surface and command panel. Cyan outlines identify objects with engine-offered
commands; gold identifies offered targets. Click or Enter selects one unambiguous
object choice. Multiple commands open an explicit chooser. Life plaques select
engine-offered player targets. Right-click/Space still inspects.

Dragging an offered hand card or permanent into the central battlefield submits
that object's currently offered play/cast/activate/attacker/blocker selection.
Release outside the battlefield, Escape, concealment, detachment or a new decision
cancels the gesture. Nothing is submitted on pointer-down or movement. The source
card stays in its authoritative zone until XMage updates the projection. Pending
commands use the panel's existing one-command admission and receipt feedback.

Blocker/defender assignment remains a sequence of engine-owned decisions: first
choose the source, then choose the newly highlighted target when prompted. A drag
does not silently queue a target for a later token, finish combat or auto-pay mana.
Mode and ambiguous ability choices remain explicit. Existing buttons remain as
accessible alternatives. These components belong to the Arena implementation;
the classic table and other presentation factories remain independent.

BattlefieldLinks draws attacker-to-defender and blocker-to-single-attacker arrows
from projected combat IDs. It skips off-page objects and ambiguous multi-attacker
pairings instead of inventing an assignment. Player library/hand counts come from
existing public snapshot fields and are copied into the immutable UI slice.

Library movement is animation, never an input gesture or draw command. After
confirmed library decreases accompanied by hand increases, anonymous card backs
fly from that player's library pile to its hand region. No card identity, future
draw or rules event is inferred. This is a presentation of observed count changes;
the current projection does not identify individual draw events. Initial snapshots,
unknown counts, milling without a hand increase, results and reduced motion do not
start flights. New revisions, disposal and reduced motion cancel active flights.

Read-only asset investigation found LibraryToHandSplineDefault and the face-down
variant in Bucket_Card.MovementPayload_Spline_0_5f15d6d3-93fa43137e6862c0a496342f85737ddb.mtga.
Face-down path ID: 8113201302534464153. The optional local pack reuses its easing
curve and a normalized lift profile adapted to this 2D table. The .6-second UI
flight duration and screen-space endpoints are Manaforge presentation choices;
this is not an import of Arena's 3D runtime or a claim of identical animation.
Source SHA-256 and path ID are recorded in the ignored local JSON pack. No supplied
runtime, texture, sleeve preference or proprietary raw data is committed.

Recreate the optional movement resource using the existing local UnityPy install:

```powershell
python tools/prepare_play_motion_assets.py --asset-root "C:/Users/ryanm/Downloads/Assets from Wizards, given with permission"
```

Absent that pack, source-only rendering uses a smooth flight fallback. Reduced
motion immediately shows the confirmed state and omits flight animation.

Validation: 30 focused EditMode checks and 41 focused PlayMode checks passed.
New coverage includes exact object/player tokens, ambiguous action menus, valid
and invalid drops, no submission before release, duplicate input, stale-drag
cancellation, immutable counts and motion cancellation/disposal. Test reports:
Artifacts/board-input-{editmode,playmode}.xml. Windows player build succeeded;
Artifacts/board-input-build.log records the result. Packaged evidence follows.

Packaged spatial-input evidence (first iteration): ArenaVisualReview-3920237b,
168 snapshots, 167 confirmed commands, native win, zero uncertainty and confirmed
cleanup. board-input-proof.json records 57 commands routed through actual card
keyboard controls by the opt-in diagnostic driver. The combat and draw PNGs were
inspected; the final iteration clamps motion within the viewport and uses the
current borrowed printing image as a drag preview, clearing it on cancellation.
Final focused PlayMode result: 42 passed (includes drag-preview resource clearing).
EditMode result remains 30 passed. No broad suite or new CI success is claimed.

Final spatial-input package: Artifacts/ArenaVisualReview-e6c0e392. Native win,
165 snapshots, 164 confirmed commands, zero uncertainty, viewer cleared and
cleanup confirmed. board-input-proof.json records 52 card keyboard inputs in
that match. draw.png shows a confirmed normal-turn library/hand flight inside
the viewport; combat.png shows projected attack links. These were inspected.
The current Windows development build includes the final drag image preview and
motion clamping. Owner visual review and CI remain pending.

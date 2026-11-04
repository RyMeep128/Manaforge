# Arena live visual review — November 3, 2026

Owner visual approval: **PENDING**. Story acceptance: **OPEN** until owner review,
required Actions evidence and the remaining live artwork/projection limitations
are resolved. No Arena parity is asserted.

## Investigation and scope

Session baseline: `777afd08dfb854930d197f04203d0fe364b12c8f` on
`codex/play-live-first-land`. Both local main and origin/main already contain
`116a810`; Git ancestry reports only the workflow-policy commit ahead of main.
The requested historical development sequence is already integrated in this
checkout. Reviewed its recent history, existing visual-pass/sweep records, Unity
roadmap, composable rendering documentation, layout gallery, live integration
notes, provided-art inventory, local asset handoff and Downloads catalog.
This session does not certify that historical integration or promote anything.

Read-only local research confirmed the supplied Wizards bundle directory and
Unity Asset Catalog. Reused the existing SOS battlefield, button skins, name
backer, card-back decal, fonts and symbols; inspected existing packaged before
captures and the supplied SOS floor reference. No additional complete Arena
match screenshot was identified in the supplied bundle directory. A decorative
floor is not evidence of Arena gameplay parity. Originals remain untouched;
no proprietary resources, extracts or local deck files enter this commit.

## Visual gaps addressed

| Before | Implemented in the normal live presentation |
| --- | --- |
| Tiny battlefield hover enlargement | Readable transient full CardView inspection on pointer/keyboard focus, opposite the source; right-click/Space pins it, Esc dismisses |
| Arbitrarily compressed large hands | Bounded overlap and keyboard-operable pages; opening geometry reuses OpeningHandFan |
| Public zones visible only as counts | Contextual graveyard/exile drawers, grouped strictly by projected zone and owner; hidden objects omitted |
| Narrow battlefield reservation | Wider permanent ranks, retained seat gaps and capped row navigation |
| Overlapping stack objects | Contextual stack heading and bounded paging |
| Generic command feedback treatment | Pending, confirmed and uncertain visual accents without changing dispatch/admission |
| Opening described as opponent turn | Dedicated opening-hand context |
| Three-second terminal display | Normal result remains until Return to Manaforge; acceptance driver still exits automatically |
| Development watermark in player | WindowsPlayer uses BuildOptions.None |

The renderer, ViewerCardSurface texture ownership, CardCompactProfile,
BattlefieldFrame, CardTypography, authenticated host and ViewerDecisionPanel
command binding remain shared. No new game-state service, protocol or rules
mechanism was added. Zone drawers expose only objects already admitted to the
viewer surface. Board rank type checks occur only after authenticated battlefield
membership/controller filtering. Hover inspection never submits a command.
Revision changes close inspection; revocation still clears the shared inspector
and its borrowed resources. Reduced motion retains the established no-transition
path. No new online assets or renderer dependencies were introduced.

Result retention delays game-closing.json until dismissal: that file starts the
parent's ten-second shutdown budget. The existing gateway waits for its owner
lifeline after serving the terminal projection. The view continues to pump
revocation while waiting and never retains textures against a cleared ticket.

## Reproduction and evidence

```powershell
./tools/unity-play.ps1 -Mode PlayMode -Graphics -TestFilter 'Manaforge.Play.Tests.ArenaTablePresentationTests;Manaforge.Play.Tests.ViewerCardSurfaceTests;Manaforge.Play.Tests.ViewerCommandDispatchTests'
./tools/unity-play.ps1 -Mode Build
python tools/capture_play_visuals.py
```

The capture tool runs an actual packaged shuffled public saved-deck 1vAI match
through XMage and the same live launch path. Its explicit acceptance driver makes
strategic choices; normal saved-deck launches do not mount that driver. It is not
proof of owner-controlled human play. Screenshots remain local, not redistributed.

Before: `Mtg_Projects/mtg_play_unity/Artifacts/ArenaVisualReview-f50107b6`.
First after iteration: `Artifacts/ArenaVisualReview-4a4870b4` under the Unity
project: native win, 162 snapshots, 161 confirmed inputs, zero uncertainty,
viewer cleared and cleanup confirmed. Actual requested/observed desktop sizes
match in resolution-proof.json. Hover inspection was visually checked and its
slight overlap with the decision prompt corrected before the final rebuild.

Focused final rendering, surface/privacy and command tests: **49 passed**, graphics
enabled, no skips. Includes large-hand keyboard paging, separate owner graveyards,
closing the zone drawer, existing four-resolution board geometry, viewer clearing,
exact spatial/choice tokens, mana, numeric decisions and stale/pending rejection.
Windows non-development player build succeeded. Broad suites were left to CI.

Final packaged captures and CI state are recorded below after verification.

## Remaining limitations and owner review

- [ ] Launch a normal saved deck from Manaforge and play human-controlled 1vAI.
- [ ] Review opening fan, Keep/Mulligan controls and transition into play.
- [ ] Review battlefield, readable hover and pinned/scrollable inspection.
- [ ] Review casting, manual mana, modes, numeric input, targets and cancellation.
- [ ] Review combat links, tapped/selected cards, counters and authoritative life.
- [ ] Review graveyard/exile drawers and large-hand/crowded-board paging by keyboard.
- [ ] Review all four framebuffer sizes: 1280x720, 1366x768, 1920x1080, 2560x1440.
- [ ] Review reduced motion and a source-only build without LocalCardVisuals.
- [ ] Verify normal terminal display remains until Return, then clean owner teardown.
- [ ] Attach complete Arena gameplay references for owner comparison if available.
- [ ] Record required exact-SHA Actions workflow/job/step evidence.
- [ ] Record explicit owner visual approval; it remains PENDING.

The authenticated live projection still lacks opponent printing identities and
current rules/mana text needed for complete Arena-quality cards. Opponent cards
therefore retain honest missing-art fallbacks; names are never used to guess
printings or access the private opponent deck. Exact local cached artwork remains
single-face limited; richer specialized gallery coverage does not prove live
multiface support. These upstream data gaps materially limit visual completeness.
The neutral card-back surround and 2D supplied backdrop are adapted presentations,
not Arena's full 3D materials/avatars/effects. Board and stack paging are deliberate
crowding fallbacks. Only the battlefield state is captured at all four resolutions;
opening and every decision variant still need owner resizing review. Full source-only
packaged review and manual normal-result dismissal are pending.

## Final package and checkpoint record

Final non-development package: `Mtg_Projects/mtg_play_unity/Builds/Windows/ManaforgePlay.exe`.
Capture directory: `Mtg_Projects/mtg_play_unity/Artifacts/ArenaVisualReview-5e1bfac8`.
`report.json`: native win, 182 snapshots, 181 confirmed inputs, zero uncertain,
viewer cleared, cleanup confirmed. `board-input-proof.json`: 72 card keyboard
inputs through real spatial controls. `resolution-proof.json` records matching
actual/requested 1366x768, 1920x1080 and 2560x1440 framebuffers; baseline captures
are 1280x720. This is the final source build, before the required Python patch
version bump to 0.5.220-alpha.1 (which does not alter Unity rendering).

Review files next to each other with the before directory listed above:

| State | Final capture |
| --- | --- |
| Opening/mulligan | opening.png |
| Battlefield | battlefield.png; battlefield-1366x768.png; battlefield-1920x1080.png; battlefield-2560x1440.png |
| Hover and pinned inspection | hover.png; inspection.png |
| Priority decision | priority.png |
| Combat with several permanents | combat.png |
| Native final result | result.png |

The supplied optional floor reference remains at
`Mtg_Projects/mtg_play_unity/Artifacts/ReferenceVisuals/SOS_BF_NoInteractables.png`.
It can be viewed alongside the captures but does not show Arena's complete HUD.
Visual inspection confirmed the final hover no longer overlaps the action prompt,
local exact artwork renders, combat/tapping/life states remain visible, and the
non-development player has no Development Build watermark. Minor stack/library
heading proximity and source-only close-button treatment remain polish items.

CI: **BLOCKED / NOT VERIFIED**. The persistent helper retains pending baseline
`777afd08dfb854930d197f04203d0fe364b12c8f`; it must not be replaced by this newer
HEAD merely because implementation advanced. Its recorded blocker is missing
GitHub CLI (`WinError 2`); no exact-SHA workflow/job/step success is claimed.
The connected workflow query is PR-only and cannot establish all required runs.
The licensed self-hosted Unity workflow and broader applicable historical-range
checks remain mandatory before promotion. No main merge, tag or release is made.
Owner visual approval remains **PENDING**.

## Continuation: public-zone layering and keyboard focus

Development continues from `dbbc140` on `codex/play-live-first-land` in the
isolated worktree `C:/Users/ryanm/Proxy App/arena-visual-continuation`.
The original directory is now checked out on `integration/all-branches-2026-11-03`
and contains uncommitted artwork/text work. It was left untouched; that pipeline
is neither incorporated nor certified by this visual continuation. The active
branch's AGENTS.md and development-workflow.md were reread, and the shared
persistent checkpoint record was resumed without replacing its pending SHA.

The earlier public-zone display assertions missed a real stacking defect:
bringing a card forward inside CardsRoot cannot put it above a sibling drawer.
Public browsing now hides table cards and moves the same owned CardsRoot above
the backdrop. Closing restores the normal layout. There is no reparenting of
card objects, new renderer or texture ownership. BrowsePublicZone rejects private,
absent and unsupported zones and consults the current admitted surface. It never
submits a game action. Existing zone buttons use that same navigation API.

Hover and keyboard focus now have separate inputs. Pointer hover temporarily
wins; leaving restores the keyboard card's preview. New revisions clear emphasis.
Inspection requires a still-admitted visible card, including during detachment
and revocation, so teardown cannot re-enter a transitioning surface through focus.
The stack heading is anchored above its row and the opponent library moved upward
to leave a clear gap. Inspection/zone close controls use the shared dark/gold
source-only button treatment rather than Unity's default gray.

The explicit packaged capture path now also captures public-zone.png when an
actual viewer-visible graveyard becomes available. It makes no strategic input
and never fabricates a zone or card. The normal launch does not run this driver.

Focused graphics PlayMode result: **50 passed**, zero failures/skips. Added checks
exercise actual panel picking of the graveyard card above its drawer, keyboard
focus restoration, authenticated hover without command bytes, and inspector
clearing after owner revocation. The Windows non-development build succeeded.
No broad application suite was run; required Actions remain a separate gate.

Local optional visual resources were copied from the already prepared local pack;
no Downloads extraction was repeated. The isolated worktree references the existing
ignored approved engine installations and uses its own runtime/session directories.
All supplied binaries, local resources and captures remain untracked/ignored.
The approved app-owned engine lock is unchanged.

Packaged match results follow after completion. Owner visual acceptance remains
**PENDING**. Source-only packaged review, full reference comparison, manual normal
result dismissal, and the prior live data/printing limitations remain open.

The first continuation package (`Artifacts/ArenaVisualReview-a8968e29` in the
isolated Unity project) completed a native loss with 191 snapshots, 190 confirmed
inputs, zero uncertainty, viewer cleared and cleanup confirmed. Its actual
public-zone capture exposed a background board hint showing through the drawer;
a bottom-library selection capture also exposed hand/control crowding. Public
browsing now suppresses battlefield hints/links and the normal fan reserves more
space for the control rail. Opening-hand geometry remains generous. A focused
bounds assertion protects the control margin. This also exposed and corrected
a transient narrow-panel startup case: the fan viewport is clamped positive
before passing it to OpeningHandFan. The corrected 50-check run passed without
skips. Final captures below supersede this first iteration for those details.

A second iteration (`Artifacts/ArenaVisualReview-fd096624`) completed a native
loss with 241 snapshots, 240 confirmed inputs, zero uncertainty and clean teardown.
It verified the hand/control margin but exposed two details in the actual drawer:
the board hint's inline display property overrode the first stylesheet suppression,
and pagination from hidden board rows remained visible. The final correction uses
visibility (which the input refresher does not override) and clears background
row navigation before laying out public-zone pages. The authenticated UI test now
refreshes the offer while browsing and checks resolved hint visibility; the crowded
board test checks that unrelated page controls are absent. All 50 checks pass.

The original directory's running client/build was not replaced. To review this
continuation, run `python run_manaforge.py` from the isolated worktree and use its
normal Play launcher, or use the capture command above. An already-running
Manaforge instance may still belong to the original workspace. The isolated
Windows build is under that worktree's `Mtg_Projects/mtg_play_unity/Builds/Windows`.
Required owner checks remain unchecked, including crowded normal-board paging,
which can still approach the lower-right rail in late-game captures.

### Final continuation evidence (0.5.222-alpha.1)

Final capture directory in the isolated worktree:
`Mtg_Projects/mtg_play_unity/Artifacts/ArenaVisualReview-dd7dc154`.
Native win; 166 snapshots, **165 confirmed inputs**, zero uncertain, viewer cleared
and cleanup confirmed. Spatial proof records **60 card keyboard inputs**.
Opening, battlefield, hover, pinned inspection, priority, combat, draw, public-zone
and result PNGs are present. Actual 1366x768, 1920x1080 and 2560x1440 framebuffer
captures match their requests; baseline captures are 1280x720. The final public-zone
image was inspected and shows its card above the backdrop, with the background
hint and unrelated row paging absent. Hand/control spacing, stack/library gap,
inspection close treatment and final native outcome were visually checked.

Final non-development Windows build: successful. Focused graphics PlayMode:
**50 passed**, no skips. Diff whitespace check: passed. Proprietary assets and
captures are not committed. Owner visual acceptance and complete story acceptance
remain **PENDING**. Required Actions remain unverified; the persistent baseline
candidate is retained. The normal source-only and human-controlled review items
above remain open; this continuation does not certify the uncommitted artwork/text
pipeline in the original directory or claim Arena parity.

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

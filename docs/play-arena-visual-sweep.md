# Arena table — second visual sweep

Owner visual review: **PENDING**. This is a visual refinement of the normal saved-deck
Arena presentation, not a parity claim or a new rules/transport implementation.

## Reference-driven changes

Reviewed the supplied SOS battlefield, the prior live captures, local static table
layout research, MainButton blue/orange skins and glows, the supplied movement
splines, and the default sleeve materials. The previous captures showed left-side
life plaques, placeholder library rectangles, crowded action lists and diagonal
combat links that competed with the battlefield.

The table now uses centered opponent/local life medallions with large shared
Beleren typography, priority borders and the supplied player-name backer. Land
ranks reserve a gap around those medallions, including tapped-card bounds. Opponent
hand backs depict only the public count, capped at twelve visible backs. No hidden
printing identity is requested or inferred.

Pass/Finish and numeric confirmation use the supplied orange MainButton skin and
glow. Secondary choices and card context menus reuse its blue counterpart. The
spatial view moves card/player button alternatives into a collapsed, keyboard-
accessible foldout; all original commands remain available and use their original
binding. The classic table keeps its existing presentation. This is an opt-in
presentation setting, not a gameplay preference or altered strategic policy.

The phase display and contextual instruction are quieter, public zone counts are
separated from library piles, and hand focus can rise above the life medallion
while inspection, decisions and confirmed results retain their overlay priority.
Confirmed combat links now use curved paths. Tap/focus transitions and confirmed
life changes have small visual transitions; reduced motion removes them.

Library-to-hand movement still uses the provided face-down movement curve/lift
profile prepared by prepare_play_motion_assets.py. The new draw and opponent hand
backs reuse the supplied default Arena decal on a neutral surround. This is a 2D
adaptation: the complete default sleeve base-texture dependency was not resolved,
and no supplied shader/runtime is imported. It is not a sleeve selector and does
not change the deck's selected card printings or existing artwork preferences.

## Local asset provenance

Newly curated, ignored resources in LocalCardVisuals/PlayHUD:

- player_name_backer, path ID 1888041602498328757, from
  Textures_Bucket_UI.DuelScene.DuelSceneUIPrefabs_0_1f301390-ac6df0b3e065ef52941caeaaa7503c71.mtga.
- CardBack_Decal_LogoArena, path ID 4086297360495280151, from
  Textures_Bucket_Card.Parts.AnimatedCardbackPart_0_33e3bd60-ec7a176a729e1a86c1f948ff9820b0f1.mtga.

The local provenance.json records source SHA-256 and names/path IDs. Source bundles
remain untouched. Only Manaforge source/tooling is tracked; proprietary images
and extracts remain ignored. The default material inventory and unresolved
shared CAB dependency are recorded under ignored Artifacts/ReferenceVisuals.

Recreate decorative resources from the supplied files using the existing local
UnityPy installation:

```powershell
python tools/prepare_play_table_assets.py --asset-root "C:/Users/ryanm/Downloads/Assets from Wizards, given with permission"
python tools/prepare_play_motion_assets.py --asset-root "C:/Users/ryanm/Downloads/Assets from Wizards, given with permission"
```

Source-only builds retain neutral backs, CSS button treatments, normal typography
fallbacks and the movement fallback when local assets are absent. No new online
asset dependency was introduced.

## Verification and manual review

Focused Unity checks cover the command panel/input lifetime, explicit collapsed
fallback commands, motion cancellation and all four target desktop sizes. Layout
assertions now verify the centered seats and that tapped lands leave life visible.
The existing engine and authenticated session checks are unchanged. Broad suite
validation remains for CI; uncommitted changes have no new CI result.

Build and run a real packaged public saved-deck match:

```powershell
./tools/unity-play.ps1 -Mode Build
python tools/capture_play_visuals.py
```

Review opening/keep/mulligan spacing, focused hand cards, centered life/priority,
land gaps, primary controls, explicit mode/payment choices, targeting, combat
curves, draw flight and authoritative final result. Verify the collapse/expand
fallback and keyboard focus. Check the other target resolutions visually; numeric
layout assertions alone do not establish visual acceptance.

The opponent printing-identity gap and missing exact artwork remain upstream
limitations described in play-arena-visual-pass.md. The default card-back surround
is adapted rather than the complete Arena sleeve shader. Full visual parity and
owner acceptance remain open.

The opening fan is centered on the viewport, with the local life medallion moved
aside during mulligan decisions so it does not sit behind the Keep/Mulligan prompt.
The normal hand is centered under the player with tighter overlap and renders
above the land rank. Availability footers are reserved for inspection; missing
art remains explicitly indicated. Opening/pregame count changes do not produce
extra anonymous flight overlays over the already displayed opening hand.

The spatial primary action remains visible even when card alternatives fill a
page; a focused command-token regression covers that case. Final focused local
PlayMode result: 44 passed. Ruff passed for the capture and asset preparation
tools. No broad application suite was run.

Earlier packaged sweep iterations completed native wins with 186 and 167 confirmed
commands respectively, zero uncertainty and clean teardown. The latter run,
Artifacts/ArenaVisualReview-31c790d6, rendered actual 1366x768, 1920x1080 and
2560x1440 framebuffers in addition to the 1280x720 baseline; resolution-proof.json
records requested and actual sizes. These are actual packaged screenshots,
not resized copies. The final spacing/primary-action package is recorded below.

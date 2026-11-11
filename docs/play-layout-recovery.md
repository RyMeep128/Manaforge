# Resolution recovery and acceptance (CT-06)

CT-06 extends the gated CT-05A live drawer editor. It adds a common viewport/body
geometry calculation, display-scale recovery, an independent reset action, and
acceptance evidence for the actual editor. The production PrivateLayout capability
remains disabled until exact-SHA hosted and full-game acceptance passes.

## Supported sizes and scale

Supported usable viewports are at least **1024 x 768 UI units**, or **1280 x 720 UI
units** for widescreen. The latter preserves the existing required 720p default;
a strict 768-unit minimum height would exclude it. A one-unit tolerance handles
panel floating-point rounding. Geometry tests and rendered captures cover 1024x768,
1280x720, 1366x768, 1920x1080, 2560x1440, and 3440x1440.

GameplayViewportContext contains the canvas's local usable bounds and measured
pixels per UI unit. Geometry always uses UI coordinates. Arena's live panel uses
constant-pixel scaling computed as max(1, min(pixelWidth/1280, pixelHeight/720)).
This preserves normal 16:9 desktop sizing, fits ultrawide by height, and does not
shrink UI to conceal a window smaller than the supported minimum. The existing
Table presentation keeps its scale configuration. PlayerDisplayControls continues
to own F11, fullscreen requests, and display preference persistence; LiveGameScene
updates Arena scale only when the actual screen size produces a different scale.

Bounds or effective-scale changes cancel captured gestures before re-resolution.
Saved normalized intent is retained, not replaced by clamped geometry. Unmodified
participants keep dynamic legacy placement; their controller defaults and transaction
snapshots are rebased so a later drag does not jump from stale pre-resize coordinates.
Custom participants and retained drafts keep their normalized intent. Resizing does
not mark untouched defaults dirty or save files.

GameplayDrawerGeometry resolves the header, body direction/height, and resize grip
once. LiveDrawerLayoutAdapter consumes that same result for its borrowed drawer and
editor handles. Bodies scroll within available space; header rails wrap rather than
stranding enlarged tabs. Legacy USS remains authoritative without an override.

Below the supported profiles, editing suspends, its input/automatic-passing gate is
released, the draft is retained, and custom placement temporarily yields to legacy
placement. A keyboard-focusable warning explains the limit and recovery route.
Enlarging restores the applied custom layout. Draft resume remains explicit. No
preset or saved startup selection is rewritten by this transition.

## Reset independently of the editor

With private layout enabled, Escape Menu exposes **Reset Layout for This Game**.
It remains enabled when the editor is blocked by a required choice, a small viewport,
initial preset loading, failed storage, or an unsupported preset schema. The menu
card scrolls and keyboard traversal scrolls the focused button into view.

A dedicated confirmation explains that reset discards the in-memory draft, restores
legacy drawer placement, and keeps saved presets and the startup selection. Reset
cancels layout gestures, clears overrides and retained edits, releases the editor
gate, restores legacy placement, and returns focus to required gameplay, reveals,
public-zone browsing, inspection, or the priority tab as appropriate. It does not
restore old expansion snapshots over current drawer attention or mandatory choices.

Reset never writes storage. An explicit save already in flight may finish, but a
generation guard prevents its completion from restoring stale layout/editor state.
Subsequent app startup can still restore the previously saved preset; reset applies
to this presentation session only. Editor Restore Default remains a separate staged
operation requiring Apply and explicit Save As to persist.

## Acceptance integration

The existing -manaforgeGameAcceptance path constructs default Arena with private
layout enabled and a MemoryLayoutPresetStore. No launch argument or user setting is
added. Custom presentation factories remain authoritative; the ordinary composition
keeps the disabled capability default and performs no layout file IO.

For a normal freeform saved-deck match, LiveHudLayoutAcceptance opens the editor
through the menu, moves/resizes Actions, checks the input gate, applies, verifies
Cancel preserves the applied layout, confirms session reset, then applies a custom
layout for the rest of the match. Required-choice interruptions allow the existing
gameplay driver to complete the choice and explicitly resume the draft. No game
commands, native rules, offers, or card identities are manufactured by this driver.

The close report includes hud_layout evidence. Python rejects ordinary Arena
freeform acceptance unless opened, moved, resized, input_gate, cancel, reset,
custom_gameplay, and complete are true. Existing native outcome, automatic payment,
confirmed-command, uncertain-state, and cleanup checks remain mandatory. Table,
concession, and focused Commander acceptance do not claim this extra certificate.

Hosted EditMode checks cover scale policy and header/body/grip bounds. PlayMode checks
cover scale/viewport gesture cancellation, retained drafts, no autosave, recovery with
attention and blocked storage, menu confirmation, F11 routing, and existing owner/
focus/session cleanup behavior. Six-size Arena captures use exact RenderTextures and
record requested/rendered/UI dimensions in Artifacts/LayoutRecovery/resolution-proof.json.
Default/custom/restored images and the dimension report are uploaded by unity-play.yml.
These captures establish render-target coverage, not physical monitor or fullscreen
acceptance. Existing targeting, mana-source, board-input, drawer, priority, and menu
suites still exercise the normal interaction paths.

## Evidence and release gate

Implementation is on main; candidate hosted acceptance is pending. The earlier local Windows player rebuild and script/test
assembly compilation passed; the new acceptance-preparation rebuild is blocked as
detailed below. No local test suite has been run. Exact-SHA hosted runs
for this worktree and the owner walkthrough remain pending. Keep production disabled.

### Current candidate evidence and remaining rollout work

On `9a967af` (`0.6.65-alpha.1`), [general tests](https://github.com/RyMeep128/Manaforge/actions/runs/43026761417),
[protocol fixtures](https://github.com/RyMeep128/Manaforge/actions/runs/43026761447),
[native payment on stock and delivery engines](https://github.com/RyMeep128/Manaforge/actions/runs/43026761285),
preview, and coverage-audit workflows passed. These are not evidence for subsequent
uncommitted changes. The [Unity run](https://github.com/RyMeep128/Manaforge/actions/runs/43027104535)
failed during setup with missing `UNITY_LICENSE`; account secrets were also empty.
Unity tests, captures, and the normal saved-deck match were skipped, not passed.
The owner must configure the secrets through repository settings as documented in
[hosted Unity setup](unity-ci.md); never place credentials in chat or tracked files.

Acceptance preparation adds a real JSON-store editor restart scenario: explicit
Save As survives disposal and reconstruction, untouched drawers stay legacy, and
session reset does not alter the saved startup preset. Arena now passes the store
a directory (`profiles/default/layouts/arena`), rather than a directory accidentally
named `presets.json`; the store itself appends the filename. No migration is added:
ordinary-game layout IO has never been enabled. Trusted pre-release compositions
that used the erroneous nested directory must retain/export their own presets.
The acceptance path continues to use isolated memory storage.

The required local rebuild was attempted on 2026-11-11 after these changes and
failed with exit 198 before compilation: `No valid Unity Editor license found`;
`com.unity.editor.headless` entitlement was unavailable. The earlier successful
rebuild does not validate these edits. No local test suite was run. Restore local
Unity licensing and repeat `./tools/unity-play.ps1 -Mode Build` before delivery.

Rollout sequence:

1. Keep ordinary composition gated; run hosted Unity and normal saved-deck acceptance
   plus the owner walkthrough on the prepared candidate. Correct failures without
   removing assertions. Rebuild the local Windows player after Unity changes.
2. Only after those pass, enable `PrivateLayout` explicitly in ordinary Arena's
   `LiveGameScene.CreateDefaultPresentation`, keeping global capability defaults
   disabled, custom factories authoritative, and acceptance memory storage isolated.
   Update the composition gate test to expect the enabled ordinary capability.
3. Re-run applicable workflows on the enabled SHA, including persistent preset
   save/restart and full-game acceptance. Menu entry is the opt-in interaction;
   add no experimental setting or launch argument. A fresh profile remains legacy.
4. Mark CT-05A/CT-06 accepted only after final-SHA evidence and owner acceptance.
   If blocked, leave the ordinary capability disabled and report the exact blocker.

Inherited evidence on base commit 1abe52d73a7670c44809e6d1fcc0e9afa314eb8d:

- Tests and protocol workflows passed on that base; they do not validate these changes.
- [Native payment](https://github.com/RyMeep128/Manaforge/actions/runs/42963467262)
  failed in NativePaymentAcceptanceChecks.phyrexianThenOrdinary with
  AUTO_CHOSE_PHYREXIAN_LIFE (delivery job 130335169270). This is beyond the earlier
  match initialization issue. Static inspection of the pinned engine showed the
  focused duel fixtures passed minimum-deck-size/starting-life/hand-size arguments
  in the wrong order, starting at 7 life. The fixtures now use 20 life (40 where
  intended), with a starting-life guard. Payment behavior and Phyrexian assertions
  remain unchanged. The next native run advanced past that assertion and exposed
  a missing native playable-object list in the focused GameView. The fixture now
  mirrors GameSessionPlayer.getGameView using payer.getPlayableObjects(game, Zone.ALL);
  source correlation still failed because XMage legitimately returned an empty public
  playable list while its private payment plan and completion receipt were valid.
  Correlation now accepts the first matching VERIFIED_ORDINARY_EQUIVALENT object
  step from server-only metadata, while retaining cycle/receipt and visible controlled
  permanent checks. Native negative cases reject absent/unsafe plans, wrong sources
  or step kinds, and hidden/foreign permanents. Native CI on eb667d1 passed the
  Phyrexian-plus-two-casts regression (three automatic completions, zero manual
  mana windows), then exposed fixture source-card names containing Java class
  paths. The factory now supplies card names, including Snow-Covered Mountain;
  CI on 0086a53 then passed through hybrid payment and found the snow fixture
  referenced SnowCoveredMountain in the wrong Java package. Its source now uses
  the pinned engine class mage.cards.s.SnowCoveredMountain. A static inventory
  verified every reflective card/game class in this fixture exists in the pinned
  engine; the remaining native scenarios still require a candidate pass.
- No Unity run exists for that base SHA. Earlier hosted Unity setup was blocked by
  license configuration; its current availability has not been established.

After an authorized candidate commit/push, run applicable Unity, protocol, native
payment, and saved-deck human-versus-AI workflows on the exact SHA. Missing, failed,
skipped, or unavailable evidence is not a pass. Ordinary private layout was enabled
at the owner's explicit request on 2026-11-11; required hosted evidence and the
owner walkthrough remain pending. Initial local rebuild attempts failed with exit
198 because the command-line editor did not recognize the Personal license.
Opening the project through Unity Hub resolved the licensing issue; the subsequent
`./tools/unity-play.ps1 -Mode Build` completed successfully on 2026-11-11 and updated
the local Windows player.

### Manual owner walkthrough

1. In an isolated acceptance composition, complete opening choices. Move/resize/dock
   drawers, Apply, change another drawer, and Cancel. Resize or press F11 during an
   active drag. Verify capture is released, no game action fires, and normalized
   applied/draft intent survives both fullscreen/window transitions.
2. At every supported size, verify all headers, body scroll controls, resize grips,
   and editor buttons are reachable with mouse and keyboard. On a monitor that cannot
   render a requested physical size, record the actual size and leave that physical
   check pending; do not relabel a substituted window as a pass.
3. Shrink below both supported profiles during editing. Verify a warning, legacy
   placement, released input gate, and retained draft. Enlarge: applied custom layout
   returns; Resume Customization restores the draft only when explicitly selected.
4. Open the menu during a required local choice/reveal and during unavailable preset
   storage. Confirm Reset Layout for This Game, then finish the existing choice. Check
   drawer attention/expansion and saved preset/startup selection were preserved.
5. With customization applied, finish a normal saved-deck human-versus-AI match using
   automatic mana payment, casting, abilities, priority/yields, stack interactions,
   targeting, and combat. Verify public zones, library ordering, Commander gating,
   menu options, and concession separately. Record exact SHA, workflow links, actual
   sizes/modes, screenshots, and unresolved inherited failures.


## Visual editor and zone preview correction

Customization is performed directly on the live table. Drag a drawer header to
move it, drag the visible corner grip to resize its expanded preview, and drop
near a viewport edge to dock. The thin cyan edge indicator shows docking intent.
The compact top toolbar contains Apply, Cancel and Restore Default. Preset storage
and keyboard controls are in a collapsed foldout; placement is no longer a grid
of movement/size buttons.

Zones automatically opens while editing. Each header has a Preview/Close preview
control. Preview expansion is temporary and does not overwrite saved drawer-open
preferences. Library, graveyard and exile piles remain browsable; public zone
navigation and admitted-card inspection are allowed while native actions stay gated.
Closing the editor closes its public-zone/card previews and restores input/focus.

Custom drawer viewports, content and scroll views now receive explicit expanded
heights. A max-height alone could leave an absolutely positioned viewport's scroll
area collapsed. Resetting to legacy geometry restores the borrowed styles, including
scroll height and flex behavior. View hierarchy, bindings and artwork ownership stay
with their existing owners.

Hosted `VisualHudEditorTests` exercises live zones, pointer dragging, resizing,
public browsing, preview toggles, Apply/Save/Cancel, restored expansion preferences
and zero native command bytes. Its screenshots are collected under
`Artifacts/VisualHudEditor`. Local Windows rebuild and hosted tests are separate
checks; screenshots and manual acceptance must not be inferred from compilation.

Resize gestures begin at the currently visible body height, including when the saved
height was clamped by the screen edge. This avoids a dead drag range caused by an
off-screen stored height. Preview scrollbars and wheel scrolling remain available.

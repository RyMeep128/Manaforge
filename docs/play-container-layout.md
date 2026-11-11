# Container layout infrastructure (CT-03)

The synthetic **Layout workspace** tab in the existing style-review scene exercises
move, resize, edge/container docking, reorder, undock and panel/drawer conversion.
No live Arena registration opts into these operations. No game state, networking,
persistence or Escape Menu customization is introduced. See the
[foundation contract](play-hud-layout-foundation.md) and [epic](customizable-tabletop-epic.md).

## Contracts and ownership

`ContainerLayoutState` is an immutable component ID, normalized remembered floating
rectangle, panel/drawer mode, optional dock target, dock edge and order. A null
target with a non-None edge means viewport docking. `ContainerConstraints` supplies
panel-unit min/max size, supported operations, allowed targets and whether a
component can accept docked neighbors. Existing live HUD descriptors are unchanged;
only synthetic descriptors advertise Move, Resize, Dock and ConvertDrawer.

`ContainerLayoutController` validates whole candidate changes before committing
and notifying. Preview resolves a copy without mutating committed state. Reorder
updates a rail atomically. Cycles, missing/incompatible targets, unsupported
operations, nonpositive sizes and non-finite geometry reject. Removing a target
floats direct dependents at their last resolved position; drawer expanded height
is retained. `ContainerLayoutResolver` is pure geometry with no Unity hierarchy or
commands. It computes viewport-relative floating bounds and ordered edge rails,
with ID tie-breaking for equal order. Viewport rails sit inside the viewport;
container rails sit against the target's outer edge. Headers clamp to nonnegative
coordinates; deliberate overlap is allowed. Scroll extent covers rails that exceed
the viewport and content whose minimum size cannot fit. Floating placement clamps
to reachable bounds; maximum/minimum sizing applies in panel units. Drawer layout
occupies a 32-unit header and can expand over neighboring content.

`GameplayContainerShell` borrows one existing content element. Panel mode uses a
scrolling body; drawer mode composes GameplayDrawer. Conversion moves the same
content element, preserving bindings/field values. It remembers expansion, restores
focus when accessible and otherwise returns focus to the drawer tab. It retains
GameplayDrawer's attention, closed-subtree suppression and reduced-motion behavior.
Shell disposal restores suppressed input, detaches borrowed content and disposes
its wrapper/drawer, never the borrowed content. The original owner disposes its
own content resources.

`ContainerGestureController` attaches callbacks only to dedicated handles/grips.
Each attachment returns an IDisposable lease; dispose it before removing the shell.
The gesture controller owns and releases pointer capture. A 10-unit threshold
starts previewing. Pointer-up commits one candidate; Escape, capture loss, detach,
component removal, viewport change, external committed changes and disposal cancel
and re-render committed state. Shell disposal also automatically releases its
handle attachment. Dock previews highlight compatible targets within
24 units of an edge; concrete targets take precedence over viewport edges.
Borrowed content fields/buttons never participate in layout gestures. There is no
session host, decision offer or game-command reference in this infrastructure.

## Fixture use and extension

The Layout workspace contains a movable panel, convertible panel, fixed panel and
docking target. Select a component in the toolbar, use its drag handle/resize grips,
or activate the labelled keyboard-accessible controls. Move/resize controls step
8 panel units. Select a target and edge to dock; Previous/Next reorder a dock rail.
Unsupported operations are disabled. Reset restores the initial synthetic state.
The workspace's Reduced motion toggle updates its drawer shells. It is distinct
from the existing review scene's appearance toggle.

To add another component, register state and constraints with the controller,
create a shell borrowing the owner's content, register its descriptor with the
presentation registry, and attach its handles to the gesture controller. Resolve
changes through the controller and apply returned bounds to the shell. This does
not require changing shell/gesture implementations. On removal, dispose the handle
attachment and HUD registration before disposing the shell/removing its state.
The workspace is one reference integration, not a live editor or preset store.

## Verification and remaining acceptance

Hosted EditMode coverage in ContainerLayoutTests exercises normalization, sizing,
all viewport edges, container docking, rail order/overflow, target removal, cycles,
invalid numbers/IDs/targets, capabilities and preview isolation. Hosted PlayMode
GameplayContainerTests covers content identity/state, focus/suppression, motion,
gesture transactions/cancellation, real pointer capture, Escape, capture loss,
detach/removal, embedded input, keyboard controls and generic component integration.
CT-01–02 tests and existing drawer/targeting/mana/board/menu regressions remain
required. New tests share the existing assembly/namespace filters; no workflow
change is needed to include them.

The existing `tools/capture_play_style.ps1` path now requires floating, docked and
collapsed workspace screenshots at each of its four baseline resolutions, in
addition to every pre-existing capture. Images are synthetic visual evidence,
not real-engine or multiplayer acceptance.

No commit/push or local test suite was run. Exact-SHA GitHub Actions evidence is
pending, including CT-01–02. Current working tree already contained unrelated
gameplay/session/protocol/menu/workflow changes, all preserved. Local verification on 2026-11-10:

- Final `./tools/unity-play.ps1 -Mode Build` succeeded (exit 0;
  `Mtg_Projects/mtg_play_unity/Artifacts/build.log`: `Build Finished, Result: Success`).
  The new test assemblies compiled; tests were not executed locally.
- Synthetic captures were generated under
  `Mtg_Projects/mtg_play_unity/Artifacts/ContainerLayoutReviewFinal`. Floating,
  docked and collapsed arrangements were visually inspected; field contrast was
  corrected with workspace-scoped styling. No runtime exceptions were reported
  by that capture player.
- The capture script exited 1 because the 2560x1440 request produced 2560x1366 on
  this desktop. Observed dimensions matched at 1280x720, 1366x768 and 1920x1080.
  Files labelled 2560x1440 are not valid evidence for that size. The strict check
  remains enabled; full four-size capture acceptance is pending a suitable runner.
- Hosted suites and real gameplay regression remain pending. A local build and
  synthetic images do not replace those gates. No commit, push, version bump,
  tag or release was made.

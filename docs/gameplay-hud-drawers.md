# Gameplay HUD and drawers

`ArenaGameplayPresentation` places components; it does not own another gameplay
model or command dispatcher. `IGameplayPresentation` and the presentation factory
remain the entry points for alternative views. `TableGameplayPresentation` also
composes the shared HUD.

## Component boundaries

| Component | Responsibility | Authority / interaction |
| --- | --- | --- |
| `GameplayPlayerHud` | Format-aware composition; explicit seat collection | Reads `ProjectedDecisionFrame`; emits player ID activation |
| `PlayerPanel` | Name, life, active/priority/target state, life animation | Existing `TryActivatePlayer` handles activation |
| `CommanderDashboard` | Independently mountable Commander information; optional owner filter and internal scrolling | Reads admitted Commander projections; borrows surface previews |
| `GameplayDrawer` | Handle, visibility, direction, focus, reduced motion and input suppression | No game/session/command dependencies |
| `GameplayActionDrawer` | Decision attention and session reset | Wraps the existing authenticated `ViewerDecisionPanel` |
| `GameplayPriorityDrawer` | Priority attention and visibility binding | Wraps `UnityPriorityControls` and its existing policy |
| `GameplayZonePanel` | Per-seat library, graveyard and exile pile composition | Existing `ZonePile` emits owner/zone requests to the authorized `ZoneBrowser` |

The launch manifest's `format` is passed through the existing private viewer
bootstrap and `ViewerSessionHost.GameplayFormat`. It is optional for older
bootstrap fixtures. Missing context displays general player information only;
life totals and card contents never determine the format. `commander` and
`unrestricted_commander` enable Commander information. The presentation applies
no deck-construction restrictions. Names are projected from already-authorized
snapshot player records, alongside the existing IDs and life totals.

HUD seats, Commander sections and zone banks are keyed by player ID. Multiple
commanders and damage recipients remain separate. The HUD has no battlefield
geometry; Arena supplies its left-rail placement. Targeting obtains the current
HUD seat collection rather than retaining a fixed two-player array. Combat and
animation anchors use these same elements. Arena's existing battlefield rows
still group non-viewer permanents together; this change does not introduce a
multiplayer battlefield layout or modify engine seat support.

## Drawer behavior and composition

Mount a `GameplayDrawer` under any view root, add an existing control to
`drawer.Content`, and set the root's position/size. Choose Left/Right/Up/Down for
the slide-out direction. `SetOpen`, `SetReducedMotion`, `SetAttention`, `Reset`
and `Dispose` have no command side effects. After rebuilding closed content,
call `RefreshInput` to suppress newly created descendants too.

Shared USS transitions animate translation/opacity for 230 ms with ease-out.
Reduced motion removes that transition and hides closed content immediately.
Closing disables the content subtree, removes it from pointer picking and
keyboard traversal, and moves contained focus to the handle. Reopening restores
previous contained focus when it still exists. Enter/Space activate the button;
Right/Down opens and focuses content; Escape collapses. Pending close callbacks
are cancelled on reopening, reset, detach and disposal. Child control values
and bindings survive ordinary open/close cycles.

Arena uses absolute overlays, so opening drawers never resizes card regions:

- Actions retain the right/bottom action position, centered opening-hand
  treatment and wide library-ordering treatment.
- Priority retains the top-right region, with its persistent handle above the
  existing controls. Its body scrolls when necessary.
- Zone banks retain their original pile coordinates (opposing bank at x=22/98/174,
  y=150; local bank at y=max(350, height-242)). The Zones handle sits below the
  banks on the left edge. Empty space between banks does not intercept pointers.

New non-priority decisions open Actions once per decision ID and keep an
attention badge if the player collapses them. Failed/uncertain decisions also
surface attention. The Priority tab shows paused/manual states while closed.
Opening Priority alone does not pause automatic passing. Its inner yield/stops
editor creates the existing editing hold only while visible. Collapsing releases
that temporary hold without resetting the foldout, manual/automatic preferences,
yields or phase stops. Paused policy state still requires the existing Resume
control. The opt-in acceptance driver opens the same action handle before using
its controls.

Libraries always use concealed presentation. Piles borrow only admitted artwork,
never infer top-card order, and route browsing to the existing authorized browser.
Session handoff clears seat/pile bindings, attention and pending animations;
disposal unhooks component bindings. The alternative Table view also clears its
HUD when its surface epoch ends.

## Verification and remaining review

Actions runs all tests; local suites must not be run. Coverage added here includes:

- Private format validation and Freeform/Commander/Unrestricted Commander HUD
  visibility, including missing format and partners with multiple damage recipients.
- Explicit IDs with matching names, seat removal/session rebinding, and an actual
  authenticated player-target command from an independently mounted HUD.
- Repeated drawer cycles, disabled commands, replacement content, keyboard focus,
  reduced motion, retired close callbacks, disposal and alternate roots.
- Priority preference preservation, mandatory-choice attention, command-free
  drawer toggles, and an actual single automatic pass with both drawers collapsed.
- Concealed library presentation and bounds at 1280x720, 1366x768, 1920x1080 and
  2560x1440. Updated existing Arena coverage checks unique HUD seats instead of
  the removed centered legacy overlays.

`GameplayDrawerLayoutTests` writes expanded fixture screenshots to
`Artifacts/HudDrawers/expanded-WIDTHxHEIGHT.png`; the Unity workflow uploads them
alongside its exact-revision record. These fixtures supplement the existing real
opening, targeting, stack, browsing and human-versus-AI acceptance checks.

Compile-only imports and lint do not establish passing gameplay or visual
acceptance. Review exact-SHA Actions results, those screenshots, actual animation
smoothness, opening/mulligan/library-ordering interactions, and real Commander
sessions before treating the story as visually accepted. Missing hosted Unity
licensing or unavailable captures must be reported as unverified. Rebuild the
local delivery player only after the exact source revision's CI is reviewed, in
accordance with `development-workflow.md`; preserve previous builds and logs.


## Stable drawer handles

Arena handles remain anchored independently of their body height. Actions stays
at the bottom right even when opening-hand, library-ordering or ordinary choice
content changes size; those body layouts retain their own positions. Zones keeps
its left-edge handle fixed while the pile banks change. Each handle carries a
code-drawn tray and open/closed chevron. The zone drawer is 252 pixels wide to
accommodate all three pile columns and the vertical scrollbar, and disables
horizontal scrolling. Layout coverage checks handle bounds through content
growth, collapse/reopen and the four desktop sizes, plus the zone viewport width.

# Expanded battlefield geometry

`GameplayCardLayout.BattlefieldGeometry` derives four row anchors from the desktop height, compact card extent, land fan clearance, and the normal hand top. Card widths stop at 110 pixels; extra desktop width increases capacity instead of card size. The 280-pixel left boundary protects the existing player and Commander rail. The right edge now leaves 24 pixels instead of the former 165, recovering 141 pixels. Lands no longer leave an unused central seat gap. Opponents continue to share rows; this is not a complete multiplayer seat composition.

Only active stack content reserves horizontal space beside the two permanent rows. Focused stack presentation remains a temporary overlay. Drawer visibility is not an input to battlefield geometry, and drawer transitions do not invoke battlefield layout. Existing land stacks, attachment placement, view ownership, animations, and input controllers remain in use.

## Hosted evidence

`GameplayDrawerLayoutTests` checks geometry at 1280x720, 1366x768, 1920x1080, and 2560x1440. Its rendered fixture includes 96 battlefield cards across three players, partner Commander information, a hand, and a stack. It compares individual card coordinates, dimensions, visibility, and pagination across each drawer transition. Existing targeting, drag, inspection, combat, grouping, and animation suites remain required.

The Unity workflow uploads `Artifacts/HudDrawers` in its SHA-labelled artifact. Images named `battlefield-previous-fixed-margins-*` reconstruct the former battlefield geometry with the same fixture and current HUD (not a historical full-player capture). `battlefield-collapsed-*` and `battlefield-*-drawer-*` show the new geometry and individual overlays. Existing `expanded-*` images show simultaneous overlays. Captures require hosted execution and visual review; source changes or compilation do not establish visual or playable acceptance.

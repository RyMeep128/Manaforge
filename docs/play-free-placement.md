# Direct battlefield placement and compact drawers

Normal Play uses organization v4. Existing versions remain strict and unchanged.
No gameplay command, rules zone, canonical card owner, or artwork owner is added.

## Interaction contract

- A normal left-button drag moves an owned, admitted battlefield permanent after
  the existing 10-unit movement threshold. No Shift key or layout editor is needed.
  Before that threshold, a click/double-click follows the existing board action.
- Mandatory targeting, mana selection, combat declaration, hand casting, embedded
  card controls, inspection and public-zone browsing retain their existing paths.
  Unknown/hidden cards and opponents' permanents cannot be organized.
- The borrowed card follows the pointer in its existing parent. Capture cancels
  the original board gesture before the organization drop; it cannot also tap,
  cast, activate or declare combat. Card and tab listeners forward captured events
  directly and unregister on disposal. Escape, session/offer retirement, capture
  loss and leaving the uncaptured surface cancel the preview.
- Empty-space release sends a single `place` command. Dropping into an owned
  group/drawer sends the existing `move` operation; closed drawers accept drops
  on their header without opening. Dragging a member out places it at the root.
- Dropping onto another owned stationary permanent prompts for a name. The host
  acknowledges create, drawer conversion and both memberships in sequence. The
  drawer header is anchored at the stationary permanent's previous top-left.
  No membership is committed before naming; Close/Escape cancels that prompt.
- Card-on-card dragging is the only group creation entry point. Right-click, G,
  menu creation buttons and empty-space selection drops do not create groups.
  The naming popover has a card count, Name, Create drawer and Cancel; Enter
  confirms and Escape/outside click cancels. Position clamps keep containers
  inside the viewport. Creating a group does not leave assignment mode active.
- Headers contain only the name and an adjacent ellipsis menu. Name click toggles
  locally; name drag moves shared geometry. The menu exposes member inspection
  and owner editing. Counts/attention details remain in tooltips and the existing
  attention border; there is no permanent Members or move button.

## Shared state and compatibility

`organization-v4.schema.json` adds `placements` to each seat and the `place`
operation. A placement has a viewer-scoped admitted handle and integer x/y in
0-1,000,000. Coordinates normalize the card's top-left against the available
viewport minus its size. Each placement must name a unique root member of that
seat; parsers reject grouped, unknown or duplicate placement handles. Generated
Java/C# contracts come from `tools/generate_play_models.py`.

The pure Java service stores positions by server incarnation, separately from
ordered root membership and groups. `place` atomically removes an eligible owned
member from its prior group, retains it as an individual root object and sets its
position. Group membership clears the free position. Reconciliation preserves
surviving eligible incarnations, and drops positions on departure, concealment,
control change or replacement. Shared snapshots translate only admitted objects
into each recipient's references. Retry receipts, exact gameplay correlation,
authority, bounded messages and reconnect reconstruction use the existing ledger.

V4 sessions select one version across recipients. The normal endpoint, multiview
bridge, private bootstrap and Unity mailbox understand v4. Existing v1/v2/v3
callers keep their previous formats; no version is inferred from packets. The
low-level launch default remains opt-in. HUD expansion and presets remain local.

## Rendering work on state updates

Retained CardViews keep their resolved mode/size across same-zone publications.
New cards and zone changes still initialize geometry; Arena remains the placement
owner. `SetPresentation`, selection and unchanged display values skip redundant
layout work. Real display changes, artwork rebinding and concealment still update
normally. Java and C# organization validators reuse immutable parsed schemas
instead of reparsing whole schema documents on every packet. These changes remove
identified sources of update-time work; no claim of a measured frame-time target
or elimination of every possible hitch is made without a profiler capture.

## Verification and rollout

Use GitHub Actions for suites. Added coverage includes v4 schema bounds, outgoing
version admission, duplicate/unknown/root placement validation, two-recipient
fanout/privacy, authority, reconnect and retry, incarnation/control changes,
normal native-game placement with zero rules submissions, direct captured-card
movement, closed-drawer drops and the create/convert/membership sequence. Native
multiview checks also run under v4. Existing targeting/mana/board/menu coverage
continues using those interaction paths. Saved-deck acceptance selects the same
v4 path as desktop Play. Full-game acceptance is separate from fixture success.

Focused live verification on 2026-11-17, at 1920x1080 using saved Grixis Affinity
versus Goblin decks: played Great Furnace normally, dragged it to empty space,
then played Vault of Whispers and observed the first position survive the rules
update. Dragging Vault onto Furnace prompted for a name and created a drawer
containing both at Furnace's former position. Click collapsed/expanded both cards;
name drag moved the drawer. Dragging Vault out placed it freely; dragging it back
onto the collapsed name added it without opening, and expansion exposed both.
This establishes that focused local flow, not a complete game or live multiplayer
session. A fresh player after the final rebuild showed the full Mana lands name
and a horizontal ellipsis next to it; dragging that name moved the drawer.

Manual regression scenarios:
1. Repeat with a tapped permanent; confirm a quick click still uses the existing
   tap/action path and dragging never changes tapped state.
2. Shift-click a selection and drag it onto another owned card to create a drawer
   at that stationary card. Confirm empty-space drops, right-click and G do not
   create groups. Cancel naming and confirm membership/positions remain unchanged.
3. Drag near each viewport edge and resize through 1280x720, 1366x768, 1920x1080
   and 2560x1440. Verify positions remain accessible and drawers still toggle.
4. Exercise targeting/mana and attacker/blocker declarations with collapsed
   groups. Inspect individual members through the ellipsis menu.
5. In authenticated multiview play, move a card, reconnect the opponent, then
   change control/zone. Check shared positions, local expansion and cleanup.
6. Capture Unity CPU/UI Toolkit profiler frames while passing priority repeatedly
   on a crowded battlefield; compare publication and layout costs to the prior
   build. Check changed counters, text, artwork and zone changes still repaint.

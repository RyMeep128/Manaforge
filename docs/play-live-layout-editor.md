# Live drawer layout editor (CT-05A)

CT-05A adapts Priority, Spells & Abilities, Zones, and Commander drawers to the
container infrastructure. It is implemented behind the existing presentation-local
`PrivateLayout` capability. The ordinary live composition continues to use the
disabled default until hosted Unity and gameplay acceptance are available. There
are no new launch arguments, profile settings, protocol changes, or shared layouts.
[CT-06 recovery and acceptance](play-layout-recovery.md) adds viewport recovery and
an independent Reset Layout for This Game action.

## Composition and ownership

Construct `ArenaGameplayPresentation` with
`new GameplayPresentationCapabilities(privateLayout: true)` in a trusted acceptance
composition. `Bind` creates its editor; `LiveGameScene` passes that editor to the
existing Escape Menu. Other presentations and the default constructor are unchanged.
An optional `ILayoutPresetStore` constructor dependency permits isolated acceptance
fixtures without touching a player's files. Production uses the existing JSON store.

The two review boundaries are:

1. `IGameplayContainerBinding`, live non-owning adapters, registry bindings, and
   shared gesture/preset infrastructure. Existing synthetic shells implement the
   same interface; their content ownership and conversion behavior are unchanged.
2. `HudLayoutEditor`, explicit live preset operations, menu composition, and the
   presentation-only decision/input gate.

Adapters keep the exact `GameplayDrawer` and its content in their original parent.
Commander coordinates are converted through the current player HUD parent. Disposal
removes adapter handles and callbacks, restores inline styles, and clears its registry
binding; it never disposes the drawer, its controls, cards, or artwork. The existing
owners retain attention, expansion, reduced motion, actions, and cleanup.

Default USS and legacy formulas remain authoritative for every drawer without an
override. Arena skips covered inline writes for custom drawers and invokes the editor
at the geometry application boundary. Returning to Default removes overrides instead
of substituting a frozen approximation of the legacy layout. Temporary required-choice,
opening, and library-ordering presentation uses legacy geometry. Headers remain 30
pixels high; custom bodies expand toward available room, with constrained scrolling.
All headers are clamped into the viewport, including overflow dock rails. Only viewport
edge docking is enabled; conversion, nesting, hand, battlefield, stack, and player-life
layout editing are excluded.

## Transactions and interruption

Escape Menu -> Customize Layout closes the menu and opens the editor. Move drawer
handles, resize their expanded bodies, or use the keyboard/control buttons. Arrows
move eight UI units; Shift+arrows resize. Dock controls select viewport edges;
Earlier/Later reorder siblings. Tab remains inside editor controls and handles.
Unavailable Commander handles cannot be edited.

Apply commits in memory and leaves editing open for explicit saving. Cancel exits
and restores the last applied geometry and expansion; Apply followed by further edits
and Cancel keeps the applied version. Restore Default stages removal of overrides
and requires Apply. Escape cancels an active gesture first; another Escape cancels
editing. Pointer capture loss, viewport changes, and teardown cancel active gestures.

The editor blocks underlying pointer, keyboard, focus, and navigation input. A
presentation-only decision gate also suppresses spatial actions and holds automatic
priority passing without changing yield preferences or offer validation. The match
continues receiving state. `LiveGameScene` checks interruption before decision Tick,
and again afterward for newly observed command failures.

Required local choices, reveals, uncertain/unavailable commands, disconnect, and
opening/library-ordering flows suspend editing. Suspension restores committed layout
and releases the gate; mandatory choices regain their existing drawer and focus.
The draft stays in memory and the menu offers Resume Customization when eligible.
Resume is explicit. Session/viewer replacement, game end, viewer cleanup, and editor
disposal discard retained drafts. Opponent updates alone do not suspend editing.

## Live presets

Live data uses `Application.persistentDataPath/profiles/default/layouts/arena/presets.json`.
The synthetic fixture retains its separate `layouts/fixture` store. Stable live keys
are `hud.priority`, `hud.actions`, `hud.zones`, and `hud.commanders`; no seat, viewer,
card, or session identities enter the file.

Stage preset changes only the draft. Apply does not write files. Save and Save As
remain disabled with unapplied edits; explicit saves remember the selected preset
for startup. Rename applied and Delete applied operate on the applied saved preset,
not an un-staged dropdown choice. Delete requires a second explicit confirmation and
keeps the applied layout. Refresh list reloads storage metadata without applying it.
Use Save As with a new name after applying Default to remember the legacy layout.

Only overridden known components are captured; absent components retain dynamic
legacy placement. Unknown fields/components and unavailable Commander entries are
preserved. Commander geometry loaded before format availability is applied when the
binding becomes available. Existing revision-conflict, backup, corrupt-file recovery,
unsupported-schema, size-limit, and asynchronous IO behavior comes from the CT-04
store. Failures leave current geometry intact and expose storage status. There is no
autosave, including Cancel, suspend, viewport changes, or session teardown.

## Register another participant

Supply a stable descriptor ID, display name, default slot, and opt-in authored preset
key. Register the owner's existing element; implement `IGameplayContainerBinding`
against that same element and attach it with `SetContainerBinding(binding, capabilities)`.
The registration rejects a mismatched element before mutation. Expose only operations
the binding implements. Register default normalized intent and constraints with the
controller; allowed targets and capabilities remain local, never supplied by a preset.
Provide handles in the editor layer, preserve the real view hierarchy, and implement
expansion restore plus a disposal notification. Unregister/detach the adapter before
its underlying owner disposes its view. An entirely new component can reuse gesture
and preset logic without adding an Arena-specific branch to either subsystem.

## Verification and release gate

`LiveHudLayoutEditorTests` covers draft/apply/cancel, explicit interrupted resume,
session clearing, capability gating, no conversion, storage isolation and failure,
partial preset capture, unknown/dormant components, non-owning lifecycle, blocked
underlying input, focus restoration, default geometry in an opted-in Arena, and
reachable headers at 1024x768, 1280x720, 1366x768, 1920x1080, 2560x1440, and 3440x1440. Existing container,
preset, drawer, board-input, mana-source, targeting, and menu tests remain in the
hosted Unity suites.

Implementation is on main; candidate hosted acceptance is pending. Local Windows player builds and editor/test
assembly compilation are compile evidence only; no local test suites are run.
There is no exact-SHA hosted evidence for this worktree. Hosted Unity licensing and
the previously observed native-payment failure are inherited acceptance gaps, not
passes established by this implementation. Do not enable the ordinary live capability
until Unity, protocol, native gameplay, and normal saved-deck human-versus-AI evidence
passes on the candidate SHA. A fixture/build pass does not establish full-game acceptance.

### Reproducible manual acceptance

Use an acceptance composition with PrivateLayout enabled and an isolated store.

1. Start a normal saved-deck human-versus-AI game. Finish opening choices. Open
   Customize Layout; move and resize each available drawer, dock two to one edge,
   reorder them, Apply, then change another drawer and Cancel. Confirm only applied
   changes remain. Verify the unchanged default with Restore Default/Apply.
2. Repeat at all six sizes above, including resize while dragging. Check every tab
   is reachable and expanded content scrolls. Verify keyboard-only editing, focus
   return, Escape gesture cancellation, and reduced motion.
3. Stage a preset, Cancel, reopen, stage again, Apply, and Save As. Restart the
   presentation and verify the saved selection. Rename/delete the applied preset;
   verify deletion keeps current geometry. Exercise a second writer conflict and
   unsupported/corrupt files; gameplay must remain usable.
4. Edit during opponent activity. Cause a required local target, mana, number, or
   library-ordering choice, and a required reveal. Confirm editing suspends, committed
   geometry returns, and the choice/reveal is accessible. Complete it, then explicitly
   Resume Customization and verify the draft. End/disconnect the session and verify
   that the draft and gate are cleared.
5. With moved drawers, cast spells using automatic mana payment, manually select
   mana sources, activate abilities, pass/yield priority, inspect/target permanents,
   resolve stack objects, attack/block, and browse public zones. Finish the game.
   Repeat Commander-specific inspection/casting and a non-Commander game where the
   Commander preset stays dormant. Verify Escape Menu options and concession.

Record candidate SHA, exact run links, outcome, screenshots, and inherited failures
separately. Keep the production capability disabled when any required evidence is
missing, unavailable, skipped, or failing.

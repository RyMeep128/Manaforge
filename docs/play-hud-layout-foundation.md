# HUD registration and default layout foundation

CT-01â€“02 implementation, 2026-11-10. Internal extension points only: there is no
Customize Layout UI, geometry persistence, grouping or protocol change in this slice.
See [the epic](customizable-tabletop-epic.md) and [workflow](development-workflow.md).

## Baseline and compatibility boundary

The implementation started on `main` at
`b97f4914dba3847036fa6094603280f826a63aea` with uncommitted gameplay work already
present. That work includes Arena input, targeting, player display controls,
Escape menu/concession, Java payment/session/engine integration, protocol/schema
changes, acceptance drivers and the Unity workflow. These existing changes were
preserved; this slice does not independently establish their correctness.
No baseline suite was run locally, in accordance with repository instructions.

The baseline scenarios to retain are: opening/mulligan, normal hand paging and
inspection, automatic/manual/full-control mana payment, deliberate spell casts and
activated abilities, priority passing/yields, focused/minimized game stack,
mandatory choices and library ordering, public zone and attachment browsing,
target selection, combat assignment/damage/cleanup, Commander format gating and
information, drawer attention/input/focus/reduced motion, menu/concession, viewer
switch/termination and private resource cleanup. Existing dense drawer layout
coverage includes 1280Ã—720, 1366Ã—768, 1920Ã—1080 and 2560Ã—1440.

Rules, card-view/artwork lifetime, current-offer admission and command dispatch stay
with their existing owners. Static USS placement is unchanged. The only production
strategy is `LegacyGameplayLayoutStrategy`; it computes the pre-existing formulas.
Arena applies the plan while retaining card filtering, attachment relationships,
paging, rendering, class changes and interaction sequencing. Its layout context
contains viewport size, opening state, game-stack focus and library-ordering state.
Public browsing geometry is always resolved but only applied by existing browsing
logic. No new strategy changes the live table.

## Registry and ownership

`ArenaGameplayPresentation.HudRegistry` is presentation-local. Descriptors supply
stable family ID, display name, default slot, current capabilities and optional
parent ID. Registrations bind an existing VisualElement, a logical layout adapter,
or both. Unregistering (including registry disposal) removes metadata only: no
view is detached/disposed and no event is installed. Existing view owners still
perform their original cleanup. Registration handles are idempotent and cannot
remove later registrations reusing their ID.

Hand and battlefield use logical geometry adapters because their cards share the
surface-owned root. The game stack binds its toolbar plus logical card region.
Player and Commander families are registered by GameplayPlayerHud; per-seat child
registrations use length-delimited session/viewer/seat keys and are removed before
view disposal, seat removal, or context replacement. They are not persistent preset
IDs. Commander registrations remain present but unavailable outside supported
formats and after presentation clearing. Library/graveyard/exile are logical
family descriptors bound to their existing shared zone panel, not per-pile owners.

Only the existing drawer shell is advertised as a component capability. No move,
resize, dock or drawer-conversion capabilities are advertised. Immutable
GameplayPresentationCapabilities are constructor-local future feature gates, all
false by default; they currently enable no controls, transport or alternate path.
They do not authorize commands or assert remote feature support.

## Adding a future component

Create/bind the view through its normal owner, then register it without modifying
Arena-specific registry code:

```csharp
var registration = registry.Register(
    new GameplayHudDescriptor("example-status", "Example status", "status-rail"),
    existingStatusView);
registration.Available = hasStatusContent;
// Before the view owner disposes/replaces its view:
registration.Dispose();
```

A logical region uses `GameplayHudLayoutAdapter` and an explicit plan slot instead
of reparenting shared CardViews. Add a slot/plan field when introducing a genuinely
new region. A future strategy implements IGameplayLayoutStrategy and returns an
immutable GameplayLayoutPlan; introducing strategy selection is separate work.
DefaultSlot is metadata, not a competing placement writer. Registry IDs must be
unique; a duplicate fails before modifying the registry. ParentId is descriptive
hierarchy only and does not reparent any Unity element.

## Verification and open acceptance

New hosted coverage: GameplayLayoutStrategyTests freezes pre-extraction geometry
for normal/opening/focused-stack/ordering/browser states at the four baseline sizes.
GameplayHudRegistryTests covers duplicate atomicity, generic extension registration,
non-owning unregister/disposal, format availability, dynamic seat removal and
session replacement, family bindings and presentation cleanup.

Existing drawer, surface, targeting, board/mana input and menu tests remain the
interaction regression coverage. The registry installs no callbacks. New tests are
under the existing Manaforge.Play.Tests namespace and EditMode/PlayMode assemblies,
so the existing Unity workflow test filter includes them without workflow changes.

Required hosted evidence after an authorized commit/push:

| Workflow | Evidence needed |
| --- | --- |
| unity-play.yml | Licensed EditMode/PlayMode including new tests, player build, default screenshots, native automatic/manual payment, choice variants, saved-deck human-versus-AI play and menu regression |
| play-protocol.yml | Shared fixtures, generated-model consistency and Java admission/session checks; distinguish pre-existing protocol changes |
| play-payment-native.yml / play-live-opening.yml | Native payment and engine progression regressions where applicable |
| tests.yml | Python/Core/play/launch regressions; packaging when requested/applicable |

No commit/push was requested, so this working tree has no exact-SHA hosted test
result. No test suite has been run locally. Hosted tests, screenshots and complete
gameplay acceptance remain pending; historical results are not substituted.
Local rebuild: `./tools/unity-play.ps1 -Mode Build` completed successfully with
exit code 0 on 2026-11-10. Evidence: `Mtg_Projects/mtg_play_unity/Artifacts/build.log`
and the rebuilt `Builds/Windows/ManaforgePlay.exe`. This proves the player build,
not hosted suite success or visual/full-game acceptance.

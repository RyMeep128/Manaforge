# Unity Play

Unity is the gameplay UI and Java/XMage owns rules and decisions. Python handles
saved-deck and artwork preparation, pinned engine provisioning, and process
startup/cleanup. The Python gameplay adapter and Qt game table are retired.

## Start a game

1. Build the Windows Unity player using the [Unity project guide](../Mtg_Projects/mtg_play_unity/README.md).
2. Open Manaforge from source and select Play. Choose Freeform or Commander,
   your saved deck, the AI opponent's deck, and a mana-payment preference.
3. Click **Start Game**. Close the Unity window to end the session. Closing
   Manaforge also requests cleanup of its owned game processes.

Returning to Play reloads saved decks. The desktop has no separate Python game
or Unity preview launch buttons. Diagnostic preview tooling remains available to
developers. Installed builds retain the release gate; the source override is
`MANAFORGE_ENABLE_LOCAL_PLAY` (enabled by default).

## Reusable visual elements and views

The current Arena-style table is the **default 1v1 view**, not the universal
layout. Other views compose the same elements around the same authorized session
projection. This is the current direction for the custom-element visual overhaul;
the shared components and default composition are implemented below. Owner visual
approval and Unity Actions execution remain separate acceptance requirements.

### Existing foundations and gaps

`IGameplayPresentation` and `LiveGameScene.SetPresentationFactory` already allow
alternate presentations. `ArenaGameplayPresentation` is the default factory;
`TableGameplayPresentation` is another implementation. Preserve that seam.
`SeatLayout` provides separate seat-count geometry, but is not a complete
alternative gameplay composition.

`CardView`, its typography/symbol/frame helpers, `ViewerCardSurface`,
`ViewerDecisionPanel`, `ViewerBoardInput`, and `BattlefieldLinks` provide existing
reusable foundations. Extend them rather than creating a second rendering,
artwork, interaction, or dispatch pipeline.

The Arena presentation now composes `PlayerPanel`, `ZonePile`, `ZoneBrowser`,
`GameplayOverlay`, and the shared `GameplayCardLayout` helpers. `GameplayTheme`
and its stylesheet supply component appearance independently of `ArenaTable.uss`,
which retains default 1v1 placement. `GameplayTableSurface` supplies an original,
decorative slate/metal material. The default view explicitly rejects extra seats
instead of combining every non-viewer player into one opponent.

Library motion resolves source/destination anchors by explicit player ID. It no
longer chooses a fixed local/opponent label, loads an Arena motion resource, or
updates library counts itself. Overlapping seat flights finish independently;
revision changes, detachment, disposal and reduced motion cancel movement.

The shared forged theme uses slate panels, metal edging, ember primary actions,
cyan focus/target accents, and text for priority and command states. It requires
no supplied Arena backdrop, button skins, name backer or sleeve. Existing card
rendering, selected printing identity and optional card-font/art resources remain
on the established pipeline. Printed card frames have not been redesigned.

### Ownership

| Layer | Owns | Receives from its caller |
| --- | --- | --- |
| Session and projection | Authorization, revision validity, artwork lifetime, authoritative state and command admission | Existing transport/session inputs |
| Shared visual elements | Rendering, accessible focus/input, local visual state, event cleanup | Explicit player/object/zone IDs, admitted display data, semantic actions, bounds and style |
| Layout/composition | Seat ordering, orientation, regions, sizing, paging placement and overlay anchors | Viewport, viewer identity, available seats, shared element instances |
| Theme and motion | Colors, typography, textures, component states, animation timings and reduced-motion behavior | Semantic style roles and geometry endpoints |
| Presentation selection | Constructing and disposing the selected composition | Supported session/view context and explicit factory choice |

A view can own its geometry. It must not own a private copy of a life plaque,
zone-pile renderer, card renderer, or command implementation. Shared elements must
not discover "the opponent," assume top/bottom seats, select a scene singleton,
load a particular view's stylesheet, or query engine/private deck state. Use
stable IDs rather than labels, dictionary order, or child names to identify seats
and zones. Theme selectors must work under any composition root.

### First extraction: player panel and zone pile

The life/name/priority/target plaque is a reusable player panel bound to one
explicit player ID. Library/graveyard/exile rendering uses a zone-pile element
bound to an explicit owner and zone. Keep supported zone
semantics explicit; arbitrary zones need not share identical behavior.

The 1v1 composition creates two player panels and the relevant zone piles, then
positions them. Shared elements receive projected life/count/visibility/target
state and emit semantic requests through the existing authorization and dispatch
path. Browsing requests identify owner and zone; player targeting retains the
current decision binding. A library shows only permitted counts and card backs;
unknown values remain unknown. Rebinding or revocation clears images, targets,
focus, callbacks and pending visual work.

The zone browser, hand/rank paging helpers, and inspection/overlay placement
are also shared; caller-supplied bounds and reserved intervals control geometry. Movement receives source/destination anchors for an explicit seat;
its visual adapter may observe authorized changes but never infer hidden card
identity or issue gameplay commands. Preserve existing motion cancellation and
reduced-motion behavior. Avoid building a general plugin or layout framework.

### Acceptance for each extraction

- Mount the same element under two distinct composition roots with different
  geometry/theme contexts; no Arena parent selector or scene lookup is required.
- Exercise two explicit non-viewer seat IDs independently in fixtures. Updating or
  targeting one must not update or target another. This demonstrates component
  reuse, not multiplayer engine or launch support.
- Preserve the default 1v1 composition and existing presentation-factory override.
  Do not silently use a two-seat layout for an incompatible seat topology; route
  it explicitly or report unsupported presentation without dropping extra seats.
- Check keyboard/pointer equivalence, unknown/concealed state, new revisions,
  rebinding, disposal and active-animation cleanup. Retain one authoritative
  surface and dispatch path; view changes cannot bypass pending-command guards.
- Run relevant Unity coverage in GitHub Actions. Review the default view visually
  at the existing desktop sizes, including missing optional assets, crowded zones
  and reduced motion. Record owner approval separately from geometry checks.

The archived [composable card requirements](archive/play-composable-card-rendering.md)
retain earlier card-rendering detail. For current live artwork authorization and
identity behavior, use the current implementation references and exact-revision
evidence; archived fallback proposals are not new runtime policy.

## Review the forged theme

Build the Windows player, then run the synthetic review from the repository root:

```powershell
./tools/unity-play.ps1 -Mode Build
./tools/capture_play_style.ps1
```

For interactive component review, run the built player with
`-manaforgeStyleReview 1`. The component sheet and side-by-side/multi-seat
compositions use the same components with explicit synthetic seat IDs. Controls
only display fixture requests; they never start a game or submit a command.
The capture script also mounts the default 1v1 composition with synthetic card
projections and intentional missing-art fallbacks. It records requested/observed
sizes and captures 1280x720, 1366x768, 1920x1080 and 2560x1440 in a unique ignored
`Artifacts/ForgeStyle-*` directory. This is visual evidence, not live gameplay
or human-controlled acceptance. Historical or uncommitted capture revisions are
not represented as CI evidence.

Unity regression coverage includes identity isolation, unknown counts, hidden
library artwork, rebinding, disposal, mounting under independent layout roots,
overlay focus and extra-seat rejection, alongside existing surface/command and
four-resolution table tests. The manual Unity Actions workflow runs the suites,
builds the player and uploads synthetic style captures.

As of this implementation, the GitHub runner inventory returned no registered
self-hosted runners. Unity Actions requires an owner-controlled Windows runner
labelled `manaforge-unity`, a valid license and a graphics session. No local test
suites were run. Owner approval, Unity Actions results and current live-match
visual acceptance remain **pending**; synthetic captures do not close these gates.

## Acceptance and references

Use [the development workflow](development-workflow.md) for exact-revision CI
requirements. The Unity workflow is manual and requires a licensed owner-controlled
runner. Python/protocol checks, Java opening checks, fixtures, and historical local
reports each cover only their stated scope. Full playable acceptance, packaging,
and owner visual approval must be assessed separately.

| Topic | Reference |
| --- | --- |
| Launcher modules and ownership | [Play package](../Mtg_Projects/mtg_play/README.md), [launch lifecycle](play-launch-lifecycle.md), [launch manifest](play-launch-boundary.md) |
| Cross-language contracts | [Protocol index](../Mtg_Projects/mtg_play/protocol/README.md) |
| Live engine implementation journal | [Live integration](play-live-integration.md) |
| Payment and priority | [Payment coordinator](play-payment-coordinator.md), [priority behavior](unity-priority-passing.md) |
| Engine pin and card coverage | [XMage fork](play-xmage-fork.md), [card support](play-xmage-card-support.md) |
| Visual review | [Arena review](play-arena-visual-review.md), [renderer measurements](play-renderer-benchmarks.md) |
| Original plans and acceptance criteria | [Archive](archive/README.md) |

The implementation references describe individual increments. Their versioned
status statements and historical pass counts are not current-revision sign-off.
The [documentation index](README.md) lists the remaining renderer, artwork,
session, and diagnostic references.

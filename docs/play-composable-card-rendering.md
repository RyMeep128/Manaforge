# P3.2a — Composable Unity Card Rendering

Project: Manaforge Play. Status: **Planned; implementation and acceptance pending.**
Priority: **P0**, required for the initial local 1v1 experience.
Placement: Phase 3, after P3.2 (Printings), before P3.3 (Interaction).
Parent: [Unity + Java roadmap](play-unity-java-roadmap.md).

This document specifies future implementation. Its addition does not establish
renderer, artwork, protocol, performance or CI completion.

## Objective

Build one reusable Unity card-rendering foundation assembled from independently
updateable artwork, name, mana cost, type line, rules text, power/toughness and
frame components. Support ordinary standard-frame creatures, instants, sorceries,
artifacts, enchantments and lands, including monocolored, multicolored, colorless
and artifact frame distinctions. Support variable mana costs, symbols, creature
subtypes and rules text.

Provide compact cropped battlefield cards and full cards for hand, hover
enlargement and inspection. Keep the common pipeline extensible to future layouts
without implementing full-art, showcase, borderless, extended-art, sagas, battles,
planeswalkers, split cards or promotional frame reconstruction now. Unsupported
layouts must remain displayable through authentic card images.

## Existing foundations to inspect

Before implementation, inspect the parent roadmap, [Play epic](manaforge-play-epic.md),
[Unity README](../Mtg_Projects/mtg_play_unity/README.md), foundation scenes,
renderers, fixtures and tests; shared Java/C# protocol definitions; Manaforge's
printing identity and artwork services; and existing Play presentation, cropping,
asset loading, cache and missing-asset behavior.

Build on P0.3 rendering feasibility, P3.1 seat-independent scenes and P3.2 artwork
retrieval/caching. Do not introduce another downloader, card database, game-state
model or rules implementation. Deterministic mock data may support visual work
before the Java gateway is complete; label it explicitly.

## Component architecture

Use a practical `CardRenderer` with shared layout definitions, reusable Unity
prefabs, cached images and appropriate text rendering. Conceptual responsibilities:

```text
CardRenderer
├── CardLayoutProfile
├── CardFrameRenderer
├── NameRenderer
├── ManaCostRenderer
├── ArtworkRenderer
├── TypeLineRenderer
├── SetSymbolRenderer
├── RulesTextRenderer
├── PowerToughnessRenderer
└── CardOverlayRenderer
    ├── Counters
    ├── Damage
    ├── Selection
    └── StatusIndicators
```

These need not be individual MonoBehaviours. Components must be reusable across
supported types and update without recreating the entire card. Layout definitions
control geometry; printed identity controls frame treatment. Artwork and text
remain aligned when resized. The renderer must be independent of battlefield,
zone layout and player seat. New layout profiles must reuse the common pipeline;
avoid a generalized layout engine or elaborate plugin architecture.

## Presentation modes

**Compact Battlefield:** retain cropped artwork with name, current creature P/T
where applicable, counters, damage, selection/target highlights, tapped
orientation, attacking/blocking and other necessary compact status indicators.
Support creatures and noncreature permanents without assuming P/T exists. Do not
show the entire traditional frame or full rules box on battlefield objects.
Use deterministic, consistent, aesthetically reasonable crops that emphasize art.
Existing image-position metadata may help; do not couple gameplay cropping to
print-sheet crop settings.

**Full Card:** assemble the border/frame, name, mana cost, full artwork region,
type line, rules text, applicable P/T and available set symbol. Hand cards may fan
or overlap while retaining full-card appearance. Use this mode for large previews,
hover enlargement and inspection.

Both modes consume the same card identity and current game-state projection.
Switching modes must reuse textures/resources and avoid repeated downloads,
database queries or authoritative-state reconstruction. Retain separate optimized
layouts where appropriate. P3.3 owns interaction behavior.

## Printing resolution and authentic fallbacks

For a selected printing with an unsupported visual treatment:

1. Preserve its selected printing identity.
2. Search the existing Manaforge database for a compatible standard-frame printing
   of the same Oracle card and relevant face.
3. Prefer a compatible printing with locally cached artwork.
4. Otherwise choose a deterministic compatible standard printing.
5. Retrieve images through the existing artwork service only when downloading is
   enabled and permitted.
6. If no standard printing can be obtained, use the best available authentic image
   of the actual card, preserving the correct face.
7. If no image exists locally and downloading is unavailable, report the missing
   asset through the existing asset-handling path.

Never replace an available real Magic card image with a generic placeholder,
unrelated card, generic illustration, blank rectangle or fabricated artwork.
Unsupported layouts may use the original card image without claiming that its
text regions are dynamically reconstructable.

Keep these identities distinct, adapting field names to the existing contract:

```text
CardVisualIdentity
├── oracle_id
├── selected_printing_id
├── rendered_printing_id
├── rendered_face
└── layout_profile_id
```

Visual substitution must never overwrite selected printings or change legality,
rules characteristics, saved decks or XMage resolution. Preserve relevant face
identity for multi-faced cards; never silently show another face. Cache standard
printing resolutions and retain original assets for later layout support.

## Dynamic characteristics and text

Receive authoritative current name, type/subtypes, supplied rules/ability text,
P/T, supplied mana cost, counters, controller-relevant appearance and other
presentation state. Update components independently: a 2/2 reported as 5/5 changes
P/T without reloading art; supplied flying text updates the rules component;
copies update current visual identity while retaining underlying object and
printing information; expiring effects display the next engine-reported values.

Unity must not calculate P/T, infer granted abilities, interpret effects or invent
current state from printed Oracle text. Document missing Java protocol fields,
provide clearly identified mock support and make the smallest compatible protocol
extension where appropriate. Keep schema/generated consumers aligned.

Support long names, multiple paragraphs, ability line breaks, embedded mana
symbols, hybrid/Phyrexian symbols, variable mana values, basic rich text,
reminder-text styling where supplied, wrapping and P/T values/modifiers. Prevent
clipping and overlap; full cards must be readable at practical inspection size.
Compact cards need no full rules text. Presentation formatting must not become a
Magic rules parser.

## Performance and demonstration

Share cached textures, avoid decoding artwork on state changes, update only changed
values, minimize normal-frame allocations, and keep loading/database work off the
render-critical path where practical. Avoid structures that scale poorly to
hundreds of objects. Preserve smooth movement, tap rotation, selection and
enlargement for eventual three-to-five-player Commander boards.

Extend or create a deterministic Unity demo that runs without Java/XMage. Include
real representative card data and permitted artwork where available, multiple
standard types/colors, short/long names and rules, full/compact modes, battlefield
crops, normal/unsupported selections, standard-printing fallbacks, changing P/T
and rules text, counters, selection, resizing/enlargement, and multiple objects
sharing a printing with different current characteristics. Make launch and manual
UX review straightforward.

Preserve benchmark fixtures for approximately 20, 70 and 200 objects, following
P0.3 scenarios. Report actual frame-time/memory measurements and environment;
invent neither thresholds nor success evidence. If P0.3's measurement environment
is unavailable, explicitly leave the gate pending. A working demo does not
complete this story or P0.3.

## Automated validation

Add appropriate Unity EditMode and PlayMode coverage for:

1. Component/layout selection.
2. Selected printing identity preservation.
3. Standard-frame fallback resolution.
4. Correct face matching.
5. Offline cached-artwork behavior.
6. Independent P/T and rules-text changes.
7. Shared printings with different per-object characteristics.
8. Compact/full transitions.
9. Resizing.
10. Missing/unavailable assets.
11. Private information under the existing presentation contract.
12. Render-object cleanup and resource reuse.

Where an approved Unity environment supports it, add deterministic screenshots or
visual regression checks. Never silently replace baselines to pass tests. Respect
existing Unity licensing and build constraints. Relevant CI must pass before
completion is claimed; preserve existing desktop and Play integration behavior.

## Roadmap ownership and boundaries

- P0.3 retains feasibility and benchmarking; no retroactive completion.
- P3.1 retains table layout, seats and zones; it consumes reusable card objects.
- P3.2 retains artwork identity, retrieval and caching, including standard visual
  fallback resolution with original selections/assets preserved.
- P3.3 consumes compact/full rendering for hover, selection, tapping, drag, zoom,
  targeting and inspection. This story must expose those interfaces without
  implementing the entire interaction system.
- P5 polishes spacing, scaling, transitions and presentation using this foundation.
- P6.1 retains advanced characteristics, tokens, copies, attachments, transforms
  and complex permanents. Basic authoritative-value rendering moves to P3.2a.
- P6.2 retains advanced text correctness, layered effects and unusual-frame
  research. Basic authoritative dynamic text rendering belongs here.
- Phase 9 retains optional full-art/showcase/specialized reconstruction.

Do not rewrite Deck Editor, Card Database or Printer; introduce a Python gameplay
intermediary; duplicate XMage rules; build all frame treatments; add a second
artwork database/downloader; replace compact battlefield cards with full cards;
change saved printing preferences; assume one face/layout; require networking;
expose concealed information to unauthorized views; or replace working code
without inspection. Prefer a small, scoped implementation.

## Implementation workflow and handoff

Inspect current active branches and create a dedicated feature branch from the
latest appropriate Unity development baseline. Review the foundations above,
implement the smallest compatible architecture, and preserve versioning,
prerelease and pinned-engine practices. Focused local tests/compilation are
permitted; do not run the full suite locally. Add CI validation, review GitHub
Actions every third commit, and continue development while runs are pending.
Never weaken validation or silently change baselines.

Handoff must identify final commit, changed files, actual tests and CI status,
screenshots/artifacts where available, known limitations and remaining gateway
integration. Confirm reusable interfaces for P3.3 and later gameplay integration.

## Foundation progress — October 30, 2026

The Unity [offline printing policy](../Mtg_Projects/mtg_play_unity/README.md#offline-visual-printing-policy--foundation-increment)
now separates selected/rendered identities and selects deterministic cached
same-card/same-face standard or authentic image fallbacks. Eight focused policy
tests pass locally (16 total EditMode checks). This uses supplied catalog
metadata only. A host-side offline collector now reads the existing Core catalog
and exact-face local images, verifies decodability and conservatively classifies
ordinary 2015-frame printings. Eighteen collector tests pass locally. No Unity
asset delivery, downloader or texture cache is implemented; the component
foundation below has no real-artwork demo yet. Online resolution and CI remain
pending. The acceptance checklist below remains open.

The first reusable UI Toolkit `CardView` now exposes binding, independent value
updates, compact/full resizing and conceal/dispose interfaces. An editor-only
mock window demonstrates component structure without pretending artwork exists.
Eight component checks pass locally (24 total EditMode plus one existing
PlayMode scene check). Mana glyphs, frame treatment, real artwork transfer,
readability, screenshots and benchmark acceptance remain pending. This does not
complete the component or change any acceptance box below.

Attached-panel runtime coverage now checks actual UI Toolkit layout resolution,
mode changes, an empty viewer-handoff frame and detachment/resource ownership.
Three PlayMode checks pass locally with a shared default runtime theme. These
headless checks do not demonstrate rendered pixels, real art or readable fonts;
all visual acceptance and CI requirements remain open.

The [real-artwork fixture preparation](play-artwork-fixtures.md) now exports
existing cached public-card art as bounded raw RGBA resources with exact printing
and face metadata. Seven local demo cards have authentic art and standard
alternatives. Unity texture ownership/loading and the actual packaged renderer
remain pending; this is preparation evidence only and changes no acceptance box.

## Acceptance criteria

- [ ] Standard cards assemble from reusable Unity components.
- [ ] Full cards show real artwork, name, mana cost, type, rules and applicable P/T.
- [ ] Battlefield cards retain compact crops with live stats and indicators.
- [ ] Hand and inspection use full-card presentation.
- [ ] Unsupported special selections resolve to compatible standard printings when available.
- [ ] Original selected identities and correct faces remain preserved.
- [ ] Authoritative or explicit mock name, type, rules and P/T update independently.
- [ ] The renderer duplicates no gameplay rules.
- [ ] Artwork and textures are reused.
- [ ] Deterministic tests cover both modes and printing fallbacks.
- [ ] A Unity demo supports manual visual review without XMage.
- [ ] Benchmarks are recorded or explicitly pending.
- [ ] Relevant CI passes.
- [ ] Roadmap dependencies and revised P6 scope are documented.
- [ ] Existing Play integration and desktop modules do not regress.
- [ ] Interfaces support P3.3 and later gameplay integration.

Done means one reusable renderer accurately presents standard cards in compact
and full modes, preserves selected printing identity, uses authentic fallback
imagery and independently displays authoritative characteristics. It is ready for
1v1 battlefield/interaction milestones without implementing advanced frames or
complex multiplayer presentation prematurely.


## Owner visual feedback revision — October 30, 2026

Owner review requested a higher artwork crop, Magic-style framing, symbol mana
costs, framed compact names and a better P/T treatment. CardView now borrows the
exact rendered printing texture for the outer surround, uses beveled inset name/
type/P/T components, and hides empty P/T plates. Full-view interior masks prevent
printed text from showing through the independently supplied labels. Compact
cards retain a framed nameplate and more upper artwork; the diagnostic source UV
extends from (0.08, 0.45, 0.84, 0.38) to (0.08, 0.45, 0.84, 0.42).

ManaCostView uses the unmodified Mana v1.18.0 symbol font, pinned to upstream commit
6ca9e696d3bda2519dcf3eebd96598f84ad9ddd8, bundled offline with OFL and notices.
Colored/generic/variable/colorless/snow glyphs and two-part compound symbols are
presentation only. Unknown/malformed notation remains visible as literal text,
without rich-text interpretation or guessed glyphs. Compound symbols currently
use paired glyphs in one disk rather than exact diagonal printed treatments.
This does not implement inline rules-text symbols or final typography.

The outer frame and artwork share borrowed printing textures; views release both
references, symbol text and tooltips on conceal/disposal. Unsupported full-image
layouts retain the existing authentic-image fallback. These are standard-layout
fixture adjustments, not reconstruction of every printing frame. The owner's
new visual review remains required before acceptance boxes can be checked.
Prior benchmark results describe the earlier renderer, not this revision.


The packaged capture now uses depth/stencil for rounded clipping; a depthless
capture produced blank white cards and was corrected before handoff. The rebuilt
20-object capture contains the card frames, artwork, symbol costs and P/T badge.
The subsequent [owner-provided asset inventory](play-provided-art-assets.md)
confirmed candidates for a more faithful renderer. No supplied assets have yet
been imported into the tracked project; their next curation should replace
prototype treatments where appropriate. Visual acceptance remains pending.


Validation for this revision: 241 focused EditMode checks, four PlayMode checks,
the Windows development build, and the 20-object packaged artwork smoke passed.
The final 20-object capture was inspected for visible content after the stencil
fix; no final aesthetic approval is claimed. No full application suite ran. CI
review follows the owner's every-third-commit cadence; this is the first increment
after the prior checkpoint, so no new CI pass is claimed.


## Pip/name alignment and compact lower trim — October 30, 2026

Owner screenshots showed displaced mana glyphs, compact names off their plate
centerline and an exposed set symbol at the compact lower edge. The renderer now
removes inherited label margins, aligns title and mana row to the nameplate's
vertical bounds, and keeps symbol glyphs in normal weight with zero margins.
Compact printing surrounds sample only the upper 53 percent rather than 58,
removing the printed type/set-symbol region without changing full-card inspection
or object/printing identities. This remains a presentation adjustment, pending
owner review of the rebuilt fixture; provided-asset integration is separate work.


The compact lower strip is explicitly masked below the art window, preventing
underlying printing pixels from leaking around the cropped overlay. Validation
for this spacing-only revision uses the Windows build and 20-object packaged
artwork smoke; no full application suite or additional unit suite is run. Owner
visual approval remains pending. CI review is due after the next commit under
the established third-commit cadence; no CI pass is claimed for this increment.


## Dynamic P/T slot and footer/rotated-edge follow-up — October 30, 2026

Owner review found a reserved P/T cutout on noncreatures, obscured printed footer
credits and a thin printing leak visible when tapping a card. The full-view P/T
mask now follows supplied P/T presence, just like the badge: null removes the
slot, later P/T restores it without rebinding. No card-type or legality inference
is introduced. The reconstructed interior stops at 90 percent rather than 94,
leaving more of the original artist/collector footer visible.

Compact views have an overlapping lower mask and an explicit final rim overlay.
Selection now changes this overlay rather than the card's layout border, so
selecting/tapping does not move artwork within its clip. Concealment clears the
selection highlight. A focused EditMode transition check covers absent/present/
absent/present P/T, and the existing PlayMode interaction check now requires the
selected/tapped content rectangle to remain unchanged. These fixes remain subject
to owner visual review; provided-asset curation remains separate work.


Validation passed: 242 focused EditMode checks, four PlayMode checks, the Windows
build and the 20-object packaged gesture/benchmark invocation. The captured
fixture includes tapped cards and visible printed artist/collector credits. This
is fixture validation, not final owner approval or live gameplay. No full
application suite ran. CI is checked after this third commit, with unfinished
runs deferred rather than awaited.


## Upper rim review adjustment — October 30, 2026

Owner screenshots showed the top border intruding on the printed surround. The
compact top rim is now lighter than the side/bottom rim, and the selection stroke
is thinner. Corner clipping uses a smaller radius in both modes, retaining more
of the upper printing corners. Side/bottom coverage and the conditional P/T and
footer masks remain as before. This is a visual adjustment requiring fresh owner
review, not new renderer acceptance.


The owner supplied a close-up of the Forest footer during this review. Comparing
it with the actual rendered printing showed that the 90-percent interior boundary
left a visible strip of original textbox below the replacement. The standard
inset now ends at 92.3 percent, above the printed credits, and is narrower to keep
the original vertical outline visible. This is a measured standard-profile
adjustment based on that printing, not a claim of exact fit for every card frame.


Validation: Windows build and the 20-object packaged artwork smoke passed. A
local, ignored fixture copy places Forest first for a direct comparison with the
owner's two images; original fixture/source images are unchanged. The corrected
Forest capture was visually inspected for the lower strip, side outline and
visible credit lines. An earlier packaged gesture run also exercised the lighter
top rim. No full application suite ran; this visual-only increment adds no unit
suite run. Final visual approval remains with the owner. CI follows the owner's
third-commit cadence; this is the first commit after the last checkpoint.

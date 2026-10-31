# Owner-provided Wizards asset inventory

On October 30, 2026 the owner supplied the local folder
`C:/Users/ryanm/Downloads/Assets from Wizards, given with permission` and stated
permission to use its assets. The supplied folder remains unchanged and external
to the repository. This records that provenance, not independent verification of
the grant's wording. No asset bundle, DLL, configuration, audio or extracted image
from that folder is committed in this increment.

Read-only inventory found 28,617 files (about 13.86 GiB), mainly compiled Unity
`.mtga` bundles, plus an indexed JSON manifest. Relevant entries include card
base, title-bar, type-line, textbox, P/T, mana-symbol and field-font parts. These
are strong candidates for replacing prototype components, rather than importing
the supplied runtime into Manaforge.

Selective local decoding confirmed:

- `BELEREN2016-BOLD` in the Fonts bundle, alongside Minion and other fonts.
- `CDC_PowerToughness_Default_Green`, `_Black` and `_Red` textures (128 by 64).
  The green P/T texture was decoded and visually inspected as a beveled inset.
- `SDF_Icons_ManaCost_Symbols`, backs, SDF variants and alternate symbol sheets.
- Card base/title-bar/type-line component entries in the source manifest;
  their complete standard texture/material dependencies are not yet resolved.

Inspection used UnityPy 1.25.4 installed only under ignored Artifacts, not in the
application dependencies. Some bundles suppress their Unity version; decoding
used an explicit 6000.3.14f1 fallback taken from the accompanying serialized player
files. This is a parsing assumption, not proof that every bundle uses that version.
Local decoded samples and inventory live under
`Mtg_Projects/mtg_play_unity/Artifacts/AssetInspection/` and are not tracked.

Next integration should curate ordinary frames, compact/full nameplates, a P/T
box, mana sprites and the required font resources, preserving source bundle/path
IDs and hashes. Rebuild Manaforge-owned components around those resources; avoid
a dependency on supplied gameplay code or shaders that have not been adapted to
our URP/UI Toolkit pipeline. SDF atlases require glyph metadata/material handling,
not just importing their PNGs. Keep XMage, native decks, viewer privacy and the
public game protocol unchanged. A fresh owner visual review will be required
when the imported components are wired into the fixture.


## Specialized card parts — October 30, 2026

The owner confirmed the same Downloads folder for specialized-layout inspection.
The manifest and selected bundles were read directly; the original folder remains
unchanged. Decoded local inventory is in ignored
`Artifacts/AssetInspection/special-layout-inventory.json`.

| Need | Confirmed resource | Integration help |
|---|---|---|
| Planeswalker | LoyaltyPart: `LoyaltyBox - Default`, `Card_Loyalty`, `Loyalty Label`; RulesTextComponent: `LoyaltyAbility`, plus/neutral/negative entries | Badge geometry, label anchors and ability-row presentation |
| Saga | `DefaultEntry_CreatureSaga`, `ChapterEntry` prefab and `Card_Chapter` textures | Chapter rows, icons and dividers |
| Battle | DefensePart: `DefenseBox`, `Defense Label`, `Card_Defense`; TitleBarPart_5: `Card Part - Titlebar Battle DoubleFaced Front` | Defense badge and front-face title treatment |
| Tokens | Double-faced token, legendary-token and Battle-front-token title-bar variants | Shared components with token variants |
| Class | `DefaultEntry_Class` and Class art-in-frame entries in the manifest | Per-level text-row structure |
| Adventure / Room | Omission-box and specialized highlight/component entries in the manifest | Distinct subcard treatment and room highlights |

These are concrete implementation references/resources, not drop-in UI Toolkit
components. Some use shared materials, SDF atlases or external texture dependencies;
those references still need a curated import and URP/UI Toolkit adaptation. Do not
infer that arbitrary source shaders, prefabs or gameplay scripts are compatible.
The current gallery uses Core printing images instead. Engine-supplied loyalty,
chapters, defense, counters and legal actions remain future runtime integration;
asset discovery does not authorize reconstructing those facts client-side.


## Local research handoff reference — October 30, 2026

The owner pointed to the ignored `UNITY_ASSETS_AI_HANDOFF.local.md`, which was
read along with `Downloads/Unity Asset Catalog/README.md`. The searchable
`catalog.html` and `inventory.json` provide filename/category indexes for future
focused work. The handoff also identifies raw ArtCropDatabase, lookup and card
metadata files; their schemas and crop semantics have not been verified here.
Its suggested projects are research leads, not authorization to implement all of
them. Keep originals unchanged and machine-specific indexes/extractions local.


## Battlefield frame, typography and symbols — October 30, 2026

The compact fixture now filters battlefield examples to permanent card types;
instants and sorceries remain available in the inspection selector. This is a
fixture filter only, not a client-side rule for live zone membership. Room cards
retain both art panels. The dark compact surround uses the projected contour of
`BattlefieldPart_Cardbase_Default` (path ID 4091911210820854842). The independent
numeric loyalty shield uses `Card_Loyalty` (5550224334418384154), allowing loyalty
and P/T together. Neither supplied shaders nor gameplay scripts were imported.
The visual reference was [Arena's planeswalker presentation](https://www.forbes.com/sites/laurenorsini/2019/05/22/magic-the-gathering-arena-launches-first-story-based-event-may-23/).

`CardTypography` assigns Beleren Bold to title, type and P/T, Plantin MT Pro's
regular/bold/italic/bold-italic faces to rules, and Beleren Small Caps to supplied
collector text. Emphasis is explicit presentation metadata; rules text is never
interpreted as rich-text markup. Existing printing credits remain visible when
no replacement collector text is supplied.

The local review build includes six fonts and 82 128-pixel symbol sprites.
`tools/prepare_play_card_visuals.py` prepares these offline from local font files
and cached SVGs. Run it with `--plantin-directory`, `--beleren-directory` and
`--svg-directory`; outputs live in the locally ignored Unity Resources folder
`LocalCardVisuals`. The tool records SHA-256 provenance. Mana cost symbols use
20-unit sizing (previously 17); inline rules use the same sprite resources for
supported tap, untap and mana tokens. Unknown tokens remain literal text.

Plantin faces come from the owner's Downloads folder. Beleren sources are pinned
to [Saeris commit cdbe3dc](https://github.com/Saeris/typeface-beleren-bold/tree/cdbe3dc354a51b620636f8effd4c4b143d8969a1);
the repository's MIT notice applies to its CSS, not the Wizards-owned fonts.
Symbol SVG references come from the [Scryfall symbology API](https://api.scryfall.com/symbology).
Font and symbol binaries remain local rather than being redistributed in Git.
Source-only checkouts retain default typography and the existing mana-font
fallback. Optional-pack tests explicitly skip when their local resources are
absent. These changes do not close G0/G1 or demonstrate live engine gameplay.


Validation for 0.5.80-alpha.1: 283 EditMode checks (including the installed font
and sprite pack), five PlayMode checks, Windows player build and two packaged
20-object artwork smoke captures. Captures are local under
`Artifacts/ArtworkScene/compact-review.png` and `artwork-20.png`. Owner review
should focus on mana size/alignment, compact title positioning, frame edges,
loyalty and preserved printing credits. CI is deferred to the next scheduled
third-commit checkpoint; these results are local evidence only.


## Custom inspection and readable titles — October 30, 2026

Known compact profiles now also provide artwork crops for a Manaforge-rendered
full inspection card: title, mana, type, scrollable rules and supplied P/T,
defense or loyalty. This replaces the previous whole-printing-only inspector
for those profiles. Unknown layouts retain the original-image fallback. The
custom inspection is a shared presentation, not a recreation of each printed
Saga chapter, Class level or planeswalker ability frame. Horizontal layouts use
their profiled art rotation; their original horizontal credits are not overlaid
onto an unrelated upright footer. Upright specialized printings retain a source
footer strip. All values still come from fixture metadata, not inferred rules.

Local fonts now use cached TextCore distance-field assets rather than a direct
Font definition. Mini titles have a minimum 11-unit size and scale from 21 at
300-unit card width, avoiding the previous approximately nine-pixel titles at
fixture size. Long titles ellipsize and remain readable in full inspection.
Rules scroll position clears on viewer handoff; symbol-bearing rules hide the
plain-text duplicate rather than reserving a transparent duplicate text block.
Owner review is required for final typography and custom inspection styling.


Local validation: 283 EditMode checks and five PlayMode checks passed; Windows
build and packaged 20-object capture succeeded. The capture was visually inspected
and used to correct title/mana spacing. Both panels remain present for known
split-art profiles in full inspection. This increment remains fixture-only.


## Shared renderer and structured layouts — October 30, 2026

The 0.5.82 increment corrects the plain-surround detour above. Known full-card
layouts again retain the exact printing image as their outer frame, using the
same CardView layering as standard creatures and auras. There is one renderer:
printing identity and borrowed texture, a layout profile, cropped artwork,
shared title/type plates, the same typography and mana resources, supplied text,
and optional supplied stats. Compact and full are presentation modes of that
same view. No per-card-name rendering branches were added. Unknown layouts retain
the authentic-image fallback; arbitrary card/frame combinations are not claimed
validated. Perfect dynamic frame composition remains roadmap research.

Specialized profiles change geometry and text organization:

- Planeswalkers use a taller inspection card, smaller art region and separated
  ability rows with costs at the left. Static text and unfamiliar costs remain
  visible; loyalty is supplied independently and the baked original badge is
  masked without extending into the collector footer.
- Classes use the tall left art panel and level sections at the right, following
  the [official Arena Class screenshot](https://media.wizards.com/2021/images/daily/MhmHVZHbLg.jpg)
  from [Wizards' AFR digital release notes](https://magic.wizards.com/en/news/mtg-arena/mtg-arena-digital-release-notes-adventures-forgotten-realms-2021-07).
  A separate full art crop avoids magnifying the mini crop into a tall panel.
- Level-up cards preserve explicit level-range headings, printed P/T and ability
  text in separated sections. Class levels and level counters are not conflated.
- Rooms retain the two-panel mini and provide door selectors in inspection. Each
  selector changes only displayed name, mana, rules, crop and printing surround.
  It never unlocks a door or creates a second card. The two-door relationship was
  checked against [Wizards' Duskmourn notes](https://magic.wizards.com/en/news/feature/duskmourn-house-of-horror-release-notes).
  A verified Arena Room gameplay screenshot was not found in this research;
  the door inspector is a Manaforge presentation, not a claim of exact Arena UX.

`CardRuleSection` recognizes explicit printed typography markers only (signed
loyalty costs, Class cost/level headings and LEVEL ranges). It does not calculate
legality, levels, unlocked doors or current characteristics. Unrecognized text
stays literal, rich text remains disabled and all sections clear on handoff.
Future live projections must supply viewer-permitted engine state and decisions;
no sections are dimmed or enabled based on inferred printed text.

Offline artwork fixture v3 carries two bounded Room display records on the same
card, fixing the earlier first-door-only export. The loader retains v1/v2 support
and rejects door metadata attached to unrelated types. This version is a local
renderer-fixture schema, not a new game-protocol version or persistent deck model.
All names move one percentage point right inside the existing plates.

Local validation: 293 EditMode checks, six PlayMode checks (including an attached
Room selector and cleared handoff), 12 focused Python fixture checks and Ruff
passed. Windows player build and five packaged captures cover Jace, Ranger Class,
Student of Warfare, Dollmaker's Shop and Bruna. Owner visual approval remains
open. Captures live in ignored `Artifacts/ArtworkScene/shared-*.png`. CI was last
checked at 22f4b88: no newer relevant runs existed; next check remains the third
commit checkpoint. No Qt CI was investigated or full application suite run.

Room inspection masks the compound printing perimeter with the shared black edge
to prevent rotated credits/text bleeding around the focused door. Exact Room
frame composition and Arena-equivalent door styling remain owner-review items.

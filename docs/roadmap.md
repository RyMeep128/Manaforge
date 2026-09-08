# Manaforge delivery checklist

This checklist coordinates work across MTG Core, Print Proxy Prep, and the Deck Editor. It is ordered by dependency and product value. Detailed requirements remain in the [printer plan](printing-roadmap.md) and [Deck Editor epic](../Mtg_Projects/mtg_editor/docs/deck-editor-epic.md).

Status: **[x] complete**, **[ ] planned**, **[~] partially complete**.

## Foundations already in place

- [x] Shared SQLite card, printing, image, and Oracle Tag data in MTG Core.
- [x] Fast local Scryfall-style search for common card properties and `otag:`.
- [x] Local thumbnail/image asset reuse and configurable preview memory cache.
- [x] Project library, explicit save, autosave, dirty `*`, and recent projects.
- [x] Interactive print placement, gaps, oversized cards, add-slot buttons, and Undo/Redo.
- [x] Preview/PDF placement agreement, backs, offsets, and under-filled-sheet warnings.
- [x] Named printer profiles with paper, margins, offsets, scaling, duplex, and output settings.
- [x] CI for Proxy, Core, and integration tests.
- [x] Root suite README, architecture overview, screenshots, GIF, and build instructions.

## Phase 1 — Finish the printer

### 1. Calibration and duplex alignment

- [x] Generate a front/back calibration PDF with orientation arrows, registration marks, rulers, and measured reference boxes.
- [x] Add a guided calibration dialog showing paper choice, orientation, duplex edge, actual-size printing, and measured X/Y drift.
- [x] Add vertical backside offset throughout state, profiles, preview, and export.
- [x] Save calibration corrections into a named printer profile.
- [x] Generate a second verification sheet from the dialog after entering corrections.
- [ ] Test portrait/landscape, Letter/A4, long-edge/short-edge duplex, and mirrored backs.

**Exit gate:** A user can calibrate a printer, save the result, reopen Manaforge, and reproduce aligned fronts and backs.

### 2. Direct printing

- [x] Enumerate system printers and select one in Manaforge through the native print dialog.
- [~] Map profiles to printer capabilities: paper, orientation, and duplex are applied; color and copies remain driver-controlled.
- [x] Provide print range and front-only/back-only controls.
- [x] Render through the same placement service used by preview and PDF.
- [ ] Show occupancy, low-resolution, missing-back, clipping, and invalid-layout warnings before submission.
- [x] Keep **Print Anyway** where output remains valid.
- [x] Show operating-system print errors and job-submission status clearly.
- [x] Require an explicit final **Print** action; calibration and preview never submit automatically.

**Depends on:** calibration and vertical offset.

**Exit gate:** Preview, PDF, and direct print produce the same geometry on a calibrated profile.

### 3. Export formats and presets

- [ ] Export each sheet as PNG with selectable DPI and transparent/solid background where applicable.
- [ ] Export each sheet as JPEG with quality control.
- [ ] Export individual prepared card fronts and backs.
- [ ] Export a ZIP containing sheets/cards plus a manifest of settings and filenames.
- [ ] Add validated presets: Letter 3×3, A4, duplex, bleed, cut guides, and oversized layouts.
- [ ] Preserve intentional page gaps and exclude empty editing-only sheets in every format.

**Exit gate:** All formats match PDF placement and have deterministic filenames and contents.

### 4. Printer bulk tools and quality workflow

- [~] Multi-select and bulk oversized changes exist.
- [ ] Bulk replace all low-resolution artwork.
- [ ] Bulk add missing DFC/custom backs.
- [ ] Bulk change printings/artwork using one filtered picker.
- [ ] Bulk remove or exclude basic lands.
- [ ] Add a persistent **Do not print / owned copy** flag.
- [ ] Add fix actions directly from print-readiness warnings.
- [ ] Add crash-recovery snapshots and a recovery chooser for interrupted writes.

**Exit gate:** A 500-card project can be audited and repaired without editing cards individually.

### 5. Printing preferences and artwork picker

- [ ] Store a global preferred printing/art choice by Oracle card in Core.
- [ ] Add preference rules for language, resolution, set, year, artist, frame, border, and source.
- [ ] Add avoidance rules for promos, textless cards, Universes Beyond, and foil-only treatments.
- [ ] Define deterministic precedence: explicit project choice → global card favorite → profile rules → best available default.
- [ ] Show DPI/resolution badges in the artwork picker.
- [ ] Add set/year/artist/source/treatment filters.
- [ ] Virtualize results and load only cached thumbnails visible on screen.
- [ ] Add a refresh/replace-all workflow that previews every proposed change before applying it.

**Exit gate:** The same preferred art is selected consistently in Core, Deck Editor, Proxy Printer, and exports.

### 6. Tokens and unusual card layouts

- [x] Read `all_parts`/component relationships and suggest created tokens or referenced cards after imports and from project-card context menus.
- [x] Let users add all suggested tokens, select some, or dismiss them.
- [ ] Verify transform and modal DFC front/back pairing.
- [ ] Add explicit tests and rendering rules for meld, split, aftermath, adventure, flip, battle, plane, scheme, token, and custom cards.
- [ ] Verify oversized behavior for each compatible layout.
- [ ] Define clear fallback behavior for unsupported physical footprints.

**Exit gate:** The supported-layout matrix is documented and every row has import, preview, save/reload, and export coverage.

## Phase 2 — Minimum viable Deck Editor

### 7. Shared deck model and persistence

- [ ] Define a versioned Core deck model separate from print-render settings.
- [ ] Store deck name, format, description, sections, commander(s), categories, tags, notes, and sort order.
- [ ] Store exact printing/art selection and owned/do-not-print state per entry.
- [ ] Migrate existing proxy projects without losing counts, backs, layouts, oversized flags, or artwork overrides.
- [ ] Add deck create/open/recent flows to the project dashboard.
- [ ] Add autosave, dirty status, atomic writes, backups, and recovery.
- [ ] Add model-level Undo/Redo commands.

**Exit gate:** Decks and legacy proxy projects round-trip without data loss.

### 8. Fast editor shell

- [ ] Build the runnable PyQt6 Deck Editor application boundary.
- [ ] Add a deck header with name, format, count, save state, Import, Add Card, and **Print Deck**.
- [ ] Add responsive search-as-you-type using MTG Core.
- [ ] Add instant add/remove and quantity controls.
- [ ] Add image/grid and compact text/list views.
- [ ] Add adjustable card sizes, collapsible groups, hover preview, context menus, and keyboard shortcuts.
- [ ] Virtualize grids/lists and decode only visible small thumbnails.
- [ ] Keep filtering and scrolling responsive with 500+ entries.

**Exit gate:** Creating a deck and adding or editing cards feels immediate on a 500-card stress project.

### 9. Sections, categories, and organization

- [ ] Support mainboard, commander, sideboard, considering/maybeboard, and excluded sections.
- [ ] Support grouping by type, mana value, color, custom category, and import section.
- [ ] Support sorting by name, mana value, color, quantity, and import order.
- [ ] Create, rename, reorder, and delete custom categories.
- [ ] Drag cards between sections and categories.
- [ ] Allow one primary category and multiple functional/user tags per card.
- [ ] Add reusable category templates such as Ramp, Draw, Removal, Wipes, Protection, Recursion, Win Conditions, and Lands.
- [ ] Support multi-select and bulk section/category/tag changes.

**Exit gate:** Users can organize a Commander deck without changing its printed quantities accidentally.

### 10. Import, export, and legality

- [x] Core proxy workflow accepts pasted names with or without a leading quantity.
- [~] Text/file/CSV and public deck-site imports exist in the proxy workflow.
- [ ] Move shared import parsing and resolution into Core for reuse by the editor.
- [ ] Preserve source sections, quantities, set codes, collector numbers, and art when supplied.
- [ ] Support public Moxfield, Archidekt, Blueprint MTG, and other chosen sources through tested adapters.
- [ ] Export common text formats with optional set/collector data and sections.
- [ ] Add Commander selection and partner/background rules.
- [ ] Validate deck size, singleton rules, color identity, banned lists, and format legality.
- [ ] Version or date legality data and explain stale/unknown results.
- [ ] Add other formats only after Commander validation is dependable.

**Exit gate:** A public or pasted Commander deck imports with sections and printings intact and receives an explainable legality report.

## Phase 3 — Make the editor enjoyable

### 11. Insights and filtering

- [ ] Add filters for name, colors/identity, mana value, type/subtype, Oracle text, keywords, power/toughness, rarity, set, artist, legality, treatment, tags, and print readiness.
- [ ] Add mana curve, average mana value, color/pip distribution, type distribution, and land count.
- [ ] Count ramp, draw, removal, wipes, protection, recursion, interaction, creatures, and user-defined roles.
- [ ] Let users override every inferred role without changing global tag data.
- [ ] Add clickable print-readiness totals for low DPI, missing art, missing backs, DFCs, oversized cards, and excluded cards.
- [ ] Add recent-search caching and background/cancellable database queries.

### 12. Playtest lite

- [ ] Draw and redraw randomized opening hands using actual quantities.
- [ ] Support mulligans and drawing additional cards.
- [ ] Exclude commanders, sideboards, maybeboards, and do-not-print entries as configured.
- [ ] Persist plain-text playtest notes.
- [ ] Keep this a sampling tool rather than a rules engine.

**Exit gate:** Users can evaluate composition and sample hands without leaving Manaforge.

## Phase 4 — Connect Editor, Core, and Printer

### 13. One-click Print Deck

- [ ] Pass quantities, exact printings, artwork, backs, and oversized flags to Print Proxy Prep.
- [ ] Preserve manual print layout when compatible and reconcile it predictably when the deck changes.
- [ ] Offer inclusion toggles for unowned cards, tokens, basics, commanders, and cards marked as real copies.
- [ ] Suggest required tokens before opening print preview.
- [ ] Reuse global artwork preferences and printer profiles.
- [ ] Return from print preparation without losing editor selection, scroll, filters, or Undo history.

**Exit gate:** A deck can move from editor to calibrated physical print without reselecting cards or artwork.

### 14. Shared preference ownership

- [ ] Put global printing/art preferences in Core with a versioned schema.
- [ ] Expose the same preference editor in Core, Deck Editor, and Proxy Printer.
- [ ] Define project overrides and a reset-to-global action.
- [ ] Notify open apps when shared preferences change or refresh on focus safely.
- [ ] Add integration tests proving the three apps resolve the same print.

## Phase 5 — Intelligence after the editor is solid

### 15. Deterministic guidance

- [ ] Detect likely shortages in lands, ramp, draw, and interaction using configurable rules.
- [ ] Use local Oracle Tags plus user overrides for functional counts.
- [ ] Explain every suggestion and allow dismissal/override.
- [ ] Avoid presenting heuristic categories as rules facts.

### 16. Local recommendation dataset

- [ ] Choose licensed/public decklist sources and document provenance and refresh policy.
- [ ] Build a resumable ingestion and normalization pipeline.
- [ ] Precompute commander inclusion rates and baseline card popularity.
- [ ] Calculate transparent synergy scores against baseline popularity.
- [ ] Store compact indexed aggregates rather than loading raw decks during editor use.
- [ ] Add freshness, source, and sample-size indicators.

**Exit gate:** Recommendations are local, fast, explainable, reproducible, and clearly sourced.

## Phase 6 — Optional ecosystem expansion

- [ ] Collection tracking by card, quantity, and printing.
- [ ] Deck usage, owned totals, missing cards, and **Print missing proxies**.
- [ ] Multi-language UI and card-data workflows.
- [ ] Linux packaging and CI smoke tests.
- [ ] macOS packaging, signing/notarization, and CI smoke tests.
- [ ] Advanced non-destructive image editing with reset and preview comparison.
- [ ] Additional export formats only when a concrete user workflow requires them.
- [ ] Plugin/extension boundary only after Core APIs and project schemas stabilize.

## Rules that apply to every phase

- [ ] Keep preview, export, and direct-print geometry in one shared layout service.
- [ ] Keep full-resolution images out of browsing views; use small cached thumbnails.
- [ ] Index searchable fields and precompute expensive derived data.
- [ ] Run long imports, downloads, rendering, and queries off the UI thread with cancellation and progress.
- [ ] Preserve backward compatibility through explicit schema versions and migrations.
- [ ] Add focused unit, Qt interaction, integration, persistence, and performance tests appropriate to each change.
- [ ] Update user documentation and screenshots when visible behavior changes.
- [ ] Keep alpha/beta versioning and CI green for every merged increment.

## Recommended next execution order

1. Calibration sheet and vertical offset.
2. Calibration wizard and profile verification.
3. Direct printing through the shared renderer.
4. PNG/JPEG/card/ZIP export.
5. Printer bulk repair tools.
6. Preferred-print rules and faster artwork picker.
7. Token relationships and unusual-layout matrix.
8. Freeze printer expansion and build the Deck Editor MVP.
9. Make the editor fast and pleasant before adding recommendations.
10. Integrate **Print Deck**, shared preferences, and owned/do-not-print state.

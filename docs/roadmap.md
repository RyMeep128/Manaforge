# Manaforge delivery checklist

This checklist coordinates work across MTG Core, Print Proxy Prep, and the Deck Editor. It is ordered by dependency and product value. Detailed requirements remain in the [printer plan](printing-roadmap.md), [Deck Editor epic](../Mtg_Projects/mtg_editor/docs/deck-editor-epic.md), [architecture cleanup epic](architecture-cleanup-epic.md), and [long-term product epic](long-term-product-epic.md). This checklist is the delivery sequence; the epics retain detailed scope and acceptance criteria. Product-epic phase numbers are mapped into the sequence below rather than replacing existing completed milestones.

Status: **[x] complete**, **[ ] planned**, **[~] partially complete**.

## Product direction and scope

**Build -> Test -> Learn -> Print -> Play:** a local-first, open-source Magic workstation for personal use and private games with friends. One serializable deck model, with separate Oracle identity and exact printing identity, feeds building, analysis, recommendations, printing, and future play modes without re-entry or export. Match card instances and print jobs reference that model through adapters rather than putting game or rendering state into card records.

Current priority remains completing and stabilizing the editor and print workflow, with incremental boundary cleanup. The later phases record direction, not authorization to implement a rules engine, AI, or networking now. Recommendations are deterministic and data-driven; a future gameplay AI is a separate system and does not require an LLM.

Keep decks, downloaded data, artwork, preferences, and future rules/recommendation datasets user-owned and usable offline where practical. Avoid required accounts, subscriptions, cloud-only storage, public matchmaking, rankings, social feeds, marketplaces, and unnecessary central infrastructure.

## Architecture cleanup - staged workstream alongside Phases 3-4

These are planned tasks from the [architecture cleanup epic](architecture-cleanup-epic.md), not newly verified defects or completed work. Confirm each against the current code before implementation. Preserve behavior, PyQt6, existing public interfaces where useful, and old project compatibility; deliver small, independently testable changes rather than a rewrite.

| Order / epic workstream | Planned outcome and acceptance gate |
| --- | --- |
| A1 / 1 | One canonical-print selection and `PrintRecord` row conversion implementation; admin paths reuse it. Regression coverage removes stale canonical mappings when the final print is deleted. |
| A2 / 2 | Domain-focused database/repository mutations own search, canonical, image-manifest, and dependent-record invariants; admin services express intent instead of duplicating SQL write rules. |
| A3 / 9 | Consistent contextual logging for bulk image and editor worker failures, preserving tracebacks while keeping user messages concise. |
| A4 / 5 | Categorization/analysis use meaningful application services; editor callers no longer reach through `service.database`. Domain behavior remains testable without Qt. |
| A5 / 3 | Split database internals into schema, cards, search, images, preferences, and sync responsibilities; keep a convenient facade and lightweight package boundary. |
| A6 / 4 | Separate search, artwork/image, and catalog-sync responsibilities internally while preserving useful `CardService` compatibility. |
| A7 / 6 | Extract stable editor session/history/persistence, task lifecycle, and search responsibilities; test session behavior independently where practical and avoid callback-sized abstractions. |
| A8 / 7 | Replace the editor's Proxy `sys.path` integration with normal shared-package imports, starting with adapter consumers. Preserve Proxy UI and print-handoff tests; keep non-UI shared code independent of Qt. |
| A9 / 8, 10 | Promote mature `extras` concepts into typed state and centralize persistent section/sync values. Preserve old serialized values and unknown extension data; test old/new round trips. Keep display labels separate. |
| A10 / 11 | Explicit schema version and ordered, tested SQLite migrations, including fresh creation and automatic legacy upgrades without unnecessary destructive rebuilds. |
| A11 / 12 | Focused Ruff adoption (`ruff check`, `ruff format --check`) alongside pytest on Python 3.12/3.13 CI; avoid a blanket formatting rewrite. Broader type checking can follow later. |

All A1-A11 items are **planned**. Start with persistence invariants and diagnostics, then service/editor boundaries and shared printing. Introduce migrations before any subsequent schema change needs them. Complete the relevant boundaries before expanding recommendations, rules storage, or gameplay; do not delay unrelated editor fixes behind the whole epic.

**Exit gate:** Existing tests and CI remain green, duplicated persistence rules and editor boundary leaks are removed, responsibilities have clear owners, failures are diagnosable, and typed state/migrations preserve compatibility. No recommendation, rules-reference, AI, or multiplayer implementation belongs to this cleanup epic.

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
- [x] Test portrait/landscape, Letter/A4, long-edge/short-edge duplex, and mirrored backs.

**Exit gate:** A user can calibrate a printer, save the result, reopen Manaforge, and reproduce aligned fronts and backs.

### 2. Direct printing

- [x] Enumerate system printers and select one in Manaforge through the native print dialog.
- [~] Map profiles to printer capabilities: paper, orientation, and duplex are applied; color and copies remain driver-controlled.
- [x] Provide print range and front-only/back-only controls.
- [x] Render through the same placement service used by preview and PDF.
- [x] Show occupancy, low-resolution, missing-back, clipping, and invalid-layout warnings before submission.
- [x] Keep **Print Anyway** where output remains valid.
- [x] Show operating-system print errors and job-submission status clearly.
- [x] Require an explicit final **Print** action; calibration and preview never submit automatically.

**Depends on:** calibration and vertical offset.

**Exit gate:** Preview, PDF, and direct print produce the same geometry on a calibrated profile.

### 3. Export formats and presets

- [x] Export each sheet as PNG with selectable DPI and transparent/solid background where applicable.
- [x] Export each sheet as JPEG with quality control.
- [x] Export individual prepared card fronts and backs.
- [x] Export a ZIP containing sheets/cards plus a manifest of settings and filenames.
- [x] Add validated presets: Letter 3×3, A4, duplex, bleed, cut guides, and oversized layouts.
- [x] Preserve intentional page gaps and exclude empty editing-only sheets in every format.

**Exit gate:** All formats match PDF placement and have deterministic filenames and contents.

### 4. Printer bulk tools and quality workflow

- [x] Multi-select and bulk oversized changes exist.
- [x] Bulk replace all low-resolution artwork.
- [x] Bulk add missing DFC/custom backs.
- [x] Bulk change printings/artwork using one filtered picker.
- [x] Bulk remove or exclude basic lands.
- [x] Add a persistent **Do not print / owned copy** flag.
- [x] Add fix actions directly from print-readiness warnings.
- [x] Add crash-recovery snapshots and a recovery chooser for interrupted writes.

**Exit gate:** A 500-card project can be audited and repaired without editing cards individually.

### 5. Printing preferences and artwork picker

- [x] Store a global preferred printing/art choice by Oracle card in Core.
- [x] Add preference rules for language, resolution, set, year, artist, frame, border, and source.
- [x] Add avoidance rules for promos, textless cards, Universes Beyond, and foil-only treatments.
- [x] Define deterministic precedence: explicit project choice → global card favorite → profile rules → best available default.
- [x] Show DPI/resolution badges in the artwork picker.
- [x] Add set/year/artist/source/treatment filters.
- [x] Virtualize results and load only cached thumbnails visible on screen.
- [x] Add a refresh/replace-all workflow that previews every proposed change before applying it.

**Exit gate:** The same preferred art is selected consistently in Core, Deck Editor, Proxy Printer, and exports.

### 6. Tokens and unusual card layouts

- [x] Read `all_parts`/component relationships and suggest created tokens or referenced cards after imports and from project-card context menus.
- [x] Let users add all suggested tokens, select some, or dismiss them.
- [x] Verify transform and modal DFC front/back pairing, including recovery when only the front image is cached.
- [x] Add explicit tests and [rendering rules](card-layout-support.md) for meld, split, aftermath, adventure, flip, battle, plane, scheme, token, and custom cards.
- [x] Verify oversized behavior for each compatible layout.
- [x] Define clear fallback behavior for unsupported physical footprints.

**Exit gate:** The supported-layout matrix is documented and every row has import, preview, save/reload, and export coverage.

## Phase 2 — Minimum viable Deck Editor

### 7. Shared deck model and persistence

- [x] Define a versioned Core deck model separate from print-render settings.
- [x] Store deck name, format, description, sections, commander(s), categories, tags, notes, and sort order.
- [x] Store exact printing/art selection and owned/do-not-print state per entry.
- [x] Migrate existing proxy projects without losing counts, backs, layouts, oversized flags, or artwork overrides.
- [x] Share a background-loaded Decks and print projects browser between Editor and Proxy, with filtering, New/Open, and preserved Editor recent-deck flows. Opening a print project creates a separate editable deck.
- [x] Add autosave, dirty status, atomic writes, backups, and recovery.
- [x] Add model-level Undo/Redo commands.

**Exit gate:** Decks and legacy proxy projects round-trip without data loss.

### 8. Fast editor shell

- [x] Build the runnable PyQt6 Deck Editor application boundary.
- [x] Deck header includes name, format, count, save state, Add Cards, Import, and **Print Deck**.
- [x] Add responsive search-as-you-type using MTG Core.
- [x] Add instant add/remove and quantity controls.
- [x] Add image/grid and compact text/list views.
- [x] Add adjustable card sizes, collapsible groups, hover preview, context menus, and keyboard shortcuts.
- [x] Virtualize grids/lists and decode only visible small thumbnails.
- [x] Keep filtering and scrolling responsive with 500+ entries.

**Exit gate:** Creating a deck and adding or editing cards feels immediate on a 500-card stress project.

### 9. Sections, categories, and organization

- [x] Support mainboard, commander, sideboard, considering/maybeboard, and excluded sections.
- [x] Support grouping by type, mana value, color, custom category, and import section.
- [x] Sort by name, mana value, color, quantity, and import order.
- [x] Create, rename, reorder, and delete custom categories.
- [x] Drag cards between sections and categories.
- [x] Allow one primary category and multiple functional/user tags per card.
- [x] Add reusable category templates such as Ramp, Draw, Removal, Wipes, Protection, Recursion, Win Conditions, and Lands. Save/update a deck's category layout and apply it to another deck without changing card assignments.
- [x] Add deterministic local Oracle Tag/text/keyword/type categorization, reviewable bulk application, manual override protection, and Undo/Redo. Aggregate recommendations remain separate work.
- [x] Add radial batch primary-category/tag editing, Auto/Manual badges, automatic organization on opening imported decks, and explicit reconsideration of manual assignments.
- [x] Support multi-select and bulk section/category/tag changes.

**Exit gate:** Users can organize a Commander deck without changing its printed quantities accidentally.

### 10. Import, export, and legality

- [x] Core proxy workflow accepts pasted names with or without a leading quantity.
- [x] Text/file/CSV and public deck-site imports are available in Editor and Proxy.
- [x] Move shared text/CSV import parsing and card resolution into Core for reuse by the editor; keep Proxy compatibility wrappers.
- [x] Add editor paste/file import with background resolution, progress, cancellation, unresolved-line review, automatic categorization, and one-step Undo.
- [x] Preserve sections, quantities, exact printing IDs, set/collector coordinates, and supported explicit custom front/back image overrides. CSV can supply image URLs; imported artwork is validated, stored in Core, previewed, persisted, and retained through print handoff. Failed image downloads are reported instead of silently substituted.
- [x] Support public Moxfield, Archidekt, and Blueprint MTG in the editor through shared Core adapters, with fixture-tested section/printing preservation, cancellation, and error handling. Live availability depends on each site's public endpoints.
- [x] Export quantity/name text with optional set/collector data and sections; preview, clipboard copy, and file saving.
- [x] Add Commander selection with compatible partner/background checks, including named partners, partner variants, and Doctor's companion; preserve quantities and support Undo.
- [x] Check Commander deck size, singleton exceptions, color identity/basic land types, cached bans/legality, the ten named companion restrictions, and chosen pregame commander colors. Unsupported/ambiguous card characteristics produce explicit Unknown findings rather than a clean result.
- [x] Version the Commander checker, show local card-cache dates, and explicitly identify stale/missing legality data. Cache dates are not represented as ban-list publication dates.
- [x] After Commander coverage, add Standard, Modern, Pauper, Legacy, and Vintage checks: main/sideboard size, shared copy limits, Vintage restrictions, companions, and dated local format legality.

**Exit gate:** A public or pasted Commander deck imports with sections and printings intact and receives an explainable legality report.

**Phase 2 complete:** Shared library navigation, import/art persistence, undoable organization,
Commander/constructed checks, and the existing editor/print bridge have regression coverage.
External site availability and current ban-list accuracy still depend on public endpoints and
fresh Core data. Custom artwork support uses explicit override fields; unknown source schemas
and ambiguous rules are not presented as verified. Phase 3 starts with filters and statistics.

## Phase 3 — Make the editor enjoyable

### 11. Insights and filtering

- [x] Add filters for name, colors/identity, mana value, type/subtype, Oracle text, keywords, power/toughness, rarity, set, artist, legality, treatment, tags, and print readiness. Local queries support combined metadata/category/section filters and entry flags in card and table views; **More > Print readiness** provides asset-based snapshot filters.
- [x] Add mana curve, average mana value, color/pip distribution, type distribution, and land count. **More > Deck insights** reads local metadata in the background and shows a quantity-weighted snapshot with section scope and missing-data notices.
- [x] Count ramp, draw, removal, wipes, protection, recursion, interaction, creatures, and user-defined roles. Role totals use assigned categories/tags without reclassifying manual choices; creature totals use card types.
- [x] Let users override every inferred role without changing global tag data. Card actions provide **Edit roles/categories** for individual or bulk membership changes, preserving mixed selections, Undo/Redo, and saved manual protection; user tags remain separately editable.
- [x] Add clickable print-readiness totals for low DPI, missing art, missing backs, DFCs, oversized cards, and excluded cards. Background local scans report copies and entries across all sections; clicking a total filters both views. Snapshot filters clear when the deck changes.
- [x] Add recent-search caching and background/cancellable database queries. Editor card search keeps up to 20 queries for 30 seconds, with Refresh to bypass the cache; query replacement, Cancel, clearing, hiding search, and closing cancel local SQL/role lookup and suppress obsolete results.

### 12. Playtest lite

- [x] Draw and redraw randomized opening hands using actual quantities through **More > Opening-hand playtest**. Each copy retains its entry/printing identity; sampling leaves deck quantities unchanged.
- [x] Support seven-card redraw mulligans, an optional free first mulligan, choosing cards to bottom before keeping, and additional draws without replacement. Handle small decks and empty libraries explicitly.
- [x] Exclude commanders, sideboards, maybeboards, excluded sections, and do-not-print entries as configured. Default to mainboard, retaining do-not-print/owned cards; recognize commander IDs as well as the commander section.
- [x] Persist plain-text playtest notes with the deck, with Undo/Redo and backward-compatible loading. Save inclusion/mulligan settings as editor preferences; Cancel discards dialog changes.
- [x] Keep this a sampling tool rather than a rules engine; the Qt-independent sampler can be reused in Phase 7 local playtest. Hands and library state are temporary, not saved matches.

**Exit gate:** Users can evaluate composition and sample hands without leaving Manaforge.

## Phase 4 — Connect Editor, Core, and Printer

### 13. One-click Print Deck

- [x] Pass quantities, exact printings, artwork, backs, and oversized flags to Print Proxy Prep.
- [x] Preserve manual print layout when compatible and reconcile it predictably when the deck changes.
- [~] Section inclusion toggles and do-not-print exclusions exist; token/basic/ownership-count toggles remain.
- [ ] Suggest required tokens before opening print preview.
- [~] Shared artwork picker and linked Proxy print settings are reused; unified preference editing remains.
- [x] Return from print preparation without losing editor selection, scroll, filters, or Undo history.

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

- [ ] Suggest deck-specific themes only when a meaningful, configurable threshold is met; keep final category assignments under user control.

### 16. Local recommendation dataset

- [ ] Choose licensed/public decklist sources and document provenance and refresh policy.
- [ ] Build a resumable ingestion and normalization pipeline.
- [ ] Precompute commander inclusion rates and baseline card popularity.
- [ ] Calculate transparent synergy scores against baseline popularity.
- [ ] Store compact indexed aggregates rather than loading raw decks during editor use.
- [ ] Add freshness, source, and sample-size indicators.

- [ ] Add a recommendation grid/list with previews, expandable reasons, immediate Add to Deck, categories/themes, and Scryfall-style filtering.
- [ ] Combine commander usage, co-occurrence, archetypes, color identity, themes, synergy, popularity, curve needs, and role gaps through transparent scoring.
- [ ] Download/cache versioned recommendation aggregates for offline use without requiring EDHREC during normal operation.

**Exit gate:** Recommendations are local, fast, explainable, reproducible, and clearly sourced.

## Phase 6 - Rules and rulings reference

- [ ] Add a local Rules section with Oracle text, official card rulings, keywords, and related Comprehensive Rules links.
- [ ] Support full-text/rule-number search, section navigation, keyword indexes, and cross-links.
- [ ] Version rules/rulings separately from decks/artwork, show installed version/date, and support updates.
- [ ] Add card-context access throughout Manaforge and eventually during matches.

**Exit gate:** Cached rules and rulings work offline, including direct rule-number navigation. This reference library is independent of rules enforcement.

## Phase 7 - Local playtest and reusable game state

- [ ] Open an existing deck directly into manual goldfish play, reusing Phase 3 hand sampling.
- [ ] Model players, unique card instances, zones, and turn state outside widgets with serializable state and explicit actions/events.
- [ ] Support library, hand, battlefield, graveyard, exile, and command zone; shuffle, mulligan, draw, mill, move, tap/untap, restart, and repeated opening hands.
- [ ] Track life, commander damage, poison, counters, and tokens.

**Exit gate:** Manual play needs no deck recreation; transitions are testable without Qt and expose an adapter boundary for the future engine.

## Phase 8 - Rules-engine feasibility prototype

- [ ] Investigate Forge/XMage before writing a new Magic engine; evaluate license compatibility before incorporating code.
- [ ] Compare embedding, subprocess, and API integration while preserving Manaforge's UI; document supported cards/formats and limitations.
- [ ] Map Oracle/printing IDs to engine definitions and consume authoritative state/events through a game API.
- [ ] Prove: load deck -> start game -> draw hand -> list legal actions -> play land -> cast simple spell -> resolve.

**Exit gate:** Documented engine/licensing decision and reproducible integration proof before sophisticated gameplay UI or networking.

## Phase 9 - Rules-enforced local play

- [ ] Keep a deterministic, authoritative engine behind presentation/client and game API layers. UI requests actions and renders events; rules stay outside UI.
- [ ] Support legal actions/targets, costs/mana payment, stack/priority, phases/steps, triggers, replacement effects, combat/damage, state-based actions, tokens/counters, and zone movement.
- [ ] Preserve hidden information and clearly identify supported-rule/card limitations.
- [ ] Provide legal-action/target highlights, readable stack, priority stops/automatic passing, attack/block selection, clear prompts, card zoom, and responsive battlefield interaction.

**Exit gate:** Supported games automate bookkeeping with deterministic tests, serializable state, and action/event logs suitable for replay and networking.

## Phase 10 - Local AI deck testing

- [ ] Run human versus local AI through the same engine and legal-action interface; prefer adapting usable engine AI.
- [ ] Progress from random legal actions to heuristics, state evaluation/search, then deck-aware strategy.
- [ ] Cover sensible spell/target choices, interaction, and combat decisions to expose deck weaknesses.

**Exit gate:** Repeatable matches provide useful testing; competitive strength and LLM integration are not prerequisites.

## Phase 11 - Private 1v1 multiplayer

- [ ] Support host, invite/code, and join; prefer peer-to-peer where practical and evaluate lightweight rendezvous only if needed.
- [ ] Reuse authoritative state and synchronized actions/events with per-player hidden-state views and reconnect support.
- [ ] Test action validation, determinism, hidden-information isolation, and disconnect recovery.

**Exit gate:** Friends can complete and reconnect to private games using existing decks without state divergence or hidden-information leaks.

## Phase 12 - Commander multiplayer

- [ ] Extend private play to 3-4 players with multiplayer priority/combat, commander damage, and readable larger battlefields.
- [ ] Consider spectators, saved/recoverable matches, and LAN play when useful.

**Exit gate:** Supported Commander games retain authoritative rules, correct private views, and reconnect behavior.

## Phase 13 - Complete-loop polish

- [ ] Once Build -> Test -> Learn -> Print -> Play works, invest in richer animations, transitions, effects, sound, onboarding, and accessibility improvements.
- [ ] Keep essential usability/accessibility and responsiveness part of every earlier phase.

## Optional ecosystem expansion - not a prerequisite for play

- [ ] Collection tracking by card, quantity, and printing.
- [ ] Deck usage, owned totals, missing cards, and **Print missing proxies**.
- [ ] Multi-language UI and card-data workflows.
- [ ] Linux packaging and CI smoke tests.
- [ ] macOS packaging, signing/notarization, and CI smoke tests.
- [ ] Advanced non-destructive image editing with reset and preview comparison.
- [ ] Additional export formats only when a concrete user workflow requires them.
- [ ] Plugin/extension boundary only after Core APIs and project schemas stabilize.

## Local data and archive strategy

- [ ] Keep the core installation relatively small: application, metadata/database, indexes, and local rules/rulings rather than mandatory full-resolution artwork.
- [ ] Resolve images by printing ID through local cache -> remote download when absent -> reusable cached asset.
- [ ] Support optional resumable archives of every English card/printing and high-quality images; a 100+ GB archive is acceptable but never required.
- [ ] Keep external data cacheable and separately versioned where appropriate, preserving user ownership and useful offline behavior.

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

1. Phase 3 is complete: preserve opening-hand sampling, cancellable search/cache, role overrides, filters, insights, and print-readiness behavior during the next refactors.
2. Begin architecture A1-A4: shared persistence invariants, regression coverage, diagnostics, and editor service boundaries.
3. Complete Phase 4 print handoff and shared preferences alongside A5-A8 database/service/session and shared-print extractions.
4. Finish typed persistent state, migrations, and focused quality tooling (A9-A11); introduce migration support sooner if schema changes require it.
5. Add explainable guidance and offline recommendation datasets/UI (Phase 5) after the editor is stable.
6. Add the versioned rules reference (Phase 6), then reusable manual local playtest (Phase 7).
7. Prove engine and licensing feasibility (Phase 8) before rules-enforced local play (Phase 9).
8. Add useful local AI (Phase 10), private 1v1 (Phase 11), then Commander multiplayer (Phase 12).
9. Invest in complete-loop polish (Phase 13); schedule optional ecosystem work only when needed.

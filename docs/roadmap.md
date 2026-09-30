# Manaforge delivery checklist

This checklist coordinates work across MTG Core, Print Proxy Prep, and the Deck Editor. It is ordered by dependency and product value. Detailed requirements remain in the [printer plan](printing-roadmap.md), [Deck Editor epic](../Mtg_Projects/mtg_editor/docs/deck-editor-epic.md), [architecture cleanup epic](architecture-cleanup-epic.md), [long-term product epic](long-term-product-epic.md), and [Manaforge Play epic](manaforge-play-epic.md). This checklist is the delivery sequence; the epics retain detailed scope and acceptance criteria. Product-epic phase numbers are mapped into the sequence below rather than replacing existing completed milestones.

Status: **[x] complete**, **[ ] planned**, **[~] partially complete**.

## Product direction and scope

**Build -> Test -> Learn -> Print -> Play:** a local-first, open-source Magic workstation for personal use and private games with friends. One serializable deck model, with separate Oracle identity and exact printing identity, feeds building, analysis, recommendations, printing, and future play modes without re-entry or export. Match card instances and print jobs reference that model through adapters rather than putting game or rendering state into card records.

Current priority remains completing and stabilizing the editor and print workflow, with incremental boundary cleanup. The later phases record direction, not authorization to implement a rules engine, AI, or networking now. Recommendations are deterministic and data-driven; a future gameplay AI is a separate system and does not require an LLM.

Keep decks, downloaded data, artwork, preferences, and future rules/recommendation datasets user-owned and usable offline where practical. Avoid required accounts, subscriptions, cloud-only storage, public matchmaking, global rankings, social feeds, marketplaces, and unnecessary central infrastructure.

## Architecture cleanup - staged workstream alongside Phases 3-4

This workstream tracks the [architecture cleanup epic](architecture-cleanup-epic.md). Completed stages are marked below; confirm remaining concerns against the current code before implementation. Preserve behavior, PyQt6, existing public interfaces where useful, and old project compatibility; deliver small, independently testable changes rather than a rewrite.

| Order / epic workstream | Planned outcome and acceptance gate |
| --- | --- |
| A1 / 1 - complete | Core owns canonical-print maintenance and `PrintRecord` row conversion; admin create/update/delete/list paths reuse them. Regression coverage checks final-print deletion, stale mapping removal, transaction rollback, and Oracle reassignment through both admin and catalog upsert paths. |
| A2 / 2 - complete | `CardDatabase` exposes Oracle/print mutation APIs backed by `db/catalog.py`. Admin mutations delegate transaction ownership, validation, canonical mappings, both search indexes, manifests, and dependent tags/favorites; shared image assets survive deletion. Catalog upserts reuse print-state maintenance. Rollback and structured-search regressions are covered. Read-only admin listing SQL remains for later database modularization. |
| A3 / 9 - complete | Bulk downloads retain contextual request/failure logs. Editor task, search, image, import, card-detail, and project-browser failures now retain tracebacks and identifiers in a shared rotating diagnostic log, with concise UI errors, thread-safe initialization, and stderr fallback. Cancellation is not logged as an error. |
| A4 / 5 - complete | Editor role analysis, dated legality inputs, and Oracle-tag lookup use `CardService` APIs. Runtime editor code no longer reaches through `service.database`; local/read-only behavior, batched reads, missing-data handling, and database-free editor test doubles are covered. |
| A5 / 3 - complete | Database internals are split into schema, cards, search, images, preferences, and sync operation groups behind the unchanged `CardDatabase` facade. `db/__init__.py` is a lightweight public boundary; `catalog.py` retains transactional mutation ownership. See the [database module guide](../Mtg_Projects/mtg_core/mtg_core/db/README.md). |
| A6 / 4 - complete | `CardService` retains its public facade and shared dependencies, with internal search, artwork, image, and catalog-sync operation groups. Cross-group overrides and injected fetch functions are preserved. See the [service module guide](../Mtg_Projects/mtg_core/mtg_core/services/README.md). Regression acceptance passed in GitHub Actions on `dd74f32`. |
| A7 / 6 - complete | Qt-independent `DeckSession` owns document/history, dirty state, save/open/new, and recovery. `EditorTaskRunner` owns task execution/cleanup and error signals; `SearchController` owns debounce, cache, cancellation, and stale-result suppression. `EditorWindow` retains presentation, autosave scheduling, and shutdown coordination. Session/controller regression acceptance passed in GitHub Actions on `dd74f32`. |
| A8 / 7 - complete | Qt-independent `mtg_print` owns payloads, physical card rules, placement/page sequencing, state/library/recovery, configuration/geometry, and image/artwork workflows. Shared dialogs/workers live in `mtg_ui`; Editor uses package imports without adding Proxy to `sys.path`. Proxy retains compatibility imports and delegates PDF geometry to the same implementation. Import-isolation, module-identity, existing UI, and handoff regressions passed in GitHub Actions on `dd74f32`. |
| A9 / 8, 10 - complete | Added Core `DeckSection` values across deck persistence, text import, sampling, legality/commander checks, and editor section controls. Display labels remain separate; unknown section strings and serialized values remain compatible. Round-trip/import regressions passed in CI. Bulk-download checkpoint values now share Core `SyncStatus` across persistence, service transitions, and admin UI; known values are typed while unknown checkpoint strings remain compatible. Sync-status regression coverage passed in CI. `DeckEntry` now owns typed oversized/crop flags and backside asset identity, with legacy constructor/JSON compatibility and shared editor/print consumers; regression acceptance passed in CI on `e959c55`. Core also owns the shared `HighResOverride` model, exposed through typed `DeckEntry.art_override`; print compatibility imports, unknown artwork metadata, and legacy JSON remain supported. Artwork round-trip, history, and handoff regressions passed in CI on `130e47f`. Temporary facts/category suggestions remain extension metadata. |
| A10 / 11 - implemented; CI pending | SQLite `user_version` and ordered migrations support fresh creation and automatic legacy upgrades. Tables/compatibility columns precede dependent indexes; an immediate transaction protects schema changes and version updates, and newer schemas are rejected. Fresh/legacy, reopen, rollback/retry, ordering, and future-version regression coverage awaits CI. |
| A11 / 12 - implemented; CI pending | Pinned Ruff runs lint and formatting checks alongside pytest on Python 3.12/3.13 CI. An explicit allowlist covers typed Core state, migrations, and their tests; basic errors/Pyflakes are enabled without a blanket rewrite. Broader coverage and type checking can follow later. |

**A1-A9 are complete; A10-A11 are implemented pending CI.** Continue with typed persistent state and shared preferences, with regression acceptance in CI. Introduce migrations before any subsequent schema change needs them. Complete the relevant boundaries before expanding recommendations, rules storage, or gameplay; do not delay unrelated editor fixes behind the whole epic.

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
- [~] Section inclusion, basic-land inclusion, token suggestions, and do-not-print exclusions exist; ownership-count controls remain.
- [x] Suggest related tokens for included cards before opening print preview; selected tokens are added only to the print handoff.
- [~] Shared artwork picker and linked Proxy print settings are reused; unified preference editing remains.
- [x] Return from print preparation without losing editor selection, scroll, filters, or Undo history.

**Exit gate:** A deck can move from editor to calibrated physical print without reselecting cards or artwork.

### 14. Shared preference ownership

- [ ] Put global printing/art preferences in Core with a versioned schema.
- [~] Share the artwork preference editor across Core (**Preferences > Artwork preferences**), Deck Editor (**More > Artwork preferences**), and Proxy's artwork picker (**Preferences**). The standalone `mtg_ui` dialog reloads shared rules on open and saves only on acceptance; printing preference editing remains.
- [ ] Define project overrides and a reset-to-global action.
- [ ] Notify open apps when shared preferences change or refresh on focus safely.
- [~] Added integration coverage for shared artwork-dialog entry points, cross-service print selection, reload, Cancel, and save errors; acceptance awaits CI. Global printing preference resolution remains.

## Phase 5 — Intelligence after the editor is solid

### 15. Deterministic guidance

Implemented pending CI; see [guidance and dataset notes](recommendation-data.md).

- [~] Detect likely shortages in lands, ramp, draw, and interaction using configurable rules.
- [~] Use local Oracle Tags plus user overrides for functional counts.
- [~] Explain every suggestion and allow dismissal/override.
- [~] Avoid presenting heuristic categories as rules facts.

- [~] Suggest deck-specific themes only when a meaningful, configurable threshold is met; keep final category assignments under user control.

### 16. Local recommendation dataset

Archidekt is the primary source. The user authorized one personal/noncommercial run with pacing, caching, and no raw-data redistribution; a resumable single-worker collector populates the primary cache with incremental aggregates. EDHREC is a behavioral reference, BlueprintMTG optional and unverified. Local data supplements public results only at 15 relevant decks. Phase 5 implementation is complete pending CI and representative public-corpus quality/performance acceptance: source adapters, importers, joint commander statistics, contextual scoring, browser controls, and versioned personal offline archives are present. No public aggregate distribution is configured. See [source policy, scoring, and acceptance limits](recommendation-data.md).

- [~] Choose licensed/public decklist sources and document provenance and refresh policy.
- [~] Build a resumable ingestion and normalization pipeline.
- [~] Precompute commander inclusion rates and baseline card popularity.
- [~] Calculate transparent synergy scores against baseline popularity.
- [~] Store compact indexed aggregates rather than loading raw decks during editor use.
- [~] Add freshness, source, and sample-size indicators.

- [~] Add a recommendation grid/list with previews, expandable reasons, immediate Add to Deck, categories/themes, and Scryfall-style filtering.
  - Add Cards now has separate Syntax Search and Recommendations tabs, preserving the search UI and visual recommendation grid with card-type browsing, quantity badges, compact explanations, shared add commands, and lazy cached thumbnails; Qt regression acceptance pending CI.
- [~] Combine commander usage, co-occurrence, type-based archetypes, color identity, themes, synergy, popularity, curve needs, and role gaps through transparent, adjustable scoring.
- [~] Download/cache versioned personal recommendation aggregates for offline use without requiring EDHREC during normal operation; explicit HTTPS transfer with checksum validation, no hosted public feed.

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

## Phase 8 - Versioned game protocol and rules-engine feasibility

- [ ] Evaluate XMage as the preferred initial authoritative engine, with Forge as an investigation alternative; verify feasibility and license compatibility before incorporating code. Keep engine-specific classes out of application models and UI.
- [ ] Compare embedding, subprocess, and API integration while preserving Manaforge's UI; document supported cards/formats and limitations.
- [ ] Define versioned Manaforge snapshots, player views, game objects, legal actions, choices, events, seats, combat assignments, and commands behind an engine adapter; run gameplay/UI against a fake engine without XMage installed.
- [ ] Map persistent Oracle/printing IDs to engine definitions without persisting XMage class identities in decks.
- [ ] Pin the Manaforge/protocol/XMage revision/adapter compatibility tuple; prohibit silent upstream engine replacement. Build compatibility and rules-scenario tests for deliberate upgrades.
- [ ] Prove: load deck -> start game -> draw hand -> list legal actions -> play land -> cast simple spell -> resolve.

**Exit gate:** Documented engine/licensing decision, fake-engine proof, and reproducible integration; upgrade between two supported XMage revisions without changing the Manaforge-facing protocol or gameplay UI before expanding gameplay scope.

## Phase 9 - Rules-enforced local play

- [ ] Keep a deterministic, authoritative engine behind presentation/client and game API layers. UI requests actions and renders events; rules stay outside UI.
- [ ] Support legal actions/targets, costs/mana payment, stack/priority, phases/steps, triggers, replacement effects, combat/damage, state-based actions, tokens/counters, and zone movement.
- [ ] Preserve hidden information and clearly identify supported-rule/card limitations.
- [ ] Render current game objects by unique ID, including copies, merged components, face-down objects, transforms, control changes, attachments, and continuous effects; Inspect explains current characteristics and provenance.
- [ ] Group equivalent objects while retaining individual IDs; split groups when state differs. Batch repetitive triggers only when rules, choices, and priority permit; retain single-step resolution and inspection.
- [ ] Target ordinary laptops (4-core CPU/8 GB RAM minimum; 6-core/16 GB recommended, integrated graphics) using thumbnails, lazy loading, bounded caches, asynchronous engine/network work, and event/diff updates. Validate these as performance targets, not measured guarantees.
- [ ] Provide legal-action/target highlights, readable stack, priority stops/automatic passing, attack/block selection, clear prompts, card zoom, and responsive battlefield interaction.

**Exit gate:** Supported games automate bookkeeping with deterministic tests, serializable state, and action/event logs suitable for replay and networking.

## Phase 10 - Mixed human/AI seats and local deck testing

- [ ] Separate match seat, player, deck, pilot, and controller; support LocalHuman, RemoteHuman, and EngineAI through the same legal-action protocol. Remote connections follow in Phase 11.
- [ ] Expose usable XMage AI first and an **Add Computer** seat action; support mixed human/AI tables as multiplayer capacity arrives in Phase 12.
- [ ] Improve adapted AI with heuristics, state evaluation/search, and deck-aware strategy only as needed; keep all decisions within engine-provided legal actions.
- [ ] Cover sensible spell/target choices, interaction, and combat decisions to expose deck weaknesses.

**Exit gate:** Repeatable matches provide useful testing; competitive strength and LLM integration are not prerequisites.

## Phase 11 - Private 1v1 multiplayer

- [ ] Support host, invite/code, and join; prefer peer-to-peer where practical and evaluate lightweight rendezvous only if needed.
- [ ] Keep the host authoritative, validate client commands, and transmit only visibility-filtered state/events; never send hidden opponent data merely to conceal it in the UI. Support reconnect.
- [ ] Keep transport replaceable across localhost, LAN, direct internet, VPN-style connections, WebRTC, or a future relay.
- [ ] Test action validation, determinism, hidden-information isolation, and disconnect recovery.

**Exit gate:** Friends can complete and reconnect to private games using existing decks without state divergence or hidden-information leaks.

## Phase 12 - Adaptive 2-5-player Commander

- [ ] Support 2, 3, 4, and 5 seats with any supported mixture of humans and AI, multiplayer priority/combat, and Commander state; avoid a protocol-level five-seat maximum.
- [ ] Provide Overview, Compare, Focus, and Inspect contexts with stable player positions and readable adaptive boards.
- [ ] Emphasize relevant attacker/defender boards, group split attacks by defender, and offer personalized blocking views with access to the complete table. Reuse radial legal actions and batch/count-based selection.
- [ ] Add visibility-filtered spectators, saved/recoverable matches, LAN support, and event logs suitable for replay without weakening player privacy.

**Exit gate:** Supported 2-5-seat Commander games remain readable and retain authoritative rules, mixed controllers, correct private views, and reconnect behavior.

## Phase 13 - Playgroups and history

- [ ] Keep portable, local/user-owned playgroups with members, decks, sharing permissions, games, ranking configuration, and statistics.
- [ ] Separate deck ownership from match piloting; support private, playgroup-visible, and borrowable decks, including AI pilots without ownership transfer.
- [ ] Resolve personal, shared, borrowed, imported public, draft, and cached preconstructed decks through the canonical deck representation; allow precon assignment directly to seats.
- [ ] Configure local ranking/bracket rules independently of official Commander brackets. Initially support ten decks per bracket with Bracket 1 strongest; snapshot rank/bracket at match time and distinguish observed win rate from deck power.
- [ ] Record digital matches automatically: players/pilots, deck identities/owners, commanders, starting player, turns, result, duration, elimination order, and event log. Support physical-game entry for the shared history workflow.
- [ ] Provide local player/deck/pilot, commander, matchup, finish, duration, and historical ranking statistics.
- [ ] Investigate optional Playgroup.gg synchronization through an adapter where its API supports it; service failure must not block play, decks, local history, or analytics.

**Exit gate:** A playgroup can select owned, borrowed, shared, or preconstructed decks, complete a game, and inspect locally retained results by deck and pilot with historical brackets preserved. External synchronization is optional.

## Phase 14 - Complete-loop polish

- [ ] Once Build -> Test -> Learn -> Print -> Play -> Track -> Improve works, invest in richer animations, transitions, effects, sound, onboarding, and accessibility improvements.
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

- [ ] Preserve a known-good application/engine/adapter combination plus locally available card/rules data, decks, playgroups, recommendations, and assets so previously supported gameplay survives upstream service loss.

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
2. Architecture A1-A5 are complete: shared persistence invariants, transactional admin operations, diagnostics, editor service boundaries, and database modularization. A6-A8 service, editor, and shared-print boundaries passed GitHub Actions verification; continue with A9 typed persistent state alongside the Phase 4 integration work below.
3. Complete Phase 4 print handoff and shared preferences alongside A6-A8 service/session and shared-print extractions.
4. Finish typed persistent state, migrations, and focused quality tooling (A9-A11); introduce migration support sooner if schema changes require it.
5. Add explainable guidance and offline recommendation datasets/UI (Phase 5) after the editor is stable.
6. Add the versioned rules reference (Phase 6), then reusable manual local playtest (Phase 7).
7. Prove engine and licensing feasibility (Phase 8) before rules-enforced local play (Phase 9).
8. Add mixed human/AI seats (Phase 10), private host-authoritative 1v1 (Phase 11), then adaptive 2-5-player Commander (Phase 12).
9. Add local playgroups, borrowing, precons, brackets, and history (Phase 13), with optional external sync.
10. Invest in complete-loop polish (Phase 14); schedule optional ecosystem work only when needed.

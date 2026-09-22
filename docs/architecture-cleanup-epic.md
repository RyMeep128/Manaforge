# Epic: Manaforge Architecture Cleanup and Boundary Hardening

## Goal

Refactor Manaforge’s current architecture so that the existing application boundaries are clearer, duplicated domain logic is removed, and future systems such as recommendations, rules lookup, and multiplayer can be added without increasing coupling.

This is **not** a rewrite. The current architecture is functional, tested, and already separated into `mtg_core`, `mtg_editor`, `mtg_proxy`, and shared UI code. The goal is to preserve behavior while reducing boundary erosion and duplicated responsibilities that have accumulated as the project has grown.

All existing behavior and tests should remain working throughout the refactor.

## Primary concerns

The current codebase has several areas where responsibilities have started overlapping:

* `EditorWindow` has accumulated too much orchestration responsibility.
* `CardDatabase` contains persistence, search, image storage, preferences, sync-state management, and canonical-print logic.
* `CardService` has accumulated search, artwork, image, synchronization, and bulk-download responsibilities.
* `CardAdminService` bypasses parts of the database abstraction and directly manipulates SQLite tables.
* Canonical-print logic and `PrintRecord` row conversion are duplicated between the database and admin layers.
* The Deck Editor reaches through `CardService` into `service.database`.
* `proxy_adapter.py` modifies `sys.path` and imports internal modules from the Proxy application.
* Important domain state is increasingly stored as magic keys inside `extras`.
* Some background tasks swallow exceptions without logging useful diagnostics.
* Stable domain concepts are represented through repeated string literals.

The objective is to clean these up incrementally while keeping the project easy to understand.

---

# Workstream 1: Remove duplicated database/domain logic

## Problem

Canonical-print selection currently exists in more than one place.

`CardDatabase` owns:

* `_refresh_canonical_print`
* `_row_to_print_record`

`CardAdminService` separately owns:

* `_refresh_canonical_print`
* `_refresh_canonical_or_delete`
* `_row_to_print_record`

These implementations are duplicated and have already diverged slightly in behavior.

For example, one canonical-print implementation returns when no prints remain, while the admin implementation deletes the stale canonical mapping.

## Desired outcome

There should be one authoritative implementation for:

* converting database rows into `PrintRecord`
* refreshing a canonical print
* removing a canonical mapping when no valid print remains
* maintaining print-related secondary indexes/data

Admin operations should reuse the same persistence logic as normal application operations whenever practical.

## Suggested direction

Move canonical-print maintenance into `CardDatabase` or a dedicated print repository.

Possible public methods:

```python
refresh_canonical_print(connection, oracle_id)
refresh_canonical_or_delete(connection, oracle_id)
row_to_print_record(row)
```

Prefer a cleaner repository-level API if that naturally emerges.

Do not preserve duplicate private implementations just to minimize edits.

## Acceptance criteria

* Only one canonical-print selection implementation exists.
* Only one authoritative `PrintRecord` row-conversion implementation exists.
* Admin create/update/delete paths use the shared logic.
* Existing admin and database tests continue to pass.
* Add regression coverage for deleting the final print belonging to an Oracle card.

---

# Workstream 2: Stop `CardAdminService` from becoming a second database layer

## Problem

`CardAdminService` directly uses:

```python
with self.database.connect() as connection:
    connection.execute(...)
```

and knows implementation details of tables such as:

* `cards_oracle`
* `prints`
* `canonical_prints`
* `image_manifest`

This creates two write paths:

```text
Normal app:
CardService
    ↓
CardDatabase
    ↓
SQLite

Admin:
CardAdminService
    ↓
SQLite directly
    + selected CardDatabase helpers
```

That makes database invariants easier to violate.

## Desired outcome

Persistence rules should live below the admin service.

`CardAdminService` should express administrative intent, not manually reproduce database invariants.

Target direction:

```text
CardAdminService
        ↓
CardDatabase / repositories
        ↓
SQLite
```

## Suggested extraction

Add explicit persistence operations where useful:

```python
create_oracle_card(...)
update_oracle_card(...)
delete_oracle_card(...)

create_print(...)
update_print(...)
delete_print(...)
```

These methods should own required follow-up work such as:

* search index refresh
* search-data refresh
* canonical-print refresh
* image-manifest cleanup
* dependent-record cleanup

Do not simply move existing SQL into equally large generic methods. Keep operations domain-focused.

## Acceptance criteria

* Admin mutations no longer manually duplicate persistence invariants.
* Search/canonical state remains correct after admin operations.
* Admin tests remain green.
* Database-related behavior is centralized enough that a future schema change has one obvious place to modify.

---

# Workstream 3: Break `CardDatabase` into maintainable internal modules

## Problem

`mtg_core/db/__init__.py` is approximately 1,250 lines.

`CardDatabase` currently handles:

* connection setup
* schema setup/upgrades
* cards and printings
* local search
* FTS maintenance
* Scryfall syntax support
* Oracle tags
* categorization data
* legality data
* image manifests
* image asset persistence
* filesystem asset storage
* artwork preferences
* sync state

The public API may remain convenient, but the implementation should no longer live in one giant `__init__.py`.

## Desired outcome

Split implementation by responsibility while preserving a simple API for callers.

One possible structure:

```text
mtg_core/db/
    __init__.py
    database.py
    schema.py
    cards.py
    search.py
    images.py
    preferences.py
    sync_state.py
```

Alternative naming is fine if a clearer design emerges.

## Important constraint

Do not force every caller to instantiate six different repositories unless that actually improves the architecture.

It is acceptable for `CardDatabase` to remain a façade:

```python
database.search_prints(...)
database.get_image_asset(...)
database.set_artwork_favorite(...)
```

while internally delegating to smaller components.

## Acceptance criteria

* `db/__init__.py` becomes a lightweight package boundary.
* No single database implementation file contains unrelated search, image, sync, and preference logic unless justified.
* Public behavior remains compatible.
* Existing DB tests continue to pass.

---

# Workstream 4: Split `CardService` internally

## Problem

`CardService` currently handles:

* local search
* remote fallback search
* card lookup
* printing lookup
* artwork preferences
* preferred-print selection
* image lookup/download/materialization
* Oracle tag synchronization
* missing-card retrieval
* bulk catalog/image download
* resumable sync state

This is becoming too broad.

## Desired outcome

Keep a convenient application-facing façade while extracting stable subsystems.

Suggested services:

```text
CardSearchService
ArtworkService
CatalogSyncService
```

Possible image-specific service if warranted:

```text
ImageService
```

`CardService` may remain as a façade for backward compatibility.

Example:

```python
class CardService:
    def __init__(...):
        self.search = CardSearchService(...)
        self.artwork = ArtworkService(...)
        self.sync = CatalogSyncService(...)
```

or retain forwarding methods if current callers benefit from them.

## Acceptance criteria

* Bulk sync logic is no longer mixed directly with ordinary card lookup/search behavior.
* Artwork preference logic has a clear owner.
* Existing callers do not require a large-scale rewrite.
* Existing tests continue to pass.

---

# Workstream 5: Remove GUI → database abstraction leaks

## Problem

The editor currently does things such as:

```python
self.service.database.categorization_data(...)
```

and:

```python
analyze_entries(self.service.database, entries)
```

That means the UI knows both the service and persistence layers.

## Desired outcome

The editor should depend on application/domain services rather than database implementation details.

Potential APIs:

```python
service.get_categorization_data(...)
service.analyze_entries(...)
```

or a dedicated:

```python
CategorizationService
```

Use whichever fits the existing design better.

## Acceptance criteria

* `mtg_editor` should not normally access `service.database`.
* Categorization behavior remains testable independently of Qt.
* No unnecessary wrapper methods should be introduced solely for aesthetics; create a meaningful application boundary.

---

# Workstream 6: Reduce `EditorWindow` responsibility

## Problem

`EditorWindow` currently handles:

* complete UI construction
* document/session state
* undo/redo
* autosave
* search
* background workers
* deck mutation orchestration
* file persistence
* project opening
* recovery
* categorization
* artwork replacement
* printing
* import/export
* project browser integration
* shutdown/background-task behavior

Much domain behavior has already been extracted, which is good, but the window still owns too much orchestration.

## Desired outcome

`EditorWindow` should primarily coordinate widgets and application actions.

Likely extractions:

### `DeckSession` or `DeckController`

Own:

* current `DeckDocument`
* `DeckHistory`
* path
* saved snapshot / dirty state
* save
* open
* new
* recovery
* document replacement

### `EditorTaskRunner`

Own:

* background task execution
* worker lifecycle
* error propagation
* enabling/disabling UI while a task is running

### Search controller or widget

Own:

* current query
* search worker
* stale-result handling
* search-result population

A dedicated `SearchPanel` widget may also be appropriate.

## Important constraint

Do not over-engineer this.

Avoid turning every 10-line callback into a class.

The goal is to remove stable responsibilities from `EditorWindow`, not maximize the number of abstractions.

## Acceptance criteria

* `EditorWindow` becomes significantly smaller and easier to scan.
* Persistence/session behavior can be tested without constructing the full editor window where practical.
* Search/task lifecycle code is not duplicated.
* Existing editor tests remain green.

---

# Workstream 7: Replace the Proxy import hack with a real shared boundary

## Problem

`mtg_editor/proxy_adapter.py` currently changes `sys.path` at runtime:

```python
sys.path.append(...)
```

and imports internal Proxy modules such as:

```python
from dialogs import HighResPickerDialog
from models import ProjectState
import high_res
import project_library
import deck_import
```

This tightly couples the editor to Proxy's directory layout and internal module names.

## Desired outcome

Reusable printing/proxy functionality should live in a proper package imported normally by both applications.

Potential structure:

```text
mtg_print/
    project.py
    artwork.py
    import_service.py
    layout.py
    printing.py
```

Exact naming is flexible.

`mtg_proxy` should become the UI/application layer for proxy printing.

`mtg_editor` should call the shared printing/project APIs.

## Important constraint

This can be incremental.

Do not move every Proxy file in one giant commit.

Start with the functionality currently required by `proxy_adapter.py`.

## Acceptance criteria

* `mtg_editor` no longer modifies `sys.path`.
* Editor-to-print integration uses normal package imports.
* Proxy's existing UI still functions.
* Print handoff tests continue to pass.
* Shared functionality has no unnecessary Qt dependency unless inherently UI-specific.

---

# Workstream 8: Promote mature `extras` keys into typed state

## Problem

`extras` is useful for compatibility, but increasingly important state currently lives there.

Examples include:

```text
facts
auto_categories
art_override
proxy_front_name
oversized
backside_name
backside_asset_id
backside_short_edge
pre_cropped
backside_pre_cropped
category_suggestion
```

## Desired outcome

Keep `extras` as an extension/forward-compatibility mechanism, but identify fields that are now permanent domain concepts and promote them into typed models.

Good candidates should be fields that:

* are used in several modules
* materially affect behavior
* are saved permanently
* have stable semantics

Do not promote truly temporary or compatibility-only metadata.

## Suggested first candidates

Evaluate:

```text
oversized
pre_cropped
backside_asset_id
backside_pre_cropped
art_override
```

`facts` may deserve its own structured/card-summary model rather than many new fields directly on `DeckEntry`.

## Acceptance criteria

* Frequently used permanent state no longer relies solely on undocumented dictionary keys.
* Backward-compatible loading from old `extras` data is preserved.
* Serialization tests cover old and new formats.

---

# Workstream 9: Standardize logging and exception reporting

## Problem

Some background operations swallow exceptions.

Example:

```python
except Exception:
    failed += 1
```

Other parts return only:

```python
str(exc)
```

and lose traceback information.

Proxy already has stronger logging patterns in places such as `deck_import.py`.

## Desired outcome

Use Python `logging` consistently across Core, Editor, and Proxy.

User-facing errors should remain concise, but debugging information should include:

* exception traceback
* operation
* relevant card/project identifier
* relevant source URL or path when safe/useful

Example:

```python
except Exception:
    logger.exception(
        "Image download failed card_id=%s url=%s",
        card_id,
        image_url,
    )
    failed += 1
```

## Acceptance criteria

* Bulk image failures are logged with context.
* Background editor worker failures retain tracebacks.
* No user-facing traceback is required.
* Existing behavior remains user-friendly.

---

# Workstream 10: Reduce magic-string domain state

## Problem

Stable concepts are represented repeatedly as strings:

```text
mainboard
commander
sideboard
considering
excluded

Grid
Stacks

Category
Mana Value
Color

running
paused
failed
completed
```

## Desired outcome

Introduce enums/constants where they improve safety and clarity.

Good candidate:

```python
from enum import StrEnum

class DeckSection(StrEnum):
    MAINBOARD = "mainboard"
    COMMANDER = "commander"
    SIDEBOARD = "sideboard"
    CONSIDERING = "considering"
    EXCLUDED = "excluded"
```

Potentially similar treatment for persistent sync statuses.

Do not convert every UI label into an enum.

Keep UI display labels separate from persistent/domain values.

## Acceptance criteria

* Core persistent states use centralized definitions.
* Serialization remains backward compatible.
* Code becomes easier to refactor without broad string search/replace operations.

---

# Workstream 11: Introduce formal database migrations

## Problem

Database evolution currently relies on schema setup and targeted column/index checks.

Manaforge is a local-first application where users may eventually have a very large local card/image collection. Database compatibility therefore matters.

## Desired outcome

Add explicit schema versioning and ordered migrations.

SQLite `PRAGMA user_version` is an acceptable lightweight mechanism.

Example:

```text
schema version 1
    ↓
migration 1 → 2
    ↓
migration 2 → 3
```

Migration implementation may be Python or SQL.

## Requirements

* New database creation must still work cleanly.
* Existing databases should migrate automatically.
* Migrations must be tested.
* Avoid destructive rebuilds where unnecessary.

## Acceptance criteria

* Current database schema has an explicit version.
* At least the migration framework exists even if current schema is treated as version 1.
* Migration tests can create an older schema and verify upgrade behavior.

---

# Workstream 12: Quality tooling

Add lightweight static-quality checks to CI.

Suggested minimum:

```text
pytest
ruff check
ruff format --check
```

Do not perform a massive formatting rewrite unless necessary.

Consider `pyright` or `mypy` later, but do not block this epic on complete typing of the existing project.

## Acceptance criteria

* CI continues testing Python 3.12 and 3.13.
* Ruff runs on pushes/PRs.
* Existing project style is brought into compliance through focused cleanup.

---

# Non-goals

Do not:

* rewrite Manaforge
* replace PyQt6
* change the persisted deck format unnecessarily
* redesign the user interface
* introduce AI functionality
* build the recommendation system as part of this epic
* build multiplayer
* implement the comprehensive-rules system
* remove backward compatibility with current projects
* create abstractions solely to reduce line counts

The point of this epic is to make the current foundation cleaner before those systems arrive.

---

# Recommended implementation order

1. Remove duplicated canonical-print and row-conversion logic.
2. Centralize admin persistence operations.
3. Add regression tests around database invariants.
4. Introduce logging improvements.
5. Remove editor access to `service.database`.
6. Split `CardDatabase` implementation.
7. Split `CardService` internals.
8. Extract editor session/task/search responsibilities.
9. Replace the Proxy `sys.path` integration boundary.
10. Promote mature `extras` fields.
11. Introduce formal schema migrations.
12. Add/finish Ruff CI and documentation cleanup.

Make each stage independently testable and preferably commit/refactor in small pieces.

---

# Definition of done

This epic is complete when:

* all current tests pass
* CI passes on Python 3.12 and 3.13
* no duplicated canonical-print implementation remains
* admin persistence uses shared database/repository invariants
* the editor does not directly reach through `CardService` to its database
* the editor no longer modifies `sys.path` to consume Proxy internals
* `CardDatabase`, `CardService`, and `EditorWindow` have substantially clearer responsibilities
* failures in background/network work produce useful diagnostic logs
* stable domain state is less dependent on undocumented magic strings and `extras`
* database evolution has an explicit migration/version strategy
* behavior visible to users remains unchanged unless a bug is being fixed

The guiding rule for the refactor is:

> Preserve the simple public interfaces that make Manaforge easy to work with, but make the internals have one clear owner for each responsibility.

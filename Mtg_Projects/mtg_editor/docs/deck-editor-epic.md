# Deck Editor Epic: Archidekt-Inspired Builder

## Epic Overview

Print Proxy Prep should gain a dedicated deck editor that lets Magic: The Gathering players build, organize, tune, and prepare decks before sending them into the existing proxy-print workflow. The experience should be inspired by Archidekt's visual deckbuilding patterns: image-first card browsing, fast card add, import workflows, flexible grouping, categories, deck stats, autosave, and playtest-style sampling.

This epic is documentation and planning only. It does not require app behavior changes yet.

## Product Goal

As a player preparing proxies, I want a visual deck editor that feels like a real deckbuilding workspace, so that I can move from an idea or imported list to an organized, printable project without bouncing between multiple tools.

Success means a user can:

- Create or open a deck project.
- Add cards by search, quick add, file import, pasted list, CSV, or public Archidekt URL.
- View cards visually with useful grouping and sorting.
- Organize cards into deckbuilding categories and tags.
- Understand deck composition and print readiness at a glance.
- Playtest sample hands before printing.
- Save and reload work without losing existing print settings.
- Continue into the existing PDF/render workflow.

## Archidekt-Inspired Principles

- Visual first: cards should be browsable as images, not only as rows of text.
- Fast entry: known cards should be addable quickly, while search still supports exact print/art selection.
- Flexible organization: users should be able to group by card type, mana value, color, import order, custom categories, and tags.
- Deckbuilding context: counts, categories, stats, missing assets, and print readiness should stay visible while editing.
- Low friction persistence: editor changes should autosave and still work with existing Save Project and Load Project flows.
- Workflow-inspired, not platform clone: collaboration, public deck discovery, shopping carts, and social sharing are later or out of scope.

## References

- Current Print Proxy Prep features: `Mtg_Projects/mtg_proxy/README.md`
- Archidekt deck editor FAQ: https://archidekt.com/faq
- Archidekt product positioning: https://archidekt.com/landing
- Archidekt feature voting themes: https://archidekt.com/features

## Release Strategy

### MVP

The MVP should deliver the smallest complete deckbuilding loop:

- Create/open a deck workspace.
- Add cards through quick add, search, pasted list, file import, CSV, and public Archidekt URL.
- Show a visual card grid with quantities and print-readiness status.
- Support basic grouping and sorting.
- Support custom categories.
- Save/reload editor state.
- Continue into the existing print preview and PDF workflow.

### Follow-Up Release

After the MVP, deepen deckbuilding ergonomics:

- Multi-tag cards.
- Bulk editing.
- More deck stats.
- Playtest-lite hand simulation.
- Autosave status and recovery messaging.
- Better category templates.

### Later / Out Of Scope

These are intentionally not required for the first deck editor epic:

- Live collaboration.
- Public deck profile pages.
- Public deck discovery.
- Shopping cart export or vendor integrations.
- Full collection management.
- Full game simulator or rules engine.
- Social feeds, comments, likes, or voting.

## Feature Themes And User Stories

### 1. Deck Workspace

Feature intent: Give users a named editing surface for deck work, connected to the existing project library and print workflow.

#### DE-001: Create A Deck Workspace

Priority: P0

As a proxy-prep user, I want to create a named deck workspace, so that my deckbuilding work is organized separately from one-off image folders.

Acceptance criteria:

- The user can create a deck with a name.
- The user can optionally choose a format, such as Commander, Modern, Standard, Pauper, or Custom.
- The editor stores deck metadata separately from render settings.
- A newly created deck opens directly into the deck editor.
- A new empty deck shows a clear empty state with actions to add or import cards.

#### DE-002: Open A Recent Deck

Priority: P0

As a returning user, I want to open a recent deck from the project library, so that I can continue editing without manually locating files.

Acceptance criteria:

- Deck projects appear in the project dashboard with name, modified date, card count, and thumbnail when available.
- Opening a deck restores card counts, categories, tags, print settings, backsides, oversized flags, and high-res overrides.
- If a deck references missing image files or cache entries, the app warns without blocking deck editing.

#### DE-003: Show Deck Header Summary

Priority: P1

As a deckbuilder, I want a compact deck header, so that I can quickly confirm what deck I am editing.

Acceptance criteria:

- Header shows deck name, format, total cards, printable copies, and save status.
- Header includes primary actions for Add Card, Import, Playtest, Save Project, and Print Preview.
- Header does not replace the existing print settings panel; it complements it.

### 2. Visual Deck Builder

Feature intent: Replace the current all-cards print grid as the main deckbuilding view while preserving print-count controls.

#### DE-004: View Cards In A Visual Grid

Priority: P0

As a user, I want to see my deck as card images, so that editing feels like arranging physical cards.

Acceptance criteria:

- Cards display as image tiles with card name, quantity, and print-readiness indicators.
- Existing low-DPI, backside, oversized, and high-res indicators remain available.
- Card quantity can be incremented, decremented, reset, or directly edited from the tile.
- Clicking a card still supports existing art/high-res selection behavior where applicable.

#### DE-005: Group Cards By Common Deckbuilding Views

Priority: P0

As a deckbuilder, I want to group cards by meaningful attributes, so that I can evaluate the deck from different angles.

Acceptance criteria:

- The editor supports Group By: None, Card Type, Mana Value, Color, Custom Category, and Import Section.
- Changing group mode changes only the view, not card quantities or print settings.
- Empty groups are hidden by default.
- Group headers show group name and card count.

#### DE-006: Sort Cards Within Groups

Priority: P0

As a deckbuilder, I want sorting controls, so that I can scan the deck in the order that matches my current task.

Acceptance criteria:

- The editor supports Sort By: Alphabetical A-Z, Alphabetical Z-A, Mana Value, Color, Quantity, and Import Order.
- Sort order persists with the deck editor preferences.
- Sorting does not change persisted card quantities or category assignments.

#### DE-007: Switch Between Grid And Text Views

Priority: P1

As a power user, I want both visual and compact text views, so that I can choose the right mode for browsing or auditing.

Acceptance criteria:

- Grid view is the default.
- Text view shows quantity, card name, category, set code, collector number, and print status.
- Text view supports the same group and sort settings as grid view.
- Switching views does not lose selection or unsaved changes.

### 3. Quick Add + Search

Feature intent: Make adding individual cards fast while preserving exact printing/art control.

#### DE-008: Quick Add By Card Name

Priority: P0

As a user who knows the card I want, I want to type a card name and add it quickly, so that deckbuilding stays fast.

Acceptance criteria:

- Quick Add accepts a card name and optional quantity.
- Exact matches add immediately using the default or preferred printing.
- Ambiguous matches open the search picker with likely candidates.
- Newly added cards default to quantity 1 unless the user entered a quantity.
- The app reports when no card can be found.

#### DE-009: Search And Choose Printing

Priority: P0

As a user who cares about art or set, I want to search printings before adding a card, so that the deck uses the image I intend to print.

Acceptance criteria:

- Search can filter by card name and set code or set name.
- Results show thumbnail, card name, set, collector number, and source status.
- Selecting a result imports or materializes the matching image.
- The selected card enters the deck with stored metadata for set code and collector number.

#### DE-010: Prefer Existing Assets When Possible

Priority: P1

As a user with cached or local assets, I want the editor to reuse available card images, so that repeated deck edits are fast and resilient offline.

Acceptance criteria:

- If an exact card asset is already available, the editor reuses it instead of redownloading.
- Offline/local database behavior remains compatible with existing card search services.
- The user is warned when a card is added without a printable image.

### 4. Import + Export

Feature intent: Preserve and improve existing import flows while making them feel native to the deck editor.

#### DE-011: Import Pasted Decklists And Files

Priority: P0

As a user with an existing list, I want to paste or load it into the editor, so that I can start from my current deck.

Acceptance criteria:

- Import supports pasted text and deck files already accepted by Print Proxy Prep.
- Import supports simple lines like `4 Lightning Bolt`.
- Import supports CSV with `count`, `name`, `set_code`, and `collector_number`.
- Import reports malformed or unresolved lines after processing.
- Successfully imported cards appear in the visual deck editor with correct quantities.

#### DE-012: Import Public Archidekt Deck URL

Priority: P0

As a user with an Archidekt deck, I want to import a public Archidekt URL, so that I can prepare proxies from an existing brew.

Acceptance criteria:

- Import accepts public `https://archidekt.com/decks/...` URLs.
- Invalid or private/non-readable URLs show a clear error.
- Imported quantities, card names, set codes, and collector numbers are preserved when available.
- Double-faced card handling continues to assign matching backsides when possible.
- Import summaries show total imported cards, total copies, and failures.

#### DE-013: Export Text Decklist

Priority: P1

As a user, I want to export the current decklist as text, so that I can share it or move it into other deck tools.

Acceptance criteria:

- Export includes quantity and card name by default.
- Export can optionally include set code and collector number.
- Export excludes helper assets such as default card backs.
- Export can include or exclude maybeboard/sideboard sections.

#### DE-014: Continue To Print Workflow

Priority: P0

As a proxy-prep user, I want my deck editor work to feed into preview and PDF rendering, so that deckbuilding and printing stay connected.

Acceptance criteria:

- Cards with positive quantities appear in the existing print preview.
- Existing render settings remain available.
- Existing PDF generation behavior is not changed by category or view preferences.
- Cards marked maybeboard are excluded from print output by default.

### 5. Categories + Tags

Feature intent: Support Archidekt-style deckbuilding organization without requiring a full collection system.

#### DE-015: Create Custom Categories

Priority: P0

As a deckbuilder, I want custom categories such as Ramp, Draw, Removal, Win Conditions, and Lands, so that I can reason about card roles.

Acceptance criteria:

- User can create, rename, delete, and reorder custom categories.
- A card can be assigned to one primary category.
- Category assignment persists after save and reload.
- Deleting a category moves affected cards to Uncategorized after confirmation.

#### DE-016: Move Cards Between Categories

Priority: P0

As a deckbuilder, I want to move cards between categories, so that I can tune the deck structure quickly.

Acceptance criteria:

- User can change a card category from the card tile menu.
- Drag and drop between category groups is supported when grouping by custom category.
- Moving a card changes category only, not quantity.
- Category headers update counts immediately.

#### DE-017: Assign Multiple Tags

Priority: P1

As a deckbuilder, I want cards to have multiple tags, so that one card can count as ramp, draw, removal, or synergy at the same time.

Acceptance criteria:

- User can add or remove tags from a card.
- Tags are separate from the primary category.
- Tags persist with the project.
- Deck insights can count cards by tag.
- Tags do not duplicate cards in print output.

#### DE-018: Category Templates

Priority: P2

As a frequent deckbuilder, I want reusable category templates, so that new decks start with my preferred organization.

Acceptance criteria:

- User can save the current category list as a template.
- User can apply a template to a new or existing deck.
- Applying a template does not overwrite existing card assignments unless the user confirms.

### 6. Bulk Editing

Feature intent: Make larger deck edits practical without forcing one-card-at-a-time changes.

#### DE-019: Select Multiple Cards

Priority: P1

As a user editing many cards, I want multi-select, so that I can apply the same action to several cards.

Acceptance criteria:

- Ctrl-click toggles card selection on desktop.
- Select All selects visible cards in the current filtered/grouped view.
- Selected cards are visually distinct.
- Selection persists while changing quantities but clears after destructive actions.

#### DE-020: Bulk Change Category Or Tags

Priority: P1

As a deckbuilder, I want to bulk assign category or tags, so that deck organization is fast.

Acceptance criteria:

- Bulk actions can set primary category for selected cards.
- Bulk actions can add or remove tags for selected cards.
- The user sees how many cards will change before applying.
- The action updates counts and group headers immediately.

#### DE-021: Bulk Edit Print Settings

Priority: P2

As a user preparing print sheets, I want to bulk edit print-specific flags, so that large decks are easier to prepare.

Acceptance criteria:

- Bulk actions can set quantity, backside behavior, short-edge backside flag, and oversized flag.
- Destructive bulk quantity changes require confirmation.
- Existing individual card controls remain available.

### 7. Deck Insights

Feature intent: Surface deck composition and print readiness without making users export to another tool.

#### DE-022: Show Deck Composition Stats

Priority: P1

As a deckbuilder, I want deck stats, so that I can see whether my deck has the right balance.

Acceptance criteria:

- Stats include total cards, total printable copies, card types, colors, mana value curve, and categories.
- Stats update after add, remove, quantity change, category change, and import.
- Stats exclude helper assets and excluded sections by default.

#### DE-023: Show Print Readiness Stats

Priority: P0

As a proxy-prep user, I want print-readiness stats, so that I can fix problems before rendering.

Acceptance criteria:

- Stats include missing images, low-DPI cards, double-faced cards, cards with custom backs, oversized cards, and total PDF copies.
- Low-DPI thresholds use existing app configuration.
- Clicking a stat filters or highlights matching cards when practical.

#### DE-024: Filter Cards

Priority: P1

As a user reviewing the deck, I want filters, so that I can quickly find cards needing attention.

Acceptance criteria:

- User can filter by text, category, tag, card type, color, missing image, low DPI, backside, and oversized.
- Filters affect the visible editor only.
- Print output is not changed by filters.
- Active filters are clearly shown and can be cleared.

### 8. Playtest Lite

Feature intent: Provide lightweight deck sampling before printing, not a full rules engine.

#### DE-025: Draw Opening Hands

Priority: P1

As a deckbuilder, I want to draw sample opening hands, so that I can sanity-check deck function before printing.

Acceptance criteria:

- User can generate a randomized seven-card opening hand from printable main-deck cards.
- User can mulligan to six, five, four, three, two, or one card.
- User can reset and shuffle again.
- Cards with quantity greater than one appear according to quantity.
- Excluded sections such as maybeboard are not included by default.

#### DE-026: Draw Cards During Playtest

Priority: P2

As a deckbuilder, I want to draw additional cards, so that I can inspect early turns.

Acceptance criteria:

- User can draw one card or multiple cards from the remaining shuffled deck.
- Drawn cards move from library to hand or playtest history.
- Reset returns to a full shuffled deck.
- The playtest view warns if sampled cards are missing printable images.

#### DE-027: Save Playtest Notes

Priority: P2

As a deckbuilder, I want to jot down playtest observations, so that I can remember cuts and additions.

Acceptance criteria:

- User can add plain-text notes to the deck.
- Notes persist with the deck.
- Notes are not included in print output.

### 9. Autosave + Recovery

Feature intent: Reduce risk of lost deckbuilding work while keeping explicit Save Project behavior.

#### DE-028: Autosave Editor Changes

Priority: P0

As a user, I want deck edits to autosave, so that I do not lose progress while building.

Acceptance criteria:

- Card add, remove, quantity, category, tag, view preference, and deck metadata changes trigger autosave.
- Header shows saved, saving, and save failed states.
- Manual Save Project remains available.
- If autosave fails, the user sees a non-blocking warning with a recovery path.

#### DE-029: Recover From Cache Or Asset Problems

Priority: P1

As a user, I want the editor to recover gracefully from missing cache or image files, so that one bad asset does not block the whole deck.

Acceptance criteria:

- Missing thumbnails use the existing fallback image.
- Missing project assets are reported in print-readiness stats.
- Reloading an older project does not discard existing counts, metadata, backsides, oversized flags, or high-res overrides.

## Interface And Data Notes

Future implementation will likely need model additions. These notes are not implementation requirements for this document task, but they define the expected shape for later engineering work.

### Deck Metadata

Likely fields:

- `deck_name`
- `format`
- `description`
- `deck_tags`
- `created_at`
- `modified_at`

### Card Organization

Likely per-card fields:

- `primary_category`
- `tags`
- `section`, such as main deck, sideboard, commander, maybeboard, or excluded
- `import_section`
- `sort_index`

### Editor Preferences

Likely fields:

- `view_mode`
- `group_mode`
- `sort_mode`
- `active_filters`
- `selected_category_template`

### Autosave State

Likely runtime fields:

- `last_saved_at`
- `save_status`
- `last_save_error`

### Compatibility Requirements

Future implementation must preserve existing project behavior:

- Existing card counts must load unchanged.
- Existing backside assignments must load unchanged.
- Existing short-edge backside flags must load unchanged.
- Existing oversized flags must load unchanged.
- Existing card metadata must load unchanged.
- Existing high-res overrides must load unchanged.
- Existing image cache and fallback behavior must remain compatible.
- Existing PDF rendering must ignore deck-editor-only view preferences.
- Older project files must migrate without data loss.

## Test Plan

### Create, Edit, Save, Reload

- Create a new deck named "Test Commander Deck".
- Add several cards through search.
- Assign cards to custom categories.
- Save and close the project.
- Reopen the project.
- Verify deck name, format, cards, quantities, categories, and print settings persisted.

### Import Workflows

- Import pasted text with lines like `4 Lightning Bolt`.
- Import a supported deck file.
- Import CSV rows with count, name, set code, and collector number.
- Import a valid public Archidekt URL.
- Verify quantities, metadata, double-faced card backs, and unresolved-line warnings.

### Grouping And Sorting

- Build a deck with mixed card types, colors, and mana values.
- Switch group modes between None, Card Type, Mana Value, Color, Custom Category, and Import Section.
- Switch sort modes between Alphabetical, Mana Value, Color, Quantity, and Import Order.
- Verify card quantities and print output do not change.

### Categories And Tags

- Create categories Ramp, Draw, Removal, Lands, and Win Conditions.
- Move cards between categories using menu and drag/drop.
- Add multiple tags to a card.
- Save and reload.
- Verify categories and tags persist and stats update.

### Bulk Editing

- Select three visible cards.
- Bulk assign a category.
- Bulk add a tag.
- Bulk change quantity after confirmation.
- Verify only selected cards changed.

### Deck Insights

- Create a deck with low-DPI cards, missing images, double-faced cards, and oversized cards.
- Verify print-readiness stats show each issue.
- Fix one issue and verify the stats update.

### Playtest Lite

- Create a 60-card deck with multiple card quantities.
- Generate a seven-card hand.
- Mulligan and reset.
- Draw additional cards.
- Verify card frequency respects quantities and excluded sections are not sampled.

### Backward Compatibility

- Load an existing Print Proxy Prep project file.
- Verify counts, backsides, oversized flags, metadata, high-res overrides, preview, and PDF rendering still work.
- Save and reload the migrated project.
- Verify no existing project data was lost.

## Definition Of Done

- The deck editor can support a complete build-to-print workflow in the MVP.
- Existing Print Proxy Prep project files remain compatible.
- Deck editor preferences never change PDF output unless they represent actual card inclusion or quantity changes.
- Import errors are visible and recoverable.
- Users can understand deck composition and print readiness without leaving the editor.
- Later platform features remain clearly separated from the local desktop editor scope.

# Manaforge Deck Editor

Card **+ / −** controls change quantities in Grid and Stacks; reducing the last
copy removes that entry and supports Undo. Syntax Search and Recommendations
highlight cards already in any deck section with a green outline and **In deck**
label, including alternate printings. Highlights refresh after edits and Undo/Redo.

Run `Launch Manaforge Deck Editor.cmd` after installing dependencies with the
Proxy setup script. Alternatively run `python Mtg_Projects/mtg_editor/run_editor.py`
from the repository root with application dependencies installed.

## Internal session boundary

`session.DeckSession` owns the current document, history, path, saved snapshot,
and save/open/new/recovery operations without importing Qt. Undo/Redo preserve
current editor preferences and the linked print project. Failed reads or writes
retain the active session; recovery creates a new, unlinked deck. Proxy imports
receive a separate deck save destination.

`EditorWindow` coordinates dialogs, dirty-change guards, autosave timing, and
widget refresh. Its document/history/store/path accessors refer to the session.
`tasks.EditorTaskRunner` owns background execution, worker cleanup, callback
error reporting, and busy/settled signals. `search.SearchController` owns the
current query, debounce timer, cache, cancellation, and stale-result suppression.
The window displays their results and errors and coordinates shutdown with
thumbnail work. Session regressions in `tests/test_session.py` need no Qt
application; controller lifecycle coverage is in `tests/test_controllers.py`.

## Visual workspace

The editor shares Proxy's dark styling and green accents. **Grid** shows complete
card images; **Stacks** overlaps cards within groups. The card canvas uses all
remaining window space, and the toolbars wrap on smaller screens.

The compact deck header contains naming, format, count, save status, Undo/Redo,
Save, Print Deck, and More. Below it, tools follow **Add Cards → View As → Group
By → Sort By → Local Filter**. **Display / Tags** contains tag actions and card
size. The filter stays compact, with syntax help available through **?**.
Toolbar **Quick Add** uses the existing search panel: press Enter to search,
then Enter again once results load to add the selected or first match.

- **Quick Add** opens a resizable visual search panel. Search names or Scryfall
  syntax against the local Core catalog. Double-click a result or click its plus
  control to add that exact printing. Closing the panel retains its search and scroll.
- **Card Search** opens the full-width **Search**, **Recommendations**, and
  **Commanders** workspace. It shares Quick Add's search and blended recommendations,
  and edits the same deck session. **Back to Deck** restores the deck view.
  Commander discovery supports local name/text/type filters and
  [explicit offline EDHREC themes](../../docs/edhrec-collection.md#offline-commandertheme-discovery).
  Use **Import cached themes** to build the theme catalog from previously collected
  responses, then type in Theme and choose a match to filter commanders, or click
  **Browse themes ▾** to choose from the full dropdown list.
  Set a commander or add a compatible second commander with Undo/Redo; replacing
  existing commanders requires confirmation.
- Group by **Type**, **Mana Value**, **Color**, **Category**, or **Section**. Commander
  cards appear first. Group headings show quantities and can be collapsed.
- Sort by **Name**, **Mana Value**, **Color**, **Quantity**, or **Import Order**. Color
  sorting orders white, blue, black, red, green, multicolor, colorless, then unknown.
  Filter the deck
  by name or user tag and adjust image sizes with the slider.
- Click cards to select; Ctrl-click toggles selection, Shift-click selects a range,
  and Ctrl+A selects visible cards. Hover reveals quantity controls and a larger preview.
  Click a deck card to inspect its larger image and Oracle text. Browse printings
  fetched from Scryfall (with cached choices available offline) and choose **Use this printing** to apply one
  (Undo is available). Double-faced cards have a **Flip card** control for both image
  and rules text. Ctrl/Shift-click still selects cards without opening details.
  Double-click a deck card to open the shared Proxy artwork picker.
- **+ Add Tag** creates or reuses a Primary Role or Additional Tag, with optional
  bulk assignment to selected cards. Without a selection, it saves an unused
  definition. Narrow windows group organization actions under **Tags +**.
- Hold right mouse for **250 ms** (configurable), hold **T**, or click **Quick tags**.
  Active deck roles share one ring with smaller clockwise wedges; choices explicitly moved out of the ring
  use the toolbar's **More > Other active roles / tags**. The popup contains only
  the radial ring, with a transparent background. No global role catalog is added. **Tab** switches Primary Role /
  Additional Tags; arrows and Enter also select. Center release or Esc cancels.
  Additional Tags toggle without replacing or locking an automatic primary role.
- Quick right-click or Shift+right-click opens normal card actions. The card stays
  highlighted and the stack pauses until the interaction ends.
- **Manage Tags**, accessible from Add Tag and the toolbar's **More** menu, separates **In Use**
  and **Available** definitions with usage counts. Rename, delete, or reorder roles
  without deleting cards. **Customize Quick Menu** sets clockwise order, ring versus
  overflow, initial mode, and hold delay for this deck. Inactive choices retain
  their configuration without empty wedges. Preview and Restore defaults are available.
- Empty decks suggest only **Plan, Interact, Ramp, Draw**. These do not create
  category definitions until used. Manage Tags can rename/remove suggestions;
  Add Tag can explicitly offer a custom role in the empty-deck palette.
  Removing the last assignment hides a choice from the quick menu, while retaining
  its definition for reuse. These edits participate in Undo/Redo and deck persistence.
- **More > Category templates** provides **Commander essentials** and saved personal
  layouts. Save the current deck's category list to reuse its names and order in
  another deck; save under the same name to update a template after editing categories.
  Applying adds missing categories, preserves existing categories and assignments,
  and keeps empty category columns hidden unless requested. Apply is one Undo step. Saving a personal template
  takes effect immediately, independently of applying it to a deck.
- Drag selections onto section/category headings or cards to assign them. With
  Import Order sorting, dropping before a card also reorders the selection. Derived
  groups such as Type do not accept reassignment; reordering within the same group
  remains available in Import Order.
- **View Oracle tags** reuses Proxy's tag dialog. Clicking a tag opens its local
  search in the side panel. **Add / Remove Tags** applies deck-local organization to
  every selected card.

Images load from Core's cache first. Only visible images and a small prefetch margin
can request missing artwork, in the background. Search itself stays local. Failed
images show a placeholder with a right-click retry action; rate limits delay further
requests. Selected alternate artwork takes precedence over a printing's normal art.

## Import and export decklists

**Import** accepts pasted lists, text/CSV files, and public deck URLs. Use section headings such as
`Commander`, `Deck`, `Sideboard`, `Maybeboard`, and `Excluded`; `SB:` and `CMDR:`
prefixes apply to individual lines. Names may have a quantity and optional printing,
for example `1 Sol Ring (cmm) 410`. CSV supports `name`, `count` (or `quantity`),
and optional `section`, `set_code`, `collector_number`, `image_url`, and
`backside_image_url` columns. Enable **Download custom artwork when supplied** to
import PNG, JPEG, or WebP front/back images. Failed downloads or invalid images leave
that card unresolved. The preview identifies custom artwork; native saves and Print
Deck retain the downloaded assets. Uncheck this option to use the selected printing's art.

Click **Review import** to resolve cards against the local catalog. Enable
**Fetch missing cards online** if desired. Resolution runs in the background;
Cancel waits for the current lookup to finish and discards the import. Review the
resolved cards and unresolved lines, then click **Import reviewed cards**. Only
resolved cards are added. An unavailable exact printing is reported instead of
silently replaced. Imports preserve sections and quantities, categorize new entries,
and apply as one Undo operation. Existing manual categories are preserved when
quantities merge. Artwork downloads continue through the normal thumbnail workflow.

**More > Export decklist** previews quantity/name text with optional sections and
set/collector numbers. Copy it or save a text file. This format does not carry custom
artwork, tags, or category assignments; native deck files retain that information.

Choose **Public deck URL** in Import to load a public Moxfield, Archidekt, or
Blueprint MTG deck. **Review import** downloads the deck data; **Fetch missing cards
online** separately controls card lookups. Supported source sections, quantities,
set/collector numbers, and explicit Scryfall printing IDs are preserved. Commander
entries remain commanders; sideboards and considering lists stay separate. Exact
printing IDs preserve that printing's artwork. Explicit source overrides are also read
from `customImageUrl` / `custom_image_url`, their `customBackImageUrl` /
`custom_back_image_url` equivalents, or `artOverride` / `art_override` objects with
`front_url` / `image_url` and `back_url` fields. Normal card thumbnails are not treated
as custom artwork. Private/unavailable decks and changed source formats show errors;
no cards are applied until you accept a successful preview. These adapters are
covered by payload-fixture tests; source availability is not guaranteed.

## Save and recover

Decks save to the shared application data directory's `decks` folder, two seconds
after editing stops. The title displays `*` while unsaved. Failed saves keep changes
in memory, report the error, and retry. **Save** also works with Ctrl+S.

**Decks** provides New, Open, and recent decks. Open accepts native editor documents
and existing Proxy JSON projects. Proxy imports save as separate editor documents;
the source is retained. Existing local artwork is imported into shared image storage.

**Decks > Decks and print projects** opens the shared library browser. The same
browser is available from Proxy's project dashboard. It loads native decks and managed
print projects in the background, supports name/type filtering, and offers New deck
and Open file. Double-click a row to open it in the editor. Unavailable files are
reported without removing their library entries. Print projects remain intact when
opened as separate editor decks.

Up to five pre-save snapshots live in the adjacent `.recovery` folder.
**More > Restore recovery snapshot** restores into a new deck without overwriting
its source. View/group/sort preferences and category collapse state are saved.

Undo/Redo covers deck edits, including quantity, artwork, sections, categories, tags,
and bulk changes. View changes do not roll back when undoing a deck edit.

## Offline rules reference

Open **More > Comprehensive Rules**, then use **Download / update from Wizards**
or **Import rules TXT** to install an English rules snapshot. The download link is
discovered from the [official rules page](https://magic.wizards.com/en/rules).
Opening, searching, and navigating installed rules never require a download.
Search by rule number (for example `702.9`), keyword, or words; use Sections and
Keywords to browse. Rule references are clickable, with Back navigation.

Card details offers **Related Comprehensive Rules**. Keyword names in the shared
Oracle/rulings viewer link to the same browser. Installed effective date, download
time, source, and checksum are shown separately. Updates replace the snapshot
atomically and preserve cached rules on failure; deck files are unaffected.
Only the English numbered rules and keyword-action/ability index are searched;
the glossary remains in the retained source document. This viewer does not enforce
gameplay rules.

## Automatic categories

New cards added through search and uncategorized cards in opened/imported decks
receive categories automatically from local card data. New decks open in category
stacks; saved view preferences remain respected. Deck cards show quantity in a
colored top-left corner. The primary role sets its color, with small top-edge
accents for additional tags; category headers show the matching color. Hovered or
selected cards reveal translucent vertical +/− controls on the right. Automatic
and manual assignment records remain intact without on-card text badges.
Syntax Search, Recommendations, and commander discovery use the same controls
and corner count. Minus reduces one matching mainboard copy first, then commander
copies, with Undo/Redo; quantities shown in discovery include alternate printings.
Commander designation remains available through its dedicated button or double-click.
Manual corrections survive subsequent categorization and saving.
To explicitly replace them, enable **Reconsider manual assignments** in the review.
For an existing
deck, choose **More → Auto Categorize…**, review the proposed roles and their
sources, and click **Apply**. Uncheck any entries to leave them unchanged. Switch
to **Category** grouping to see the results; new decks use this grouping by default.
Apply is one Undo/Redo operation, and category assignments persist with the deck.
Empty categories are hidden automatically, including old categories left behind
by reclassification. They remain available in assignment menus and Manage categories.
Use **More → Show empty categories** to reveal them as drag destinations; this view
preference is saved with the deck. Categories reappear when cards are assigned to them.

This uses only local database data: no AI, remote inference, or popularity guesses.
The explicit rules live in `mtg_core/categorization.py`, `category_rules.py`, and
`role_analysis.py`.
Roles include Board Wipes, Counterspells, Interaction, Ramp, Removal, Tutors, Protection,
Recursion, Win Conditions, Draw, Card Advantage, Tokens, Lifegain, Stax, Anthem,
Counters, Blink, Equipment, Spellslinger, Graveyard, Sacrifice / Aristocrats,
and Utility. Every matching role is retained; the first is primary. Commanders
and front-face Lands take precedence. Effect evidence is weighted by strategic
role rather than a fixed category order. Removal stays ahead of incidental
cantrip draw. Other cards fall back to their front-face type. A spell with a land back
is not classified as a land merely because of that back.

Spell redirection counts as Interaction. A card's own flashback/escape-style
recursion is secondary to its functional effect, so draw spells with flashback
remain Draw. Actual graveyard-recovery effects retain normal Recursion priority.
Sacrificing the card itself does not alone establish a general sacrifice outlet.
Cost reductions for spells you cast count as Ramp, including conditional and
experience-counter-based reductions. A discount solely on the card itself does not.

Functional roles use locally synchronized Oracle Tags, explicit Oracle wording
patterns, and structured keywords. Text rules work even without the tag dataset.
Reminder text is excluded, faces are evaluated independently, and land-only
library searches putting lands onto the battlefield or into your hand count as
Ramp rather than Tutors. Overload removal can count as a Board Wipe, and returning
a spell from the stack counts as Counterspells. Restrictions on opponents count
as Stax; attack taxes protecting you count as Protection. Self-only defensive
keywords, incidental life gain, and conditional mana-token rewards have less
weight than a card's main functional engine. Repeated draw, life-gain rewards,
team buffs, and counter movement receive distinct evidence.

Batch analysis uses commander abilities and repeated mainboard mechanics for
small score adjustments (at most eight points). Sideboards and maybeboards do
not contribute to deck themes. Strong functional differences outweigh these
adjustments. Among supported roles, existing custom categories are preferred;
known aliases such as Land/Lands and Life Gain/Lifegain are recognized. Unrecognized
custom category names require manual assignment. Automatically generated secondary
categories do not become preferences on subsequent runs. The review displays the
matching tags, text rule, keyword, deck adjustment, or type fallback.
Missing data leaves an entry unchanged. Scores in saved evidence are explicit
rule priorities, not confidence estimates. Arbitrary user tags are not interpreted
as functional roles. These conservative role hints are not a complete Magic rules
engine; unusual wording and context-dependent combos can still need manual edits.
Rerun **Auto Categorize** on existing decks to apply the expanded rules.

Manual assignments, including explicitly choosing Uncategorized or deleting an
assigned category, are protected from subsequent automatic passes. Additional
category associations remain intact. Renaming an automatically created category
keeps its identity. Existing legacy categories count as manual assignments.
Deck-wide analysis runs in a worker and reads the database in batches.
Effect parsing uses a bounded cache shared across unchanged card metadata.

Offline CI fixtures live in `mtg_core/tests/fixtures`, including the supplied Lyra
list and Scryfall Oracle snapshots. The supplied list contains **110 cards across
77 distinct entries**, including 34 Plains; its parsed counts include 11 Draw
and 9 Protection cards. These quantities take precedence over the story's summary.
Card names appear in regression expectations, not production classification rules.

A local statistics store and source interface now support Phase 5 development;
the primary public corpus is populated by the authorized one-time Archidekt collector. See the guidance and
recommendation-source section below for current capabilities and limits.

## Deck insights

Open **More > Deck insights** for a quantity-weighted mana curve, average mana
value, color and mana-symbol counts, types, lands, and assigned category/tag totals.
Choose mainboard plus commanders, mainboard only, or all sections. Owned and
do-not-print copies still contribute to deck composition. Lands are excluded
from the curve and average; unknown types are excluded from the nonland count.
Missing local metadata is reported instead of being treated as zero or colorless.
Hybrid symbols count toward both colors, and multi-type cards count in each type.
Roles come from your existing categories/tags and never overwrite manual choices.
This is a snapshot: reopen it after editing the deck.

## Print Deck

**More > Deck artwork preferences** saves artwork rules for this deck, with
Undo/Redo. Uncheck **Use global preferences** to customize rules, or check it and
Save to reset to global inheritance. This influences artwork browsing and
recommendation printings while retaining existing art and global favorites.
Rules travel with Print Deck; repeat handoffs copy the deck's current override
or reset into the linked print project.

**More > Global printing defaults** opens the shared Core-owned preference editor.
Saved defaults initialize a deck's first new print project. Existing linked print
projects and settings imported from Proxy keep their overrides. To reset those
settings, use Proxy's **Print Settings > Printer profiles > Reset project to
global defaults**. Changes saved in another app are read on the next defaults
dialog opening or new project creation.

**Print Deck** asks which sections to include. Mainboard and Commander are selected
by default; cards marked do-not-print are excluded. The deck is saved, printable
assets and paired backs are resolved using Proxy's import workflow, and a managed
Proxy project opens in a separate process.

Use a card's context menu **Owned copies** to record how many copies of that entry
you own. With multiple entries selected, **Set owned copies** applies the entered
count to each selected entry in one Undo step; Cancel leaves all counts unchanged.
Counts are saved with the deck and can exceed its current quantity. They are per
entry, not shared across alternate printings or other decks.

Enable **Print only missing copies** to print `max(0, quantity - owned)` for each
included entry. For example, a four-copy entry with three owned copies prints one.
The option is off by default. **Do not print** still excludes the entire entry,
and basic-land and section exclusions still apply. Only the print snapshot changes;
saved deck quantities and ownership counts stay intact. Token suggestions use the
remaining printable cards. If no copies remain, no print project is created or
updated. Repeating a handoff starts from the deck's full quantities each time.

Handoffs preserve explicit front/back pre-cropped metadata alongside stable unique
entry filenames. Catalog artwork is not cropped again; custom artwork retains its
normal crop processing. Legacy Scryfall filename detection remains supported.

Subsequent handoffs reuse that project's latest paper, backside, offset, and manual
layout settings. Surviving placements stay put where possible; displaced copies are
reconciled with Proxy's normal layout service. Close the linked Proxy project before
sending it again: an open-project lock prevents overwriting active print work.

Print/PDF preflight checks remain in Proxy. Printing does not close or reset the
Editor: selection, filters, scroll position, and Undo history remain available.
Concurrent changes are not synchronized live between the two applications.

## Commander selection and deck checks

**More > Commander / format deck checks** lets you choose one commander or a
partner/background pair. The report previews those choices before you apply them.
Applying moves previous commanders to the mainboard, preserves all card quantities,
and supports Undo. Invalid choices remain editable for unfinished decks and house rules.

Checks cover the 100-card total, commander eligibility, supported partner abilities,
singleton limits (including basic lands and explicit copy exceptions), color identity,
basic land types, and locally cached Commander legality/bans. Legendary Vehicles and
Spacecraft with printed power/toughness are included. Sideboard, considering, and
excluded cards are outside the checked deck; owned/do-not-print cards still count.
Choose a **Companion** from the sideboard and, for commanders that request one,
choose their pregame color. Both choices persist and support Undo. Companion checks
include the starting commanders and enforce the companion's own legality, color
identity, quantity, and restriction. All ten named Ikoria companions are supported;
ambiguous activated abilities or unfamiliar companions receive Unknown findings.

With **Standard**, **Modern**, **Pauper**, **Legacy**, or **Vintage** selected in the
deck header, the same dialog checks that format instead: a 60-card minimum, a maximum
15-card sideboard, combined main/sideboard copy limits, explicit card-copy exceptions,
Vintage restricted cards, companion restrictions, and cached format legality.
Pauper legality comes from format metadata rather than the selected printing's rarity.
Custom decks can use the Commander preview without changing their format.

The report separates violations from unknown results and shows the checker version
and oldest known card-cache date. Data older than 30 days is flagged for refresh.
Refresh card data in Core and reopen the report to use it. A cache timestamp records
local retrieval, not publication of a ban list; a clean report means no violations
were detected in that local data. House rules are not enforced; unsupported or ambiguous
characteristics remain explicit Unknown findings. Printing and deck edits remain available.

Rule references: [Comprehensive Rules](https://magic.wizards.com/en/rules), sections
903 and 702.124; [Vehicle/Spacecraft eligibility update](https://magic.wizards.com/en/news/announcements/edge-of-eternities-update-bulletin).

## Shortcuts and remaining work

Ctrl+N: New; Ctrl+O: Open; Ctrl+S: Save; Ctrl+Z: Undo;
Ctrl+Y/Ctrl+Shift+Z: Redo; Ctrl+F: deck filter; Ctrl+K: Quick Add;
Ctrl+A: select visible cards; Delete: remove selection; hold T: quick tagging;
Tab in the radial menu: switch primary/category tag mode; Esc: cancel.

Expanded filters, statistics, and opening-hand playtesting are available.
The compact table is available under **More**.

## Opening-hand playtest

Open **More > Opening-hand playtest** to sample seven cards using actual deck
quantities. Each copy is drawn separately without replacement; chosen printings
remain identified by set/collector number. Hover a row for cached card text.
**New sample** reshuffles the full included deck and resets mulligans.

Choose which sections to include. Mainboard is the default; commanders are
excluded even when identified by the deck's commander list. Do-not-print cards
are included by default because owned cards still belong in the deck. Changing
settings starts a new sample. No card data or images need to download.

**Mulligan** redraws seven, or the full included deck if smaller. Enable **First
mulligan is free** as desired (on by default for Commander). Each later mulligan
requires one more card to be put on the bottom. Select the indicated number of
rows (Ctrl-click for multiple cards), then **Keep hand**. **Draw a card** draws
from the remaining library; it disables when empty. This is a sampler, not a
rules-enforced game or a legality check.

**Save notes/settings** stores plain-text notes with the deck and remembers the
inclusion/mulligan settings. Notes support Undo/Redo; preferences stay in place
when undoing deck edits. **Cancel** discards changes to notes/settings. Trial
hands are temporary and never change deck quantities, artwork, or print settings.

## Background diagnostics

Background failures keep short messages in the editor and record technical details
in `%LOCALAPPDATA%\PrintProxyPrep\mtg_core\logs\diagnostics-<process-id>.log`.
The log includes tracebacks and relevant operation/card/project identifiers.
Each process keeps a 5 MB current log and up to three rotated backups. When
`PRINT_PROXY_PREP_DATA_DIR` is set, logs use its `mtg_core/logs` folder instead.
If that folder cannot be written, diagnostics fall back to stderr. Bulk download
requests and failures continue using the existing `downloads-<process-id>.log`.
Review paths, queries, and identifiers before sharing a log.

## Override inferred roles

Select cards and right-click **Edit roles/categories** to add or remove any
category, including secondary automatic roles. Checked assigns to all selected
cards, unchecked removes from all, and partially checked preserves each card's
current assignment. Cancel leaves the deck unchanged.

The primary category stays first when retained; removing it promotes the next
remaining category. Use **Primary category** to choose a different primary, and
**Manage categories** to create custom roles. Changes are deck-local, support
Undo/Redo, and survive save/reload. Changed cards become Manual; **Auto Categorize**
preserves them unless you explicitly enable reconsidering manual assignments.
User tags remain editable through **Edit user tags** and also count toward role
totals. Global Oracle tags and factual card-type statistics are unchanged.

## Deck filtering

**Quick Add** and **Add Cards > Search** share local background search. Typing a new query
cancels the previous search; **Cancel**, clearing the field, hiding the search
panel, and closing the editor also stop outstanding searches. Obsolete results
never replace the current query's results. Recent successful searches (including
empty results) are cached in memory, up to 20 queries for 30 seconds. Use **Refresh**
to bypass the cache after updating card data or Oracle tags. Search errors are not
cached. This cache is separate from the deck-view filter below.

The deck filter supports combined queries in card and table views. Plain text
matches names and tags. Examples: `type:creature mv<=3`, `id:wu -color:r`,
`category:"Card Draw"`, `legal:commander`, and `is:do-not-print`.
Use **Filter help** for supported fields and flags, and the field's clear button
to restore all entries. Filters change only the view, never deck quantities or
print output. Hidden entries are removed from the current selection.

Metadata filters use locally cached facts; missing data does not match positive
filters. Color `:` includes the specified colors and `=` requires an exact match;
`C` means colorless. Treatment matches available printing metadata (for example,
foil availability), not a selected physical finish. Legality reflects cached data.
Invalid queries show an error and preserve the last valid results.

**More > Print readiness** scans local artwork in the background and reports
clickable totals for missing/unreadable fronts, low DPI, missing required or
assigned backs, double-faced cards, oversized cards, and excluded/do-not-print
copies. Totals include all sections and show both copies and distinct entries.
Low DPI uses the printer's front source-image calculation and warning threshold.
Default backs are checked when duplex output is enabled; required DFC and assigned
backs are checked regardless. No images are downloaded. Unknown layout metadata
is reported because it can prevent DFC detection.

Click a total to filter the deck, then optionally narrow it with the text filter.
Clear the readiness filter with its labelled × button. Editing the deck clears
the snapshot filter; rerun the scan after edits or external asset changes.
This scan does not replace the printer's final placement and output checks.

### Shared artwork preferences

Use **More > Artwork preferences** to edit the same artwork rules used by Core
(**Preferences > Artwork preferences**) and the print picker (**Preferences**).
The dialog reloads saved rules whenever opened. **Save** updates global rules;
**Cancel** leaves them unchanged. Existing exact printing/artwork selections are
retained. Already-open pickers can reopen Preferences to load another app's changes.

### Guidance and recommendation sources

**More > Deck guidance** provides configurable, explainable composition checks
with saved dismissals and Undo/Redo. **More > Import recommendation decks**
imports your native Commander decks as a supplementary local signal.
**More > Recommendations** exposes dataset status and the recommendation browser.
Archidekt is the primary source, using the authorized one-time local cache;
local data never replaces the public dataset and requires 15 relevant decks.
See [source policy, scoring, and remaining work](../../docs/recommendation-data.md).
# Token suggestions when printing

**Print Deck** includes basic lands by default. Uncheck **Include basic lands**
to omit them from this print job, including snow-covered basics and Wastes.
Cards with unknown types remain included. Saved deck quantities and printing
exclusions are unchanged.

After choosing sections in **Print Deck**, Manaforge offers related tokens for
the included cards. Choose **Add Selected** to include one copy of each selected
token, or **Not Now** to continue without them. Tokens are added to the print
job only; your saved deck stays unchanged. Suggestions use catalog relationships
and may fetch missing related card records.


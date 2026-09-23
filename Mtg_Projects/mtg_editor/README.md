# Manaforge Deck Editor

Run `Launch Manaforge Deck Editor.cmd` after installing dependencies with the
Proxy setup script. Alternatively run `python Mtg_Projects/mtg_editor/run_editor.py`
from the repository root with application dependencies installed.

## Visual workspace

The editor shares Proxy's dark styling and green accents. **Grid** shows complete
card images; **Stacks** overlaps cards within groups. The card canvas uses all
remaining window space, and the toolbars wrap on smaller screens.

- **Add Cards** opens a resizable visual search panel. Search names or Scryfall
  syntax against the local Core catalog. Double-click a result or click its plus
  control to add that exact printing. Closing the panel retains its search and scroll.
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
- Hold the right mouse button on a card for **100 ms**, hold **T** with cards selected, or click **Quick tags** to open
  the radial menu. Move toward a role and release, or click a role after opening.
  **Primary** mode replaces the primary category; **Tab** or the mode wedge switches
  to purple **Secondary tags** mode, which adds/removes tags without changing categories.
  Mixed selections add a tag to all; when all have it, the same action removes it.
  **More…** includes other roles, custom categories/tags, and creating a new one.
  Release in the center or outside the ring to cancel a mouse hold. **Esc** cancels. The six common roles keep fixed positions for muscle memory.
- A quick right-click (or Shift+right-click) opens artwork, Oracle/user tags, section/category assignment, commander
  assignment, oversized/normal size, owned/do-not-print, retry artwork, and removal.
  Bulk actions affect all selected entries in one Undo step.
- **More > Manage categories** creates, renames, reorders, and deletes categories.
  Deleting a category preserves its cards. The first category association is primary;
  additional associations survive changing the primary category.
- **More > Category templates** provides **Commander essentials** and saved personal
  layouts. Save the current deck's category list to reuse its names and order in
  another deck; save under the same name to update a template after editing categories.
  Applying adds missing categories, preserves existing categories and assignments,
  and shows empty category columns. Apply is one Undo step. Saving a personal template
  takes effect immediately, independently of applying it to a deck.
- Drag selections onto section/category headings or cards to assign them. With
  Import Order sorting, dropping before a card also reorders the selection. Derived
  groups such as Type do not accept reassignment; reordering within the same group
  remains available in Import Order.
- **View Oracle tags** reuses Proxy's tag dialog. Clicking a tag opens its local
  search in the side panel. **Edit user tags** applies a comma-separated list to
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

## Automatic categories

New cards added through search and uncategorized cards in opened/imported decks
receive categories automatically from local card data. New decks open in category
stacks; saved view preferences remain respected. **Auto** and **Manual** badges show
assignment sources. Manual corrections survive subsequent categorization and saving.
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
The explicit rules live in `mtg_core/categorization.py` and `category_rules.py`.
Roles include Board Wipes, Counterspells, Interaction, Ramp, Removal, Tutors, Protection,
Recursion, Win Conditions, Draw, Card Advantage, Tokens, Lifegain, Graveyard,
Sacrifice / Aristocrats, and Utility. Every matching role is retained; the first
is primary. Front-face Lands take precedence, followed by functional roles in
the listed order. Removal and other stronger roles stay ahead of incidental
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
library searches putting lands onto the battlefield count as Ramp rather than
Tutors. The review displays the matching tags, text rule, keyword, or type fallback.
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

An EDHREC-like local statistics/recommendation database remains a later step;
this version supplies the deterministic, saved role data for that work.

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

**Print Deck** asks which sections to include. Mainboard and Commander are selected
by default; cards marked do-not-print are excluded. The deck is saved, printable
assets and paired backs are resolved using Proxy's import workflow, and a managed
Proxy project opens in a separate process.

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
Ctrl+Y/Ctrl+Shift+Z: Redo; Ctrl+F: deck filter; Ctrl+K: Add Cards;
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

**Add Cards** searches the local catalog in the background. Typing a new query
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

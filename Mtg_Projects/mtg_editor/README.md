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
- Sort by **Name**, **Mana Value**, **Quantity**, or **Import Order**. Filter the deck
  by name or user tag and adjust image sizes with the slider.
- Click cards to select; Ctrl-click toggles selection, Shift-click selects a range,
  and Ctrl+A selects visible cards. Hover reveals quantity controls and a larger preview.
  Double-click a deck card to open the shared Proxy artwork picker.
- Right-click for artwork, Oracle/user tags, section/category assignment, commander
  assignment, oversized/normal size, owned/do-not-print, retry artwork, and removal.
  Bulk actions affect all selected entries in one Undo step.
- **More > Manage categories** creates, renames, reorders, and deletes categories.
  Deleting a category preserves its cards. The first category association is primary;
  additional associations survive changing the primary category.
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

## Save and recover

Decks save to the shared application data directory's `decks` folder, two seconds
after editing stops. The title displays `*` while unsaved. Failed saves keep changes
in memory, report the error, and retry. **Save** also works with Ctrl+S.

**Decks** provides New, Open, and recent decks. Open accepts native editor documents
and existing Proxy JSON projects. Proxy imports save as separate editor documents;
the source is retained. Existing local artwork is imported into shared image storage.

Up to five pre-save snapshots live in the adjacent `.recovery` folder.
**More > Restore recovery snapshot** restores into a new deck without overwriting
its source. View/group/sort preferences and category collapse state are saved.

Undo/Redo covers deck edits, including quantity, artwork, sections, categories, tags,
and bulk changes. View changes do not roll back when undoing a deck edit.

## Automatic categories

New cards added through search receive categories automatically. For an existing
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

## Shortcuts and remaining work

Ctrl+N: New; Ctrl+O: Open; Ctrl+S: Save; Ctrl+Z: Undo;
Ctrl+Y/Ctrl+Shift+Z: Redo; Ctrl+F: deck filter; Ctrl+K: Add Cards;
Ctrl+A: select visible cards; Delete: remove selection.

Decklist import UI, legality analysis, category templates, statistics, and playtesting
remain on the roadmap. The compact table is available under **More**.

# Deck building and discovery

Quick Add and Syntax Search work on empty decks. Card Search opens its last
workspace tab; Discover Deck Ideas opens through its tab or explicit discovery
actions. Closing and reopening search preserves its input and loaded results.

Search and recommendations default to the deck's local legal pool. Commander
also uses the known commander's color identity, including saved pregame color
choices. Unknown legality is excluded when a format is known. Custom decks have
no format restriction. **Include illegal cards** is a shared, saved deck setting
that disables format and commander-color defaults. Explicit format or identity
operators in Syntax Search replace the corresponding default; quoted Oracle
text does not count as an override. Vintage restricted cards remain playable.
Oracle-tag actions quote and escape multiword values automatically.

Multi-face cards have a flip icon. Select a card and press **F**, or use **Flip
preview** in its menu. The card's displayed name, details and artwork follow the
selected face without changing deck data. Layouts with shared artwork retain
that artwork while changing the displayed face text. Alternate-face images use
the existing image asset cache. Expanded discovery grids honor the card-size
slider and fit a complete card vertically, retaining its aspect ratio.

In Stacks view, use **Expand** on a group header, **Expand / collapse stack** in
the card menu, or **E** with a card selected. Expanded stacks expose each card's
artwork and actions and remain scrollable. Expansion is presentation state.

**Themes** beside Card Search opens a searchable, grouped checklist. Multiple
manual selections persist with the deck and are labeled separately from
automatically inferred themes. Recommendations match any selected theme; the
first selected theme supplies the EDHREC audience when automatic audience
selection is enabled. Matching functional roles receive a bounded category
priority bonus during Auto Categorize. Existing manual categories stay intact.

Drag a card from a deck or candidate grid into a search/recommendation panel to
open discovery. Drops copy the discovery seed; they never move deck cards.
The same action is available through **Discover similar cards / popular
commanders** in card menus or **D** with a card selected.

- **Similar Cards** compares functional roles, effects and keywords, with a
  per-card explanation. It examines at most 2,000 local catalog candidates and
  displays up to 200 matches. This is an explainable heuristic, not a guarantee
  of rules equivalence or an exhaustive online search.
- **Popular Commanders** reverses cached inclusion statistics from enabled
  providers and the local imported-deck corpus. Counts and denominators remain
  separate by provider and exact commander/partner cohort. Unavailable data
  produces an empty state. Select a result to inspect it or start a new deck.

Escape closes the discovery dialog. Searches cancel when it closes, and stale
results from a previous card, tab, or deck are ignored.

Auto Categorize includes **Keyword Soup** for cards with at least three relevant
structured keywords or grants involving at least two relevant keywords. The
same keyword reader supports similarity discovery. Single-keyword cards do not
qualify solely for that keyword; manual category overrides remain authoritative.

**More → Auto Add Basic Lands** proposes additional basics from quantity-weighted
mana costs in the mainboard and command zone. It shares the mana-symbol reader
with Deck Insights: hybrid symbols count once toward each color, phyrexian and
monocolor hybrid symbols contribute their colored component, and generic,
variable and snow symbols contribute no color. Double-faced cards use their
front-face cost. Explicit colorless requirements are reported separately.

Choose the additional slots, then edit the per-land counts before applying.
Largest-remainder allocation makes the counts sum exactly to the requested
slots, with ties resolved in WUBRG order. The plan respects known Commander
colors even when browsing illegal cards. With no colored pips, it splits known
commander colors evenly or proposes Wastes. Missing mana costs are reported.
Commander plans cannot exceed 100 total mainboard and commander cards; formats
with minimum sizes but no maximum do not acquire an artificial 60-card cap.

The tool adds to existing mainboard basics without replacing artwork, deleting
cards, or subtracting existing mana sources. Resolving a missing basic must
succeed for the entire plan before any cards are inserted. Applying the plan is
one undoable edit. This is a starting point, not mana-base optimization.


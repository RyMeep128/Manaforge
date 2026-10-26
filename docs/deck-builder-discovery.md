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

Basic lands are automatic, with no menu action or slot-count setting. Once a
nonempty deck has usable mana-cost or commander-color data, they fill the
unoccupied slots toward 100 cards for Commander (including decks with a
commander in Custom format), or 60 for other decks. These are automatic filling
targets, not restrictions on manually building a larger constructed deck.
Empty decks stay empty. Decks without sufficient local facts wait for metadata.

Adding cards replaces automatic basic copies and recalculates the color ratio
from mainboard and commander mana pips. Explicitly added basics and nonbasic
lands stay in place and consume slots; existing basic colors are reserved when
allocating the remaining basics. Only copies owned by automation are reduced
or recolored. Artwork, manual roles, and explicitly added copies are preserved.

Removing or reducing any land, including moving one out of the main deck,
automatically stops filling and rebalancing for that deck. This state persists
when saving and reopening. Undoing the removal restores automation along with
the previous cards. Each card edit and its automatic basic adjustment share one
undo step; metadata/image loading never creates an extra undo step.

Allocation shares the mana-symbol reader with Deck Insights. Hybrid symbols
count once toward each color, phyrexian and monocolor hybrid symbols contribute
their colored component, and generic, variable and snow symbols contribute no
color. Double-faced cards use their front-face cost. Largest remainders resolve
whole-land counts deterministically in WUBRG order. Known Commander identity
still limits the plan when browsing illegal cards. Without colored pips, known
commander colors are split evenly; otherwise existing basic colors are reused
or Wastes fills a colorless plan.

Catalog data and artwork resolve in the background. If a basic is unavailable,
it remains a name-only deck entry and a status message explains the missing
catalog data. Saved decks retain these entries for later resolution. This is a
pip-based starting point, not full mana-base optimization.

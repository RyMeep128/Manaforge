# Create from Precon

Choose **New deck → Create from Precon** in the project browser, recent-deck
menu, or Ctrl+N. Blank decks and normal imports remain available in that chooser.
Search by product/deck name, commander, set code/name, or year; combine this with
format, release-year, and color filters. Commander products appear first. The catalog uses a wrapping grid of commander/featured-card
tiles, with deck name, format, colors, source product, and release year above each
card. Commander names remain searchable without repeating them in tile labels.
Color identity uses locally installed card data; products with incomplete color
coverage do not appear under a specific color filter. They remain searchable.

Select a tile, optionally rename the deck, and choose **Create deck**. The grid
fills the chooser; raw deck lists and import review tables are hidden. Tiles use
the app's dark surfaces, subtle selection outlines, and color identity badges.
Full source details remain available in tooltips. Enable **Fetch missing cards
online** if the local catalog lacks cards. Creation resolves source printings in
the background with progress and cancellation, and displays errors when needed.
Creation is blocked if a printing fails to resolve. Cancel leaves the current
deck intact. The new independent deck supports normal editing, recommendations,
undo, saving, and export.

Mainboard, sideboard, both partner commanders, planar, scheme, and oversized
display-commander sections retain their identities. Display commanders are
marked do-not-print. Source foil/MTGJSON identifiers are retained as entry metadata;
MTGJSON IDs are never treated as Scryfall or Oracle IDs. Text exports preserve the
extra zones, but consumers outside Manaforge may not understand those headings.

## Data and updates

The existing [taw preconstructed-deck dataset](https://github.com/taw/magic-preconstructed-decks-data)
is reused, rather than introducing an individual-user scraping workflow. Its
`decks_v2.json` supplies product/set names, release dates, formats, quantities,
printing coordinates, and all original sections. The bundled compressed catalog
contains 3,126 nonempty products from the snapshot retrieved on 2026-10-26.
This is community-maintained data for official products, not a Wizards API.
Upstream documents inferred printings and ambiguous basic-land variants. Products
whose lists are empty are omitted. Coverage and correctness follow upstream;
Manaforge does not claim independent verification of every original list.

Normal card-data updates refresh the catalog atomically at
`mtg_core/precons.json`. A failed optional refresh retains the previous catalog
and logs the failure; the bundled catalog supports first use without downloading.
The existing `tools/collect_preconstructed.py` also writes the full catalog beside
its recommendation database, before retaining its existing Commander-only
recommendation statistics. Collection still uses its existing cached responses;
normal Data Management updates retrieve the latest catalog.

## Artwork and provenance

Cover selection supports `artwork.key_art_url`, then `artwork.product_image_url`
in normalized records, then the existing commander/featured-card cover fallback.
The source currently supplies neither key-art nor packaging URLs, so bundled
products use card artwork. Authoritative product-art references remain follow-up
data work. Cached product images reuse the shared image-asset store by source URL;
new images use its content-addressed storage. No separate image cache is created.
On-demand mode retrieves supplied product art during review. Full-offline mode
uses existing product art and otherwise falls back to normal card covers. Browser
tiles show commander/featured cards through the shared card thumbnail service.

`deck.precon_origin` preserves a versioned source identity, metadata, immutable
original list, source printings, and release date. Editing the new deck does not
alter this snapshot or the catalog. Future comparison/upgrade features can compare
this baseline with current entries. Those features are not implemented here.

Automated core and UI tests accompany the feature. Run them in GitHub CI; no local
tests, builds, or validation suites were run for this implementation.

# Phase 5 guidance and recommendation data

## Available workflow

**More > Deck guidance** loads local Oracle Tag/text evidence in a worker and
shows quantity-weighted lands, ramp, draw, and interaction. Manual roles,
including explicitly empty roles, override inference. Owned cards remain in
scope; sideboards and considering/excluded sections do not. Each interaction
copy counts once even when it has several interaction roles.

Targets are editable starting points (Commander: 36/10/10/10; other decks:
24/6/6/6), not format rules. Set a target to zero to disable that shortage.
Theme suggestions require ten distinct card identities by default, configurable
in the dialog. They do not assign categories. Save persists settings and
dismissals with the deck through Undo/Redo; Cancel discards them. Missing local
data and incomplete tags can undercount roles.

**More > Import recommendation decks** imports selected native Commander deck
files into a separate, local SQLite dataset under
`mtg_core/recommendations/local.sqlite3`. Stable deck IDs deduplicate copies;
file digests skip unchanged imports. Reimport files to update or resume after
cancellation. Each completed deck and its aggregates commit atomically. Invalid
files are reported individually; entries without Oracle IDs are reported and
omitted. Quantities and duplicate printings do not inflate inclusion counts.
No local deck data is uploaded. Deleting source files does not remove previously
imported samples; dataset removal/editing is not yet exposed in the UI.

**More > Recommendations** provides optional local Scryfall-style filtering,
statistics/reasons, roles/themes, Inspect/preview, and explicit Add to Deck with
Undo. It shows an unavailable-source message until an approved primary source
provides data; it does not substitute local-only recommendations. Candidate
processing is bounded at 200 and local search at 10,000 matches. Image previews
reuse the normal card-detail behavior, which can fetch uncached images.

## Source policy (reviewed 2026-09-29)

| Source | Role | Current access status |
| --- | --- | --- |
| Archidekt public Commander decks | Designated primary dataset | Bulk collection disabled pending an approved API/data-reuse arrangement |
| EDHREC | Behavior and validation reference | No deck-data ingestion or runtime dependency |
| BlueprintMTG | Optional secondary public source | Disabled; API and data-reuse terms not verified |
| User-imported local Commander decks | Supplementary signal | Enabled only alongside public results and at least 15 relevant local decks |

[Archidekt's published terms](https://archidekt.com/terms), sections 2 and 3,
restrict copying/reuse, collection of other users' data, and automated queries.
Public visibility is not a verified bulk-data license. Before enabling its
collector, establish permitted endpoints, reuse/redistribution rights, rate
limits, attribution, refresh cadence, deletion handling, and caching retention.
This implementation does not scrape the site or contact its operators.

BlueprintMTG's main site could not be inspected successfully during this review;
no verified public API/reuse agreement was found. Existing single-deck import
support does not establish permission for bulk dataset collection.

EDHREC's [December 2025 explanation of lift](https://edhrec.com/articles/from-synergy-to-lift-the-math-behind-edhrecs-new-era)
describes replacing synergy difference with log-lift and accounting for color
eligibility and card availability dates. Manaforge currently exposes a simpler
inclusion-minus-global-baseline statistic. It is not EDHREC's current metric,
and has not been validated as equivalent. Eligibility/date correction and
public-corpus validation remain required before claims about the wider meta.

## Source interface and local blend

`RecommendationSource` returns a versioned aggregate snapshot with provenance,
sample counts, source status, and scored Oracle IDs. `CachedSource` wraps an
aggregate store; unavailable source adapters expose their reason without making
network requests. `recommend()` accepts sources by injection, so adapters can
be added/replaced without changes to the ranking engine. The editor loader also
accepts injected sources. Approved public transport/normalization and a
versioned downloadable aggregate distribution are not implemented yet.

Relevant local decks contain every selected commander as a commander. Thus a
partner pair needs 15 decks with that pair, not 15 unrelated Commander decks.
Below this threshold, the local signal is inactive. At or above it, local scores
contribute 20% and public scores 80%, over the primary candidate set. Local
data never supplies a replacement primary corpus. Secondary-source blending
remains disabled until an explicit policy and a verified source are available.

Current cached scores are `inclusion + 0.5 * (inclusion - baseline) + 0.25 *
baseline`, with baseline-only ranking when no commander sample exists.
Inclusion uses distinct decks, not card quantities. Partner samples currently
display the strongest individual commander inclusion signal, explicitly naming
that commander; the 15-deck local eligibility check uses the full pair.
Refresh is manual via reimport, and source file paths/import times remain local.

## Remaining Phase 5 acceptance

- Approved primary dataset access, resumable public ingestion, normalization,
  permitted aggregate downloads, and refresh/deletion policy.
- Color/date-eligible baselines, co-occurrence/archetype signals, curve/role-gap
  scoring, and wider-meta validation against documented reference behavior.
- Source removal controls and scalable incremental aggregate updates. The
  initial local importer rebuilds aggregates per changed deck; it is not the
  planned high-volume public ingestion implementation.
- CI acceptance and public-corpus performance validation. No local tests or
  CI monitoring were performed for this increment.

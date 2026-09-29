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
Undo. It uses the cached Archidekt dataset when present and shows an unavailable-source
message when no primary cache exists; it does not substitute local-only recommendations. Candidate
processing is bounded at 200 and local search at 10,000 matches. Image previews
reuse the normal card-detail behavior, which can fetch uncached images.

## Source policy (reviewed 2026-09-29)

| Source | Role | Current access status |
| --- | --- | --- |
| Archidekt public Commander decks | Designated primary dataset | User-authorized one-time personal/noncommercial collection; conservative caching collector available |
| EDHREC | Behavior and validation reference | No deck-data ingestion or runtime dependency |
| BlueprintMTG | Optional secondary public source | Disabled; API and data-reuse terms not verified |
| User-imported local Commander decks | Supplementary signal | Enabled only alongside public results and at least 15 relevant local decks |

[Archidekt's published terms](https://archidekt.com/terms), sections 2 and 3,
restrict copying/reuse, collection of other users' data, and automated queries.
The user subsequently reported permission for one personal/noncommercial run,
with rate limiting, caching, and no redistribution of raw user deck data. That
permission governs this run; it is not a general redistribution license or an
automatic recurring-refresh authorization. The collector uses public endpoints
without authentication and stops on access denial. No operator messages are sent.

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
accepts injected sources. A one-time Archidekt API collector now normalizes public Commander samples into
the same versioned store. A downloadable aggregate distribution is not implemented,
and this permission must not be treated as redistribution permission.

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

- Public-corpus quality/performance validation, permitted aggregate distribution,
  and a refresh/deletion policy beyond the authorized one-time run.
- Color/date-eligible baselines, co-occurrence/archetype signals, curve/role-gap
  scoring, and wider-meta validation against documented reference behavior.
- Source removal controls and scalable incremental aggregate updates. The
  local file importer rebuilds aggregates per changed deck; public ingestion
  incrementally replaces per-deck counts in one transaction.
- CI acceptance and public-corpus performance validation. No local tests or
  CI monitoring were performed for this increment.

For pacing, run bounds, cache paths, and stop/resume controls, see the
[one-time collection runbook](archidekt-collection.md).

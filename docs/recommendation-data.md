# Phase 5 guidance and recommendation data

## Available workflow

**Add Cards** has separate **Syntax Search** and **Recommendations** tabs.
The existing search controls and results remain together in Syntax Search.
The Recommendations tab shows a responsive card grid (about two columns at the normal sidebar width)
with name, mainboard-plus-commander quantity across printings, **+ Add**, and a
compact **Why?** popover containing reasons, provenance, and dismissal. Its type
filter matches normalized type tokens, including multi-type cards and card faces;
it preserves recommendation rank within each filter.

The sidebar shares the existing recommendation loader, contextual ranking,
preferences, and dismissals. Existing deck cards can remain visible so quantities
update immediately. A candidate does not count as evidence of its own
co-occurrence. Search and recommendations call the same add-card command, keeping
manual categories, dirty state, autosave, and Undo/Redo behavior consistent.

Loading and ranking run in a separate worker without disabling search. Changes
to the deck debounce a refresh; results from an older deck/context are discarded.
Refresh reads local recommendation caches; it does not start public collection.
The grid reuses the shared bounded thumbnail cache and background image reader
(at most 300 × 420 decoded pixels), requesting only visible/nearby cards. It does
not load full-resolution artwork into the browser. Missing-image behavior follows
the existing thumbnail cache policy. Hiding the tab releases queued thumbnail
interest. Advanced weighting and dismissal restoration remain available through
**More > Recommendations**.

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
resolution examines at most 2,000 statistical candidates and keeps up to 200
with local card data; local search is capped at 10,000 matches. Adjustable
context weights rerank that resolved pool, not the entire corpus. Image previews
reuse the normal card-detail behavior, which can fetch uncached images.

## Source policy (reviewed 2026-09-29)

| Source | Role | Current access status |
| --- | --- | --- |
| Archidekt public Commander decks | Designated primary dataset | User-authorized one-time personal/noncommercial collection; conservative caching collector available |
| EDHREC | Optional offline primary recommendation source | Explicit one-time commander JSON download; separate cache, no runtime network dependency |
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
the same versioned store. Personal aggregate archives can be transferred manually;
no public distribution or recurring feed is configured, and this permission
must not be treated as redistribution permission.

Relevant local decks contain every selected commander as a commander. Thus a
partner pair needs 15 decks with that pair, not 15 unrelated Commander decks.
Below this threshold, the local signal is inactive. At or above it, local scores
contribute 20% and public scores 80%, over the primary candidate set. Local
data never supplies a replacement primary corpus. Secondary-source blending
remains disabled until an explicit policy and a verified source are available.

Current cached scores are `inclusion + 0.5 * (inclusion - baseline) + 0.25 *
baseline`, with baseline-only ranking when no commander sample exists.
Inclusion uses distinct decks, not card quantities. Partner samples use the
joint commander cohort for both ranking and the 15-deck local eligibility check.
Refresh is manual via reimport, and source file paths/import times remain local.

## Context scoring and controls

The final score is the sum of individually displayed weighted components:

| Component | Default weight | Evidence |
| --- | --- | --- |
| Statistics | 1.0 | Public commander inclusion, synergy difference and popularity, with optional eligible local blend |
| Co-occurrence | 0.25 | Mean conditional inclusion across known, distinct nonbasic mainboard cards, minus global popularity, floored at zero |
| Roles | 0.25 | Largest matching proportional shortage against guidance targets; respects manual roles and dismissed shortages |
| Themes | 0.15 | Match to a threshold-qualified, nondismissed guidance theme |
| Type archetype | 0.15 | Match to Artifact/Enchantment/Creature/Instant/Sorcery represented by at least the theme threshold and 25% of distinct deck cards |
| Curve | 0.15 | Candidate nonland mana value at most 3 when at least five known nonland copies average above 3.5 |

These bonuses are heuristics, not probabilities or competitive archetype labels.
Missing evidence earns no bonus. Co-occurrence queries are bounded to 200 seed
identities and 2,000 candidates and run in a worker against indexed membership
data; raw deck payloads are never loaded by the editor. Single-commander inclusion
uses precomputed counts; pairs use indexed joint membership counts.

**Adjust ranking weights** exposes each weight (0 disables it, maximum 2) and
the local-supplement toggle. **Save preferences**, **Dismiss card**, and
**Restore dismissed** persist per-deck preferences with Undo/Redo. Unsaved weight
changes remain dialog-local. The name/role/theme filter operates on the loaded
pool. After adding cards, reopen recommendations to refresh deck-context scores.
Commander color identity is a hard filter only when all commander identity data
is available locally; its availability is shown explicitly.

## Personal offline cache

**More > Recommendation cache** selects the live collected dataset, an imported
personal archive, the offline EDHREC cache, or disabled primary recommendations. Switching sources does
not alter, stop, or restart the collector. The local supplement can be disabled
independently in ranking preferences.

The [EDHREC downloader](edhrec-collection.md) uses a separate database and response
cache. Select **Use offline EDHREC cache** after downloading. EDHREC ranking uses
the published card inclusion fraction, with each card's own eligible-deck count.
It does not fabricate global popularity, co-occurrence, or partner cohorts.
Existing contextual ranking and optional eligible local blending still apply.

Export creates a schema-versioned gzip JSON archive from a consistent snapshot
of the collected public dataset. It includes global popularity, collection time,
sample counts, and commander-cohort aggregates, never deck IDs, deck names,
authors, source URLs, or raw decklists. Export requires at least 15 decks;
cohorts smaller than 15 and cohort/card cells smaller than 3 are omitted.
Suppressed cells contribute zero, so portable scores can differ from live scores.
Portable archives omit deck-card co-occurrence, which contributes zero.

Import validates identities, counts, version, and size before atomic replacement.
Download is an explicit HTTPS operation requiring the export's SHA-256 checksum;
both download and expanded JSON are capped at 40 MiB. Failed verification leaves
the existing cache intact. The archive remains available offline without EDHREC
or Archidekt requests. These controls support personal transfer, not publication;
no hosted feed, automatic download, or redistribution is enabled.

## Acceptance and limits

Phase 5's planned implementation is present. The full application suite and lint
passed on Windows/Python 3.12 and 3.13 for `6453d75`; its formatting failure was
corrected separately. No local tests are run for this closeout; GitHub Actions
owns acceptance.

CI now includes an offline scale/reproducibility gate with 20,000 synthetic
100-card decks, 4,000 candidate card identities, 20 commander cohorts, and a
2,000-result query with co-occurrence evidence. It blocks socket connections,
checks exact results after reopening the database, verifies sample counts and
score explanations, and requires the initial query to finish within ten seconds
on the CI runner. Fixture construction is outside that query budget. This
complements existing ingestion, guidance, local-blend, archive, and Qt interaction
regressions. The gate is pending its first CI run.

Representative public-corpus recommendation quality and worst-case latency with
200 co-occurrence seeds remain unvalidated. Synthetic acceptance does not replace
that evidence or establish competitive deck quality. The collector can finish its
authorized run independently; completing every source download is not required
to use the offline feature.

Global baselines do not yet correct for color eligibility or card release dates;
do not interpret these rankings as EDHREC-equivalent or a representative measure
of the entire Commander meta. Source selection and offline transfer are available;
selective sample deletion and recurring refresh remain future extensions. Local
file import rebuilds aggregates per changed deck; public ingestion incrementally
replaces counts. BlueprintMTG remains optional and disabled until verified.

For pacing, run bounds, cache paths, and stop/resume controls, see the
[one-time collection runbook](archidekt-collection.md).

# Phase 5 guidance and recommendation data

## Available workflow

**Quick Add** keeps the lightweight **Syntax Search** and **Recommendations**
sidebar beside the deck. **Add Cards** opens a persistent full-width workspace
with **Search**, **Recommendations**, and **Commanders**, while the deck header
remains available. **Back to Deck** restores the deck view and previous sidebar
visibility. Ctrl+K continues to open Quick Add; Ctrl+F returns to the deck filter.
The empty deck's Add Cards action opens the full workspace.

Both presentations host the same search and recommendation widgets/controllers,
not independent engines or deck sessions. Query text, cached search results,
selection, filters, dismissals and recommendation state survive switching.
Each presentation retains its scroll positions. The full workspace provides
larger cards, card-size control, Undo/Redo, and visible recommendation type tabs.
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
Search, recommendations and commander discovery display mainboard-plus-commander
quantities from the active document, including alternate printings. Temporary
result entries remain display objects only.

Loading and ranking run in a separate worker without disabling search. Changes
to the deck debounce a refresh; results from an older deck/context are discarded.
Refresh reads local recommendation caches; it does not start public collection.
The grid reuses the shared bounded thumbnail cache and background image reader
(at most 300 × 420 decoded pixels), requesting only visible/nearby cards. It does
not load full-resolution artwork into the browser. Missing-image behavior follows
the existing thumbnail cache policy. Hiding the tab releases queued thumbnail
interest. Advanced weighting and dismissal restoration remain available through
**More > Recommendations**.

## Commander discovery

**Add Cards > Commanders** browses local cards using the existing search syntax
backend and commander eligibility/pairing rules. Theme is an editable searchable
catalog driven by the [offline discovery snapshot](edhrec-collection.md#offline-commandertheme-discovery),
with a clear unavailable state when no snapshot exists. Local discovery still
works without EDHREC. Refresh reads local data only.

Filters include name, type/creature type, Oracle text, exact selected WUBRG color
identity, colorless, color count (zero through five), and supported
Partner/Background capabilities. These do not inherit the deck's color identity.
An optional compatible-partner filter uses the current single commander's local
rules. Combining a theme with the compatible-partner filter requires an explicitly
cached association for the exact pair. The default legality filter includes only
cards marked Commander-legal in the local catalog; disabling it allows inspection
of other locally known cards.
This does not claim current online legality. Results load asynchronously with
debouncing, bounded recent caching, cancellation and stale-result suppression,
and offer Show more up to 2,000 displayed cards. Only visible/nearby artwork is
requested through the existing thumbnail cache.

**Set as Commander** adds or moves one copy in one history edit. Existing copies,
artwork, categories and print settings are retained; if an entry has multiple
copies, one is separated into the commander section. Replacing a commander
requires confirmation and moves the old commanders to the mainboard. **Add as
Second Commander** validates the proposed pair with the same rules used by deck
checks. Backgrounds cannot be set as standalone commanders. A change from a
non-Commander/non-Custom format also requires confirmation. The existing
**Commander / deck checks** dialog remains available for detailed legality,
pregame color, companion and selection handling.

All mutations use the active session's history, autosave and persistence path;
counts and recommendation context refresh through the normal changed handler.
Recommendation blending, source-specific statistics and contextual scoring are
unchanged. Discovery theme membership is a separate data model and never becomes
a new recommendation score or provider switch.

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
Undo. It combines available Archidekt and EDHREC caches into one list and shows an
unavailable-data message when neither can contribute; local-only recommendations never replace them. Candidate
resolution examines at most 2,000 statistical candidates and keeps up to 200
with local card data; local search is capped at 10,000 matches. Adjustable
context weights rerank that resolved pool, not the entire corpus. Image previews
reuse the normal card-detail behavior, which can fetch uncached images.

## Source policy (reviewed 2026-09-29)

| Source | Role | Current access status |
| --- | --- | --- |
| Archidekt public Commander decks | Public recommendation evidence | User-authorized one-time personal/noncommercial collection; conservative caching collector available |
| EDHREC | Public recommendation evidence | Explicit one-time commander JSON download; separate cache, no runtime network dependency |
| BlueprintMTG | Future public source (unavailable) | Disabled; API and data-reuse terms not verified |
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

Public candidates are the union of Archidekt and EDHREC Oracle IDs, including
cards present in only one source. Each adapter supplies up to 2,000 compact rows.
Weighted reciprocal-rank fusion uses `weight / (60 + rank)` with one-based ranks
and initial weights of 1.0 for both datasets. The sum is divided by the maximum
possible sum for sources with usable results (`sum(weight / 61)`). This bounded
0?1 value is a ranking signal, not a probability. Ties use Oracle ID. Raw source
scores are never averaged; source ranks and all statistical metadata remain in
`source_evidence`. Weights are internal constants, with no source-weight sliders.

The top 2,000 fused rows are retained before resolving printings; at most 200
available, color-compatible cards are retained for contextual ranking. Failed,
missing, empty, and disabled sources have their own status. One broken cache
cannot suppress another working source. Provenance and per-source sample sizes
are retained; overlapping corpus sizes are never added into a combined total.

Relevant local decks contain every selected commander as a commander. A partner
pair therefore needs 15 decks with the complete pair. Below 15, with the per-deck
local toggle disabled, or without public candidates, the local signal is inactive.
Eligible local ranks normalize to `61 / (60 + rank)`; absent candidates receive
zero. The statistical component becomes `0.8 * public_score + 0.2 * local_score`.
Local-only candidates never enter the public union.

Archidekt preserves its raw `inclusion + 0.5 * (inclusion - baseline) + 0.25 *
baseline` ordering, with baseline-only ranking when no cohort sample exists.
EDHREC preserves eligible-deck inclusion, categories, and uninterpreted reported
synergy. Exact cached EDHREC pairs use order-independent keys; missing pairs
never fall back to individual commander pages. Archidekt may still contribute.
Manaforge does not reproduce EDHREC rankings or equate these statistics with lift.

Association providers are selected by their optional `associations()` capability.
Currently the live Archidekt store supplies conditional inclusion and its own
baseline, including for EDHREC-only candidates. Portable Archidekt and EDHREC do
not fabricate co-occurrence. Candidates exclude themselves from seed evidence.
Missing association evidence earns zero while other ranking components continue.

## Context scoring and controls

The final score is the sum of individually displayed weighted components:

| Component | Default weight | Evidence |
| --- | --- | --- |
| Statistics | 1.0 | Normalized public rank fusion, with optional eligible normalized local blend |
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

**More > Recommendation cache > Configure recommendation sources** independently
enables Archidekt and EDHREC. Archidekt can use its live collected cache or a
portable personal aggregate without switching off EDHREC. Local-supplement
preferences remain per-deck. Refresh reranks cached data in the existing worker;
opening recommendations never downloads or recollects either public dataset.

`source-settings.json` version 2 stores `archidekt: {enabled, cache}` and
`edhrec: {enabled}`. New installations enable both. Legacy `live`/`portable`
settings retain that Archidekt choice and enable EDHREC when its cache exists.
Legacy `edhrec` enables EDHREC plus a valid existing Archidekt cache (live preferred,
otherwise portable). Legacy `disabled` keeps both off. Migration saves version 2;
no dataset regeneration is required. Explicit per-source disables remain saved.

The [EDHREC downloader](edhrec-collection.md) retains its separate database and
response cache. Why? shows every contributing source's rank and statistics,
EDHREC categories and exact pair identity, the fused ranking signal, local
supplement state, and the existing context reasons. Unavailable-source messages
are displayed separately from absent evidence for a particular candidate.

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

# One-time EDHREC recommendation snapshot

Run explicitly from the repository root:

```powershell
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_edhrec.py
```

The downloader follows the `more` links returned by
`https://json.edhrec.com/pages/commanders/year.json`, deduplicates slugs, and fetches
each listed commander page once. These are frontend JSON endpoints, not a stable
public API contract. The recommendation snapshot captures available commander category lists, not
raw decks, every possible card, separate theme pages, average decks, or combos.
It does not follow category-list continuation pages within commander pages.

## Offline commander/theme discovery

Build the discovery snapshot explicitly from responses already collected:

```powershell
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_edhrec.py --build-discovery
```

For a new or resumed collection followed by discovery normalization, use
`--with-discovery`. Both modes use the existing collector lock and STOP file.
`--build-discovery` makes **no network requests**, works after a completed
recommendation run, and leaves its database and checkpoint unchanged. The editor
never collects EDHREC data. In **Add Cards > Commanders**, use **Refresh local
data** after publishing a snapshot.

The raw commander frontend responses contain explicit `tag_counts` records
(`panels.taglinks` is the equivalent supported representation), with theme slug,
display name, and deck count for that exact commander cohort. Discovery normalizes
these real source-provided associations. It does **not** infer themes from
recommendation categories such as Creatures or High Synergy Cards. No separate
theme pages, invented theme catalog, or additional downloader are needed for this
snapshot. The available themes and membership coverage are limited to the cached
commander pages; this is not a complete global EDHREC theme-page index.

`edhrec-discovery.sqlite3` is a separate schema-versioned normalized database:

- `themes`: source slug and display name;
- `commanders`: order-independent cohort key, source name/slug, cohort sample,
  and cached response timestamp;
- `commander_members`: locally resolved Oracle identities for each cohort;
- `theme_commanders`: exact theme/cohort membership and source deck count.

Pair memberships retain the complete pair identity. A pair's sample/count is
never presented as a single commander's sample, a global theme total, or a card
recommendation score. Discovery orders theme matches by the largest available
matching cohort count, with name as a tie-breaker; this is a local browse order,
not a claimed EDHREC global rank. Selecting a result exposes the exact cohort,
counts, cache date, and source URL.

Normalization resolves exact names before unambiguous front-face aliases or pair
splitting, using the same filtered local Oracle catalog as recommendation ingest.
Unresolved/ambiguous cohorts are omitted and reported with candidate identities
in `edhrec-run/discovery-state.json`. Missing theme fields, conflicting records,
invalid counts, malformed responses, and missing previously collected responses
stop publication explicitly. An empty source-provided tag list is valid; absent
tag data is not silently treated as an empty list.

`discovery-staging.sqlite3` and `discovery-state.json` checkpoint completed pages.
STOP preserves the staging work for resume. A changed raw-response/catalog
signature starts a fresh build. Integrity, foreign keys, and retention of
previously resolved cohorts are checked before atomic publication. The previous
snapshot and checkpoint are backed up under `discovery-backup-<unique-id>`;
publication failure rolls back the live snapshot. Readers continue using the
previous snapshot throughout normalization. Raw response reads retain the 8 MiB
bound; network collection retains all existing pacing, retry, and access-denial
behavior.

Without a usable discovery snapshot, name, type/subtype, Oracle text, color
identity, and commander capability filters remain available from the local card
catalog. The Theme control explicitly reports unavailable data. Refresh does
not download themes or change recommendation-source preferences.

Files live in `%LOCALAPPDATA%\PrintProxyPrep\mtg_core\recommendations` (or the
configured `PRINT_PROXY_PREP_DATA_DIR`):

- `edhrec-run/responses`: compressed responses reused on resume.
- `edhrec-run/state.json`: status, current slug, imported count, completed slugs,
  skipped pages and reasons, and any terminal error.
- `edhrec.sqlite3`: normalized per-commander recommendations read by Manaforge.

Archidekt's process, checkpoint directory, database, and source selection are
not modified. The downloader reads the local card catalog in read-only mode.
EDHREC IDs are not assumed to be Oracle IDs: names resolve through that catalog,
including unambiguous front-face aliases. Unknown cards are omitted and retained
in each page's unresolved-name report. Unsupported commander names or
invalid pages are reported as skipped, not merged into unrelated cohorts.

One process holds a directory lock. Requests are serial with at least six seconds
between starts. Network failures, timeouts, HTTP 408/429, and server errors retry
indefinitely with exponential delays from 30 seconds up to 15 minutes, honoring
longer Retry-After headers. STOP remains responsive during retry waits.
Missing commander pages (404/410) and invalid pages are skipped. Other HTTP
errors (including 401/403) and redirects stop the run with a recorded reason.
Each response is limited to 8 MiB; index traversal is limited to 200 pages and
the run to 10,000 imported commanders. `--max-commanders N` allows a smaller
trial; rerunning with a larger bound resumes using cached responses. A completed
run exits without refreshing. No scheduled or startup download is installed.

To stop gracefully, create an empty `edhrec-run/STOP` file. Remove only that file
and rerun the command to resume. Do not manipulate Archidekt's STOP file.
For a background launch, record the process ID and redirect stdout/stderr to
files in `edhrec-run`; use a hidden window on Windows.

In Manaforge, use **More > Recommendation cache > Configure recommendation sources**
to enable EDHREC independently of Archidekt. Refresh recommendations to apply;
both available caches contribute to one list. These settings do not interrupt
either downloader. Missing commander pages
produce an explicit unavailable status. Partner pairs use only their exact cached
joint page, independent of commander order; they never fall back to individual
pages. Commander-free decks remain unavailable.

## Repair an existing snapshot offline

```powershell
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_edhrec.py --reprocess-cached
```

This explicit mode reprocesses every indexed cached page, even after completion,
without network requests. It filters art-series, token, emblem, and synthetic
proxy identities before matching exact names and unambiguous front-face aliases.
Full card names are resolved before attempting a two-commander split. Genuine
ambiguities stay skipped with candidate Oracle IDs in `reprocess-report.json`.

The existing collector lock protects rebuilding. A temporary database is checked
for integrity, missing/invalid pages, and loss of previously completed pages.
Only a validated rebuild replaces the live cache and checkpoint. Both originals
are backed up in `edhrec-run/backup-<unique-id>`; publication errors roll back.
STOP or processing failures preserve the existing cache. Rerunning starts a fresh
offline rebuild. The report separates imported, ambiguous, unresolved, invalid,
and missing-cache counts; imported pages can exceed unique commander cohorts.
Existing single-commander keys remain compatible; pairs use sorted Oracle IDs.

Ranking uses `num_decks / potential_decks` for each candidate. The UI preserves
categories and the reported EDHREC `synergy` value as uninterpreted provenance.
It does not equate that value to Manaforge's inclusion-minus-baseline statistic.
Global popularity and co-occurrence are unavailable and contribute zero.
The page's overall deck count can differ from a card's eligible-deck denominator.
Existing context bonuses and the optional 15-deck local supplement still apply.

The downloaded data stays outside the repository and is ignored by Git. No
redistribution, publishing, emailing, or recurring refresh is configured.

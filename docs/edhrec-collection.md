# One-time EDHREC recommendation snapshot

Run explicitly from the repository root:

```powershell
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_edhrec.py
```

The downloader follows the `more` links returned by
`https://json.edhrec.com/pages/commanders/year.json`, deduplicates slugs, and fetches
each listed commander page once. These are frontend JSON endpoints, not a stable
public API contract. This run captures available commander category lists, not
raw decks, every possible card, separate theme pages, average decks, or combos.
It does not follow category-list continuation pages within commander pages.

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

In Manaforge, choose **More > Recommendation cache > Use offline EDHREC cache**.
Reopen recommendations to apply the selection. Switching back to the live
Archidekt cache does not interrupt either downloader. Missing commander pages
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

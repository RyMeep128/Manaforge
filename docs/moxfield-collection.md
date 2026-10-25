# Explicit Moxfield collection

Use the existing collector pattern for public Moxfield Commander decks:

```powershell
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_moxfield.py --search
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_moxfield.py --username SomeUser
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_moxfield.py --deck-id PUBLIC_DECK_ID
```

Replace the example username and ID with real values. `--username` and `--deck-id`
are repeatable and may be combined with `--search`. Nothing runs on application
startup or on a schedule. Running without arguments resumes pending work; a
completed run makes no requests unless new IDs or listing sources are added.

The collector uses the supplied `https://api2.moxfield.com` endpoints:

- `/v2/decks/search` for public search;
- `/v2/users/{username}/decks` for a user's public decks;
- `/v3/decks/all/{deckId}` for complete decks.

Listings use `pageNumber`, `pageSize=64`, and the Commander format filter.
Responses must contain a `data` array with `publicId` values. Empty pages end a
listing; repeated pages stop with an error. `--max-pages` defaults to 200 per
listing and can be raised explicitly to resume bounded work. These endpoints
and response schemas are not a stable contract; live responses were not verified
during implementation. Unexpected listing schemas stop rather than silently
publishing an empty sample.

Detail normalization requires `format=commander`, `visibility=public`, and v3
`boards.mainboard.cards` / `boards.commanders.cards`. Only these boards count.
Samples need exactly 100 included cards and one or two distinct commanders.
Oracle UUIDs are used when explicitly supplied; otherwise names resolve through
the existing read-only local Oracle catalog, including unambiguous front-face
aliases. Moxfield card IDs and Scryfall printing IDs are never treated as Oracle
IDs. Unresolved, malformed, nonpublic, and incomplete samples are rejected with
counts and the latest reason in the checkpoint.

Default output under the configured core data directory:

- `recommendations/moxfield-run/state.json`: queue, processed IDs, listing pages,
  sample counts, status, and errors;
- `recommendations/moxfield-run/responses/`: compressed response cache;
- `recommendations/moxfield.sqlite3`: normalized membership, provenance URLs,
  popularity, and commander inclusion, using `RecommendationStore`.

Manaforge reads this database as an independent public recommendation source.
After collecting, open **More > Recommendation cache > Configure recommendation
sources**, enable **Moxfield recommendations**, and refresh recommendations.
Available Moxfield, Archidekt, and EDHREC datasets contribute to one combined list
with equal source weights. Evidence identifies each contributing source, and
Moxfield's commander inclusion and baseline statistics also support High Lift
browsing. Missing caches report unavailable; opening the app never downloads data.

Moxfield is enabled by default for new settings. Existing version-2 settings that
lack a Moxfield preference enable it when either existing public source is enabled;
if both are disabled, Moxfield stays disabled. The preference is saved independently
by the source dialog. Legacy disable-all mode also disables Moxfield.
Archidekt and EDHREC data and checkpoints are unaffected. Keep response caches
and per-deck data private and outside the repository.

One collector lock protects each run directory. Requests are serial, at least six
seconds apart, with an 8 MiB response bound and 10 GiB compressed-cache bound.
The existing downloader retries network failures, HTTP 408/429, and server errors
with exponential backoff and Retry-After handling. Redirects and other HTTP errors,
including 401/403, stop the run without bypass attempts. Missing/deleted deck
details (404/410) are counted and skipped. `--user-agent` allows an operator to
provide a Moxfield-issued identifier; no credentials are collected or stored.

Create `moxfield-run/STOP` to pause, remove that file and rerun to resume. Cached
responses are reused. `--max-decks` defaults to 20,000 accepted samples across the
whole run; raise it explicitly to continue a bounded run. Already processed IDs
are deduplicated and completed listings are not refreshed. Database updates are
atomic and idempotent, including after an interrupted checkpoint write. Collection
coverage reflects the requested listings and limits, not all public Moxfield decks.

# One-time Archidekt collection

The user reported permission for one personal/noncommercial run: rate-limit,
cache responses, do not hammer the API, and do not redistribute raw user decks.
The collector is manually launched, never scheduled or triggered by opening
Manaforge. Completed checkpoints do not start a new collection on rerun.

## Behavior and limits

- One worker, at least six seconds between request starts, plus up to one second
  of jitter. API traffic is roughly ten requests/minute, usually less.
- Public listing endpoint `/api/decks/v3/?deckFormat=3&orderBy=...` and public
  detail endpoint `/api/decks/{id}/`. No credentials or private/unlisted access.
- Follow only returned pagination on Archidekt, upgrading HTTP links to HTTPS.
  Stop on repeated pagination instead of looping. Sample popular, recently
  updated, newly created, and oldest accessible results, deduplicating deck IDs.
  Search result caps are respected; this is not a guarantee of every public deck.
- HTTP 429/5xx: honor `Retry-After`, exponential backoff starting at one minute,
  maximum five attempts. HTTP 401/403 stops the run; no bypass. Missing/deleted
  decks are skipped. Network timeouts also back off.
- Every successful response is compressed and cached locally. Checkpoints retain
  the outstanding queue; resume uses the cache. One OS-held file lock prevents
  concurrent collectors using the same checkpoint directory.
- Accept samples with exactly 100 included cards and one or two commanders.
  Ignore sideboard/maybeboard/deleted entries. Every included card must have a
  valid Oracle UUID. This is a completeness screen, not a complete legality check.
- Update normalized membership, popularity, and commander inclusion atomically
  per deck. Replacement samples remove old contributions before adding new ones.
  Raw descriptions/owner data stay in the private response cache, not aggregates.
- Default bounds: 24 hours from the first launch, 20,000 accepted decks, and
  10 GiB of compressed cache. These are local safety bounds, not claimed API limits.
  The run also finishes when all returned pagination is exhausted. Increasing
  duration later requires an explicit operator decision; nothing automatically
  starts another run.

## Files and controls

Windows default directory:
`%LOCALAPPDATA%\PrintProxyPrep\mtg_core\recommendations\archidekt-run`

`state.json` reports imported/rejected counts, request count, queue, current URL,
status, and errors. `stdout.log`, `stderr.log`, and `pid.txt` describe the initially
launched background process. The primary database is the adjacent
`archidekt.sqlite3`. The editor automatically reads that cache without network
collection. Leave the machine running for the background collection to progress.

Read progress without making network requests:

```powershell
$runFolder = Join-Path $env:LOCALAPPDATA 'PrintProxyPrep\mtg_core\recommendations\archidekt-run'
Get-Content (Join-Path $runFolder 'state.json') -Raw | ConvertFrom-Json |
    Select-Object status, imported, requests, rejected, unavailable, last_error
```

Stop gracefully by creating an empty `STOP` file in that directory. The current
request may finish, then collection pauses. To resume the same run, remove only
that file and run, from the repository root:

```powershell
& '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe' tools/collect_archidekt.py
```

Do not run a second collector with another root: locks and pacing are scoped to
one checkpoint directory. Do not commit, upload, package, or redistribute the
response cache or per-deck membership database. The permission does not establish
a license for publishing an aggregate dataset either; verify that separately.

## Provenance and sampling limitations

Aggregate provenance retains public deck URLs and import timestamps. Raw JSON
is private to this machine. Rankings will initially be biased toward the search
orders already processed; the UI's sample counts and source status should be
considered when evaluating recommendations. Public data access does not make
synergy scores equivalent to EDHREC's current lift methodology.

Endpoint discovery used the public API directly and Archidekt's own forum:
[public search example](https://archidekt.com/forum/thread/21858972),
[staff API guidance](https://archidekt.com/forum/thread/2832338).
No local tests or CI monitoring were performed. Regression tests for the
collector and incremental aggregates are supplied for CI.

# Additional public recommendation datasets

Run from the repository root using the existing environment and local card catalog:

```powershell
$python = '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe'

# Commander precons from taw's decks_v2.json
& $python tools/collect_preconstructed.py

# Commander / cEDH entries from t-my's metagame manifest
& $python tools/collect_metagame.py

# Replace example numeric IDs with actual public Playgroup IDs
& $python tools/collect_playgroup.py --deck-id 431905
& $python tools/collect_playgroup.py --user-id 1234
```

Playgroup `--deck-id` and `--user-id` options are repeatable. Its
[documented API](https://playgroup.gg/api-docs/index.html) returns tracking metadata
and a `decklist_url`, not a full card list. The collector requests the documented
public deck/user endpoints without credentials, then follows only public
Archidekt or Moxfield deck URLs using their existing normalization rules.
Records without a supported linked card list are explicitly rejected. Archived
records are rejected. Multiple records linking to the same host/deck ID count
once within the Playgroup dataset; hosted samples may also occur in separately
collected Archidekt/Moxfield datasets. Game counts and win rates do not inflate
card counts or ranking scores.

## Deckstats and MTGGoldfish exports

Direct Deckstats and MTGGoldfish deck-page requests returned HTTP 403 during
endpoint research. These two scripts support **local text exports only**; they
make no requests to either website and do not invent a JSON API or bypass access
controls. Obtain a public deck's text/MTGO export through the site's normal UI,
then run:

```powershell
& $python tools/collect_deckstats.py --file 'C:\Decks\deckstats.txt' --commander 'Atraxa, Praetors'' Voice'
& $python tools/collect_mtggoldfish.py --file 'C:\Decks\goldfish.txt' --commander 'The Ur-Dragon'
```

Choose the actual commander already present in the export. Repeat `--commander`
for partners. Explicit `Commander`/`Commanders` headings, `CMDR:` prefixes, and
Deckstats `#!Commander` annotations are also supported. Counts use `1 Card Name`
or `1x Card Name`. A blank line after mainboard cards starts the sideboard;
sideboard, companion, maybeboard, and considering sections are excluded. Do not
insert blank lines within a mainboard. Extra text or unresolved included names
rejects the sample instead of silently dropping cards. Put commanders in an
included section; `--commander` does not move sideboard cards into the deck or add
a second copy. Exports with set/collector suffixes use `1 Name (SET) 123`.

`--file` is repeatable; all files in that invocation share the specified commander
names. For one file, optionally supply `--source-url` with its original HTTPS deck
URL on that site's host to retain public provenance. Without it the local file URI
is recorded. Only supply Commander exports: 60-card competitive tournament decks
are not converted into Commander recommendation samples.

## Recommendation integration

All five datasets use separate `RecommendationStore` databases and contribute to
the app's combined public ranking. Open **More > Recommendation cache > Configure
recommendation sources**, enable the desired datasets, then refresh recommendations
after collection. Independent switches, source status, sample counts, per-source
evidence, inclusion/baseline statistics, and High Lift browsing are supported.
Sources have equal rank-fusion weights. Precon inclusion describes stock products;
the metagame sample describes competitive Commander, not general casual usage.
Overlapping source corpora are not summed into a claimed unique global deck count.

New settings enable these sources. Older settings enable missing preferences when
an existing Archidekt, EDHREC, or Moxfield source is enabled; existing disable-all
preferences stay disabled. Missing databases report unavailable. App startup,
settings changes, and recommendation refresh never trigger collection.

The [precon dataset](https://github.com/taw/magic-preconstructed-decks-data) uses
`decks_v2.json`: only `format=commander` entries and their `cards` plus `commander`
sections are included. Oversized display commanders, sideboards, planar decks,
and scheme decks are excluded. MTGJSON identifiers are not Oracle IDs.
The [metagame dataset](https://github.com/t-my/metagame-decks) uses `manifest.json`:
only the `commander` group is read, with its documented convention that the final
sideboard section holds the commander(s). Duel Commander and other formats are
excluded. Current snapshots are cached; the scripts do not schedule weekly updates.

## Storage, resume, and bounds

Files live under the configured core data directory, normally
`%LOCALAPPDATA%\PrintProxyPrep\mtg_core\recommendations`:

- `{source}.sqlite3`: normalized card membership, source provenance and aggregates;
- `{source}-run/state.json`: persisted inputs, completed/rejected/unavailable
  samples, counts, current work, and errors;
- `{source}-run/responses/`: compressed network responses for network collectors.

Source names are `playgroup`, `deckstats`, `mtggoldfish`, `preconstructed`, and
`metagame`. One exclusive collector lock protects each run directory. Create an
empty `STOP` file inside that directory to pause; remove it and rerun the same
script without arguments to resume persisted inputs. Do not delete checkpoints to
resume. Completed and rejected samples are not automatically refreshed or retried.
For exports, keep input paths available and use a new filename for a corrected
previously rejected sample. Imported databases remain usable throughout collection.

Every accepted sample needs exactly 100 included copies, one or two distinct
commanders, and locally resolved Oracle UUIDs for every included card. This is a
completeness screen, not a full legality check. Name resolution uses the existing
read-only catalog; unknown and ambiguous names are reported, never guessed.
Writes are atomic and idempotent per source deck key; interrupted checkpoint writes
do not double-count database samples. Local export keys are absolute file paths;
copying an export to a different path can create another sample.

Network collectors reuse the existing serial downloader with at least six seconds
between request starts, exponential backoff, Retry-After handling, and responsive
STOP checks. They stop on authentication/access errors and redirects; missing or
deleted decks are recorded separately. Responses are bounded at 64 MiB to support
the combined precon export; compressed cache storage is bounded at 10 GiB.
`--max-decks` defaults to 20,000 total accepted samples; raise it explicitly to
resume a bounded run. `--root`, `--catalog`, and `--user-agent` are configurable.
Run only one collector per source/root. Downloaded user data stays outside Git;
these scripts do not publish, export, or redistribute it.

Offline regression coverage is provided for GitHub CI. Local tests, linting,
formatting, and full collections were not run during this implementation.

# Recommendation data builds and distribution

The existing collectors remain developer/operator tools. Installed Manaforge uses
processed SQLite snapshots from versioned GitHub prereleases, through the same
download manager, manifest contract and safe generation installer prepared by the
infrastructure story. No card catalog or artwork is published with them.

## Source audit and permission

On 2026-10-26 the user confirmed permission to share processed recommendation data
for EDHREC, Archidekt and Moxfield. This confirmation is the recorded basis for
enabling these three sources; it does not broaden existing collection permissions,
authorize raw-deck redistribution, or authorize repeated automated collection.

| Source | Existing central collection | Published representation |
| --- | --- | --- |
| EDHREC | `tools/collect_edhrec.py`, optional cohort/discovery collectors; cached, bounded, rate limited, resumable | Whitelisted normalized pages, filtered cohorts and theme discovery tables; no response cache, crawl state, seeds, errors or credentials |
| Archidekt | `tools/collect_archidekt.py`; existing one-run bounds and lock remain | Popularity, exact commander-set cohorts, inclusion and card-pair counts; no deck identifiers, deck URLs, owners or membership records |
| Moxfield | `tools/collect_moxfield.py`; existing public visibility/access-denial and request limits remain | Same aggregate-only schema as Archidekt |
| Playgroup, Deckstats, MTGGoldfish, preconstructed, metagame | Existing `public_deck_ingest` tools/adapters | Excluded until redistribution permission is separately recorded; existing local functionality remains |
| Personal `local.sqlite3` | Local user imports | Never included |

The exporter reads the existing collected data in read transactions and creates
fresh output databases from explicit tables/columns. It never uploads the original
database. Source-specific scoring and filtering remain: EDHREC inclusion/categories
are retained, and statistical providers retain exact commander-pair and card-pair
counts, so their baseline, inclusion, synergy and association calculations agree
with the live store. This new public format does not apply the lossy suppression
rules of the older personal Archidekt portable archive. It contains aggregate counts,
including small cohorts, without per-deck identifiers or records.

Source quality/sampling restrictions remain those documented in
[EDHREC collection](edhrec-collection.md), [Archidekt collection](archidekt-collection.md)
and [Moxfield collection](moxfield-collection.md). Public access alone is not a
redistribution license. No provider protections are bypassed and no messages are sent.

## Collect and build centrally

Run from a developer machine with its existing environment and private checkpoints:

```powershell
$python = '.\Mtg_Projects\mtg_proxy\venv\Scripts\python.exe'
# Explicit operator action only; delegates unchanged to the existing collector:
& $python tools/recommendation_data.py collect edhrec -- --with-discovery
# Other existing CLI arguments can follow the separator for each source.
```

Collection is not required to build an already collected snapshot. GitHub-hosted
ephemeral workers are not used for long-running collection: they lack the private
checkpoints, have runtime limits, and should not upload raw caches for persistence.
The permitted alternative is the developer-machine collector plus CI publication.
No monthly collection schedule is enabled by this change. A future explicitly
authorized recurring collector can invoke the same tools with retained state;
rerunning completed collectors currently respects their existing checkpoint rules
and does not imply a refresh.

Build processed assets, outside the checkout:

```powershell
$output = Join-Path $env:LOCALAPPDATA 'PrintProxyPrep\mtg_core\recommendation-release-builds\2026.10.26-alpha.1'
& $python tools/recommendation_data.py build --output $output --version 2026.10.26-alpha.1
```

`--root` chooses the existing recommendation directory; `--sources edhrec archidekt
moxfield` selects approved sources. Missing sources are reported in manifest metadata,
not replaced with invented data. The output contains compressed ZIP assets, a
`manifest.json`, and a **private** `.build-state.json`. Fingerprints include source
database/WAL contents. Unchanged inputs reuse completed archives. Never upload the
build-state file, staging folders, source databases, raw responses or user decks.
Only the explicit manifest/archive allowlist is uploaded. Keep only one build writer
per output directory. Existing collector locks govern collection concurrency.

Statistical aggregation is intentionally performed once centrally; computing full
co-occurrence aggregates can take time and disk space. Exports include normalized
Oracle UUIDs only, never provider printing IDs. Card/printing metadata and rulings
continue to come from Scryfall via the installation story. Collectors' existing
name-to-Oracle mappings are reused; unresolved names remain reported, never guessed.

## Stage, validate in CI, publish

Commit/push the implementation first. The staging command requires the full commit
SHA and an alpha/beta dataset version. GitHub dataset versions are independent of
`APP_VERSION`. Use a new version for changed public assets; existing published
versions are immutable and are never overwritten.

```powershell
$commit = git rev-parse HEAD
& $python tools/recommendation_data.py stage --directory $output --commit $commit --branch infrastructure-readiness --git-credentials --dispatch
```

`GH_TOKEN`/`GITHUB_TOKEN` can be supplied instead. `--git-credentials` uses the existing
Git credential helper in memory without printing or storing the credential. Staging
creates a **draft prerelease**, uploads only manifest-listed archives and the
manifest, and dispatches the existing Tests workflow. Failed/partial uploads can
resume into the same draft if the target commit and existing checksums agree.
Do not use `promote` locally as a substitute for CI.

The workflow's optional `recommendation_release_tag` input runs publication only
after both Windows test jobs pass. A single publication concurrency group prevents
overlapping feed updates. CI downloads the staged processed assets, verifies
archive/file SHA-256 and sizes, bounded safe extraction, SQLite integrity, exact
schema/table/column allowlists, and normalized EDHREC payloads. Unexpected files or
schemas fail before publication. The release target must match the CI-tested SHA.
Only the publication job receives `contents: write`; normal tests remain read-only.

CI publishes `recommendations-<dataset-version>` as a prerelease, then updates the
manifest-only `recommendation-data-latest-alpha.1` prerelease. Neither becomes the
repository's latest stable application release. A failed test/validation run leaves
the release draft and the existing feed untouched. A failed feed swap attempts to
restore the old manifest name. Previous versioned archives remain available.

To retry a failed CI publication, dispatch Tests on the same branch/commit with the
same staged release tag. Resolve reported errors first; changed implementation
requires a new commit/version and corresponding draft. To recover a feed, use a
previous versioned release's `manifest.json` or the feed's `manifest.previous.json`.
No user installation is switched until its own verification/activation succeeds.

The optional `validate --directory ...` CLI is available for CI; per the story,
tests, smoke tests and standalone validation commands are not run locally.

## Application and wizard integration

The default feed is:
`https://github.com/RyMeep128/Manaforge/releases/download/recommendation-data-latest-alpha.1/manifest.json`.

Use `RecommendationDistribution.check()` from a shared background job. It downloads
a bounded manifest, checks schema compatibility and returns the manifest plus
`(missing_or_changed_entries, unavailable_optional_ids)`. Successful checks persist
their timestamp; failure preserves the prior cache and working datasets. Call
`install(entry, cancel=event, progress=report)` for selected entries. Shared download
integrity checks, archive bounds, dataset-specific validation and atomic SQLite
activation precede use. The wizard owns progress UI, required-source policy and
first-run completion; no duplicate installer or monthly scheduler is added here.

Each dataset has an identifier (`recommendations-edhrec`, `recommendations-archidekt`,
`recommendations-moxfield`), opaque dataset version, schema version 1, GitHub URL,
compressed size, SHA-256 and expanded-size limit. Source identifiers, generation
timestamps and Scryfall identifier mapping are included in manifest/bundle metadata.
Individual sources are optional, allowing unavailable providers to be reported;
the wizard must require at least one usable recommendation source if setup needs it.
Schema compatibility, rather than application version equality, controls updates.
This producer only publishes schema 1; a future incompatible producer must retain
a schema-1 feed or provide an explicit compatible-manifest route.

After activation, existing `default_sources` adapters read installed aggregates and
EDHREC pages/cohorts; discovery uses the installed normalized discovery database.
Opening recommendations never starts a collector. Explicit local collected files
and existing source preferences retain precedence, and local user-import ranking
remains supplementary. The registry contributes to recommendation cache signatures
so updates invalidate cached results. Existing open SQLite readers can finish on
previous immutable generations. No application update is needed for compatible data.

The [infrastructure notes](infrastructure-readiness.md) describe storage, shutdown,
interrupted work and generation retention. UI controls, recurring user-side checks,
artwork modes, and a full first-run installer remain in the next story.

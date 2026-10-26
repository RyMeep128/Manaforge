# Infrastructure readiness

This is the foundation for dataset distribution and first-run setup. It does not
run collectors, download the artwork collection, schedule updates, or publish a release.

## Audit and ownership

| Responsibility | Existing owner and decision |
| --- | --- |
| Startup | `run_manaforge.py`, `mtg_home.launcher`, standalone entry points. Keep the single application and lazy workspace creation. |
| User preferences | `mtg_print.config` INI settings, card DB preference tables, project/deck JSON and their existing recovery mechanisms. Preserve these stores. |
| Card catalog | `mtg_core.db.CardDatabase`, SQLite with WAL, migrations, full printing payloads and search indexes. `CardService` is the application API. |
| Card downloads | `sync.fetch_json/fetch_bytes`, `services.catalog_sync` and persisted catalog checkpoints. Keep small lookup APIs and existing catalog behavior; add streaming bulk staging for future importers. |
| Rulings/rules | Separate SQLite stores in `rulings.py` and `rules_reference.py`. Rulings replacement validates first and uses a transaction. Existing bulk rulings/tag parsers still materialize JSON in memory. |
| Recommendations | `recommendations`, `recommendation_sources`, EDHREC caches/discovery, public-deck datasets, Archidekt/Moxfield and other ingestion modules. Preserve scoring and provider restrictions. `recommendation_cache.download_cache` now uses the shared streaming downloader before semantic validation and replacement. |
| Artwork | `services.images` and `db.images`: printing/face manifests and content-addressed assets, with SQLite metadata and filesystem payloads; legacy blobs remain readable. Materialized copies and bounded decoded thumbnails are presentation caches. No automatic eviction or limit on SQLite record growth is introduced. |
| Background work | Existing Qt workers in Core Admin, Editor and shared dialogs remain. `mtg_ui.jobs.JobQueue` supplies a reusable cancellable sequential queue for installation/update operations; its worker reports through queued Qt signals. Home owns a queue and cancels active work before closing. |
| Logging | Existing rotating network logs and `diagnostics` logs. New retry logs contain host/status rather than signed URLs or credentials. |
| Packaging/CI | `Build Manaforge.cmd` already builds the unified PyInstaller bundle. `.github/workflows/tests.yml` already tests Windows/Python 3.12 and 3.13 and runs scoped Ruff checks. It now has an optional manual Windows bundle job using that same build script and uploading an artifact after tests pass. No release publication permissions or duplicate workflow are added. |

Large GUI modules still coordinate UI/legacy workers; new downloading, staging,
integrity and manifest logic lives in Core, with Qt lifecycle handling in shared UI.
There is no reason to rewrite those GUI modules for this story.

## Storage and configuration

The existing root remains `%LOCALAPPDATA%/PrintProxyPrep` on Windows, or
`PRINT_PROXY_PREP_DATA_DIR` when explicitly overridden. Existing decks, catalog,
preferences and artwork are not migrated or deleted.

`InstallationState` uses `<root>/mtg_core/installation.sqlite3`, separate from the
catalog. It persists arbitrary JSON settings and installed manifests with current
and previous generation paths. Integration keys are:

- `setup_complete` (default supplied by caller: false).
- `artwork_mode`: `on_demand` or `full_offline` (caller default: on demand).
- `cards_root`, `recommendations_root`, `artwork_root`: absolute user-selected paths.
- `last_successful_update_check`: set by the future update checker after success.
- `last_successful_dataset_update`: recorded transactionally at dataset activation.

Downloaded dataset generations default to `<root>/mtg_core/datasets/cards` and
`.../recommendations`. Existing live databases stay at their existing paths.
Setting these roots chooses staging/generation ownership; it does not relocate or
replace a live catalog. Card importers must merge into the catalog transactionally
so favorites and user preferences in that database survive.

The default `CardService` honors a configured `artwork_root` for new assets and
materializations. Existing asset records retain their original path references.
Explicitly injected catalogs retain their existing storage behavior. Changing a
root does not move existing files; a future Settings migration flow must do that.
Artwork and its SQLite metadata can continue growing. The core cache is shared
by front/alternate faces and both future artwork modes; no new artwork mirror,
database engine, image-quality policy, or competing cache is introduced.

## Download and job interfaces

Use `get_download_manager().download(url, destination, sha256=..., size=...,
cancel=event, progress=callback, validate=semantic_validator)` from a worker.
SHA-256 and size are optional for sources that do not publish them. GitHub dataset
manifests require both. Bytes stream in 1 MiB chunks with disk checks and bounded
concurrency; retries cover transient network errors and retryable HTTP statuses.
Timeouts, retry count, concurrency and per-host request intervals are configurable.
Scryfall shares its existing process-wide minimum pacing/cooldown with old lookups.
HTTPS redirects are enforced; `Retry-After` supports seconds and HTTP dates.

The `.part` file and `.part.json` sidecar beside a destination describe interrupted
work. Resume uses Range/If-Range only with an ETag or Last-Modified validator.
Changed/ignored representations restart; unvalidated bytes never append to a new
representation. Checksum, HTTP length and semantic validation precede atomic
replacement. Sidecars can contain provider URLs and belong in user data, never
in Git or published assets. A caller must own its destination and use the shared
manager; separate application processes must not write the same destination.

`sync.stage_bulk_download(kind, destination, ...)` retrieves official Scryfall
metadata and stages its export through this manager, returning `(path, metadata)`.
It does not import the export. Scryfall exports without published checksums still
need semantic validation by their importer. Existing small byte-returning APIs
remain appropriate for individual images and API responses.

`JobQueue.submit(work)` invokes `work(cancel_event, report_progress)` off the GUI
thread. Connect `progress(job_id, value)` and `status(job_id, state, value)` to
QObject slots. States are queued/running/completed/failed/cancelled. Progress
objects expose bytes, optional total, speed, remaining seconds and phase.
The future wizard can derive percentages/overall progress. Use `cancel(job_id)`
or `cancel_all()` to pause cooperatively; resubmitting the download resumes its
sidecar. `shutdown()` stops admission and requests cancellation. Keep the owner
alive until `busy` is false/`idle` fires. Home defers closing while jobs stop;
it does not terminate threads or block the event loop. Tasks must check cancellation
between processing chunks; network cancellation waits at most the request timeout.

## Dataset contract and recovery

`parse_manifest` accepts this versioned envelope (values below are illustrative):

```json
{
  "manifest_version": 1,
  "datasets": [{
    "dataset_id": "recommendations",
    "version": "2026.10",
    "schema_version": 1,
    "url": "https://example.org/recommendations.zip",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "size": 1000,
    "category": "recommendations",
    "required": true,
    "format": "zip",
    "expanded_size": 10000
  }]
}
```

Versions are opaque dataset identifiers, independent of application versions;
consumers explicitly allow supported schema versions per dataset. The envelope
may carry publication metadata such as generation timestamps/source identifiers.
The distribution story must finalize those optional producer fields and publish
a compatible manifest. Unsupported required datasets block setup; the wizard may
skip unsupported optional datasets and report them.

`DatasetInstaller.install(manifest, supported_schemas={id: {versions}},
validate=validator, cancel=event, progress=callback)` downloads/verifies an artifact,
stages a unique generation, validates its contents and activates it by one SQLite
transaction. Raw `file` payloads and bounded ZIP extraction are supported.
ZIP paths, Windows device/stream names, links, duplicate paths and expanded size
are checked. Consumers supply semantic/SQLite integrity validators and open the
returned path or the installed active path; downloaded files are never assumed
safe solely because their checksum matches.

Failure before activation leaves the previous active pointer and data intact.
Old generations remain available, including to existing Windows readers; previous
generation paths are recorded for recovery. Completed archives survive a failed
extraction and can be reused. Interrupted transfers retain partial files.
Permissions, insufficient space, invalid checksums/schemas and extraction errors
surface to the job/UI without replacing working installations. Offline operation
continues against installed data. No background update check runs in this story.

## Remaining integration work and risks

- The distribution story owns permissible collection, stable Oracle/printing ID
  mappings, generation metadata, manifest publication and release asset URLs.
  Existing collectors have source-specific permission restrictions; an available
  collector does not establish redistribution permission.
- The wizard/update story owns first-run UI, monthly checks, importer/index refresh,
  consumer activation/reopening and persistent artwork work enumeration. It should
  reuse these services rather than add another downloader or Qt worker framework.
- Existing bulk rulings/tag JSON parsing is memory-heavy; large card importers need
  bounded parsing/staging. No full catalog import or monthly scheduling was added.
- The current catalog mixes card records and user preferences. Never replace that
  SQLite file with a downloadable catalog. Use transactional imports or explicitly
  separate preference ownership before a future whole-file catalog swap.
- Artwork retrieval uses per-printing locks and unique atomic temporary files;
  missing/corrupt asset payloads are not materialized as empty images. Existing
  materialized copies can duplicate disk use. Estimate actual collection size and
  quality before the offline story; no 100–200 GB scale claim has been verified.
- Generation retention is intentionally conservative. A crash can leave inactive
  staging directories, and old datasets consume space. Future cleanup must only
  remove verified application-owned inactive generations, never user directories,
  decks, current/previous datasets, or referenced artwork.
- Process-wide locks/pacing do not coordinate independent collector/admin processes.
  Use one writer per managed destination. Concurrent collection is still governed
  by existing collector locks and provider rules.
- CI bundle artifacts are optional, unsigned, and are not an installer or a release.
  Dataset packaging/publication and release automation belong to the later stories.

Regression coverage added for streaming/resume/cancellation, checksum/semantic and
disk failures, safe dataset activation/extraction, concurrent artwork recovery and
Qt queue lifecycle. No tests, smoke tests or builds were run locally. GitHub Actions
is the authority for test results.

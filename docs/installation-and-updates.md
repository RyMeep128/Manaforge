# Installation, artwork and data updates

## Friends installing Manaforge

Run **Manaforge-Setup.exe** for a per-user Windows installation without administrator
access. Use the Manaforge Start Menu shortcut or
`%LOCALAPPDATA%/Programs/Manaforge/Manaforge.exe`. The optional desktop shortcut
and Start Menu shortcut target this permanent, windowless launcher. The legacy
`Manaforge.cmd` now forwards to it as well. Application binaries live under
`versions/<APP_VERSION>`; data remains in its existing configured locations.
The optional **Manaforge-Windows.zip** remains a portable distribution: extract
the entire archive and keep `_internal` beside `Manaforge.exe`.
Both distributions include Python and dependencies.

Windows bundles are available as artifacts of manually requested
[Tests workflow builds](https://github.com/RyMeep128/Manaforge/actions/workflows/tests.yml).
The same workflow can publish an application **prerelease** when its explicit
`publish_windows_prerelease` input is selected. Dataset releases are separate and
are not application installers. Building an artifact does not publish a release.

On first launch, setup asks for a data location and artwork mode, checks the local
installation, and automatically looks up download sizes. Completed checks stop the
loading indicator and show the next action; detailed local diagnostics are collapsed
under **Show diagnostic details**. **Check download sizes** repeats the lookup
after changing options. It retrieves current official Scryfall metadata and the published recommendation
manifest; it does not save a new artwork mode or start installation. The estimate
includes expansion, catalog/index staging and selected artwork. Select **Install**
to download, verify and initialize the library. Finish launches the Home page.

Existing installations can **Continue with existing data (artwork as needed)**
without requiring a network connection. Existing catalogs/favorites stay in place;
setup never copies a replacement catalog over user preferences. User decks and
printing settings retain their existing locations. All subsequent setup attempts
reuse completed datasets/downloads where their version still matches.

## Installation progress

Setup and Data Management share the same progress cards. Overall progress counts
completed stages rather than claiming a percentage of an unknown total duration.
The stages cover requirements, cards/rulings, Oracle Tags and comprehensive rules,
recommendations, artwork preparation,
and final verification. On-demand mode prepares artwork storage; it does not
schedule a full-artwork download. Completed stages stay visible.

The current operation shows measured bytes or record counts, with percentages only
when a total is available. Unknown totals and verification without measured counters
use an indeterminate indicator. Receiving all bytes does not mark verification or
installation complete. Download speed and estimated remaining time appear only when
available. Artwork transfers report the current card/face and the scan's card count;
these are per-file byte measurements, not a fabricated total for the entire library.

Pause cooperates with active transfers and processing checkpoints. Resume rechecks
the dataset plan, reuses installed versions and verified files, and resumes partial
HTTP downloads when the server supports safe range requests. Otherwise the transfer
restarts, with an explicit notice. Interrupted stage snapshots are persisted locally
and restored when reopening setup/settings. Changed dataset plans reset stage
completion; imports interrupted before activation may need to repeat processing.
Failures identify the operation, keep working data, and offer Retry. Technical error
details remain collapsed; Diagnostics & Repair is available separately.

## Artwork modes

- **Download as needed** is the default. Missing images are fetched directly from
  Scryfall, cached permanently, and reused offline. Existing thumbnail workers
  display their placeholders while the shared service fills the cache.
- **Full offline artwork** fills images for every supported printing and available
  face in the Default Cards catalog. PNG is preferred, with large/normal fallback
  when required. This is English printings, plus the printed language when a card
  has no English printing; it does not claim all localized printings in All Cards.
  The same catalog and recommendation data are used in both modes.

The wizard reserves an estimated **up to 200 GiB** for artwork; actual size depends
on supported printings and image formats. This is not a measured guarantee. A full
fill can take many hours or days under the existing conservative Scryfall pacing.
No artwork is mirrored on GitHub. The implementation was not used to download the
full artwork collection during development.

Artwork fills enumerate bounded batches and persist printing checkpoints in SQLite.
Pause requests cooperate with network timeouts and processing; Resume continues the
same catalog checkpoint. A changed catalog starts a fresh scan, reusing valid images.
Failures retain existing artwork and report a retryable count. Completed scans reset
their checkpoint so later runs also find changed URLs, not just new printing IDs.

Image URLs are tracked **per printing and face**, independently of content-addressed
asset IDs, because different URLs can share identical image bytes. Front/back aliases
refer to the same cached face asset where appropriate. Header/format verification,
checksums, atomic asset writes and existing per-printing locks protect cached data.
Custom/user-selected images are preserved. Canonical files and SQLite metadata may
continue to grow; no automatic cache eviction or database size cap is introduced.
New fills point directly at canonical files instead of making a second full copy.

## Data Management

Home → **Settings → Data Management** provides:

- Installed card/rulings, Oracle Tags, comprehensive rules, and recommendation versions.
- **Check for Updates**, estimated sizes and **Apply updates**.
- Artwork mode and future data/artwork storage selection.
- **Download missing artwork**, including resumable fills and changed-image retries.
- Artwork asset count/size and **Audit artwork storage**.
- Pause/Resume with current operation, byte/item progress, transfer speed, time estimate
  when calculable, and overall installation stage progress.

Changing locations affects new generations/assets. Previously referenced artwork
remains accessible at its stored path; this UI does not automatically move 100–200 GB
of existing data. Catalogs already containing user preferences are kept in place.
**Audit artwork storage** inventories the selected artwork folder, verifies recorded
checksums, and shows logical file sizes, unique file storage (hard links counted
once), verified reclaimable bytes, existing hard links, and preserved/problem files.
These file-byte totals exclude filesystem compression, sparse allocation, and
metadata overhead. The first audit reads the artwork and can take hours for a large
offline collection. Verification checkpoints live in a separate SQLite audit journal
beside the card catalog; pause/restart reuses hashes only while file signatures match.
The selected root can be an existing junction such as C: artwork redirected to E:;
unexpected links inside managed artwork directories are excluded.

After reviewing a completed audit, choose **Reclaim verified duplicates** and confirm.
The operation rechecks ownership and both checksums, then atomically replaces each
eligible Scryfall cache copy with a hard link to its canonical asset. Legacy file paths
continue working for saved decks and print projects. Changed/custom/unknown files,
unsupported links, other-volume files, and locked destinations are preserved and
reported. No canonical artwork, deck, setting, or arbitrary file is deleted. The
journal supports interruption recovery without another full artwork backup. Normal
image requests now return canonical paths; explicit exports still create independent
copies. Managed artwork publication replaces files atomically instead of writing
through hard links. Audit again after reclaiming to refresh the storage totals.

Closing a dialog that owns a running setup/update first cancels safely and waits for
its worker to settle. Closing a dialog that is merely observing an automatic update
leaves it running. The main application cancels and defers shutdown until its shared
job queue is idle. Partial file downloads and installed generations remain available.

## Application updates

Home and Print Studio show the running bundle's embedded `APP_VERSION` as the
installed version. This metadata is packaged from `mtg_proxy/constants.py`; it is
never inferred from the newest release, Git checkout, or a saved settings value.
Launching an older extracted copy correctly continues to report that older version.

**Check for Updates** is muted green, shows an indeterminate indicator while checking,
and becomes burnt orange **Update Available** when a newer downloadable release is
found. All application update entry points share one check and result. Failures stay
visible and allow retry; an empty channel is a check failure, never ?up to date?.
Automatic checks respect online/startup settings, are limited to once per six hours,
and notify once per offered version. Manual successful checks have a 30-second cache;
failed checks can be retried immediately. Data updates below are independent.

The checker reads published GitHub Releases from `RyMeep128/Manaforge`, paginating
past dataset releases. It ignores drafts, malformed versions and releases without an
uploaded Windows application installer or ZIP. Installers are preferred. Both `Manaforge-Windows.zip` and legacy
`PrintProxyPrep-<version>-win.zip` are supported. Semantic precedence includes numeric
prerelease identifiers and ignores build metadata. Alpha installations accept alpha,
beta, RC and stable; beta accepts beta, RC and stable; stable accepts stable only.
Only Windows packages currently exist; other operating systems report that limitation.

Select **Download & Install** to download inside Manaforge. Shared background workers
show measured percentage, bytes and speed in the update panel and Home status bar.
Click the downloading button to cancel; retry resumes partial transfers when safe.
The release's `SHA256SUMS.txt` must contain a unique installer SHA-256 checksum.
Incomplete or mismatched downloads are never executed. Legacy ZIP-only releases are
still recognized but cannot be installed by this workflow; they show an explanation.
Source checkouts cannot launch application installers.

After verification, normal window close guards save work or postpone installation.
The installer writes a completion receipt and waits for the old process to exit
before launching the new executable. A persistent record in
`PrintProxyPrep/application-updates/pending.json` (under the existing data root,
including `PRINT_PROXY_PREP_DATA_DIR` overrides) tracks download, readiness,
pending installation, verification and cleanup. It is created on confirmation only.
Installer cancellation/failure retains the old executable. Reopen that executable
to retry; no automatic rollback overwrites application or data files.

The new application verifies its embedded version, installation path and receipt,
initializes its required card service, runs the existing local health checks, and
confirms prior data locations remain accessible before allowing cleanup. Failed
initialization or checks retain the record and old installation. Successful updates
write `last-success.json` and clear the pending record after cleanup.

The permanent launcher reads `active-install.json` beside itself (with an atomic
backup record). This is the single authority for the active and previous verified
installation; it never selects a directory merely because it has a newer name.
Fresh/manual installs run the packaged startup diagnostic and verify every payload
hash before activation. In-app updates activate only after the existing startup and
data checks succeed. One previous verified installation remains as a fallback;
later successful updates clean displaced fallbacks using the same conservative
inventory rules. Interrupted or failed activation leaves the previous target usable.

Normal launch forwards arguments without a command prompt, checks payload presence
and sizes, hashes the application executable, and rehashes dependencies whose file
timestamps changed since activation. Missing, modified or immediately failing
executables fall back to the previous verified installation. If neither record
provides a usable copy, a repair message asks the user to rerun the installer.
Failures occurring after the launcher's brief process-start check still use the
application's existing diagnostics; they cannot always trigger automatic fallback.
The launcher requires Windows' .NET Framework 4.x, present on supported CI runners.

Shortcuts and windows share the `Manaforge.Desktop` application identity, and new
window-created taskbar pins carry a permanent relaunch command and icon location.
The installer refreshes its Start Menu shortcut and safely migrates an existing
standard desktop shortcut targeting a managed version or the legacy CMD launcher.
Customized desktop shortcuts with arguments are preserved unless the desktop task
is explicitly selected. Windows does not provide reliable automatic migration of
existing taskbar pins or arbitrary user-created links to old version directories:
unpin those once and pin the new Start Menu shortcut. User-created links targeting
the permanent executable remain valid across updates. Launcher maintenance touches
only application files and activation metadata, never decks or configured data.

Cleanup only handles installer-owned version directories under
`%LOCALAPPDATA%/Programs/Manaforge/versions`. It rejects junctions, symlinks and
invalid inventories. Only files whose hashes still match the installer inventory
are removed; unknown and modified files survive. Configured data locations within
an old installation protect the entire folder. Portable installations are always
preserved for explicit manual review, including folders containing decks or artwork.
No recursive directory deletion occurs. Locked files retain `cleanup_pending` and
retry after health verification on a later startup without blocking the UI.

The Windows build workflow compiles the Inno Setup installer, smoke tests its
receipt/payload, and uploads the installer, ZIP and checksums. Publication still
requires the explicit prerelease input; building never creates a release or tag.
CI tests cover updater ownership, interrupted cleanup, verification and startup
failure contracts. Local tests, builds and application launches were deliberately
not run. CI and a Windows installed-app exercise must validate end-to-end updating,
installer cancellation, restart, version reporting and data preservation.

## Automatic updates

After completed setup, Manaforge checks approximately every **30 days**. Startup
and a lightweight six-hour timer decide whether a check is due; no provider is polled
continuously. Explicit offline mode disables automatic network work. Failed/interrupted
updates retry no more often than daily, and manual checks remain available.

Setup installs Scryfall Oracle Tags for offline tag search and the official English
Comprehensive Rules from Wizards for offline rules browsing. Later data updates also
refresh these references. Tag imports replace their index transactionally; rules use
the existing validated snapshot importer. Failed or cancelled reference work retains
previous usable data and leaves setup/update pending for retry. Completed card and
rulings imports are reused on retry. Artwork-only fills and targeted card repairs do
not download reference datasets.

Checks compare Scryfall Default Cards, Rulings, and Oracle Tags timestamps and the GitHub manifest
independently. They do not depend on set-release dates or application releases.
New recommendation archives use the existing compatibility/schema and integrity
checks. Card and rulings downloads use current compressed JSONL exports, with legacy
JSON-array support through [ijson](https://github.com/ICRAR/ijson). Parsing, staging,
index creation and artwork work run off the GUI thread.

Each card export is parsed into a temporary SQLite catalog using existing normalization
and compact search data. Only a complete nonempty validated export enters the live
catalog transaction. The merge preserves custom records, favorites, image records
and preferences, then refreshes canonical choices and indexes atomically. Cancellation,
invalid input, permissions or disk failures before commit roll back the transaction.
Rulings are independently staged/grouped and applied transactionally, including empty
snapshots for local cards without rulings. Recommendation generation activation retains
the previous dataset. The installation stays usable with older working datasets if
any later operation fails; setup completion is recorded only after all selected work
succeeds. Managed bulk exports and previous generations are retained for recovery.

In on-demand mode, updates refresh only previously cached artwork whose source URL
changed; uncached artwork remains on demand. Full offline mode scans the catalog and
downloads only missing or changed images. A cached-refresh failure remains pending
for retry, without deleting its previously working image.

## Building and validating Windows bundles

The existing `Build Manaforge.cmd` still owns PyInstaller packaging. It now includes
Core's bundled data and ijson backends. The optional Windows workflow build runs after
both Python 3.12/3.13 test jobs. It invokes the actual packaged executable's
`--verify-bundle` diagnostic offscreen, checking imports, bundled starter data and
Home construction without provider requests or first-run downloads, then uploads the
ZIP. This diagnostic and all tests/build checks run **in CI only**.

The separate publication input permits only `-alpha.1`/`-beta.1` application versions,
uses the tested commit, and marks the release as a prerelease, never the latest stable
release. It does not embed downloaded datasets or artwork in the application ZIP.

The [infrastructure](infrastructure-readiness.md) and
[recommendation distribution](recommendation-distribution.md) documents describe the
shared transport, generation manifests, source permissions and data publication.

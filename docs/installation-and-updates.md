# Installation, artwork and data updates

## Friends installing Manaforge

Download a tested **Manaforge-Windows.zip**, extract the entire archive to a normal
writable folder, and open `Manaforge/Manaforge.exe`. Keep the accompanying `_internal`
directory beside the executable. The standalone bundle includes Python and its
dependencies; installing Python, Git, or development tools is unnecessary.

Windows bundles are available as artifacts of manually requested
[Tests workflow builds](https://github.com/RyMeep128/Manaforge/actions/workflows/tests.yml).
The same workflow can publish an application **prerelease** when its explicit
`publish_windows_prerelease` input is selected. Dataset releases are separate and
are not application installers. Building an artifact does not publish a release.

On first launch, setup asks for a data location and artwork mode. **Check download
sizes** retrieves current official Scryfall metadata and the published recommendation
manifest; it does not save a new artwork mode or start installation. The estimate
includes expansion, catalog/index staging and selected artwork. Select **Install**
to download, verify and initialize the library. Finish launches the Home page.

Existing installations can **Continue with existing data (artwork as needed)**
without requiring a network connection. Existing catalogs/favorites stay in place;
setup never copies a replacement catalog over user preferences. User decks and
printing settings retain their existing locations. All subsequent setup attempts
reuse completed datasets/downloads where their version still matches.

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

- Installed card/rulings and recommendation versions.
- **Check for Updates**, estimated sizes and **Apply updates**.
- Artwork mode and future data/artwork storage selection.
- **Download missing artwork**, including resumable fills and changed-image retries.
- Artwork asset count/size and **Clear optional artwork copies**.
- Pause/Resume with current operation, byte/item progress, transfer speed, time estimate
  when calculable, and overall installation stage progress.

Changing locations affects new generations/assets. Previously referenced artwork
remains accessible at its stored path; this UI does not automatically move 100–200 GB
of existing data. Catalogs already containing user preferences are kept in place.
Clearing optional copies removes only verified reproducible materializations with an
intact canonical asset. Canonical artwork is retained because saved decks and print
projects can refer to its IDs outside the catalog. No cleanup deletes decks, settings,
arbitrary files, active datasets or canonical artwork.

Closing a dialog that owns a running setup/update first cancels safely and waits for
its worker to settle. Closing a dialog that is merely observing an automatic update
leaves it running. The main application cancels and defers shutdown until its shared
job queue is idle. Partial file downloads and installed generations remain available.

## Automatic updates

After completed setup, Manaforge checks approximately every **30 days**. Startup
and a lightweight six-hour timer decide whether a check is due; no provider is polled
continuously. Explicit offline mode disables automatic network work. Failed/interrupted
updates retry no more often than daily, and manual checks remain available.

Checks compare Scryfall Default Cards and Rulings timestamps and the GitHub manifest
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

# Unity and XMage release delivery

Windows application packages contain a complete Unity player, the app-approved
Manaforge XMage fork, its Java runtime, and a precompiled Java bridge. Both
`Manaforge-Setup.exe` and `Manaforge-Windows.zip` contain the same gameplay files.
Users do not need Python, a JDK, Unity, or a GitHub account. Unity updates with
Manaforge; it is not updated independently.

The application updater continues to verify and install `Manaforge-Setup.exe`.
Unity, engine and bridge files participate in the existing installer inventory,
startup verification, side-by-side activation and application fallback.

## Optional XMage updates

Open **Home → Settings → XMage Updates**, or select **XMage Updates** in Print
Studio's update panel. Choose **Check for XMage Updates**, then **Update XMage** to install an offered compatible
engine. The panel shows the installed/offered version, transfer size, measured
progress and speed. The check button cancels an active operation. Interrupted
downloads use the shared transport's safe resume support.

Checks and downloads respect explicit offline mode. There is no automatic engine
installation. Only releases explicitly tested for the installed application
version and matching its bridge source fingerprint can be offered. A card/rules
update can therefore ship independently; a bridge/protocol change requires a new
application version.

Engine updates live below the existing data root at `play-components`, including
`PRINT_PROXY_PREP_DATA_DIR` overrides. `active.json` selects immutable installed
payloads; separate `approved` records establish authority, rather than trusting a
bundle's own marker. Every file and engine-lock entry is checked before use.
Selection falls back to the previous compatible verified engine, then the bundled
engine if an override is damaged or incompatible with a newer application.

An update verifies its archive, extracts to a new staging directory, verifies the
full inventory, and starts an isolated engine/bridge connection and shutdown check
before activation. Activation is atomic. Games and updates share an OS-backed
ownership lock: operations attempted during a game ask the user to retry afterward.
A session never changes engines while running.

**Revert to Previous Engine** verifies and selects the retained predecessor. The
first independent update can revert to the application-bundled engine. Failed or
cancelled work retains the old selection. Payloads, partial staging and downloads
are retained for recovery; this first implementation does not automatically delete
old component directories. Decks, settings, artwork and configured data are not
replaced by engine updates.

## Build and publish

The Tests workflow's Windows build now builds Unity at the checked-out application
revision, prepares the exact engine lock, and invokes `tools/package_play_runtime.py`
before `Build Manaforge.cmd`. The build script rejects a missing gameplay payload.
The engine preparation helper first looks for durable published engine assets
matching the app-owned lock, then uses the existing hash-pinned Actions artifact.
An expired/missing artifact without a matching release blocks the build; it never
silently substitutes stock XMage.

`package_play_runtime.py --engine ENGINE --jdk JDK` produces:

- `Mtg_Projects/build/gameplay/distribution`: input to PyInstaller.
- `Manaforge-XMage-Windows.zip`, `xmage-component.json`, and `SHA256SUMS-XMage.txt`
  in the same build directory: durable engine release assets.
- A Unity file inventory with the application version and source revision.

Use a fresh output directory; existing payloads are not overwritten. The bridge
is compiled against the selected engine during packaging. Installed launches copy
verified compiled classes into their writable session workspace instead of invoking
`javac`. Source checkouts retain their developer compilation path.

Application publication still requires the explicit `publish_windows_prerelease`
input. The **XMage component prerelease** workflow is a separate manual entry point:
provide a unique `component_version` such as `0.6.107-alpha.1`. Leave `publish` false
for a reviewable build artifact; select it only to publish the verified engine.
This workflow also builds and exercises the matching application to certify
compatibility. It publishes only engine assets under `xmage-v<VERSION>`, not an
application installer release. These tags cannot be mistaken for application
updates. Only the current tested `APP_VERSION` is advertised; adding older versions
requires additional compatibility certification rather than an unchecked range.

Publishing either type requires Python tests, Unity tests, packaged Java/bridge
handshake, a complete packaged human-versus-AI acceptance match, installer checks,
and successful exact-revision protocol, native-payment, Unity and live-opening
workflows. The pinned fork must also have a successful **Broad engine validation**
step at its exact revision. Skipped/unavailable checks block publication. The gate
reports missing evidence immediately; it does not poll other workflows. Run those
workflows first, then retry publication. Cross-repository Actions access must be
available to the workflow token for engine artifact and broad-test evidence.

Published assets are public downloads without credentials. Releases remain
alpha/beta prereleases with `latest=false`. Building never creates a release/tag.
Hosted CI and a Windows installed-app exercise remain required evidence; local
build success alone does not certify gameplay or updater acceptance.

## Component manifest v1

`xmage-component.json` uses `schema: 1` and declares `platform: windows-x64`,
`component_version`, `bundle_id`, `fork_commit`, `java_identity`, the exact
`compatible_app_versions`, and a normalized Java bridge source fingerprint.
`url`, `size`, and `payload_sha256` identify the immutable release ZIP. `files`
maps each relative payload path to its SHA-256, including the app-owned
`manaforge-engine-lock.json`, Java executable and compiled bridge classes.

The manifest is external to the ZIP to avoid self-referential hashes. Extraction
rejects traversal, links, duplicate/unexpected files, incomplete inventories and
oversized archives. Compatibility is established by the maintainer-published
manifest in the Manaforge repository; payloads cannot approve themselves. The
existing GitHub HTTPS release/checksum trust model is retained.

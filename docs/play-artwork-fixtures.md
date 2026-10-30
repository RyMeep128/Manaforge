# Offline real-artwork fixture preparation — G0/P3.2 foundation

Status: offline preparation, worker loading and packaged real-artwork rendering
are exercised locally. Packaged 20/70/200 screenshots exist; measured benchmarks
and remaining G0 requirements stay open. Existing decks, artwork preferences, engine pins and gameplay are unchanged.

## Existing services, no new downloader

`tools/prepare_play_artwork_fixture.py` uses the existing Core CardService and
`mtg_play.visual_catalog` against the installed catalog/cache. Remote callbacks
explicitly fail, and print lookups disable remote refresh. It selects public demo
cards by name, not user decks or session snapshots. It uses Core's existing
artwork materialization/verification; normal Core service initialization and
legacy cache handling remain owned by Core. No second catalog/cache/downloader
or persistent deck model is introduced.

The default public set is Grizzly Bears, Lightning Bolt, Counterspell, Sol Ring,
Pacifism, Forest and Doom Blade. Selected printing/Oracle/face identities are
retained. Candidate metadata preserves standard-compatible versus authentic-only
profiles, so Unity's existing VisualPrintingPolicy chooses the rendered printing.
The exporter does not write rendered identities back to saved selections.

The collector now has an opt-in preparation budget. It verifies selected artwork
first, then standard candidates in ordinal ID order, stopping image inspection
after the requested number of usable images. The default collector API still
checks every candidate. Unexamined entries are unverified, not declared missing;
in a bundle cached=true means an actual included resource. Correct face matching
and explicit unsupported flip-back behavior remain unchanged.

This matters for basic lands: the installed catalog has 961 Forest printings.
The first unbudgeted attempt scanned those and hit a 512-candidate preparation
limit. It published no manifest. The revised bound is 2048 candidates/card under
an unchanged 1 MiB manifest cap, with at most three included images per card.
It does not silently truncate metadata or fabricate a missing image.

## Pixel and metadata boundary

`export_visual_fixture` creates a new directory only. It never overwrites an
existing bundle or source image. It decodes/scales on the separate preparation
process/asset worker and writes raw RGBA8 bytes with bottom-left row origin.
Dimensions never exceed 1024; default longest edge is 896 without upscaling.
Texture creation/upload must later happen through Unity's permitted main-thread
APIs, but Unity need not decode JPEG/PNG or query a database on the render thread.

Asset IDs hash dimensions plus raw bytes. Manifest descriptors contain a relative
hash filename, width/height, exact byte length, raw SHA-256, pixel format and row
origin. Identical resources are shared. The destination contains no absolute
source paths, credentials, decks, player ownership or hidden session state.

The bundle is explicitly fixture_only=true. Card display fields are labelled
values_source=printed_reference_mock and contain only supplied printed-reference
name, mana cost, type, rules and P/T. They are not authoritative current game
characteristics. Never use this bundle to fill unknown live engine fields or
feed it into gameplay snapshot routing.

Preparation is bounded to 16 cards, three images/card, 2048 candidates/card,
64 MiB raw assets and 1 MiB JSON. Budget failure leaves no loadable manifest;
manifest publication is last. Partial directories are diagnostic artifacts,
not valid inputs. The future Unity loader must require the fixture marker and
validate dimensions, filenames, byte lengths and hashes off the render thread,
then share textures and clear owned resources when finished.

## Repeat locally

From the repository root, choose a fresh directory:

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/prepare_play_artwork_fixture.py --output Mtg_Projects/mtg_play_unity/Artifacts/CardFixture-new
```

Optional repeated `--name` arguments choose other public catalog cards. Output
is restricted to a new directory under ignored Unity Artifacts. The operation
never downloads. Missing local artwork remains explicit; an entirely image-less
bundle fails instead of publishing generic/fabricated art. These assets are
local diagnostics, not source-controlled redistribution or installer content.
The roadmap's distribution/licensing review is still pending.

## Actual evidence — October 30, 2026

The bounded local preparation completed in about two seconds using only installed
cache data: seven public cards, 21 authentic resources, 48,219,136 raw bytes
(about 46 MiB), and a 425,187-byte manifest. All seven cards have included authentic
art and cached standard-compatible alternatives. A raw resource was reconstructed
for local visual inspection; the Grizzly Bears printing was upright and authentic.
This is pixel-format/source evidence, not a Unity screenshot or GPU benchmark.

The successful ignored bundle is
`Mtg_Projects/mtg_play_unity/Artifacts/CardFixture-20261030-bounded/manifest.json`.
The initial partial `CardFixture-20261030` directory has no manifest and must not
be loaded. No source images or generated binaries are committed.

Twenty-seven focused tests passed for catalog and fixture preparation, covering
source preservation, selected/standard identities, correct face, shared pixels,
row origin/checksum, scale bounds, budget failure, missing art, no overwrite and
opt-in preparation limits. Lint passed. No full suite or new Unity build ran in
this increment. CI evidence is pending and follows the third-commit cadence;
Qt CI remains outside this work at owner direction.

Next: connect this validated raw bundle to a worker-loaded, bounded/shared Unity
texture owner; produce the packaged real-artwork renderer fixture; then capture
20/70/200-object interactions and actual timings/memory/startup evidence. G0,
P0.3, P3.2/P3.2a and the LTS/licensed-CI/distribution decisions remain open.

## Unity worker loader — October 30, 2026

`ArtworkFixture.LoadAsync` now reads the bundle on a task worker, with cancellation,
strict JSON parsing, exact field/type checks and the exporter's manifest/card/asset
budgets. It rejects linked directories/files, non-hash resource filenames, invalid
pixel format/origin/dimensions, mismatched byte lengths, raw SHA-256 and
content/dimension asset IDs. Candidate Oracle/face identities and cache references
must agree. No Unity APIs, database access or image decoding run in the loader.

The immutable result resolves display printings with `VisualPrintingPolicy`, keeps
selected printing identities, labels every display value PRINTED MOCK and shares
asset objects. Pixel access returns a defensive copy. This is an explicitly public
fixture API; it is not a live-session asset cache or private seat handoff mechanism.
The shared strict JSON parser was factored internally without changing wire error
codes or envelope validation.

Focused EditMode checks cover selection preservation, pixel ownership, invalid
fixture markers, resource paths, dimensions, checksums, identities, faces and cache
references. An optional local diagnostic also loads the actual seven-card bundle;
CI skips that diagnostic when its uncommitted artwork is absent. Texture creation,
GPU ownership/disposal, visible scene integration and benchmarks remain pending.

Local validation: 66 focused Unity EditMode checks passed, including the actual
seven-card/48,219,136-byte bundle, plus the Java protocol preflight. No full
application suite ran. CI review remains scheduled for the next (third) commit.

## Packaged real-artwork scene — October 30, 2026

`FixtureTextures` shares uploads by immutable asset reference, bounds RGBA pixel
allocation to 64 MiB, disables mipmaps, discards Unity's readable CPU copy, rejects
cross-thread access and destroys only its owned textures. Views are cleared before
the owner is disposed. This public diagnostic owner is not a private game cache.

The existing foundation player accepts `-manaforgeArtworkFixture <bundle>` to
replace its placeholder view with `ArtworkFixtureScene`. Without that argument the
original foundation smoke remains available. The opt-in scene exposes 20/70/200
object buttons, compact artwork cards, full inspection and hover/click callbacks.
It explicitly labels printed mock characteristics and has no gameplay commands.
The fixed diagnostic grid is not the intended final seat/table layout. It does
not demonstrate tapping, target animation, an Arena-quality playmat or live play.

Repeat the packaged capture after building:

```powershell
./tools/unity-play.ps1 -Mode Build
./tools/unity-play.ps1 -Mode ArtworkSmoke -FixtureDirectory Mtg_Projects/mtg_play_unity/Artifacts/CardFixture-20261030-bounded -FixtureCount 20
```

Repeat the last command with 70 or 200. The script bounds the owned process,
removes only prior known outputs, and validates the fixture report and screenshot.
UI Toolkit renders to a panel RenderTexture for capture; camera capture alone
would omit these cards. Outputs stay in ignored `Artifacts/ArtworkScene`.
For hands-on inspection, launch `Builds/Windows/ManaforgePlay.exe` with the fixture
argument and omit `-manaforgeArtworkOutput` so it remains open. Keep the entire
Windows build folder together. No artwork is copied into source or installers.

Actual local packaged screenshots at all three counts were visually inspected:
upright authentic artwork, cropped compact cards and full inspection are visible.
All counts use seven textures, 16,074,240 RGBA bytes (~15.3 MiB), on the AMD Radeon
RX 6600 under Unity 6000.6.7f1. This is raw pixel allocation, not measured total
GPU/process memory. The 200-card grid intentionally requires inspection to read
small cards. Pointer interactions still need hands-on owner acceptance.

Sixty-seven focused EditMode checks and three PlayMode checks passed; the Windows
player built successfully. The new texture check covers shared upload, budget
rejection, released CPU copy and destruction. No full application suite ran.
Frame timing, input latency, startup, memory profiling, integrated-GPU evidence,
licensed CI, approved LTS and licensing/distribution acceptance remain open.

Third-commit CI snapshot: protocol run for `498dbf9` passed
(https://github.com/RyMeep128/Manaforge/actions/runs/41101096687).
The `daac5b7` run was still in progress
(https://github.com/RyMeep128/Manaforge/actions/runs/41104134788); deferred to the
next scheduled check without waiting. No new licensed Unity CI evidence exists.
Qt CI was not investigated.

# Manaforge Play Unity foundation

Current scope: P0 feasibility, P1 protocol/dummy-exchange checks and P3 rendering foundations. Gameplay and multiplayer
are future design targets, not implementation scope for this increment. **Fixture rendering only**, without a game engine,
deck import, card artwork, gameplay actions or AI integration. First playable
target is one human versus XMage AI; design for up to five players. The shared
protocol must not hardcode a five-seat maximum. Existing Qt/Python remains intact.

## Pinned toolchain

- Installed/editor pin: `6000.6.7f1`, revision `b22767f04f04`.
- URP `17.6.0`; test framework `1.8.0`. Track manifest and resolved package lock.
- Official Newtonsoft JSON package `3.2.2` supports generated fixture DTOs. See
  the [protocol guide](../mtg_play/protocol/README.md); these do not connect the scene to gameplay.
- Windows x64 development player, Mono, .NET Standard, text serialization and
  visible tracked `.meta` files. No XMage, Python or database calls in Unity.
- Project starts from the editor's official blank URP template. `FoundationBuild`
  creates a deterministic saved scene, shared fixture material and build settings.
- **LTS decision remains open:** the installed 6.6 editor is a current/update
  release, not LTS. Use it for this reversible feasibility spike; do not claim
  the roadmap's approved LTS selection is complete.

## Reproduce on the licensed Windows host

Close this project in interactive Unity before running batch commands. Other
Unity projects can remain open. From the repository root in PowerShell 7:

```powershell
./tools/unity-play.ps1 -Mode Prepare
./tools/unity-play.ps1 -Mode EditMode
./tools/unity-play.ps1 -Mode PlayMode
./tools/unity-play.ps1 -Mode Build
./tools/unity-play.ps1 -Mode Smoke
```

Override `MANAFORGE_UNITY_EDITOR` or pass `-EditorPath` for a different installation
path of the exact pinned editor. The script rejects mismatched versions, nonzero
exits, missing/failed test results, empty test runs and stale smoke evidence. It
times out and terminates only its owned process tree. Generated logs, tests,
screenshots and binaries stay in ignored `Artifacts/` and `Builds/`.

The player is `Builds/Windows/ManaforgePlay.exe`; keep its full containing directory.
Running it without smoke arguments leaves a fixture window open for manual review.
Smoke mode renders 20 placeholder quads in URP at 1280×720, captures a camera render-target PNG (without the OnGUI labels) and
records device/version/count/resolution. It must use a graphics device, not
`-nographics`. This is neither an artwork benchmark nor an Arena-quality UX claim.

## CI and licensing

`Unity Play feasibility` is a manual-only workflow on an owner-controlled Windows
runner labelled `manaforge-unity`. The host needs PowerShell 7, the pinned editor,
Windows build support, an independently valid license and a usable graphics
session. Do not assume a license activated for one interactive account works for
a service account. A logged-in desktop runner may be necessary for screenshot
capture; establish this before claiming CI viability.

No Unity serial, password, activation file or account token is stored in the repo,
workflow or uploaded artifacts. This workflow does not activate or return licenses.
Use Unity's supported activation for the actual runner account; installation on
the owner's desktop does not prove CI licensing. Do not schedule untrusted PR
code on this persistent host. Registration and a successful workflow run remain
required before P0.2 is complete. Logs remain local because licensing/runtime logs
can contain host/account information; CI uploads synthetic screenshots, reports,
source revision and player output only.

## Local evidence — October 30, 2026

On the owner-licensed host: Prepare/import and Windows build exited 0; six focused
EditMode tests and one PlayMode scene test passed. The packaged smoke passed on
AMD Radeon RX 6600 at 1280×720 with 20 fixture cards and 102,340 colored card
pixels. The camera PNG was visually inspected. Reports are in ignored Artifacts;
these are local results, not CI evidence or integrated-GPU benchmarks.

No Unity-specific connector was exposed in this session. Automation uses the
official installed editor command-line interface and Unity Test Framework.

The protocol-consumer increment passed eight EditMode tests: six layout checks
plus two checks covering 14 positive and 12 negative shared fixtures.

## Remaining acceptance

G0 remains open: approved LTS choice, executed CI/license evidence, real-artwork
20/70/200-object interactions, packaged timing/memory/integrated-GPU measurements
and distribution review. G1/shared protocol and human-versus-AI integration also
remain open. No installer or installed Play gate changes are made here.

Owner checks: launch the whole player folder, verify two rows of cards and readable
labels, resize the window and close it. This does not exercise real gameplay.

References: [roadmap](../../docs/play-unity-java-roadmap.md),
[editor release](https://unity.com/releases/editor/whats-new/6000.6.7f1),
[official command-line reference](https://docs.unity.com/en-us/engine/6000.6/manual/unity-editor/command-line-arguments/editor).

## Offline visual printing policy — foundation increment

`VisualPrintingPolicy` is a pure presentation helper for P3.2/P3.2a, not a
renderer or asset loader. It preserves selected printing identity and chooses
cached standard-compatible artwork before authentic image fallbacks. Ties use
ordinal printing IDs, independent of catalog ordering. It never writes decks,
preferences or caches. Missing artwork remains explicit; concealed input returns
no identity and does not enumerate candidates.

The future trusted asset boundary must supply viewer-permitted candidates from
Core `get_prints(oracle_id, allow_remote=False)` and verified exact-face local
assets (`get_image_path`, with the appropriate variant). `Cached` means a usable,
verified asset, not just an image URL or database row. `FaceKey` means equivalent
card-face identity across printings, not merely a numeric face index. Do not infer
compatibility from matching indices. Profile classification must explicitly
exclude unsupported treatments. The host-side collector described below supplies conservative classification;
Unity delivery and the live bridge remain pending. Never feed the private all-decks launch manifest to Unity.

The existing Qt cache remains unchanged. Core's `ensure_face_image` can fall back
to the front image for some layouts; a future bridge must verify the actual face
before marking that result usable. Downloads, resolution caching, invalidation,
texture reuse, dynamic components and compact/full rendering remain pending.
This offline helper does not implement the roadmap's complete online fallback
sequence. Retry policy selection when verified cache availability changes.

Local validation: 16 EditMode tests passed (8 existing and 8 printing-policy
checks). CI evidence and all rendering/benchmark gates remain pending. There is
no new visual screenshot or packaged-player behavior in this increment.

### Host-side local catalog collector

`mtg_play.visual_catalog.collect_visual_candidates` supplies immutable internal
host metadata using existing Core catalog/image APIs only. It requests no remote
catalog refresh or downloads and does not change saved printings. Call it on an
asset worker during fixture preparation or one-time launch asset preparation,
not in the gameplay action loop. No app launch integration is installed yet.

Its initial `standard_compatible` profile requires normal layout, 2015 frame,
black/white border, explicitly false full-art/textless/promo flags, no frame
effects and no multiple faces. Unknown/special metadata stays authentic-image
only; broader frame support needs separate profile evidence. Equivalent faces
match exact names within the same Oracle identity. Ambiguous selected faces fail
explicitly. Exact image variants are decoded to reject corrupt files. Flip backs
remain unavailable here until rotation metadata is supported.

The collector returns selected-first candidates, then ordinal printing IDs,
including missing-asset candidates. Its local paths are **host-internal** and must
not be serialized to Unity. Cache flags are observations and can become stale.
There is no second database, downloader or persistent resolution cache. The next
bridge must pass approved asset handles and candidate metadata to Unity's policy,
verify viewer ownership and clear assets on viewer handoff. No shared wire schema
for that transfer exists yet; these Python records are not public protocol DTOs.
Eighteen focused collector tests passed locally; Unity delivery, real artwork
demo, screenshots, dynamic rendering and CI evidence remain pending.

## Reusable UI Toolkit card component

`CardView` is a seat/zone-independent presentation component. Its immutable
`CardDisplayValues` input contains explicitly supplied name, mana string, type,
rules text, P/T and status text; null stays unavailable. It does not parse rules,
compute characteristics or read the catalog. Existing protocol DTOs are unchanged:
this projection is not permission to fill unsupported fields from printed text.
The gateway still needs authoritative mana/current-text support before live use.

`Bind` accepts a resolved visual identity, a borrowed texture and normalized
artwork crop from a verified layout profile. Full standard mode places components
around that artwork crop; compact mode hides mana/type/rules and retains artwork,
name/stats/status. Authentic-image-only full mode shows the whole supplied image
without claiming reconstructed dynamic text. Text values update independently
without replacing component objects or artwork. Mana symbols currently remain
literal strings; symbol glyph rendering, frame colors, set symbols, overlays,
long-text fitting and advanced layouts are still pending.

`SetPresentation(mode, width)` resizes the two layouts and reuses textures.
`Conceal` clears identity, image reference, all label text and tooltip; `Dispose`
also detaches the view. The external asset owner must separately revoke/destroy
private cached textures during viewer changes. This view cannot establish seat
authorization, authenticate artwork handles or prevent a caller binding the wrong
texture. Those checks belong to the still-pending trusted asset boundary.

In Unity, open **Window → Manaforge → Card component fixture** to see explicitly
mock full/compact components and toggle supplied P/T/rules. Artwork is honestly
marked unavailable; no real card art or assembled-card visual acceptance is
claimed. This editor fixture is separate from the packaged 20-quad smoke scene.
It supplies no game interactions. Reusable interfaces for later P3.3 work are
`Bind`, `UpdateValues`, `SetPresentation`, `Conceal` and `Dispose`.

Local validation: 24 EditMode tests passed, including eight card-component checks
for updates, shared artwork, modes/resizing, missing assets, concealment and
cleanup; the existing PlayMode foundation scene check also passed. Reports remain
in ignored `Artifacts/`. These tests do not prove rendered text readability or
privacy of the future cache. No new screenshot/benchmark/player evidence exists.
Real-artwork delivery, reusable verified layout profiles, visual review and CI
remain required; P3.2a and G0/G1 are open.

### Attached-panel runtime checks

`CardPanelTests` now attaches `CardView` to a runtime `UIDocument` using the shared
`Resources/CardTheme.tss` import of Unity's default runtime theme. Future runtime
panels must also assign an appropriate theme; the editor window supplies its own
editor context. Tests check resolved full/compact geometry (including pixel
rounding), dynamic updates without texture replacement, an empty handoff frame,
clean rebinding and disposal from the panel. These use a synthetic tiny texture,
not real Magic artwork. The fixture owns and destroys its panel/settings/texture;
the view owns none of those shared resources.

Local validation: three PlayMode tests passed (two attached-panel scenarios and
the existing foundation scene). The launcher now requires at least 24 EditMode
and three PlayMode results, so losing the new test assemblies cannot silently
pass the former eight/one baseline. Headless layout checks do not validate actual
GPU pixels, font readability or the future private texture-cache lifecycle.

Scheduled CI snapshot: Tests for `547e30b`, `84fa6d5`, `712cef8` and the earlier
Qt teardown fix `7501539` were still running. No waits or success claims; defer
unfinished runs to the next scheduled check. The manual licensed Unity workflow
has not supplied CI evidence for these components.

## Java↔Unity dummy transport milestone

EditMode now prepares a test-only Java peer and runs three owned process scenarios:
mutually authenticated fixture exchange, wrong viewer key with no session data,
and owner EOF stopping the listener. The happy path receives a mock snapshot,
compares opaque action/decision tokens, rejects stale/pending submissions,
receives submitted (not confirmed), a fixture-only result and clean shutdown.
See the [exchange guide](../mtg_play/protocol/dummy-exchange.md) for exact scope.

`EditMode` now requires Python and JDK java/javac on PATH. It verifies the existing
pinned Gson dependency; add `-DownloadGson` only when explicitly allowing the
existing pinned Maven download. The licensed workflow installs the same JDK pin
as hosted protocol CI. No runtime key, bootstrap or proof is written to disk or
uploaded. Local results: 40 EditMode tests and four schema checks passed; CI is
pending. The packaged scene still has no real Java connection or gameplay.


The receive-boundary follow-up validates nested snapshot/event/result DTO shape,
explicit concealment fields and authenticated session/viewer/revision context
before deserialization in the dummy exchange. Fixture mode must be explicitly
allowed and is refused by default in production contexts. Generated schema data
comes from the original contracts, not another game-state model. Forty-two
EditMode checks and five focused schema checks pass locally; licensed CI,
immutable scene projection and real gateway visibility remain pending. See the
[receive guide](../mtg_play/protocol/receive-boundary.md).


`CommandTracker` now preserves pending/uncertain commands and validates correlated
ACKs in the dummy client. Neither a submitted receipt nor a terminal fixture
snapshot confirms a command; disconnect blocks replay. Eleven new focused checks
bring EditMode to 53 passing local tests. See [tracking scope and capacity limits](../mtg_play/protocol/command-tracking.md).
No actual gameplay, UI change or licensed CI evidence is added.


The wire parser now accepts all six existing choice-family shapes alongside
perform, preserving engine option/source IDs and signed numeric values. The
tracker uses the same uncertain/pending lifecycle for choices. This is contract
coverage only: the dummy exchange remains perform-only, no choice UI or real
engine dispatch is added. Fifty-six local EditMode and six schema checks pass;
see [choice contract scope](../mtg_play/protocol/choice-commands.md).


The Java dummy now retains per-viewer submission receipts. Identical retries
return the existing ACK without another fixture result; changed request contents
under the same ID close the connection. Fifty-seven local EditMode checks pass,
including four real Java-process scenarios. This remains protocol-only evidence;
see the [submission ledger limits](../mtg_play/protocol/submission-ledger.md).

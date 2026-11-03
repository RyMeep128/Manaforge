# Packaged renderer measurements — G0/P0.3 partial evidence

Status: repeatable local diagnostic implemented; G0 remains open. Source version
0.5.55-alpha.1, October 30, 2026. No live engine, private cards or saved decks.

## Method and limits

`ArtworkSmoke -Benchmark` runs a Windows development player with the prepared
seven-card public fixture at 1280×720. It waits 60 warm-up frames, temporarily
disables vsync/frame limiting, repaints a panel RenderTexture and samples at least
five seconds/240 end-of-frame intervals (hard cap 100,000). Every 60 samples it
sends an explicitly targeted pointer event, toggles a mock tap and starts a mock
target line. This is deliberately heavy scripted interaction, not human pacing.
The normal interactive fixture retains its 60 fps cap.

The wall-clock intervals include Unity loop scheduling and script/diagnostic work.
**Do not convert these offscreen loop intervals into displayed FPS, GPU throughput
or input-to-photon latency.** Hidden-window rendering may run without a presented
swapchain frame. FrameTimingManager CPU/GPU counters are collected independently
with frame-timing statistics enabled, deduplicated by frame-start timestamp.
The current Direct3D 12 run returned CPU samples but **no GPU samples**. The
report's gpuTimingAvailable=false and gpuFrames.sampleCount=0 mean unavailable;
JsonUtility's zero-filled absent result object does not mean zero GPU cost.

The owner PowerShell process samples only its child every 50 ms from launch to
exit. Peak working set and private bytes include startup, validation, screenshot
readback and JSON encoding, not just the steady measurement window. They are
sampled maxima, not a guarantee of the OS lifetime high-water mark. Unity native
allocated/reserved and managed-heap counters are also captured before screenshot
readback; they are separate measurements and must not be added to process memory.
Total GPU/driver allocation is not measured. Mono's in-player process memory
counters returned zero during setup, so they are not used.

Process-to-ready is measured from OS process start until the verified fixture has
loaded/uploaded and yielded two panel frames. Setup/load and upload-with-frame-yield
phases are recorded separately. These are warm machine/cache observations; they
are not controlled cold-boot startup or display-visible latency measurements.
Raw pixel sharing remains seven textures / 16,074,240 RGBA bytes at every count.

## Actual local evidence

Unity 6000.6.7f1, URP, Windows development player, Direct3D 12 [level 12.2],
AMD Radeon RX 6600, Ryzen 5 7600X, 31,879 MiB system memory, quality index 0.
Sequential captures were made at approximately 18:21 UTC on October 30, 2026.
Other application/OS load was not controlled. Each run completed five seconds
and hundreds of scripted selections/taps/targets without logged exceptions.

| Objects | Loop samples | Loop p95 ms | Loop p99 ms | Process→ready s | Peak working set MiB | Peak private MiB |
|---|---:|---:|---:|---:|---:|---:|
| 20 | 31,693 | 0.205 | 0.596 | 4.38 | 567.7 | 1015.3 |
| 70 | 23,563 | 0.236 | 0.700 | 4.23 | 574.7 | 1001.2 |
| 200 | 14,148 | 0.392 | 1.561 | 4.24 | 572.1 | 1003.2 |

All three screenshots were visually inspected: authentic artwork is upright,
compact cards and full inspection are visible, and the final cyan line and tapped
cards are present. The stress grid can overlap rotated cards and cannot provide
readable card text at 200 objects without inspection. It is a diagnostic layout,
not accepted gameplay UX. A PlayMode check drives selection through the actual
pointer callback, verifies inspection/tap/target state, and confirms disposal
unregisters callbacks. Statistics checks verify nearest-rank percentiles and reject
empty, nonpositive and nonfinite samples. No full application suite is run.

## Reproduce and review

```powershell
./tools/unity-play.ps1 -Mode Build
./tools/unity-play.ps1 -Mode ArtworkSmoke -FixtureDirectory Mtg_Projects/mtg_play_unity/Artifacts/CardFixture-20261030-bounded -FixtureCount 20 -Benchmark -TimeoutSeconds 60
```

Repeat with 70 and 200. The artwork bundle must already exist; see
[preparation and the manual fixture](play-artwork-fixtures.md). Outputs are ignored:
`Artifacts/ArtworkBenchmark/artwork-{20,70,200}.json`, corresponding PNGs, and
`process-{20,70,200}.json`. Player JSON retains bounded raw loop/CPU/GPU sample
arrays and hardware/build metadata. Console output omits those arrays. The script
rejects missing artifacts, incomplete samples, missing gestures, zero external
process memory and logged player exceptions. Prior known outputs are removed so
stale artifacts cannot pass a fresh invocation.

For manual review, launch the player with `-manaforgeArtworkFixture <absolute bundle
path>` and omit output/benchmark arguments. Hover cards, click one, use Mock tap /
untap and Mock target next, then switch object counts. Inspect text/artwork and
confirm selection/rotation/target state clears when the grid is replaced. These
controls are presentation-only and make no legality claims.

## Remaining acceptance

Visible presented-frame GPU timings and physical input latency are still required,
as are integrated-GPU/low-end evidence, real playmat treatment, adaptive seat layouts,
controlled startup/memory profiling and owner UX review. Licensed CI, approved LTS
and distribution review also remain open. This harness does not establish G0,
G1, Java parity, engine integration or a human-versus-AI match. CI review continues
on the owner's third-commit cadence; no Qt CI investigation is involved.

Local validation: 73 focused EditMode checks, four PlayMode checks, the Windows
build and all three packaged benchmark invocations passed. Java protocol preflight
also passed. This is local evidence; no new CI result is claimed for this increment.

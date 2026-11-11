# Named layout presets (CT-04)

The synthetic Layout workspace now supports explicit Save, Save As, Load, Rename,
Delete and Restore Default. Live Arena layout, gameplay input, networking and
PlayerPrefs display settings are unchanged. See [container primitives](play-container-layout.md)
and [the epic](customizable-tabletop-epic.md). The gated [CT-05A live editor](play-live-layout-editor.md) reuses this infrastructure.

## Use the fixture

Open the existing style-review scene and select **Layout workspace**. Move, resize,
dock or convert components, then use **Save As** with a unique name. **Save** updates
the selected user preset. Selecting another name does not apply it until **Load**.
**Rename** uses the Name field; **Delete** confirms before removing the selected
saved entry and keeps the current workspace in memory. Deleting its saved preset
marks the current workspace unsaved. Load and Restore Default require confirmation
before discarding unsaved layout edits. Field values inside fixture components are
not part of layout presets.

There is no autosave. Committed geometry, mode and expansion changes mark the layout
dirty; previews and viewport resizing do not write files. **Restore Default** changes
only the workspace in memory. To remember Default for the next startup, select
Default and explicitly Load it. Save and Load remember the selected preset. On
startup the last selection is restored, or built-in Default is used if missing or
unusable. Default is generated from registrations, cannot be renamed/deleted, and
requires no disk file. Storage conflicts can be resolved with **Refresh list**,
which refreshes metadata without replacing the current layout.

File operations show busy/error/recovery status and disable overlapping edits.
Unsupported-version files remain read-only; default layout and in-memory editing
remain available. Corrupt data may recover from backup; Save As preserves damaged
original files instead of silently erasing them. No credentials or private game
references enter the store or its UI diagnostics.

## Identity, snapshot and application contracts

GameplayHudDescriptor.PresetKey is optional. Only explicit stable authored keys
participate in capture; live drawers opt in only through their container adapters. The fixture
uses `fixture.panel`, `fixture.drawer`, `fixture.restricted`, and `fixture.host`.
Registration rejects duplicate persistent keys before mutation. Runtime component,
viewer, seat, session and card identifiers are never automatically captured.
Constraints/capabilities come from registrations, never serialized permissions.

HudLayoutPreset and HudComponentSnapshot expose immutable data. A snapshot stores a
normalized remembered floating rectangle, dock target as another authored key,
dock edge/order, panel/drawer mode and remembered drawer expansion. Shells expose
expansion preference even in panel mode. Unknown JSON fields and dormant component
entries survive round-trips, without narrowing dormant numeric values to Unity floats. Missing
registered components use their defaults. Unavailable components remain dormant.

LayoutPresetApplicator resolves keys, stages defaults/adjustments and prepares a
whole prospective layout. Unsupported operations/modes use the component default;
missing/incompatible docking targets float the component at its remembered rectangle
with an adjustment message. Cyclic graphs, duplicate keys and malformed geometry
reject. ContainerLayoutController.PreviewLayout validates the complete proposed
graph, so a valid reparent is not rejected due to intermediate old relationships.
TryApplyLayout changes all states with one notification. Gestures cancel before
application; drawer expansion restores after mode/geometry. Failed validation or
failed load metadata writes leave the current layout unchanged. No card views are
reparented or acquired by this layer.

## Storage and recovery

Normal scene use captures Application.persistentDataPath on the UI thread and
constructs JsonLayoutPresetStore at:

```text
profiles/default/layouts/fixture/presets.json
```

There is no profile selector or cloud sync. Programmatically constructed workspaces
and automated style captures default to MemoryLayoutPresetStore; tests can inject
a JsonLayoutPresetStore rooted in a temporary directory. Existing user profiles
are never touched by automated captures.

ILayoutPresetStore asynchronously reads/writes immutable LayoutPresetLibrary
snapshots with an expected revision. Library operations provide create/update,
rename, delete and explicit selection; generated preset IDs are independent of
names and filenames. The library limits are 64 presets, 256 components per preset,
and 1 MiB UTF-8 JSON. Names are trimmed, 1–64 UTF-16 characters, contain no control
characters, and are unique ignoring case; Default is reserved. Normalized geometry
must be finite, have positive dimensions and stay within an absolute 10000-unit
normalized budget. JSON reader depth is capped at 32; duplicate properties reject.

Schema version 1 has `version`, `lastSelectedId`, and a `presets` array. Each preset
has `id`, `name` and a `components` object keyed by authored IDs. Component fields:
`rect` (`x`, `y`, `width`, `height`), `mode`, `dockTarget`, `edge`, `order`, and
`drawerExpanded`. Unknown fields are retained at library, preset and component
levels. No historical preset format exists: other schema versions are protected,
not guessed or silently migrated. Version dispatch is the boundary for adding a
real migration when a second supported format exists.

Worker-side file I/O takes an exclusive `.lock` file with a two-second acquisition
budget. Revision tokens cover primary and backup contents; stale writes return a
conflict. Writes validate reader compatibility, flush a same-directory temporary
file and atomically replace the primary while retaining the last-good `.bak`.
The first write also establishes a backup. Failed writes clean their own temporary
file; prior valid data remains recoverable. Damaged primary/backup files are moved
to uniquely named `.recovery-<id>.json` files before repair. A newer-version primary
or backup blocks writes. File paths never derive from preset names or snapshot IDs.
A filesystem failure returns a structured status; no delete-then-write replacement
is used for a valid primary.

## Tests and acceptance

Hosted EditMode LayoutPresetStoreTests covers CRUD/restart, selection, name/size
limits, profile isolation, unknown fields, precision, injected interrupted writes,
cancellation, backups, corruption, unsupported versions, reader depth, locks and
concurrent/stale writers. Hosted PlayMode LayoutPresetIntegrationTests covers
atomic graph application, stable keys, fallback/dormancy, explicit-save dirty
tracking, confirmations, failed load, restart and drawer preferences, busy controls
and read-only behavior. Existing CT-01–03 and gameplay interaction regressions
remain required; the component-selector regression test now uses a stable element
name rather than assuming it is the first dropdown.

The existing style capture path additionally records saved-preset and unsaved-discard
confirmation screenshots at its four baseline sizes, using only the memory store.
Local suites are not run. Exact-SHA hosted evidence is pending; the earlier Unity
CI license-secret block remains unresolved. Local verification on 2026-11-10:

- `./tools/unity-play.ps1 -Mode Build` succeeded, including compilation of the new
  test assemblies; suites were not executed locally. Build evidence is in
  `Mtg_Projects/mtg_play_unity/Artifacts/build.log`.
- Synthetic saved-preset and discard-confirmation captures were generated under
  `Mtg_Projects/mtg_play_unity/Artifacts/LayoutPresetReview`. These were visually
  inspected at 1280x720, including busy/confirmation input isolation and readable
  controls. The synthetic memory-store Save As completed and no runtime exceptions
  were logged. This is not filesystem integration-test evidence.
- The strict capture script exited 1 at its resolution check: the 2560x1440
  request rendered at 2560x1366 on this desktop. The first three requested sizes
  matched. Images labelled 2560x1440 are not valid evidence for that resolution;
  full four-size capture acceptance remains pending a suitable hosted runner.
- Exact-SHA hosted suites, recovery/concurrency filesystem tests, and gameplay
  regression acceptance remain pending. No commit, push, version bump, branch,
  tag or release was made. The unrelated CI fixture repair remains untouched.

# Unity gameplay animation

The Arena presentation uses a shared visual-only coordinator. It reuses UI Toolkit
Painter2D (as used by battlefield links), existing card-back resources, typography,
and the draw-count confirmation logic. No external effects pack, new render
pipeline, sound assets, or third-party license is required.

## Pacing and appearance

Draws arc from library to hand in 0.8 seconds, with 100 ms staggering. Casts lift
toward the stack over one second. Battlefield arrivals take 0.9 seconds; tap and
untap rotations take 0.6 seconds. Attacks and blocks use short card lunges and
illuminated confirmed combat links. Damage uses orange impact rings and floating
numbers; stat increases use green energy and reductions use orange energy.
Departures fade and travel toward their confirmed destination over one second.
Turn changes show a 1.5-second banner; results receive a two-second rune reveal.
Warm ember trails, rotating rune rings, and restrained scale flourishes tie these
moments together. The permanent result label remains after its flourish ends.

Controls remain live throughout. Only automatic priority passing waits for major
moments, for at most two continuous seconds before normal offer validation resumes.
Required choices, manual passing, cancellation, inspection, and navigation do not
wait for animation completion.

## State, privacy, and limits

The receive mailbox records compact transition cues before snapshots coalesce.
Cues describe confirmed visible changes, never actions or a reconstructed game.
Visible cards carry a separate viewer-scoped `presentation_id`, retained only
while continuously visible. Artwork, inspection, and animation transitions follow
that identity; authenticated command references still rotate and are resolved from
the latest offer at interaction time. Concealment or disappearance retires the
presentation identity. Consumed animation batch revisions cannot be replayed.
An uncorrelated stack disappearance is labeled **Stack updated**, rather than
claiming a resolution or inventing a spell target. A battlefield disappearance
with no confirmed destination fades locally rather than claiming a death.
Concealed draws use card backs and observed counts only.

The coordinator borrows artwork only from the current viewer's admitted bindings.
Pending visibility or printing changes revoke an affected visual before the new
snapshot is rendered. Viewer changes and disposal clear all borrowed references.
On disconnect, gameplay effects stop; an authenticated text-only result can finish
after private artwork resources have been cleared.

Independent effects overlap; effects sharing a card serialize. There are at most
eight active effects, 64 procedural particles, and 32 pending groups. Each journal
group contains at most 64 cues. Overflow becomes a combined update pulse; queued
effects older than four seconds collapse instead of accumulating a long replay.

**Reduced motion** immediately removes travel, rotation, scaling, and particles,
replacing them with static rings and fades lasting at most 150 ms.

## Validation

EditMode coverage checks coalescing, duplicate revisions, draw counts, stat/damage
changes, extra turns, unknown stack departures, bounded overflow, and completion.
PlayMode coverage checks continuity across snapshots, live controls/inspection,
same-card ordering, the automation hold limit, pending visibility revocation,
reduced motion, particle limits, disposal, and result fanfare after viewer cleanup.

Run suites through GitHub Actions only. Unity visual evidence should include draws,
casting/arrivals, combat, damage/stat changes, turn banners, and results in both
motion modes. Compilation alone does not establish visual or playable acceptance;
report exact-SHA CI and human-versus-AI acceptance results separately.

The existing `tools/capture_play_style.ps1` capture step now requires 80 animation
images: ten scenarios in full/reduced motion at four resolutions, with an
`animation-proof.json` manifest. The Unity workflow uploads these alongside the
existing style evidence. These synthetic captures do not replace live acceptance.

## Retained session logs

Unity sessions keep `player.log` and a small `diagnostic.json` report under the
application data directory at `mtg_core/logs/unity-sessions/session-*`. On a
default Windows installation this is
`%LOCALAPPDATA%/PrintProxyPrep/mtg_core/logs/unity-sessions`.
The newest 20 sessions are retained; each player log keeps at most its final
4 MiB. This includes failed sessions with no close report. Private launch
manifests, authentication bootstraps, artwork, and decks remain temporary and are
removed during normal cleanup. Failed-session archive paths appear in the shared
diagnostic log. Restart the desktop launcher after a source update to load this
Python logging behavior, and rebuild the Unity player after runtime/protocol changes.

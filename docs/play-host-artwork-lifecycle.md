# Authenticated host artwork-sidecar lifetime

Status: host integration at 0.5.99-alpha.1. The packaged session fixture's UI review
is still pending and its visible layout remains unchanged. This increment does
not enable real-engine Play or close G0/G1.

ViewerSessionHost now opens the optional CoreArtworkBundle declared by its owned
private bootstrap. Connection and peer authentication finish first. The supplied
manifest digest, session and viewer must then validate before receiving/rendering
session snapshots. Invalid sidecar metadata fails closed with VIEWER_ARTWORK_FAILED.
Authentication failure never opens the artwork sidecar. No sidecar retains the
existing explicit unavailable-artwork behavior.

The launcher must still export only viewer-permitted printing IDs. A manifest pin
proves integrity/context agreement, not permission to include another seat's deck
membership. The host neither exports decks nor derives artwork from hidden
objects, names, transforms or unrestricted engine state.

Index loading and raw-pixel reads run on workers. The UI Tick installs exactly
one bounded artwork coordinator for the epoch, then uses the existing presentation
pump for admission/uploads. Provider requests remain tied to current opaque object
ID, exact Oracle/printing identity, revision and explicitly face-up visibility.
Only the existing normal, standard-compatible single-face contract is supported.
There are no fallback printing substitutions or printed-rule replacements.

Individual missing/unsupported entries and failed/corrupted raw-pixel reads stay
visually unavailable; they do not invent an image or game outcome. Entire manifest
integrity/context failure prevents session mounting. Current rules and mana fields
remain unavailable where the engine contract does not provide them. No Java rules,
Python action loop or second persistent card/deck database is introduced.

Stop revokes the mailbox and cancels artwork jobs without waiting on the UI thread.
Host Completion now waits for its artwork workers/cancellation callbacks as well
as receive retirement, then disposes the sidecar index, channel and bootstrap.
The parent may delete its verified owned sidecar workspace only after that
completion and its own cleanup requirements. The host never deletes source files.
Private GPU textures still clear through UI Tick/Dispose and Unity's deferred
destruction; Completion is not proof of GPU destruction or OS process containment.
Cancellation remains cooperative around regular file reads; no hard OS I/O deadline
or global retired-provider resource bound is claimed.

A Tick also notices that its captured mailbox was externally retired, cancels that
old host and avoids attempting an artwork mount on a replacement epoch. Existing
UI-thread and per-update budgets remain enforced before mutating state. A newer
viewer has an independent GPU cache even for identical source bytes.

Focused local evidence: 56 graphics-enabled PlayMode checks passed with zero skips.
New real-loopback/panel cases cover authenticated loading into a private texture,
owner-loss cleanup and exclusive file reopening after worker retirement, manifest
pin/viewer mismatch, corrupt raw pixels, hidden and face-down objects, replacement
texture/cache isolation, and authentication failure preceding sidecar access.
Existing GPU-copy, protocol, receipt and lifecycle checks remain active. Synthetic
raw pixels/metadata are used; this is not real-deck or specialized-card acceptance.
No full application suite ran.

The session fixture intentionally still rejects artwork-bearing bootstraps and
shows placeholders, preserving the current owner-review target. Its pending UI
review is not inferred from a request to continue implementation. Production
launcher/scene artwork wiring and specialized face contracts remain separate work.
Relevant CI is checked at this third-commit checkpoint without waiting for runs.

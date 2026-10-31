# Authorized single-face artwork binding

Status: tested asset boundary for the viewer surface. The production Core cache
provider, bounded job/completion mailbox and session-scene mounting remain open.
This is not a new card database, persistent deck format, wire schema or XMage
adapter. It extends the [viewer surface owner](play-viewer-surface.md).

## Permission and identity

`RequestArtwork(ticket, objectId)` issues an immutable request only for an applied,
current viewer epoch/revision, a visible object with explicitly false face-down
state, and known physical printing/Oracle IDs. No identity request is issued for
concealed objects, unknown face-down state or missing printing data. Repeated
requests for the same pending object/revision share one token. New snapshots,
watermarks and viewer changes retire pending requests. Already bound single-face
images can survive a same-incarnation update only while visibility, known face-up
state and physical printing/Oracle identity still match. Current display name is
never an artwork lookup key.

The trusted existing Core catalog must provide a `CatalogArtworkFace` describing
the exact requested printing and Oracle identity, one face, its explicit face key,
normal layout, compatible standard-frame classification and printed type line.
`PreparedCardArtwork.Prepare` rejects incompatible identities, ambiguous layouts,
multiple faces and unsupported frames. Metadata is trusted host asset input, not
an authentication proof or permission to fabricate catalog records. A verified
one-face printing does not need a guessed back-face mapping. General DFC/modal,
flip-card, compound and cosmetic-frame resolution remains unavailable. The
existing public printing gallery retains its broader fixture-only profiles.

Physical printing identity remains independent of current copied name, type,
P/T, counters and other engine characteristics. Prepared artwork carries no
printed rules or mana cost into current game state. Current rules stay unavailable
instead of promoting engine presentation text or substituting printed Oracle text.
The live projection requests a printed-stat mask even when current P/T is unknown,
so a baked printing badge cannot silently become authoritative current stats.
Presentation mode follows the engine-provided zone: compact on battlefield, full
elsewhere; instant/sorcery metadata does not create a fixture battlefield example.

## Workers, buffers and private graphics ownership

The host uses Core's existing asset mapping and decoder on a worker. Preparation
accepts decoded RGBA8 with bottom-left rows, bounds dimensions to 1024 per edge and
validates byte length. It copies/hashes the input without graphics, file IO,
network access or a new decoder. The producer retains ownership of its input
buffer and must manage/clear private input copies itself.

`ViewerArtworkScope` is created on the Unity UI thread and transferred to one
successful BeginViewer epoch. A claimed or disposed scope cannot be reused by
another surface or even the same viewer's next epoch. It creates its own textures;
it cannot accept or destroy borrowed public textures. Only raw GPU upload occurs
on the UI thread; the temporary upload buffer is cleared and Unity's readable
CPU texture copy is discarded. The private cache deduplicates by pixel digest and
dimensions, has a 64 MiB maximum configurable budget and at most 256 textures.
Budget refusal leaves the surface usable with artwork unavailable, without an
unrelated substitute. This is a memory bound, not performance acceptance.

`TryApplyArtwork` checks the current ticket, exact pending request object, applied
revision and watermark before upload. An admitted UI-thread call always consumes
and clears the prepared owned pixel buffer, including stale/rejected completions.
An off-thread/closed-owner exception occurs before ownership transfers; the
producer still must dispose that completion. Each pending token is one-shot.
Inspection and normal views borrow the same admitted texture. Their current text
continues to come from the snapshot. Concealment/removal clears bindings; known
pixel cache entries may remain within that viewer's private scope until bounded
scope eviction/teardown, without an object-to-hidden-card association.

Viewer switches clear views, inspection, bindings and pending requests before
scope disposal requests texture destruction. The existing empty-frame barrier
precedes the next viewer. The host must still cancel old jobs, dispose discarded
completion buffers, and clear every other viewer-dependent surface. These helpers
are not a production worker pump, global authorization layer or process owner.
No Python per-action gameplay relay was introduced.

## Validation

Local evidence at 0.5.86-alpha.1: 315 EditMode checks and 19 graphics-enabled
PlayMode checks passed, including existing Java protocol preflight. The PlayMode
run used the AMD Radeon RX 6600 with Direct3D and had zero skipped checks. A real
GPU readback verifies red pixels remain red after the producer reuses its input
buffer for blue pixels. Other checks cover identity/layout rejection, unknown and
concealed faces, one-shot and stale completions, epoch isolation, scope reuse,
private texture destruction, shared inspection textures, budget refusal and
within-viewer deduplication. Normal source-face art survives a current-name change.

Run `./tools/unity-play.ps1 -Mode PlayMode -Graphics` for this evidence. The default
headless run explicitly skips the GPU-readback check and is not GPU evidence;
-Graphics rejects any skipped check. Existing lifecycle assertions remain active
in both modes. No full application suite ran. The public scene is unchanged and
no new UX/real-engine acceptance is claimed. CI review remains every third commit,
with the next checkpoint after 0.5.87; licensed Unity CI and G0/G1 remain open.

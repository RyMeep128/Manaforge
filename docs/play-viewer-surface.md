# Viewer card surface ownership

Status: tested UI-owner foundation; not mounted in the public artwork scene or a
live match. Parent: [Unity/Java roadmap](play-unity-java-roadmap.md).

`ViewerCardSurface` accepts the immutable [viewer card projection](../Mtg_Projects/mtg_play/protocol/viewer-card-projection.md)
and updates the existing composable CardView components. It is owned by its
creating thread; construct it on the Unity UI thread. Worker code may retain an immutable ticket and projected
frame, but cannot call its UI-mutating methods. The caller supplies a parent;
the surface creates/removes only its own cards container and inspection view.

## Epoch and revision rules

`BeginViewer(session, viewer, ownedPrivateAssets, minimumRevision)` clears old
cards, text, inspection, tooltips and projection references before disposing an
explicitly transferred private resource scope. Ownership transfers only on a
successful return; shared/public caches must never be passed as private assets.
Every successful Begin returns a fresh, opaque ticket, even for the same session
and viewer. New cards cannot appear until two Unity frame counts later, leaving
one complete empty frame for deferred texture destruction and animation revocation.

`TryPresent(ticket, frame)` rejects retired tickets, mismatched session/viewer,
frames below the receive owner's minimum revision, and duplicate/older applied
snapshots. `SetMinimumRevision` lets trusted newer events raise the admission
watermark before the next coherent snapshot. It does not make events into
snapshots. Visibility revocation, disconnect and viewer changes must clear the
surface with `ClearViewer(ticket)`, not just advance this watermark. A retired
disconnect ticket cannot clear a newer viewer. The host still owns authoritative
receive order and a bounded latest-frame mailbox; this class is not that worker
pump or an authentication boundary.

Same-viewer updates reuse CardView instances by opaque object incarnation.
Concealed cards clear their views, removed objects dispose their views, and every
accepted update invalidates prior inspection. Inspection requires the current
ticket and a currently visible object. Old inspection requests cannot clear or
change a new viewer's inspection. No game command is submitted here; legality and
pending action ownership remain in ClientSessionChannel. UI callbacks cannot
re-enter the owner during cleanup, presentation or inspection. Failures clear
owned views and close the surface with a code-only diagnostic. A failed private
scope stays owned for a disposal retry; successful cleanup does not reopen a
faulted surface. Reentrant disposal is rejected along with other mutations.

## Deliberately unresolved artwork and text

The current protocol lacks a general authorized current-face artwork binding.
A subsequent [single-face boundary](play-viewer-artwork.md) supports verified
normal one-face printings. For unresolved cases, `CardView.BindUnavailable`
presents supplied name, type and current P/T,
loyalty or defense without a fabricated printing/face identity or substitute
texture. Engine presentation text is not promoted to complete Oracle rules text;
unknown artwork/rules/tap state is marked unavailable. Exact printing and current
characteristics remain in the immutable projection for a subsequent authorized
asset boundary. The existing public artwork gallery remains unchanged.

The host must cancel/clear every other viewer-specific panel, discard obsolete
worker completions, release old projected frames and provide a truly private
resource scope. Current-face resolution, production private artwork loading,
object-lifetime cache eviction, the main-thread mailbox and real session/scene
mounting remain subsequent work. No global asset cache or new deck format exists.

## Validation

Attached-panel tests exercise a complete empty handoff frame, removal of private
inspection textures and tooltips before private-scope disposal, deferred texture
destruction, preservation of an unowned shared texture, flip cancellation, late
workers/tickets, wrong session/viewer, revision watermarks, view reuse,
concealment/removal, safe inspection, reentrant detach callbacks, cleanup failure
and off-thread rejection. A focused CardView check covers unavailable binding
without retained or fabricated printing data. These are automated lifecycle
checks, not a new hands-on game/UX acceptance claim.

Local evidence at 0.5.85-alpha.1: 314 EditMode checks and 13 PlayMode checks
passed, including the existing Java protocol preflight. No full application suite
ran. The public fixture scene was not changed or rebuilt for this owner-only
increment, so no new owner UX verification is required. Production mounting
remains open. CI follows the every-third-commit schedule (next at 0.5.87).

The single-face follow-up adds bounded private texture scopes and one-shot
revision-bound artwork requests. Core cache jobs, general face resolution and
the session-scene mailbox are still separate integration work.

The [render-mailbox follow-up](play-render-mailbox.md) adds one coalesced frame,
bounded owned artwork completions and a main-thread drain per ticket. Begin/clear
closes prior mailboxes; newer worker state also blocks obsolete direct artwork
admission. This does not mount the surface into a live session or create a Core
asset job scheduler.

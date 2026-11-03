# Viewer-scoped mana source submission — P1.2/G1

Status: client admission for select_mana_source exercised locally. All seven
specified wire operations now have client-owner admission paths. This is not
Java/XMage payment execution, complete G1 acceptance or installed Play enablement.

## Preserve the existing adapter boundary

The working Python adapter requires a current mana-family decision and resolves
an opaque object ID from that viewer's current _wire_objects map. It does not
enumerate every usable mana source; XMage checks available abilities/payment.
The Qt table currently exposes its source-click affordance on battlefield objects;
that UI policy is separate from the public adapter's object-addressing boundary.

The C# owner mirrors that boundary: select_mana_source must match trusted session,
viewer, revision and decision token, the current family must be mana, and object_id
must exist in the latest validated viewer snapshot. It then uses the existing
command reservation, bounded write and correlated ACK/uncertainty path. No lookup
into an unrestricted session or another viewer's objects is performed.

These are **addressable objects**, not a list of legal mana sources. The client
does not infer usability from zone, land type, rules text, ownership/controller,
tapping, face-down status or available printing/characteristic metadata. An opaque
ID may remain addressable while its identity is concealed; no card identity is
reconstructed or added to the command. The actual gateway must still resolve the
current viewer incarnation and ask XMage whether the requested source/ability is
usable. A local admission pass is not legality or successful payment.

## Lifetime and failures

Each new snapshot replaces the object-ID set. Higher-revision events, result,
non-active state and channel failure revoke it with the other decision permissions.
Old/blinked IDs, IDs supplied by another viewer and invented IDs do not become
valid from caller-provided card metadata. The current snapshot/engine mapping,
not a stored printing ID or card name, determines addressability.

A non-mana request fails DECISION_FAMILY_MISMATCH. An unaddressable source fails
STALE_OR_INVALID_OBJECT. Shared context checks still reject wrong session/viewer,
revision and decision token before writing. These are local admission categories,
not new wire ACK codes. An empty object set cannot invent a source; other explicitly
offered actions/options/control flags may still permit their separate operations.
CanSubmit does not promise that any particular source can produce mana.

No source is selected automatically, no abilities are synthesized, and no costs,
restrictions or mana totals are calculated here. All existing legal-action and
choice routes stay available according to their provided tokens/constraints.
The lifecycle Cancel() method, engine-decision cancel command and concession
remain distinct; concession still has no newly authorized wire operation.

## Actual evidence

Fifteen new focused owner checks cover current source addressing, wrong family,
empty object set, stale decision, unaddressable/foreign/old-incarnation IDs, snapshot
replacement, revision revocation and pending receipt uncertainty. Cases with tapped,
face-down, concealed, other-controller, hand/unknown-zone and unknown-characteristic
objects demonstrate that the client is not duplicating mana-eligibility rules.
They do not claim those objects are usable sources in a real game.

A sixteenth authenticated Java-dummy scenario adds a public synthetic object and
an explicit mana request. The client submits its supplied object ID; the dummy
matches only that fixture ID, emits submitted and explicitly simulated confirmed
receipts, then sends its fixture-only result and matched shutdown. No real XMage
payment, chosen ability or natural game completion is claimed.

Local validation: 202 focused Unity EditMode checks, including 63 owner checks and
16 actual Java-process scenarios, plus all Java corpora/16 read/14 write socket
checks passed. Model-generation drift check passed. No full application suite ran.
No new UI/renderer, native deck export, engine pin or installer behavior changes.

G1 still needs complete authentication/session budgets, Java session ownership,
immutable renderer projection, product launch/containment and licensed Unity CI
acceptance. G0 stays open. Java/XMage rules/choice behavior parity belongs to
Phase 2/G2 after G0/G1; this fixture is not that port.

Scheduled third-commit CI snapshot: `2184f56` protocol checks passed
(https://github.com/RyMeep128/Manaforge/actions/runs/41129523375), as did `f2caeed`
(https://github.com/RyMeep128/Manaforge/actions/runs/41128561702). The `f3d7e26`
run was still in progress
(https://github.com/RyMeep128/Manaforge/actions/runs/41130496606) and was deferred
without waiting. These are hosted Java/model checks, not licensed Unity evidence
or CI results for this increment. Qt CI was not investigated.

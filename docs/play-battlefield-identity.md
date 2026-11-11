# Battlefield identity foundation (CT-07A)

This is an internal Java foundation, not shared battlefield organization or full
CT-07 delivery. No production caller, protocol field, Unity behavior, or native
game rule is changed. Private layout remains gated while Unity licensing and
full-game acceptance are unavailable.

## Ownership and contracts

`BattlefieldIdentityRegistry` is created for one authoritative native game UUID by
its future match owner and must be closed by that owner. There is no static cache.
It mints a match epoch, canonical seat IDs, and permanent incarnation IDs. Native
UUIDs and zone-change generations are internal; names and viewer array order never
establish identity. The same card's leave/reenter creates a new incarnation even
when no snapshot was taken while it was absent. Controller changes retain the
incarnation and update its canonical controlling seat.

`NativeBattlefieldIdentity.capturePaused` reads under a live HumanPlayer response
monitor, mirroring the existing metadata boundary. It requires an authorized live
viewer, a matching native GameView/cycle, and consistent native generation data.
Its Game and GameView supplier are server-owned capabilities, never wire input.
Snapshots defensively copy all collections and contain no mutable native objects.
Callers must not build observations from an untrusted client payload.

Reconciliation validates the whole snapshot before mutation. Foreign games, stale
cycles, conflicting same-cycle identities, missing generations, duplicate native
objects, unknown controllers, and invalid admissions are rejected. Results expose
immutable host identities and removed incarnations; no membership exists yet.

Viewer projection emits only opaque member handles, canonical seats, and current
viewer-admitted object references. Each viewer has independent handles. Native
identities are never part of this projected member type. Resolving a handle is a
presentation lookup, not authorization to issue a game command. Existing offer,
target, and command admission must still validate every future action.

Disappearances, control transfers, and face-down transitions revoke affected
handles. Viewer-specific visibility loss revokes that viewer's handles on their
next coherent projection. The future fanout owner must project each admitted viewer
before publishing or accepting organization intents; this slice has no such
transport or admission path. Face-down permanents are omitted from organization
projection and keep their normal existing gameplay path. Becoming visible again
issues a new handle. Closing the registry clears all mappings and prevents reuse.

## Verification and delivery

`NativeBattlefieldIdentityChecks` runs through the existing hosted native-payment
checker on both stock and hash-pinned delivery engines. It uses the existing real
native game fixture and response boundary. Native moves, battlefield entries,
transformation, control transfer, concealment, and token creation/removal exercise
the registry. Zone counters are never manually assigned to manufacture lifecycle
proof. Negative snapshots test atomic rejection; two native viewer views test
independent handles and canonical seats. Existing payment assertions stay intact.

Local verification is compile-only against the pinned SDK, Python lint/format, and
diff checks; no local suite is run. Hosted results must be recorded for the pushed
SHA before CT-07A is marked accepted. The preceding Unity edits were committed as
`8deb471` with their local license failure recorded separately. There are no new
Unity edits in CT-07A; the earlier rebuild failure is not a successful build.

## Next integration boundary

Full CT-07 still needs match-lifetime construction/disposal, coherent per-viewer
projection admission, and integration with the future organization contract.
Do not enable persisted membership, shared organization, or advertise multiplayer
support from these internal types. CT-08 can consume the proven incarnation and
canonical-seat boundary only after native lifecycle evidence passes. Wire DTOs,
multiplayer coordination, reconnect, and Unity group rendering remain later work.

## Stabilization evidence

The first hosted run on `fc4e6d8` failed before characteristic-transition checks:
Delver was no longer present after the payment fixture's generic advance helper.
That helper also queried playable actions, which is unrelated to identity capture.
Identity checkpoints now consume their own real native ASK and response monitor,
save the completed transition state, and build only a native GameView. They assert
initial permanent/incarnation presence, promptly surface transition-worker failures,
and verify response/query completion between checkpoints. Native transitions and
all lifecycle assertions remain required; this is not yet passing hosted evidence.

The live idle proof on the same base failed before the idle callback. Static
inspection found the new adapter linked HumanPlayer from a plugin absent from the
ordinary bridge compilation classpath. The adapter now uses the existing metadata
reader's reflection pattern; a library-only compile verifies that SDK boundary.
Idle proof now writes allowlisted stage/reason/timing evidence before failure, and
the workflow uploads the report even on failure. No raw errors, paths, authentication
material, or event transcripts are included. The 240-second idle and expiry checks
are unchanged. Hosted confirmation and the subsequent live gameplay steps remain
required; unrelated shared-worktree Unity rollout edits are not part of this fix.

### Double-faced fixture correction

On `1208202`, Java live gameplay passed, including the full idle proof. Both native
jobs failed at the initial Delver presence assertion. Pinned `ZonesHandler`
bytecode confirms that entry of a composite `DoubleFacedCard` rewrites the event
object to its registered left-half ID. The fixture incorrectly looked up the
composite ID as a permanent; the permanent had not disappeared.

The fixture now obtains registered cards from the native game, enters through
native zone movement, and resolves the registered front half explicitly for the
Delver transform scenario. It asserts the distinct composite/front IDs and the
front permanent's incarnation before transformation, then requires the same
incarnation and generation after a real native transform. No registry, rules, or
adapter behavior changes are needed for that lookup correction.

Seven independently owned native games cover ordinary characteristic/attachment
changes, transformation, coalesced blink, controller transfer, concealment, token
replacement, and viewer/rejection/disposal behavior. Synthetic fixture traces
contain only IDs, zones, generation, and presence at registration, entry, effect
application, and checkpoint boundaries. All native lifecycle assertions remain
required. Compile-only checks do not establish passing hosted acceptance.

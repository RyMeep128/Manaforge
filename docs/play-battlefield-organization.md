# Flat battlefield organization model (CT-08A)

This internal Java module implements organization independently of Unity, XMage,
and transport. It has no live-match caller, native mutations, IO, wire schema, or
player-facing controls. CT-07A native acceptance remains a prerequisite for future
integration; its current control-transfer fixture failure does not gate these
independent reducer checks.

## Manual organization contract

`BattlefieldOrganizationService` contains immutable `Basis`, `Member`, `State`,
`Seat`, and `Group` types. A server-owned basis identifies one match epoch, a fixed
canonical seat roster, and current permanent incarnations with controlling seats
and organization eligibility. Native UUIDs, viewer handles, and card names do not
identify members. Every live member appears exactly once: in its controller's
default root or in one flat group. Ineligible members can only appear at root.

`create(basis)` establishes deterministic root ordering by incarnation ID. A group
has a caller-supplied match-unique ID, a trimmed nonblank display name, normalized
position in [0,1] on each axis, and an ordered member list. These are presentation
coordinates, not rule-zone positions or HUD geometry. Display names do not act as
keys. Protocol limits and wire validation belong to the future contract.

`apply(state, trustedActorSeat, operation, battlefieldBasis)` returns a new state
or throws `Rejected` with a stable reason code. The supplied basis must equal the
state's last reconciled basis. The actor is trusted host context, never an editable
operation field. The host must still authenticate and serialize future requests;
this reducer is not a multiplayer authority boundary by itself.

Create appends an empty group. Rename, position, reorder, and delete apply only to
the actor's groups. Delete appends the group's members to root in existing order.
Move takes an explicitly ordered selection and a destination group (null means
root). Its insertion index is measured after removing the selection from all old
locations. The selection order is retained. Group reorder indices address the
final group list. Moving the last member out never deletes the empty group.

Invalid ownership, stale basis/incarnations, duplicate selection/group IDs,
ineligible selected members, bad indices, and non-finite/out-of-range coordinates
are rejected atomically. State, basis, operation selections, and result collections
are defensively copied and immutable; old states remain valid snapshots.

## Verification

`tools/check_play_organization.py` compiles only this module and its Java checks,
with an empty SDK classpath. Its default mode executes checks in GitHub Actions;
`--compile-only` supports local static verification without running a suite.
The independent **Play organization reducer** workflow requires only Python/JDK.
Neither Unity licensing nor a failed native identity/payment job can skip it.

Initial coverage includes all manual operations, ordered selection and insertion,
empty group preservation, default-root behavior, ownership isolation, stale basis,
invalid input, input immutability, and unchanged state after rejection. No passing
hosted evidence is claimed until the exact pushed SHA's workflow completes.

Lifecycle reconciliation and retained-seed invariant sequences are the next review
step within CT-08A. Drawers, stacks, nesting, automatic assignment, persistence,
networking, and Unity projections are deliberately outside this module.

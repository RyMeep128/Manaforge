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

## Lifecycle reconciliation

`reconcile(state, battlefieldBasis)` accepts a new server-owned basis for the same
match and fixed seat roster. Roster changes are rejected until join/leave policy
is implemented separately. The future serialized host must supply current bases;
this pure model does not infer network freshness, authenticate seats, or mint
incarnations. No direct dependency on the unaccepted native fixture is introduced.

Surviving root and group members retain their relative order. Departed incarnations
are removed. A control change removes old membership and appends the member at the
new controller's root. Concealment removes custom membership and places the object
at root; restored eligibility never restores an old manual assignment. New entries,
transfers, and newly eligible entries append in incarnation-ID order. Existing
empty groups, labels, coordinates, and group order are preserved. A returning card
with a new incarnation has no relationship to its previous group membership.
Reconciliation is atomic, deterministic, and idempotent for an unchanged basis.

Hosted checks cover these lifecycle cases and sixteen retained seeds
`2026111100` through `2026111115`. Each seed executes 400 mixed edit/reconcile
steps, validates one-location/ownership/eligibility invariants after every step,
checks old-state immutability and rejection atomicity, checks reconciliation
idempotence, and replays to an equal final state. No suite is executed locally.

Drawers, stacks, nesting, automatic assignment, persistence, networking, and Unity
projections are deliberately outside this module. CT-08A is implemented internally;
full CT-08 and CT-07 integration are incomplete. Do not advertise shared groups or
enable persisted membership from this reducer alone. Native control-transfer
acceptance remains separate unfinished work before production integration.

## Match-scoped session: edit admission

`BattlefieldOrganizationSession` owns a reducer state on its constructing thread.
It starts at organization revision zero and a caller-supplied nonnegative basis
revision. `apply(trustedActorSeat, expectedOrganizationRevision,
expectedBasisRevision, operation)` returns APPLIED or REJECTED, a stable rejection
code when relevant, an organizationChanged flag, and the current immutable host
snapshot. Stale revisions are rejected before reducer invocation. A changed edit
increments organization revision exactly once; successful no-ops retain the same
snapshot and revision. Rejections retain the exact previous published snapshot.

Snapshots expose match epoch, organization revision, basis revision, and reducer
state. They contain host incarnation/seat information and are never wire messages
or viewer-safe projections. Immutable snapshots may be read or retained on other
threads, but apply and close require the constructing thread. Close releases the
session's reference to state, is idempotent on that owner, and rejects subsequent
snapshot/edit access. Previously returned immutable snapshots remain valid.

The independent organization workflow runs both reducer and session check classes.
Session coverage includes two seats, stale revision rejection, invalid batch
atomicity, no-op revision behavior, historical snapshots, cross-thread mutation
rejection, and disposal. Local verification remains compile-only. The session is
not authentication, a retry ledger, networking, or live-match integration. Basis
revision handling is the second review step for this session slice.

# Shared organization channel (CT-11A)

Opt-in integration work only. The ordinary launcher and its authentication hello
are unchanged. A registration must explicitly allow the extension, and the owner
must install a factory before starting channels. Default registrations retain the
read-only behavior. No capability probe is sent to a legacy receiver.

## Transport extension boundary

`ViewerChannelExtension` is a protocol-level callback interface without organization
model or native SDK dependencies. Its factory and all callbacks execute on the
coordinator owner. The authenticated listener registration supplies the canonical
seat; packet identity fields cannot replace it. Trusted `updateExtension` actions
allow later basis updates on that same serialized owner, never from socket workers.

Each enabled reader has at most 32 pending input packets, each bounded to 256 KiB.
The single socket writer owns one initial control slot, one replacement gameplay
snapshot, a 32-item receipt FIFO, and one replacement organization snapshot. Initial
control precedes publication; gameplay snapshots otherwise precede organization
traffic. Overflow or write failure disconnects only that viewer. No sibling ACK is
required. Disconnect clears outgoing organization queues. Match shutdown closes
the extension on the owner before disposing the shared match resource.

`ExtensionPlumbingChecks` uses actual authenticated sockets with explicitly synthetic
transport packets to verify owner binding, opt-in isolation, one-writer delivery,
and cleanup. It is not organization or native-game acceptance. Existing read-only
coordinator tests remain in the protocol suite. Local checks are compile/static
only; no suites are run locally.

The native helper now includes game-plugin JARs for both real-game modes. Previously
multi-view mode compiled fixtures without TwoPlayerDuel/TwoPlayerMatch available.
This fixes a source-assembly condition, not a change to native rules or identity
assertions. The native identity/control-transfer failure remains a separate gate.

Host admission, retry handling and viewer-safe fanout are implemented below.
Live shared organization remains disabled.

## Host admission and historical receipts

`OrganizationChannel` owns a `BattlefieldOrganizationSession` on the coordinator
owner. Its constructor takes explicit trusted per-viewer contexts and a fixed-seat
basis. These are harness inputs; no native identity bridge or production launcher
wiring is implied. Socket registration supplies the actor. Capabilities must be
mutually selected before commands or snapshots use the extension.

Each seat retains at most 4096 command records for the match lifetime, without
eviction. The SHA-256 digest covers recursively key-sorted command body JSON,
including revisions and handles, excluding the transport message ID. An identical
known command returns its exact original receipt before checking current basis or
handles. Conflicting bodies reject with `COMMAND_CONFLICT`; capacity rejects new
IDs with `COMMAND_LIMIT_REACHED`. Neither replaces an existing record. Rejections
for admitted new IDs are recorded as well. Receipts precede snapshot fanout.

Pure reducer candidates are rendered and validated for every viewer before session
mutation, including group counts and the 256 KiB wire limit. Rejected edits leave
state intact and return an issuer-only resynchronization snapshot. Changed edits
broadcast viewer-specific snapshots; no-ops refresh only the issuer. A basis update
similarly preflights reconciliation and contexts before committing. Context mapping
refresh requires a new basis revision; equal-revision contexts are never adopted.

Historical receipts carry no object mappings. Java `parseReceipt` and C#
`ParseReceipt` accept them only for a trusted match and known pending command ID.
They do not advance a snapshot or admit historical object handles. Normal parsing
continues to require the current basis. Consumers must keep pending IDs scoped to
their authenticated session. `OrganizationChannelUnitChecks` covers admission,
foreign edits, stale/duplicate/unknown handles, atomic limits, retry conflicts and
ledger saturation through hosted protocol CI only. The shared Java/C# corpus also
covers new stable rejection codes and receipt-specific admission.

## Two-client integration and remaining gates

`OrganizationChannelChecks` connects two real authenticated loopback sockets to the
opted-in coordinator. The basis, identity contexts and gameplay snapshots are
explicitly synthetic. It exercises create, rename, move, unassign, reorder, delete,
position, opponent inspection, unauthorized edits, stale and duplicate selections,
exact receipt replay, conflicting reuse, lifecycle reconciliation, privacy canaries,
slow-reader isolation, authenticated reattachment and retained retry history. The
gameplay revision advances only through explicit read-only fixture publication.
Sending a gameplay command through this extension disconnects its sender.

`ExtensionPlumbingChecks` additionally forces input overflow while the owner is
paused and receipt overflow while a socket reader is stalled. Queues are bounded,
disconnect clears them, and the other viewer continues. Writer startup waits for the
owner's connection callback, ensuring the initial capability control packet precedes
a retained gameplay snapshot on reattachment. This wait applies only to opted-in
registrations. Existing production/read-only registrations keep their behavior.

This slice has a fixed two-registration roster and an in-memory match-lifetime
ledger. Reattachment is to an existing listener and credential, not host restart
recovery or remote peer discovery. It does not implement TLS, internet transport,
seat joining/leaving, native command ownership, a Unity network receive mailbox,
shared visual panels or in-game gestures. Group collapse remains a future local
presentation preference, outside shared state.

The next integration gate is a trusted native basis/context bridge with verified
incarnation and controller identity, followed by CT-12 coherent Unity receive and
rendering. Native `CONTROL_HANDLE` acceptance must be resolved independently before
production wiring; do not weaken that assertion to enable this feature. Normal
saved-deck human-versus-AI acceptance and hosted Unity tests remain required for
live rollout. Synthetic socket success cannot substitute for either.

### Verification record

- Plumbing commit `3ea1afc`: hosted protocol and native two-viewer coordinator passed.
  Native payment failed at the inherited `NativeBattlefieldIdentityChecks`
  `CONTROL_HANDLE` assertion, independently of organization admission.
- Host admission commit `9a68c1c`: hosted protocol passed, including the shared
  corpus, per-seat 4096-command bound, preflight rejection and historical receipts;
  native two-viewer coordinator also passed. Later end-to-end additions need their
  own exact-SHA run.
- Local `./tools/unity-play.ps1 -Mode Build` after parser/contract changes completed
  with `Build Finished, Result: Success.` No local test suites were run. The local
  build also included pre-existing uncommitted HUD rollout edits, which are outside
  these commits. Hosted Unity and playable acceptance are separate evidence gates.

## CT-11B: native identity bridge

The control-transfer fixture previously called `changeControllerId` directly and
then applied native effects. The control layer resets transient controller changes;
the fixture now installs native `GainControlTargetEffect` with a generation-aware
`FixedTarget`. It asserts the new native controller after effects before testing
incarnation stability, old-handle revocation and projected seat ownership. Public
fixture diagnostics record controller/generation and old-handle resolution. No
identity assertion is removed and no native production rules are changed. Hosted
stock and delivery-engine evidence is required for this correction.

### Trusted projection bridge

`NativeBattlefieldIdentity.captureBatchPaused` captures all registered viewers and
runs their native callback projection under a single open native response monitor.
Its identity snapshots are immutable host inputs. `projectObserverWithBindings`
returns the existing read-only gameplay snapshot plus immutable native-to-opaque
object and seat mappings, collected during projection, never inferred from names.
Only eligible visible battlefield objects appear in those object bindings.

`NativeOrganizationBridge`, in the explicitly compiled `java/organization-native`
module, is an optional `ViewerChannelExtension`. Construct it in the coordinator
factory with the exact registrations and match ID. Pass its `publication` hook
alongside the captured observation batch to the overloaded `publishNative` call.
The ordinary launcher and old publication overload do not install this bridge.

On the coordinator owner, the hook stages registry reconciliation on a private
candidate and preflights organization contexts and payloads. The coordinator first
validates and enqueues the entire gameplay batch, then commits identity and the
prepared organization basis. There is no intervening owner work. Failed validation
leaves committed identity, contexts and organization unchanged. Native projection
may consume an unused gameplay revision on failure; no rejected snapshot is sent.
A prepared update rejects double commit or intervening committed state changes.

The bridge starts with empty basis zero and temporary opaque seat references. Each
accepted native publication replaces these with the exact gameplay seat/object
references and advances its own basis revision, including same-cycle reference
refreshes. Group membership remains incarnation-based. Native cycle validation
remains independent of this revision. Fixed roster, public eligibility and existing
receipt/queue limits remain enforced. The bridge owns and disposes its registry and
channel with the match. No native response transport is available to this module.

### Native socket acceptance

`NativeOrganizationChecks` runs alongside the existing native two-viewer proof in
both stock and hash-pinned delivery-engine matrix jobs. Its battlefield is created
through real native entry operations, with two Forests, a creature, Equipment, a
transforming permanent and a native token. Two authenticated sockets create and
edit groups. Each received mapping is checked against that viewer's exact admitted
gameplay object and controller references; native IDs and private hand names must
not appear in organization payloads.

Coverage includes individual unassignment, foreign groups/owners/viewer handles,
same-cycle object-reference rotation, stale basis, historical receipts, mixed tapped
lands, counters/damage/attachments, transformation, coalesced blink, native control
transfer, face-down/reveal and token removal. Invalid game/cycle/roster/admission
batches must leave the committed organization snapshot and viewer handles intact.
A non-reading and then disconnected viewer does not stop the other viewer's edits
or subsequent native publication; reattachment reconstructs state and retains retry
history. Protocol overflow/stalled-writer tests remain the deterministic queue-pressure
proof. Organization edits must leave the native checkpoint cycle unchanged and
record zero native response submissions. Parent shutdown disposes the bridge and
shared native fixture exactly once.

The first control-effect CI attempt exposed a null source because basic lands have
no spell ability. The fixture now gives the effect an explicit activated-ability
context with the real permanent source/controller, without activating it or inventing
zone counters. The post-effects native-controller assertion remains mandatory.

No Unity files changed in CT-11B, so this slice does not require a new local Unity
player build. The previous local player rebuild remains separate from hosted Unity
and normal saved-deck human-versus-AI acceptance. No live launcher capability is
enabled by this work. Final exact-SHA checks must be reported as pending until they
finish; native fixture success alone is not full-game acceptance.

Hosted protocol coverage also exposed a disconnect-reason race: closing a saturated
socket could wake its reader before the overflow path recorded the cause. The
coordinator now records the first disconnect and clears its queues under the
channel lock before closing the socket. The overflow assertion remains strict;
secondary reader/write failures cannot overwrite the recorded cause.

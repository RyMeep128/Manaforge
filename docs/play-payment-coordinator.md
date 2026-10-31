# Safe automatic mana payment â€” Java coordinator

Status: isolated foundation through 0.5.112-alpha.1 for P2.3; production automation is
**disabled/unmounted**. P4.3 real-engine acceptance has not happened. This implements
the fallback scope explicitly allowed by the [owner story](play-safe-automatic-mana-payment-story.md),
not the story's end-to-end definition of done. The existing manual command contract and Unity renderer are preserved. The manual
Java bridge now shares the native response executor described below. No XMage fork/source copy,
binary edit, upgrade, new download or weakened artifact verification is introduced.

## Pinned API investigation

Inspected the installed 1.4.62-V1 / xmage_1.4.62V1 binary distribution using javap,
after matching SHA-256 against Mtg_Projects/mtg_play/artifacts.json. Manifest hash:
525fe515ed4e7540b3b02884d01c37732a5e1b1e650784ea1c2259e422a700b4.

- mage-1.4.62.jar: 40cfe1249c1c562ce857eaffcf82f089c10d48bfbf278b704fe78b3c943140dd
- plugins/mage-player-human-1.4.62.jar: bee4bb9940e3ba8f28bd8603088583bad65c77ec3922a5756312ce8e0b654892

| Exact pinned facility | Verified meaning/limit from signature and bytecode inspection |
|---|---|
| ManaPool.setAutoPayment(boolean), setAutoPaymentRestricted(boolean) | Native pool-spending flags; not battlefield source selection. isAutoPayment also accounts for forcedToPay. |
| UserData.setManaPoolAutomatic(boolean), setManaPoolAutomaticRestricted(boolean) | Seat preference inputs; PlayerImpl copies them into pool flags. No new preference is applied by this increment. |
| HumanPlayer.playMana(Ability, ManaCost, String, Game), protected playManaHandling | Handles the engine response cycle. firePlayManaEvent publishes a prompt with an initially empty data map, then waits for a response. A boolean response cancels; it is not an auto-pay command. |
| HumanPlayer.playManaAbilities(UUID, Ability, ManaCost, Game), protected | Works on an already-selected source. Calls getUseableManaAbilities for the source/zone, checks special-payment sequencing, and activates through engine behavior. |
| ManaUtil.tryToAutoPay(ManaCost, Map<UUID,ActivatedManaAbilityImpl>) | Narrows a supplied ability map, not a full battlefield planner. It returns the original map for unsupported ability classes. A nonempty return is not proof of safe auto-payment. |
| ManaUtil.tryToAutoSelectAManaColor(Choice, ManaCost) | Called inside native choice handling with currentlyUnpaidMana. That protected HumanPlayer field is assigned around selected-source activation, not exposed as a safe client payment plan. |
| CardImpl.caresAboutManaColor(Game) in the HumanPlayer path | The pinned selected-source implementation bypasses tryToAutoPay when the spell cares about mana color. A gateway must not erase that distinction. |
| PlayerImpl.setPayManaMode(boolean) | Native state flag, not permission to automatically choose any source or cost. |

Inspection is not a real-game behavioral test. These existing facilities are the
intended reuse points for the future engine port; the isolated coordinator does
not invoke XMage, replace its solver or apply native preferences in production.
Exact signatures can be checked again with the tool below. Detailed read-only
bytecode reports are local under Unity Artifacts/AutoManaInvestigation, not shipped.

## Why production wiring is still unavailable

GatewaySessionBoundary.dispatch reserves/deduplicates authenticated client
submissions and calls a trusted enqueue hook. There is no live Java gameplay
session owner executing that hook against XMage yet. The older Java headless
bridge forwards GAME_PLAY_MANA, but does not supply the associated Ability,
ManaCost, safety classification or a verified multi-source plan to this gateway.
The public snapshot object list proves addressability only. It cannot be used to
infer legal or safe sources. Pinned source-selection helpers need trusted in-engine
context; prompt/card-name parsing cannot fill that gap.

Consequently there is no production EnginePort and no call site instantiates this
coordinator in a real session. No existing engine defaults were changed to imply
this feature is enabled. All actual automatic basic-land, multi-source and floating
mana acceptance cases remain unproven. No engine process was launched for that isolated increment. The native executor
follow-up below has a focused real-engine proof.

## Implemented boundary

PaymentCoordinator belongs to one serialized Java engine owner and one human seat.
Its default mode is Auto; Manual and Full Control suppress bridge activation and
remain independent of priority automation. Non-human seats do not run this policy.
The class has no networking, Python, Unity, database, JSON or rules-engine dependency.

A trusted engine port must inspect the exact current session/viewer/payment/decision/
revision and certify a bounded equivalence class of already-safe next-step tokens.
Only VERIFIED_ORDINARY_EQUIVALENT with a nonempty class is eligible. Unknown,
unsupported or strategic states fall back to manual before any enqueue. This is a
policy interface, not implemented evidence that a given card/cost is safe. The
future port must establish basic/unrestricted ability safety, usable cost, selected
X, additional costs, special mechanics, conditional mana and color/source-sensitive
effects using native data. Until verified, those cases must remain manual.

The policy chooses the lexicographically smallest opaque token within an engine-
certified equivalence class, giving deterministic selection without a mana solver.
It cannot rank flexibility or choose across strategically different classes. It
rechecks currentness after inspection; enqueue must atomically revalidate the
step under the same engine owner used by authenticated manual submissions.

At most one attempt is made per offered context. claimManual wins before automatic
inspection/enqueue, or refuses when automatic work is unresolved. Mode changes do
not undo already submitted work. The port's enqueue result is only Submitted;
progress/completion require a separately correlated semantic engine observation.
No Unity command ID or client ACK is fabricated. Progress does not automatically
repeat a step: a fresh trusted offer and new inspection are required.

Replacement while unresolved, enqueue failure and uncertain results fail closed.
Repeated consider calls never retry. Only an exact attempt identity can receive an
engine observation; old observations cannot complete another attempt. Stop/cancel/
disconnect/owner-close drops private context references and retains only bounded
Stopped/Uncertain status. No rollback, reconnect recovery or automatic replay is
implemented. A semantic late observation can resolve uncertainty only while the
same owner/context remains alive; it does not itself initiate another action.

Integration must put both manual and automatic admission on that same serialized
engine owner after existing viewer authorization. This class does not extend or
replace GatewayCommandGate, SubmissionLedger or GatewaySessionBoundary receipt
ownership. A port must enqueue promptly and cannot call back into the coordinator
until it returns. Cross-thread and reentrant access fail closed.

## Verification and remaining acceptance

Run the focused Java safety/lifecycle checks:

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_payment_coordinator.py
```

Verify the existing pinned binaries read-only as well (javap must be on PATH, or
supply --javap with the installed JDK executable):

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_payment_coordinator.py --verify-pinned-api --javap 'C:/Program Files/Java/jdk-23/bin/javap.exe'
```

The protocol CI workflow includes the isolated checks and path triggers. No public
protocol/schema or launch-manifest field changed, and no shared DTO regeneration
is required. No Unity payment UI is added. Reference assets can inform later UI,
not supply gameplay rules or engine safety evidence.

Next required work: integrate a trusted live Java/XMage session owner, implement
its safe native assessment/dispatch port and seat preference application, then
prove actual one-Forest {G}, ordinary {1}{U}/{2}{G}, equivalent-source and floating
mana games. Required evidence includes engine-confirmed source activation, mana
spending, spell resolution, manual fallback, privacy and clean owned shutdown.
Only that can satisfy the story. Synthetic coordinator tests are not substitutes.

Local evidence for this increment: 65 focused synthetic Java safety/lifecycle
checks passed, and the optional read-only probe verified the exact signatures in
five pinned native classes after artifact hash checks. No full application suite
or real engine game ran. CI wiring is added; no new CI result is claimed. The next
scheduled relevant CI checkpoint is 0.5.111 under the established every-third-
commit cadence. No owner UI verification is needed for this backend-only increment.

## Native helper adapter and executable probe — 0.5.110

SelectedSourceMana is a small optional Java/XMage adapter around the native
ManaUtil.tryToAutoPay helper for ONE already-selected source. It validates native
ability-map keys, copies the map before delegation and returns an unmodifiable
map. Native ability objects remain borrowed engine objects; no deep copy, rules
calculation, safety certificate or source-activation permission is implied. This
adapter has no production call site and cannot enable automatic gameplay.

Execute focused native object checks with the installed pinned runtime:

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe tools/check_play_payment_coordinator.py --probe-pinned-helpers --javap 'C:/Program Files/Java/jdk-23/bin/javap.exe'
```

This opt-in probe verifies every explicit runtime classpath JAR against the
existing artifact manifest before loading native classes, compiles the adapter
and tests in a temporary workspace, and invokes only utility-object operations.
It starts no game/server, loads no decks, downloads nothing and modifies no engine
artifact. The default CI invocation still runs the dependency-free coordinator
checks; it does not imply native helper or real-game CI coverage.

Verified native behavior includes three integration traps:

1. ManaCostsImpl.testPay(Mana) is an ANY-component contribution predicate. The
   pinned bytecode returns on the first component that accepts mana. It returns
   true for a {2}{G} cost against a two-mana green/blue value. This is recorded as
   native behavior, NOT a weakened payment-feasibility acceptance gate. It cannot
   certify that the entire cost is payable.
2. ManaUtil.tryToAutoPay can clear/replace its input map, and that map uses native
   ability IDs, not battlefield source IDs or Unity object IDs. The adapter keeps
   the original map intact while narrowing copies for different unpaid costs.
3. tryToAutoSelectAManaColor selects the first offered color for generic-only
   costs. It chooses green for an unambiguous {G} choice and declines a {G}{U}
   choice, but its generic fallback is not strategic equivalence/safety evidence.

Local evidence: 65 coordinator lifecycle checks and 31 real pinned utility-object
checks passed, plus five-class signature/hash verification. Checks cover separate
UserData instances, pool flags, native cost contribution, actual green/blue ability
narrowing, preserved maps, rejected foreign keys, immutable result maps and color
selection. No source was activated and no payment or spell resolved in a game.
Production activation and all P4.3 real-game acceptance remain open. No full app
suite or UI changes. Next scheduled CI check remains 0.5.111.

## Downloaded reference implementation — October 31, 2026

Per the owner request, selected managed types were inspected from Downloads/
Assets from Wizards, given with permission/Managed. This was code-path inspection,
not just prefab/sprite discovery. Original files were read only. ILSpyCmd 9.1.0.7988
and local decompiled reports stay under ignored Unity Artifacts; no supplied DLL,
source implementation or reference engine is added to Manaforge.

| Inspected reference path | Observed behavior |
|---|---|
| Core: SettingsPanelGameplay.OnAutoPayToggled | Sends the change through AutoResponseManager and disables the toggle until a changed current-settings object is observed. |
| Core: AutoResponseManager.SetManaAutoPayment | Requests Auto/Manual ManaSelectionType and records the local preference. Startup also sends the configured selection type. |
| SharedClientCore: GreInterface.SetAutoPayMana / SetAutoPass | Sends engine settings. Full Control changes ManaPaymentStrategyType to Manual; leaving it requests Auto. Manaforge's payment and priority preferences remain separate as required by the owner story. |
| SharedClientCore: AutoTapActionsRequest | Copies AutoTapSolutions supplied by the GRE request. SubmitSolution verifies membership and sends the ORIGINAL solution index in PerformAutoTapActionsResp. This inspected path does not construct a battlefield payment plan. |
| Core: AutoTapActionsWorkflow | Previews source/mana highlights, presents engine-offered alternatives and confirmations, and maps display-sanitized solutions back to originals before submission. |
| Core: PayCostsRequestHandler_AutoTap | Its loop/playback response validation correlates request/response IDs, payment request type and available auto-tap solutions. This is not proof of when every live automatic payment is triggered. |

Reference file SHA-256 provenance:

- Core.dll: 48347a833961d311da7a3ccdecc6116f3ee75b6db8fa313b1871aecea8b54e85
- SharedClientCore.dll: aceb0cd5004b322ceb59b28b0ad44ec799b3d47a46666b17a50150da5449e392
- Wizards.MDN.GreProtobuf.dll: 9569420c5ba7f6b33316d74d8208ffa29a872ab96566a45fe26cd63cf1e75306

The useful Manaforge pattern is engine-owned proposals, immutable current-request
identity, manual override, engine-confirmed settings and source previews. It does
not supply an XMage planning API or prove a safe XMage combination. Keep payment
planning/execution in the Java engine adapter, render only viewer-permitted state,
and preserve the original engine proposal identity through any presentation sort.
The existing coordinator already requires trusted engine-certified step handles;
reference findings do not justify replacing that contract with client heuristics.

## Shared manual/internal session admission — 0.5.111

GatewayPaymentPort now connects PaymentCoordinator.EnginePort to the existing
GatewaySessionBoundary before a trusted native enqueue. This is a tested
adapter-to-session integration, not live XMage execution: its native delegate is
still absent in production, so automatic gameplay remains disabled.

The boundary has a generic private InternalReservation, scoped to its authenticated
session/viewer and current revision/decision. It contains no payment policy or
native game state. GatewayCommandGate supplies a current-binding comparison only;
SubmissionLedger supplies unresolved-client-command status only. All safety
classification and automatic selection remain outside those components.

Internal reservations and client-command reservations share the same boundary
monitor. A valid manual command admitted first blocks internal reservation. An
internal reservation acquired first causes overlapping client commands to receive
the existing COMMAND_PENDING rejection. Invalid/stale command rejections retain
their original meaning, and duplicate command history remains unchanged. No client
command, command ID or acknowledgement is invented for internal automatic work.
A repeated old client terminal receipt cannot release an internal reservation.

GatewayPaymentPort acquires that reservation, rechecks currentness, then calls the
trusted native enqueue without holding the boundary monitor. Native enqueue must
still atomically validate its engine context/source before executing. A failed
read-only preflight or definite nonexecution releases the reservation so manual
input is available. An enqueued result stays pending until a correlated semantic
observation, not a queue acknowledgement. Exceptions after native enqueue begins,
null/uncertain results, decision replacement and disconnect retain a blocking
reservation rather than permit replay.

The serialized engine owner must notify both the port and coordinator of semantic
observations. A resolved observation releases only its own opaque reservation;
progress does not initiate a further action without fresh assessment. Per-instance
attempt identity history is bounded to 4096 and prevents repeated internal enqueue.
Cross-owner/thread and reentrant native callbacks cannot release the reservation.
Fatal JVM/programming errors retain uncertainty and propagate their original error.
Closing the port clears its private attempt references, leaves unresolved ownership
marked uncertain, and does not close the borrowed session boundary. The session
owner must close both coordinator and boundary during shutdown.

The existing authenticated client admission/deduplication path remains the authority
for manual commands. Parent integration must serialize engine callbacks, manual
enqueue and coordinator operations on one engine owner; invoking the wrapper from
arbitrary UI/socket threads is forbidden. The boundary itself remains synchronized
so even competing admission attempts cannot both win. No protocol/schema or Unity
fields changed and no complete native source planner is added.

Local shared-admission evidence: the focused Java protocol runner passed its
existing checks plus 110 new synthetic admission/port checks, including sixteen
competing manual/internal races with exactly one winner, native definite rejection,
preflight failure, enqueue exception/fatal/null outcomes, reentrant close, stale
bindings, disconnect, foreign reservations, repeated attempts and old manual
receipts. The separate 65 coordinator and 31 pinned native-helper checks also
passed. No full application suite, Unity tests or real-game acceptance ran for
this backend increment. CI is checked at the 0.5.111 checkpoint without waiting
for unfinished runs; no result is inferred from these local tests.

## Native response executor and manual-path reuse — 0.5.112

ManaResponseExecutor provides the selected-source transport step. The existing
ManaforgeBridge now uses it for object responses to GAME_PLAY_MANA. Its authority
callback validates the owned game ID, exact native callback decision ID and mana
prompt method under the bridge's existing monitor, then consumes the decision
immediately before IO. Callback publication uses that same monitor. The initial
bridge validation remains in place, and other response families retain their
existing dispatch path. Source address authorization and legality still belong to
the viewer adapter/gateway and XMage; this executor does not calculate eligibility.

The bridge supplies the unchanged native SessionImpl.sendPlayerUUID method as its
sender. A true SDK result is Submitted, never payment progress/completion. False
or an ordinary exception is Uncertain, with no retry and no exception detail
added to viewer messages. Interrupts retain the thread interrupt flag. Fatal errors
propagate while the native decision claim remains consumed. A later callback is
not cleared by completion of an older send. The borrowed session remains owned by
the existing bridge; the helper creates no connection, process, deck or game state.

Execute the sender on the serialized native-response worker. SDK IO must not run
inside GatewaySessionBoundary's prompt enqueue callback or on Unity's rendering
thread. The future native port must enqueue that worker and correlate subsequent
engine state before resolving its internal reservation. This source-response step
does not provide the still-missing engine-safe automatic planner or a live Java
session/controller integrating the coordinator. No automatic source activation
has been enabled. Native floating-mana behavior is preserved.

The response guard uses a small injectable sender, so the default CI check now
runs 65 coordinator checks plus 77 response-claim/transport checks without any
engine dependency. The optional pinned probe additionally compiles all three owned
bridge entry points and the executor against the verified SDK and runs 31 native
utility checks. The existing runtime launcher includes the extra Java source in
its owned workspace compilation. It changes no installed engine artifact or pin.

### Real-engine manual execution evidence

The existing `number` fixture was strengthened to require two explicitly submitted
manual sources, two Forests observed tapped, spent mana observed after resolution,
and Walking Ballista on the battlefield as a 1/1 after choosing X=1. Fixture-only
source selection remains in the acceptance driver, not in production automation.
The result comes from XMage snapshots and authoritative game result, not a response
acknowledgement. The fixture concludes by concession after its semantic checks;
it is not natural-match completion, Unity integration, or automatic-payment proof.

Reproduce from the repository root with the existing installed runtime:

```powershell
$env:PYTHONPATH = 'Mtg_Projects;Mtg_Projects/mtg_core'
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe -m mtg_play.adapter_acceptance --scenario number --jdk-path 'C:/Program Files/Java/jdk-23' --output Mtg_Projects/mtg_play_unity/Artifacts/ManaResponseNumber112Final.json
```

Focused Python checks cover connection proof, lifecycle and the adapter. An
existing forced-cleanup test initially failed while measuring a child before
interpreter startup completed. It now waits for a child-ready marker before the
same 200 ms timeout; forced/reaped assertions and product cleanup timeouts are
unchanged. All 105 checks passed after that synchronization fix. No full
application suite or Unity UI test/build ran, and no owner UX review is needed.

Final-source evidence is in ignored Artifacts/ManaResponseNumber112Final.json:
success=true, mana_sources_submitted=2, two_sources_tapped=true, mana_spent=true,
resolved=true and engine_result=true. The peer_0, compiler, bridge and server owned
roots all exited 0; forced_cleanup=false. Root exit is not a claim of OS descendant
containment. Compiled source evidence from that owned workspace:

- ManaforgeBridge.class SHA-256: 416ec8fe38f9eea5df6a761c7e0d1d6b1d778f99789b898f667ebc9abe68f8dd
- ManaResponseExecutor.class SHA-256: d1de2b259330627eb0d3d7432f37c9bf323705f828563c5fc9d16d7851724dce

The default 65 coordinator / 77 response-guard checks and opt-in 31 pinned native
checks passed, as did bridge SDK compilation and the 105 focused Python checks.
Reports were produced from the 0.5.112 working tree before commit; no clean-commit
provenance or current CI success is inferred. CI is next checked at 0.5.114 under
the established cadence. Public game/launch schemas and private bridge response
fields are unchanged; only the acceptance report gains bounded evidence counters.
Packaged distribution was not rebuilt and automatic-source story acceptance
remains open.

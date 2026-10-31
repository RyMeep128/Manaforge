# Safe automatic mana payment — Java coordinator

Status: isolated foundation at 0.5.109-alpha.1 for P2.3; production automation is
**disabled/unmounted**. P4.3 real-engine acceptance has not happened. This implements
the fallback scope explicitly allowed by the [owner story](play-safe-automatic-mana-payment-story.md),
not the story's end-to-end definition of done. The existing manual command path,
Python adapter and Unity renderer are unchanged. No XMage fork/source copy,
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
mana acceptance cases remain unproven. No engine process was launched for this work.

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

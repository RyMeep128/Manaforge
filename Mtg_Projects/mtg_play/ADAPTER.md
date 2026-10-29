# Manaforge local gameplay adapter

Status: **implemented alpha adapter with partial epic acceptance**. This extends
Milestone A; it does not certify every Magic mechanic or finish the full epic.
There is no gameplay UI, rendering code, AI, remote transport, or networking layer.

## Public entry points

`contracts.py` imports only the Python standard library. It defines versioned
setup, seat, compatibility, state, object, characteristics, action, choice, combat,
event, command-result, lifecycle-report, and `GameSession` contracts. Public values
serialize through `to_dict()` and JSON. The bridge wire protocol and public game
protocol both currently have version 1; they are distinct contracts.

```python
from mtg_play.adapter import LocalGameAdapter
from mtg_play.contracts import GameSetup, MatchSeat

setup = GameSetup((MatchSeat("alice", "Alice"), MatchSeat("bob", "Bob")))
with LocalGameAdapter() as adapter:
    game = adapter.create_game(
        setup,
        (alice_deck_document, bob_deck_document),
        oracle_lookup=core_repository.get_oracle_card,
    )
    events = game.poll("alice", timeout=0.1)
    view = game.snapshot("alice")
    # Present this player's view and required decision to its authorized consumer.
    # Explicitly submit a supplied action_id or option_id with its decision_id.
```

The owner/orchestrator authorizes seats. Each `snapshot(player_id)` contains one
engine-created player's permitted view. This API is for trusted local orchestration;
passing its root session to an untrusted consumer would grant access to all seats.
Calls must be serialized by the consumer. Blocking startup and command calls are
independent of Qt and should run on a consumer's worker when responsiveness matters.

`GameSession` supports `snapshot`, `poll`, `perform`, `choose`, `choose_number`,
`choose_amounts`, `select_mana_source`, `cancel`, and `concede`. `ScriptedGameSession`
in `fake.py` satisfies the same interface using supplied snapshots. It implements
no rules and never invents a game result.

## Deck resolution

Pass existing Core `DeckDocument`s directly. An entry with an Oracle ID requires
Core's existing `get_oracle_card` lookup (or the same callable interface); its
canonical name is resolved by the pinned engine's actual `CardRepository`. Legacy
entries without Oracle IDs use their stored names. This is name-based mapping of
Core Oracle identity to XMage; XMage does not provide a Scryfall Oracle-ID API.

A local stdin request asks the owned server to resolve each name with the preferred
set/collector number. The result must have the exact canonical name. Unsupported
cards produce individual entry-ID/error-code issues. Resolved data is not a second
persistent deck model. Private resolution response files are deleted after reading.

Mainboard quantities and sideboard cards are maintained. Core commander sections
and `commander_entry_ids` become engine sideboard commander configuration for the
Commander validator. Considering/excluded entries are ignored; unknown sections and
unresolved Oracle IDs fail explicitly. Original documents and artwork remain untouched.
Missing images do not prevent loading. If distinct selected printings collapse to
one engine printing and cannot be associated unambiguously, loading fails with
`AMBIGUOUS_INSTANCE_PRINTING`. Duplicate entries sharing the same printing retain
the printing/Oracle identity; their individual entry association is unknown.
Partners, backgrounds, and companions have not received acceptance coverage.

## State, identity, and visibility

Snapshots contain life, hand/library counts, mana, player counters, phase/step,
turn, active/priority seats, the local hand, battlefield, graveyard, exile,
command-zone commanders, stack, combat groups, choices, and available object actions.
They are complete supported views, not reconstructed deltas. Omitted unsupported
fields are named in the contracts. `None` means unavailable/unknown; zero and empty
collections remain valid known values. `left_game` is the engine's departure flag;
`eliminated` remains unknown because the client view has no explicit loss flag.

Object references are opaque Manaforge IDs, separate from printing IDs and deck
entries. References are stable for a continuously visible engine identity in one
zone. Leaving the zone, disappearing, or changing hidden status retires the reference,
even if the consumer skipped intermediate updates. Continuous characteristic changes
do not change the reference. Separate players have separate opaque object references.
The current client snapshot does not carry a zone-change counter: blink/re-entry
that completes between delivered snapshots is not yet verified and may retain a
reference incorrectly. This is explicitly listed as an incomplete identity capability.
Printing identities are attached only when the visible object's original engine
printing can be associated with its owner's deck.

The Java boundary constructs a view from each client's `GameView`, never an
unrestricted game snapshot. Opponent hand contents and library order are absent.
Face-down/engine-hidden objects omit names, rules, printing, and characteristics.
Python repeats the hidden-characteristics restriction and never restores concealed
names from a cache. Decisions and private prompts remain per-seat. Transcripts record
routing metadata only. JVM logs are local diagnostics, not a public event stream;
they must not be shared as player-safe telemetry. Permitted revealed/looked-at zones
are not yet fully translated, so some legitimately visible information is unavailable.

Characteristics are current engine view name, power/toughness, type line, color,
loyalty/defense, counters, transformation and copy/flip flags, damage, and tapped state.
Attachment references are translated when the corresponding objects are visible.
`engine_view_text` is the engine's view text, **not** a promise of fully dynamic Oracle
text or complete ability identities. No printed-text fallback is used. Copy provenance,
merged components, and complete dynamic ability text remain explicitly unsupported.

## Actions and decisions

Available object actions come from XMage's `PlayableObjectsList`; action hints use
its `PlayableObjectStats` categories. Attacker/blocker choices use the engine's
explicit possible-attacker/blocker lists. Targets and option identities come from
its prompts. The adapter does not decide whether a spell, ability, or combat is legal.

Every command includes the current seat, session-scoped decision token, and opaque
action/option reference. Consumed or obsolete decisions cannot be reused. The bridge
also checks game ID and engine decision sequence before sending a response.
Integer and multi-amount responses preserve engine constraints. Cancellation is
offered only when supported by the particular engine prompt.

XMage's mana prompt accepts object selections and validates usable mana abilities
on submission; its client API does not enumerate every legal payment source.
`select_mana_source` submits a current visible object for that engine check. It does
not claim every visible object can produce mana. A transport acknowledgement returns
`submitted`, not success. Consumers observe subsequent authoritative snapshots and
new decisions for the outcome. Timeouts or lost transport return `uncertain` and
must not be blindly retried. Public errors contain stable codes, not Java exceptions
or arbitrary private payloads. Unknown prompts fail explicitly.

## Compatibility and lifecycle

Compatibility includes the application version, game protocol, adapter version,
engine version, and artifact-manifest hash. Startup retains all existing artifact
SHA-256 checks, including the original configuration and runtime. There is no silent
engine download, repinning, or upgrade. Incompatible public protocol versions fail
before game creation. Actual game-type bounds are checked by XMage; the public setup
has no artificial five-seat maximum.

The adapter reuses `run_proof` process ownership and isolation. The public owner holds
the runtime in a worker until context exit; cleanup gracefully disconnects all player
bridges and then shuts down the server. Normal process exit codes and forced cleanup
are available through a sanitized `RuntimeReport`. Unrelated processes are untouched.
Duplicate/obsolete state and choice messages are ignored, command replies are
correlated only with outstanding requests, and game state stays per-seat.
Unexpected EOF, game errors, disconnection, or unsupported prompts report failure.
No session restoration or automatic reconnect/replay is claimed. An uncertain response fails the session explicitly rather than silently losing a
pending decision or guessing whether to replay it. Complete snapshots
are the only update format; no synchronization infrastructure was introduced.

For an engine upgrade: obtain the candidate separately, inspect its real Java API,
run the acceptance harness in an isolated workspace, review visibility/decision and
identity behavior, deliberately update the manifest and compatibility claims, and
rerun CI. Never edit the installed bundle or weaken hash validation to pass a run.
XMage is MIT licensed; preserve the engine license and all bundled dependency notices.
Distribution requires separate engine/JRE/dependency license review. This work does
not change packaging, redistribute binaries, or authorize a release.

## Reproducible verification

From the repository root in PowerShell, with the existing bundle and compiler:

```powershell
$env:PYTHONPATH = 'Mtg_Projects;Mtg_Projects/mtg_core'
python -m mtg_play.adapter_acceptance --scenario basic
python -m mtg_play.adapter_acceptance --scenario combat
python -m mtg_play.adapter_acceptance --scenario commander --seats 2
python -m mtg_play.adapter_acceptance --scenario commander --seats 3
python -m mtg_play.adapter_acceptance --scenario commander --seats 4
python -m mtg_play.adapter_acceptance --scenario commander --seats 5
```

`--output <path>` retains a JSON acceptance report. The harness's game logic interacts
only through the public adapter. It chooses scripted responses for its fixture decks;
these choices are not adapter policy or AI opponents. Engine directories and runtime
artifacts remain ignored. Existing CI runs `mtg_play/tests`; the existing lint/format
job also covers the new modules. Ordinary test suites were not run locally, per the
epic's workflow. CI cannot verify unpushed changes; no push or merge is authorized.

| Capability | Actual evidence/status |
|---|---|
| Two-player Core decks, independent opening hands, mulligans, land, cast, resolution, stale response, concession | Passed public adapter harness |
| Selected printing association and distinct visible objects | Public adapter harness plus boundary regression cases |
| Attacks, life loss, mana source payment, targets, P/T changes and expiration | Passed Giant Growth/Memnite combat scenario |
| Type/color change and expiration | Passed Snakeform scenario |
| Commander 2, 3, 4, 5 seats | Each passed command-zone, opening-hand, concession, result and normal-cleanup scenario |
| Numeric, multi-amount, modes/options, pile choices, supported cancellation | Implemented from pinned API/source; dedicated live coverage still pending |
| Trigger ordering, search, sacrifice, blockers, multiple commanders/companions | Mapping implemented where ordinary target/choice prompts apply; dedicated scenarios pending |
| Hidden hands, conservative face-down filtering, concealment, obsolete updates, interruption | Live independent-hand scenario and CI boundary regressions; broader live scenarios pending |
| Commander damage/tax | Unsupported structured fields: absent from pinned `PlayerView`/`CommanderView` interfaces; no Python rule calculation |
| Full dynamic abilities/text, copy provenance, merged components, restored sessions | Unsupported/unverified; never reported as working |

Live verification on October 28, 2026: basic public-adapter run
`20261028-184447-3ccb1462`; Commander runs `20261028-184951-fae35c71` (2),
`20261028-185052-fae47b56` (3), `20261028-185130-100f4457` (4),
`20261028-185208-de5ac8f5` (5); dynamic/combat run `20261028-185710-121009d2`.
All reported normal exit code 0 for every owned JVM, without forced cleanup.
These are retained under `.runtime`; the source and hashes reproduce setup.

The full epic remains open until the pending scenarios, CI, broader visibility,
Commander metadata, and unsupported mechanics are resolved or explicitly accepted
as reduced product scope. This adapter is a working foundation for those tasks,
not certification that every deck can complete every game.


Final dynamic/combat run at application version `0.4.4-alpha.1`:
`.runtime/20261028-190601-e03df3c5/result.json` and
`.runtime/final-public-acceptance.json` passed P/T and type/color changes, expiration,
combat damage, stable identity during continuous effects, selected printing
association on the battlefield, engine results, and normal cleanup of all three
JVMs. A regression check exposed XMage's empty-owner-name sentinel: [`PermanentView`](https://github.com/magefree/mage/blob/xmage_1.4.62V1/Mage.Common/src/main/java/mage/view/PermanentView.java)
leaves the owner name empty when the owner equals controller; the adapter now
translates that encoding explicitly. CI tests cover this mapping.

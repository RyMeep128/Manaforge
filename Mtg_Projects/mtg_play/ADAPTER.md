# Manaforge local gameplay adapter

The alpha adapter implements engine-backed local games without Qt, rendering,
AI, or remote multiplayer. Integration acceptance is implemented and has passed
locally against the pinned engine. **Consult the Tests workflow for CI acceptance
of a particular commit.** This does not certify every card or engine mechanic.

## Public API

`contracts.py` imports only the standard library. Frozen contracts serialize with
`to_dict()` and JSON. Game protocol 1 is separate from private bridge protocol 1.
Compatibility records the application version, adapter `0.2.0-alpha.1`, engine
`1.4.62-V1`, and the SHA-256 of `artifacts.json`.

```python
from mtg_play.adapter import LocalGameAdapter
from mtg_play.contracts import GameSetup, MatchSeat

setup = GameSetup((MatchSeat("alice", "Alice"), MatchSeat("bob", "Bob")))
with LocalGameAdapter() as adapter:
    game = adapter.create_game(
        setup, (alice_document, bob_document),
        oracle_lookup=core_repository.get_oracle_card,
    )
    events = game.poll("alice", timeout=0.1)
    view = game.snapshot("alice")
```

The trusted local owner authorizes seats. Each snapshot is a permitted player
view, but handing the root session to an untrusted consumer grants all seats.
Consumers serialize calls and run blocking operations on their own worker.
`SNAPSHOT_NOT_READY` means a coherent current frame is not available yet; poll
again. `None` means unavailable, distinct from valid zero or an empty collection.
Public values contain domain IDs, never engine UUIDs or Java class names.

`GameSession` provides `snapshot`, `poll`, `perform`, `choose`, `choose_number`,
`choose_amounts`, `select_mana_source`, `finish_selection`, `cancel`, and `concede`.
The fake `ScriptedGameSession` implements the same interface with supplied
snapshots and no rules implementation.

## Decks and object identity

Existing Core `DeckDocument`s are consumed without modification. Oracle entries
require Core's existing lookup; legacy entries use their stored names. The engine
CardRepository resolves canonical names and preferred set/collector numbers.
Canonical double-face names are accepted only when the engine confirms the exact
second face. Artwork is irrelevant to legality. Quantities and mainboard/sideboard
sections are preserved. Commander sections and `commander_entry_ids` map to the
engine's Commander configuration; partners and backgrounds are verified. Unknown sections and
unresolved cards produce individual `DeckIssue` codes. Unsupported companion
section encodings fail with `UNSUPPORTED_SECTION` rather than silently becoming
mainboard cards. Companions use the existing sideboard section. The engine validates their
restriction and exposes its optional pregame choice; Kenrith/Jegantha is verified.

Selected Core printing/Oracle identities remain separate from game objects.
Ambiguous associations fail with `AMBIGUOUS_INSTANCE_PRINTING`; duplicate entries
with the same printing retain that printing but have unknown individual entry ID.
Physical engine printing metadata preserves Clone's selected printing while its
live name and characteristics become Memnite's.

Opaque object references are per viewer and current incarnation. Zone changes,
visibility changes, disappearance, and the engine zone-change counter retire them,
including blink that completes between delivered frames. Continuous effects and
transformation preserve the appropriate reference. Commander designation IDs are
persistent and separate from current zone objects; hidden objects never acquire
a public designation link. Copy-source links exist only when both current objects
are visible and the source incarnation still matches; history is unsupported.

## Authoritative state and visibility

Snapshots include players, life, resources, loss/departure flags, turns, steps,
priority, permitted zones, stack, combat links, attachments, pending decisions,
and object actions. Commander state includes engine watcher damage, command-zone
play counts, and the engine-calculated additional casting cost. No tax or combat
formula is implemented in Python. Terminal commander metadata can be unavailable
(`None`) once the engine has removed the game controller. Such terminal views
list incarnation, physical-printing, commander and live-ability metadata as
unavailable in `unsupported_fields`. They do not guess printing associations from
a copied display face. Object reference continuity applies to active coherent
frames; controller removal ends that guarantee.

The Java client starts with its own scoped GameView. A narrow server metadata
reader supplies fields omitted from that view: incarnation counters, physical
printing, current permanent ability text, explicit owner/controller/loss flags,
and commander watchers. It intersects requested objects with the server's same
permitted player view and repeats hidden-identity checks. It never exports a Game,
Card, library, or unrestricted object collection.

This reader deliberately depends on private members of the pinned engine:
Main.server, its connector/manager factory, GameController.game, and HumanPlayer's
response monitor. Reads occur while the human response monitor is held and the
engine is waiting for an answer. Cached view and authoritative state cycles must
match before and after reading. Mismatches retry; missing interfaces fail with
`PINNED_METADATA_INTERFACE_CHANGED`; stalled metadata fails after 30 seconds.
The reader never answers a decision or changes authoritative state. Review these
anchors and quiescence assumptions on every engine upgrade.

Opponent hands and library order are absent. Face-down/hidden objects omit names,
printing, and characteristics at both boundaries. Permitted reveals, private
looked-at cards, top-card and companion observations are separately represented.
A `CardObservation` has no persistent game-object link, so a legitimate earlier
peek cannot track a concealed card. Authorized seat events retain what that seat
was allowed to learn; `observations_cleared` and the next coherent snapshot remove
current observations. The Gitaxian Probe scenario verifies private peek and clear
across both seats.

Characteristics expose current name, P/T, type, color, counters, loyalty/defense,
copy/transform/flip flags, damage, and tapped state where available. Permanent
`current_abilities` comes from live engine abilities, including copy/transform
changes. `engine_view_text` is the engine's presentation text, not a guarantee of
complete dynamic Oracle text. No printed-text fallback is used. Unsupported fields
(current rules text, ability identities, color identity, provenance history, merged
components) are explicitly named on `CardCharacteristics`.

## Commands, choices, and lifecycle

Object permissions come from PlayableObjectsList; category hints can be
`select_object` when the engine offers multiple kinds of operation. Targets,
attackers/blockers, modes, amounts and options come from actual prompts. The
engine validates every response. Mana prompts accept current visible source
selections; exhaustive legal mana-source enumeration is unavailable.

Commands carry the current seat and decision token plus opaque action/option IDs.
Obsolete tokens cannot answer a later prompt. Acknowledgement means `submitted`,
not resolution; observe subsequent snapshots for the result. Timeouts or lost
transport are `uncertain`, fail the session, and must not be blindly replayed.
Numbers and multi-amounts preserve constraints. `selected` supports target
selection/deselection. `can_finish` permits `finish_selection` without claiming
cancellation; `cancellable` separately permits `cancel`. Optional choices are
always exposed to the consumer, never answered as adapter policy.

Unknown decision families fail explicitly. Pile response mapping and both permitted pile contents are verified with Fact or Fiction. Legacy GAME_PLAY_XMANA, restored
sessions, automatic reconnect, and remote multiplayer are unsupported. Real
Walking Ballista X announcement/payment uses the supported number/mana path.

The existing runner owns only its launched processes in isolated `.runtime`
directories. Context exit disconnects all players and shuts down the server.
Closing with a pending choice is verified. Normal exits and forced-cleanup flags
are reported through `RuntimeReport`; unrelated processes are untouched. Obsolete
or duplicate state/decision/reply messages are ignored. Deferred metadata prevents
publishing incoherent or stale cached frames. Failed snapshots omit stale private
state. Boundary tests cover EOF, unknown prompts, stale replies and uncertain
commands; ordinary test execution belongs to CI.

Default transcripts contain routing metadata only. Public errors use stable
codes. Local JVM diagnostic logs can contain private engine data and must not be
shared as player-safe telemetry. CI uploads sanitized reports, routing transcripts,
and compiler diagnostics, not JVM logs.

## Acceptance and reproducibility

The additional [real-deck validation paths and baseline methodology](REAL_DECK_VALIDATION.md)
separate Commander loading/extended play from the deliberate Elemental/token/copy
stress fixture. Their implementation is awaiting CI evidence; they do not expand
the verified capability claims below.

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'Mtg_Projects;Mtg_Projects/mtg_core'
python -m mtg_play.adapter_acceptance --scenario basic
python -m mtg_play.adapter_acceptance --scenario transform
python -m mtg_play.adapter_acceptance --scenario commander --seats 5
```

Use `--output` for JSON reports; `--xmage-root` and `--jdk-path` override locations.
All fixture decisions use the public API. Fixture policies are harness scripts,
not adapter policy or AI. The existing Tests workflow runs boundary tests on
Python 3.12/3.13 and real-engine scenarios on 3.12 when adapter/Core/workflow paths
change. Engine acceptance still runs if unrelated ordinary tests fail; their job
remains failed and those failures are never suppressed. Manual input `verify_xmage`
forces acceptance regardless of changed paths.

`ci_prepare` downloads only explicitly pinned archives in `ci-artifacts.json`,
checks archive hashes, extracts into a new isolated directory, and verifies all
88 original installation artifacts. Existing destinations are never overwritten.
The official engine/JRE archives were downloaded and this bootstrap passed locally.
Normal adapter startup does not download or update an engine.

| Scenario | Live evidence on October 28, 2026 |
|---|---|
| basic | Core decks, independent hands, mulligans, land, cast, stack/resolution, stale rejection, result |
| combat | Giant Growth and Snakeform P/T/type/color changes, expiration, attacks and damage |
| identity | Cloudshift blink creates a new incarnation while preserving physical printing |
| commander-play | Isamaru cast, command-zone play count, engine tax and commander combat damage |
| commander (2/3/4/5) | Each actual seat count: command zones, opening hands, concession and results |
| partners | Rograkh/Yoshimaru: two independent commander designations and selected printings |
| background / companion | Wilson/Raised by Giants designations; Kenrith/Jegantha optional pregame choice and public companion |
| piles | Fact or Fiction split, both pile contents, chosen pile and spell resolution |
| visibility | Gitaxian Probe private peek only for authorized seat, then current observation cleared |
| number / modes / sacrifice | Ballista X/payment; Evolution Charm mode/search; Diabolic Intent sacrifice/search |
| distribution | Pyrotechnics two targets, selected targets, finish-selection, constrained damage allocation |
| triggers | Two Soul Wardens: explicit trigger ordering and resulting life gain |
| copy / transform | Clone physical printing with copied characteristics; Delver name/ability transformation and stable identity |
| blockers | Distinct Memnites, attacker/blocker links and both creatures dying in combat |
| cancellation | Cancel Ballista payment, return to hand, stale rejection, successful recast |
| string-choice | Utopia Sprawl chooses Blue and resolves with attachment |
| interruption | Close with pending choice, later access rejected, normal process cleanup |

Every listed completed scenario reported all owned JVMs exiting 0 without forced
cleanup. Reports are retained locally under ignored `.runtime`; no ordinary local
pytest result is claimed. CI reports are separate from this local evidence. Arbitrary card mechanics remain uncertified;
capability claims describe the demonstrated fixtures rather than inferring
universal support from engine presence.

CI acceptance at commit `dc32e0e` passed all 24 real-engine scenarios, with normal
cleanup, and all adapter boundary tests on Python 3.12 and 3.13. The full workflow
at that commit remained red solely because of three pre-existing Editor/library
test failures. See the [Tests run](https://github.com/RyMeep128/Manaforge/actions/runs/40803512696).

For upgrades, obtain a separate candidate bundle, inspect real interfaces and the
metadata reader's private anchors, run all scenarios, review privacy/identity,
and deliberately update archive/artifact hashes and compatibility. Never edit the
original installation or weaken integrity checks. XMage is MIT licensed; preserve
its license and bundled dependency notices. Engine/JRE/dependency redistribution
requires a separate license review. This work does not package binaries, create
releases/tags, or authorize pushing/merging.

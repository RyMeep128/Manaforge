# Python protocol inventory — P1.1

Status: source inventory, pending review and CI. Not a frozen Java/C# wire schema,
captured engine transcript, or G1 acceptance. See the [migration roadmap](../../../docs/play-unity-java-roadmap.md).

`python-api-inventory.json` records every frozen dataclass field, type/default,
`GameSession` signature, protocol/adapter version and pinned artifact manifest hash.
It is generated without importing the application or starting an engine:

```powershell
python tools/export_play_protocol_inventory.py
python tools/export_play_protocol_inventory.py --check
```

Review generated changes before accepting them. Uppercase string candidates are
source locations for error review, not an exhaustive public error enum; dynamic
codes and lower-level exceptions still require inspection. The pinned manifest
hash is over exact file bytes, matching runtime compatibility behavior.

## Existing boundaries

| Boundary | Existing behavior | Migration requirement |
| --- | --- | --- |
| Setup | `GameSetup`, variable `MatchSeat`s, format; local human/engine AI | Independent controllers/seats; no five-seat protocol maximum |
| Owner | `LocalGameAdapter` context, compatibility, capabilities, deck validation, create/close, runtime report | Authenticated gateway owner and isolated runtime workspace |
| Read | `snapshot(player_id)`, `poll(player_id, timeout)` | Viewer-bound snapshots/events; never expose root multi-seat session |
| Actions | `perform`, `choose`, `select_mana_source` | Current session/seat/decision and exact engine action/option/object authorization |
| Numeric | `choose_number`, `choose_amounts` | Preserve integer type, per-value and aggregate bounds |
| Selection | `finish_selection`, `cancel` | `can_finish` and `cancellable` are distinct permissions |
| Result | `CommandResult`, snapshot status/result, events | Submission is not resolution; never replay uncertain commands |
| Shutdown | `concede`, owner `close`, `RuntimeReport` | Concession acknowledgement does not establish terminal result; track cleanup separately |

The current Python session API has no explicit revision argument, public wire
command envelope, seat credential, negotiation handshake, or deserializer.
`to_dict()` uses dataclass recursion; JSON converts tuples into arrays. Type hints
are not wire validation. P1.2 must define parsing, limits, unknown fields,
compatibility, revision policy and authenticated command/session binding rather
than assume those guarantees already exist.

## Visibility, identity and unsupported state

- `CardIdentity` separates Oracle, selected printing and deck-entry identity.
  `GameObject.object_id` is viewer/incarnation scoped, not persistent deck identity.
  Blink, hidden transitions and skipped intermediate frames retire references.
  Commander designations are separate; copied characteristics do not replace artwork.
- Hidden objects omit characteristics/printing. Opponent hands/library order must
  not travel to the renderer. Engine metadata is intersected with the same viewer.
- `CardObservation` represents permitted reveals/private peeks without persistent
  object links. Clearing observations removes current observations, not knowledge
  from already-authorized events. Tokens, artwork caches and logs need equal care.
- `None` is unknown/unavailable, distinct from zero and empty. Preserve all
  `unsupported_fields`, including terminal metadata loss. `current_abilities` and
  `engine_view_text` are not complete dynamic Oracle text.
- Preserve combat assignments, attachments, current P/T/type/color/counters,
  transformation/copy/flip, mana, elimination and commander damage/cost/play state.
  The inventory lists exact fields; no derived rules formulas belong here.

## Decisions, errors and evidence

Engine prompts cover priority/actions, targets, attacks/blocks, options/modes,
mana, numbers, amount distributions, ordering, piles and optional selections.
Unknown families fail explicitly. Mana-source selection is engine-validated;
the adapter does not claim exhaustive legal-source enumeration.

The contract permits submitted/confirmed/rejected/uncertain. Existing `_submit`
normally returns submitted on acceptance; later state establishes actual effects.
Lost acknowledgements or engine availability can leave uncertain outcomes and fail
the session. Preserve stale-decision/object rejection, unavailable coherent frame,
unsupported cancellation, invalid amounts and closed/unauthorized-seat errors.
AI seats cannot be inspected or commanded through the human session boundary.

Use [ADAPTER.md](../ADAPTER.md) for existing scenario evidence and limitations.
`tests/test_adapter.py` covers serialization, hidden printing scrubbing, incarnation
retirement, private observations, stale/consumed prompts, disconnect/uncertainty,
amounts, selection completion, metadata coherence, commanders and AI seat isolation.
`tests/test_server_responses.py` and Java bridge scenarios cover actual translation;
existing real-engine scenarios cover 2–5 seats and complex choices. Test existence
does not establish acceptance of a new commit.

Native `DeckDocument` remains persistent truth. `decks.py`/`PreparedDeck` are
internal translation, not a new deck file. Preserve exact printing mappings,
unresolved-card/section errors and commander/partner/background/companion checks.

P1.2 still requires reviewed schemas, sanitized golden scenarios and shared
Java/C# consumers, including positive/negative/privacy fixtures. P1.3/P1.4 still
require launch-manifest and process-lifecycle contracts. None is completed here.

## P1.2 baseline schema and fixtures increment

`python-contracts-v1.schema.json` exports the current serialized DTO baseline in
JSON Schema Draft 2020-12. It covers every existing dataclass, including nullable
fields, fixed-length pairs, variable arrays, enum outcomes and protocol version.
Concealed objects cannot carry characteristics, printing identity, commander or
copy-source links; concealed observations cannot carry card names or printing data.

`fixtures/python-baseline-v1.json` is generated by the current adapter using
synthetic inputs from the existing test harness: visible/concealed objects,
mulligan, numeric choice and failed session/events. Four outcome examples are
constructed DTOs, including confirmed; they are not engine observations. Inputs
contain no user decks or private match data. Opaque IDs are deterministic fixture
IDs, and provenance includes normalized-source hashes. No real engine starts.

```powershell
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe Mtg_Projects/mtg_play/tests/generate_protocol_fixtures.py
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe Mtg_Projects/mtg_play/tests/generate_protocol_fixtures.py --check
./Mtg_Projects/mtg_proxy/venv/Scripts/python.exe -m pytest Mtg_Projects/mtg_play/tests/test_protocol_schema.py -q
```

The baseline requires all fields emitted by `to_dict`, including defaults, and
rejects unknown properties. This is a conservative artifact check, **not the final
network compatibility/unknown-field policy**. Python constructors still accept
their existing defaults. No runtime code starts validating or rejecting existing
application traffic in this increment. The schema does not establish ownership,
revision freshness, permitted-zone membership, duplicate-key rejection, bounded
wire parsing or action authorization; those require the future transport/session
boundary and adversarial shared-consumer tests.

Focused tests cover valid fixtures and invalid version, missing fields, booleans
used as integers, negative revisions, malformed pairs, unknown properties/outcomes
and concealed identity leaks. Existing adapter tests remain intact. CI checks
regeneration drift and runs these tests with the existing Play tests.

Still pending before P1.2/G1: actual Java/C# consumers of the shared artifacts,
wire commands/envelopes, handshake/authentication, acknowledgements/error mapping,
engine-derived complex/reveal/terminal golden transcripts, shared negative cases
and dummy-process exchange/shutdown. The added fixtures are a reviewable baseline,
not a frozen replacement protocol or a completed parity claim.

References: [JSON Schema tuple semantics](https://json-schema.org/draft/2020-12/release-notes)
and [validator documentation](https://python-jsonschema.readthedocs.io/en/v4.23.0/validate/).

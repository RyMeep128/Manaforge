# Python protocol inventory — P1.1

The private [launch boundary](../../../docs/play-launch-boundary.md) adds a separate
native-deck export schema and Java-only DTOs. It is never a Unity snapshot or a
second persistent deck format.

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

P1.2 still requires a reviewed wire contract and engine-derived golden scenarios.
The fixture consumers below add Java/C# checks without completing G1. P1.3/P1.4
still require launch-manifest and lifecycle contracts.

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

Still pending before P1.2/G1: wire commands/envelopes, handshake/authentication,
acknowledgements/error mapping and engine-derived complex/reveal/terminal transcripts
and dummy-process exchange/shutdown. The added fixtures are a reviewable baseline,
not a frozen replacement protocol or a completed parity claim.

References: [JSON Schema tuple semantics](https://json-schema.org/draft/2020-12/release-notes)
and [validator documentation](https://python-jsonschema.readthedocs.io/en/v4.23.0/validate/).


## Generated Java/C# fixture consumers

`tools/generate_play_models.py` emits every DTO from the schema into
`java/manaforge/protocol/PlayContracts.java` and Unity's
`Assets/Manaforge/Runtime/Protocol/PlayContracts.cs`. Do not hand-edit outputs.
The generator records the normalized schema hash, checks drift and rejects
schema keywords outside the subset implemented by both test validators.

Both consumers validate the same 14 positive and 12 negative cases, then round-trip
positives through generated types. Negatives cover missing viewer, wrong version,
unknown fields, invalid life types, negative revision, malformed pairs, concealed
identity links/printing and unknown outcome. Positive setup/printing examples are
DTO-only: two seats include a human and AI; five seats test variable configuration
without implementing multiplayer. Neither model imports XMage types.

```powershell
python tools/generate_play_models.py
python tools/generate_play_models.py --check
python tools/check_play_java_protocol.py
./tools/unity-play.ps1 -Mode EditMode
```

Java requires `javac`/`java` on PATH, compiles Java-8-compatible classes into a
temporary directory, and verifies Gson 2.13.2 against the existing XMage artifact
hash. It uses the installed pinned jar or an explicit `--gson` path.
`--download-gson` explicitly permits that hash-pinned Maven Central download for
CI. No engine installation/startup or upgrade occurs.

Unity uses official Newtonsoft JSON package 3.2.2, pinned in manifest/lock.
EditMode reads shared fixtures directly; the corpus is not copied into the player.
Newtonsoft type-name loading is disabled. The independent `Play protocol fixtures`
workflow compiles/runs Java without Unity or XMage. Tests also checks model drift;
C# checks remain in the licensed Unity workflow.

These are **test-only schema-subset readers**, not production parsers or complete
Draft 2020-12 implementations. Mutable generated DTOs are intermediate values, not
immutable viewer snapshots for rendering. They use 64-bit integers and token arrays
for heterogeneous pairs. Final integer limits, immutability, duplicate-key/depth/
size handling, unknown-field negotiation and authenticated current-decision routing
remain wire-boundary work. No Unity scene uses these DTOs for live actions or
receives a root all-seats session.

Local evidence: Java round-tripped 14 positives/rejected 12 negatives; Unity's
eight EditMode checks passed, including both fixture-consumer checks. CI review
is every third commit; pending CI permits continued development but is unverified.


## Bounded text framing foundation

See [text framing v1](text-framing.md) for the shared Java/C# four-byte length
prefix, 1 MiB byte cap, strict UTF-8, safe error codes and shared adversarial
fixtures. Local Java checks and 28 Unity EditMode tests pass. These codecs do not
parse JSON, authenticate a peer or dispatch gameplay; dummy process exchange,
shutdown and G1 acceptance remain pending. The Java protocol CI helper includes
the framing corpus without starting Unity or XMage.


## Strict JSON envelope foundation — G1 remains open

`wire-envelope-v1.schema.json` defines a header with exactly `wire_version` (1),
`message_type`, `message_id` and object `body`. The type vocabulary is hello,
snapshot, command, ack, event, result, shutdown and error. Message IDs use 1–128
ASCII letters/digits/underscore/hyphen. IDs correlate messages; they confer no
identity or authorization. This header version is separate from existing DTO
protocol versions and does not establish a compatibility handshake.

Java/C# `WireEnvelope` readers validate strict JSON, reject duplicate keys at
every object depth (including escaped aliases), preserve date-like strings,
reject lone surrogates/BOM/comments/trailing data, enforce 32 container levels
including the envelope, and cap encoded text at 1 MiB. This initial protocol
accepts signed 64-bit integer numbers only: decimal/exponent syntax is rejected
rather than silently rounded or coerced. No current DTO requires float values.
A future fractional field requires an explicit compatible contract decision.

The schema expresses structure, not lexical number spelling, duplicate-key or
nesting checks; the readers enforce those extra wire constraints. The C# reader
uses a bounded lexical guard before Newtonsoft, which otherwise accepts several
non-JSON spellings and replaces lone escaped surrogates. Java uses strict Gson
streaming with duplicate detection. Both return JSON trees, not separately
maintained typed models; generated existing DTOs remain unchanged. No type-name
or polymorphic object loading is enabled. Trees remain intermediate mutable data.

The five positive/25 negative shared cases in `fixtures/wire-envelopes-v1.json`
run in Java's existing hosted protocol helper and Unity's focused EditMode suite.
A focused Python check validates the corpus against the schema. Local Java checks,
30 Unity EditMode checks and the focused schema check pass. CI remains pending.

**Bodies are unvalidated.** Never dispatch these trees directly or treat a valid
header as a viewer-safe snapshot. Still required: per-message body schemas,
compatibility/seat authentication, session/revision/decision/action binding,
acknowledgement outcomes, stale-command rejection, unknown-field evolution,
private DTO validation, deadlines/cancellation, and the actual dummy exchange.
Unknown header fields/types/versions currently fail closed. Before enabling any
future extension, negotiate and test its handling in both consumers.

Readers expose only JSON_INVALID, JSON_DUPLICATE, JSON_DEPTH, ENVELOPE_INVALID or
ENVELOPE_VERSION; never reflect raw content in diagnostics. Multiple defects may
fail at the first parser-specific check; no recovery/replay is implied. Framing,
JSON and semantic validation are distinct layers. Run these readers on workers.
No socket listener, real engine, launcher or gameplay dispatcher is introduced.


## First command-body slice

[Command boundary](command-boundary.md) documents the new perform/ack/shutdown
schema and shared Java/C# readers. Commands bind session, viewer, revision,
decision and action IDs; a current-context comparison rejects stale/mismatched
values without duplicating game rules. Submitted, confirmed, rejected and
uncertain remain distinct. Other bodies/families, real authentication, pending
tracking and dummy exchange remain pending. Local checks: six positive/19
negative body cases, six current-context cases, 33 Unity EditMode checks and two
schema checks passed. See that guide for this increment's scheduled CI snapshot.


## Viewer authentication primitive

[Viewer authentication](viewer-authentication.md) defines the separate per-seat
credential audience, hello schema and ordered HMAC transcript. Java/C# pass two
independent known answers, 14 tamper cases and single-use/concurrent verification
checks. Local focused evidence: 37 Unity EditMode and three schema checks passed.
This does not deliver bootstrap credentials, open a listener or exchange actual
peer messages. Private launch delivery, both-direction handshake and G1 remain
pending. Never pass owner credentials or the all-decks manifest to Unity.


## Actual dummy process exchange

The [dummy exchange](dummy-exchange.md) now runs an owned Java loopback peer
against a Unity EditMode C# client, with private pipe bootstrap, mutual viewer
proof, mock snapshot/action, stale/pending rejections, submitted ACK,
fixture-only result and clean shutdown. Wrong-key and owner-EOF scenarios also
pass. Python is used for build preparation only. Local evidence: 40 Unity
EditMode tests, the Java corpora and four schema checks passed. This is neither
packaged-player gameplay nor final public snapshot/result validation; G1 and CI
acceptance remain pending.


## Viewer-bound receive validation

The [receive boundary](receive-boundary.md) now validates snapshot/event/result
bodies from generated existing DTO schemas, then binds viewer/session/revision
and fixture mode before deserialization. The dummy exchange exercises these
checks in both languages. Local evidence: eight positive/24 negative receive
cases, 42 Unity EditMode checks and five schema checks passed. No engine privacy
filter, immutable renderer projection or G1 completion is claimed. See the guide
for the scheduled protocol CI snapshot; licensed Unity CI remains pending.


## Pending and uncertain client commands

[Command acknowledgement tracking](command-tracking.md) now binds receipts to
registered session/viewer/command/revision, preserves pending and uncertain state,
rejects ID reuse/conflicting receipts and prevents blind replay after disconnect.
The live dummy exchange uses it. Local evidence: 53 focused Unity EditMode
checks passed, including Java process scenarios. This is C# client bookkeeping;
Java engine deduplication/reconciliation and licensed CI remain pending.


## Choice command-family shapes

The [choice-family contract](choice-commands.md) now covers option IDs, mana-source
IDs, signed numbers/amount vectors, finish and cancellation alongside perform.
Both consumers enforce exact fields and bounded values; context comparison is
explicitly separate from legality. Concession and real gateway choice execution
remain pending. Local checks: 12 positive/37 negative bodies, 12 choice-binding
cases, amount-vector bounds, 56 Unity EditMode and six schema checks passed.
No G1 completion or actual choice gameplay is claimed.


## Java duplicate submission reservations

The [submission ledger](submission-ledger.md) now retains session/viewer-bound
receipts, returns history for identical retries and refuses changed contents
under an existing command ID. Uncertainty/capacity cannot silently permit replay.
The live dummy uses it, including duplicate and conflict probes. Java checks and
57 Unity EditMode tests pass locally. This reserves protocol submissions; it is
not actual engine exactly-once execution or crash reconciliation. The linked
guide records this increment's scheduled protocol CI snapshot.


## Terminal session-channel failures

[Session errors](../../../docs/play-session-errors.md) add a shared version-1
terminal error body with fixed safe categories and authenticated session/viewer
binding. The C# command tracker preserves pending uncertainty and refuses further
submission/reconnect after valid or malformed terminal error input. A fifth
owned Java↔Unity dummy scenario proves submitted ACK → session error → EOF without
a result. Six positive/23 negative corpus cases, 80 focused EditMode checks and
seven schema checks pass locally. This does not prove actual engine failures,
production cleanup, licensed CI or G1 completion.


## Bounded receive history

[Receive history](receive-history.md) adds matching Java/C# admission for an
ordered authenticated viewer stream: duplicate IDs with identical content are
dropped, conflicting IDs/rollback/full history fail closed, and results terminate
new data. IDs/digests are bounded and raw private messages are not retained.
Ten shared sequences plus mutation/concurrency/disposal checks pass; the real
Java-dummy exchange now drops a repeated snapshot. Local evidence is 86 focused
EditMode and eight schema checks. Missing-event detection, rejoin/recovery and
immutable renderer projections remain pending; no G1 completion is claimed.

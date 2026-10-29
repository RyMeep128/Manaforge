# Real-deck compatibility and complex-board baseline

Status: implemented acceptance paths, awaiting CI evidence. No new live-engine
results or numerical baseline are claimed in this change. The existing 24
scenarios remain enabled with their integrity and privacy checks intact.

CI run [40884348259](https://github.com/RyMeep128/Manaforge/actions/runs/40884348259)
passed all 24 original engine scenarios and the Python suites on both versions.
Its real-deck scenario failed at an unhandled boolean decision. The pinned
Mind's Eye implementation uses `DoIfCostPaid` to ask `Pay {1} and draw a card?`;
the fixture now explicitly declines that payment while retaining its mana policy.
Other unfamiliar booleans still fail. The routine `optional-payment` scenario
forces this trigger with a redundant deck, independently of shuffled Commander
draws. Unsupported decision reports now retain a bounded family suffix without
exporting prompt text. These new checks await the next CI run.

## Reproduce

Use the existing Tests workflow. Routine pinned-engine acceptance now also runs
`real-decks`. For the heavier board baseline, manually dispatch Tests with
`stress_xmage=true`; that input also forces engine preparation. No engine upgrade,
external card service, user deck, UI, AI or networking feature is required.

For an explicitly requested verification outside chat, the existing CLI supports:

```powershell
$env:PYTHONPATH = 'Mtg_Projects;Mtg_Projects/mtg_core'
python -m mtg_play.adapter_acceptance --scenario real-decks --output real-decks.json
python -m mtg_play.adapter_acceptance --scenario complex-board --output complex-board.json
```

CI uploads these JSON files with the existing sanitized acceptance artifacts.
Failure reports retain diagnostic codes/categories and available runtime cleanup
results. Raw JVM logs, prompt text and source decks are not uploaded by this work.

## Evidence boundaries

| Path | Assertions required for a successful report | Limits |
| --- | --- | --- |
| real-decks | Two public synthetic 100-card singleton Commander documents; commanders visible; each participant reaches turn 12 or later and resolves at least two artifacts; selected M10 Forest printing remains associated; documents unchanged; authoritative results for both seats | Does not certify every included card, Commander synergy, interaction, or competitive deck quality |
| complex-board | Each viewer sees a board with distinct Elemental token and Clone identities, multiple Master of Waves bonuses, relevant permanents for both players; Intruder Alarm produces explicit trigger ordering; two token attackers share combat; Evacuation receives a Counterspell response; at least two stack objects observed; counter and wipe reach graveyards; a later wipe removes tokens; turn 12 or later and authoritative terminal results | High-redundancy freeform fixture, not a legal Commander list; creature combat damage is covered separately by the existing scenarios |
| existing scenarios | Trigger ordering, combat, continuous-effect expiration, blink incarnation, selected Clone printing, private reveals and the other existing targeted checks | Evidence remains scenario-specific; combining passing isolated tests does not prove all interactions |

Both new paths terminate by scripted concession **after** their evidence gates.
They do not claim natural victory, exhaustive rules support, or visual grouping.
The complex fixture uses the same public session operations as existing acceptance;
it never injects board state or controls the Java engine directly.

Fixture version 1 lives in `real_deck_fixtures.py`. Animar Elementals and Rhys
Tokens include multicolor mana, rocks, activated/triggered abilities, tokens,
copies, wipes and interaction. Engine loading resolves all entries, but successful
resolution proves card availability only. Name-only entries have no fabricated
Oracle or selected-printing ID. Explicit printing requests now fail rather than
binding a requested identity to the engine's fallback printing.

Deck lists and decision policies are reproducible; XMage shuffles are not seeded
through this API. Draw order, exact turn of completion and timings vary. A timeout
is a failed verification, never a passed compatibility claim. Repeated CI runs are
needed to characterize variance and establish reliability.

## Performance report interpretation

Successful gameplay reports include `performance` counters: count, total and
maximum milliseconds for snapshot calls, metadata enrichment, and command reply
round trips. Snapshot latency includes pumping/enrichment; these metrics overlap
and must not be added. Snapshot timing includes unsuccessful/not-ready calls in
its overall counter; successful calls also appear in object-count bands 0–15,
16–63 and 64+. Command reply latency measures submission acknowledgement, not
spell resolution. Metadata counts include coherence retries.

Reports also record maximum visible object, stack-object and decision-option
counts. Stack objects include spells and triggers; decision options are the
currently offered volume, not an unrestricted server-side trigger queue. No
private engine collection is inspected to infer unavailable queue state. Owned
JVM memory/CPU observations remain unavailable; no Python-only resource figure
is presented as engine memory usage.

The first passing CI artifacts establish the initial baseline. Compare reports
with identical compatibility tuples, fixture version, workflow runner and Python
version; retain several runs before selecting budgets. No arbitrary performance
thresholds or speculative optimizations are introduced.

## Diagnostics and outstanding acceptance

`DeckIssue.category` and CLI failure reports distinguish missing pinned-engine
cards, identity/printing resolution, unsupported deck configuration, unsupported
decisions, and adapter translation failures. Remaining engine/harness failures
are explicitly categorized as unexpected and retain their original code; they
are not mislabeled as unsupported cards.

Pending evidence: all new CI scenarios, the unchanged 24-scenario regression run,
measured baseline values, reliability across shuffled games, and
the full Elemental Commander interaction scenario from the Play epic. The
single freeform stress path is a narrower validation step, not completion of that
epic acceptance gate.

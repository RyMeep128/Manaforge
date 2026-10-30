# Java submission receipt ledger — G1 increment

Status: viewer/session-owned Java receipt history and dummy transport integration
implemented. No XMage calls, engine-rule port, real confirmation or crash recovery.
Existing wire schemas/outcome values remain unchanged; G1 stays open.

## Reserve once, return history on a retry

`SubmissionLedger.prepare` validates a supported command and binds it to the
ledger's trusted session/viewer. Before a future dispatcher may submit anything,
it records one submission reservation and returns shouldSubmit=true with a
submitted ACK. The caller must honor that reservation on the serialized gateway
worker. This is not a claim of exactly-once engine execution or delivery.

An identical command ID/envelope returns the cached current receipt with
shouldSubmit=false. JSON property order/spacing does not change identity. Changed
contents under an existing ID fail COMMAND_ID_CONFLICT; the connection must close
without resubmission or replacement of the original record. Invalid/unknown
command fields still fail the existing strict parser.

For a new ID, the caller supplies a pure current-state admission rejection or
null. That admission check must never execute an engine operation. Actual
legality, tokens, decision-family constraints and confirmation remain gateway/XMage
responsibilities. The caller must serialize admission, reservation and the one
engine submission; this ledger itself cannot prove that a dispatcher honored it.
A new request while another is pending is recorded as rejected/COMMAND_PENDING.
Repeated rejected requests retain that rejection even if current state changes;
a retry is not a fresh action with a new decision token.

## Outcomes and uncertainty

`recordOutcome` accepts only a registered command and an existing valid ACK
outcome/code pair. Trusted engine-correlated evidence is required to call it with
confirmed/rejected; a successful write, ACK send or game result is insufficient.
Identical repeated terminal outcomes are harmless, and contradictory terminal
outcomes fail ACK_CONFLICT without overwriting history. An old completed record
cannot release a different active command.

`disconnected` marks an active reservation uncertain and retains its ID/payload.
Identical retries then return uncertain without reserving another submission.
A late submitted update cannot downgrade that uncertainty. Only a correlated
terminal outcome resolves it. This API does not implement reconnect, engine
query/reconciliation or durable recovery; losing the ledger in a process crash
is not evidence that a command had no effect.

Records are bounded by an explicit capacity (1–65536; the dummy uses 4096).
Capacity exhaustion fails COMMAND_HISTORY_FULL rather than evicting IDs that
could then be replayed. This is operational scaffolding, not accepted long-game
or Commander capacity. Before long-session acceptance, provide bounded history
compaction/reconciliation without weakening duplicate protection. Never replace
or close the ledger merely to bypass uncertainty/capacity in the same live game.

Methods serialize concurrent access. Prepared receipts are defensive copies and
cannot mutate stored history. Only strict command fields are retained: IDs,
revision, operation/arguments and outcomes, without snapshots, card artwork,
credentials or all-seat state. Close clears records and forbids reuse; managed
memory erasure is not guaranteed. A real session owner must retain unresolved
records until engine/lifecycle cleanup is established.

## Actual validation

The Java fixture consumer checks duplicate/canonical retries, changed-payload ID
conflicts, one pending reservation, uncertain retry, correlated terminal outcomes,
old receipts versus a newer reservation, capacity, closed ledgers, defensive
copies and concurrent calls yielding one reservation. It uses the existing
public synthetic command fixture, not real decks.

The actual Java↔Unity EditMode exchange now uses this ledger. The happy path
makes an intentional raw retry probe and receives the cached submitted ACK,
without another fixture result. A separate scenario changes the request revision
under the same ID and verifies socket EOF/child rejection exit 2. Normal client
tracking still prevents ID reuse; these raw probes are test-only adversarial
traffic. The dummy remains perform-only and starts no engine or descendants.

Local evidence: Java ledger and existing protocol corpora passed; 57 focused
Unity EditMode tests passed, including four owned Java-process scenarios. No full
suite, engine game, screenshot or new packaged UX is claimed.

Scheduled protocol CI: [receive validation at 6999f53](https://github.com/RyMeep128/Manaforge/actions/runs/41098486977)
and [client tracking at b6be577](https://github.com/RyMeep128/Manaforge/actions/runs/41099384156)
passed. [Choice contracts at 30920a8](https://github.com/RyMeep128/Manaforge/actions/runs/41100188056)
were still running and deferred without waiting. Those hosted jobs do not run
Unity. Licensed Unity CI and this commit's verification remain pending. Qt CI
is outside this work at owner direction.

Remaining: actual engine-correlated confirmation/reconciliation, private product
bootstrap, choice dispatch, transport queue/cancellation ownership, process
containment, immutable viewer projections and licensed CI. Do not retire the
fallback or start the bulk P2 port on this evidence.

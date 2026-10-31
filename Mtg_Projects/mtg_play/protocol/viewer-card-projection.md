# Viewer-scoped immutable card projection

Status: card-slice foundation, not full renderer/session integration or G1 acceptance.

`ViewerCardProjection.ParseSnapshot` is a worker-side boundary between the
existing validated receive contract and future scene handoff. It consumes a
snapshot/result envelope plus trusted session, viewer, minimum revision and
explicit fixture mode. It reuses `ReceiveMessages` validation: malformed data,
wrong sessions/viewers, stale revisions and concealed identity leaks fail before
any projection is returned. Events are rejected because they are not complete
card frames. Existing channel/inbox history still owns ordered delivery,
deduplication, terminal state and revision tracking; this stateless projection
cannot replace those responsibilities or authenticate an arbitrary JSON string.

The output is a card-only `ProjectedCardFrame`, with shared immutable context
and read-only collections. Every card carries that context, so object IDs cannot
be mistaken for persistent or cross-viewer identities. No JSON token, mutable
wire DTO, deck-entry identity, legal-action list, prompt or private observation
is retained. There is no static card cache. The existing wire-size bound and a
4096-object defensive allocation ceiling apply; the latter is a resource limit,
not an engine rule, seat limit or claim of rendering performance.

Visible cards retain the supplied printing/Oracle IDs independently of current
name, P/T, counters, loyalty/defense, copy/transform/flip flags and permitted
relationships. Unknown fields remain null; explicit zero, false and empty arrays
remain distinct. Concealed cards retain only context, opaque object ID, zone and
owner/controller routing; all artwork/characteristic/relationship data is absent.
A face-down flag alone does not infer another printing or face. Asset lookup,
layout selection and an authoritative face-selection contract remain subsequent
work; this slice never guesses artwork from a name or transform flag.

`engine_view_text`, `current_abilities` and `unsupported_fields` remain separate,
read-only properties. As [ADAPTER.md](../ADAPTER.md) states, engine presentation
text is not guaranteed complete dynamic Oracle text. There is no automatic
conversion to `CardDisplayValues.RulesText`, no printed-text replacement of
unknown current text, no extracted ability identities and no legality inference.

The consumer must dequeue and dispose its `ReceivePacket`, project on a worker,
then hand the immutable result to the UI. It must still reject obsolete handoffs,
clear prior views/inspection/animations and release prior frame references on
viewer change, disconnect or teardown. This increment does not add that UI owner,
private artwork-cache destruction, session bootstrap or live gateway dispatch.
It introduces no new wire schema or persistent deck model.

Focused checks reuse every valid snapshot/result and every invalid receive
fixture, including concealed-data rejection. Additional checks cover null versus
zero/false/empty, concealed relationship suppression, current copy name versus
exact printing, unsupported current text, read-only collections, no mutable JSON
escape, event rejection and missing trusted context. No visual behavior changes.

Local validation at 0.5.84-alpha.1: 313 Unity EditMode checks passed, including
ten new projection checks and the existing Java protocol preflight. No full
application suite, visual build acceptance or live engine parity is claimed.

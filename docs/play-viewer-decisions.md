# Immutable viewer decision projection

Status: P3.4 data boundary at 0.5.100-alpha.1. No new decision controls or outgoing
commands are enabled. The session fixture's owner UI review remains pending.

ViewerDecisionProjection turns an already versioned snapshot/result envelope into
a small immutable UI slice. It reuses the card projection's receive validation:
authenticated expected session/viewer, monotonic minimum revision, strict shape,
seat-scoped decision actor, unique IDs, visibility and explicit fixture mode.
Events cannot masquerade as decision snapshots. Mutable intermediate JSON stays
inside the worker projection boundary; generated wire DTOs remain unchanged.

The frame retains status, actions_complete, unsupported_fields, engine-offered
actions and the optional decision. It copies exact action/option/decision IDs,
labels, object/player references, priority class, family, prompt, selection flags,
minimum/maximum, cancellation/finish/priority flags and ordered amount constraints.
Actions/options share their frame's immutable context and current decision ID;
actions without a decision retain a null binding. No token or legal option is
generated. The existing immutable viewer/revision context is reused rather than
creating another persistent game or deck model.

Null bounds/defaults remain distinct from zero. Selected flags and engine defaults
are display data, not instructions to choose or submit. Unknown families and
inconsistent numeric constraints are preserved without client interpretation;
the existing channel owns numeric-command validation. Amount order is retained;
labels are never converted into invented option IDs. No card printing, deck entry,
card characteristics, observations/reveals or root all-seat information is added.
Prompts and option labels may themselves be private viewer data: never log them
or apply them to another viewer epoch.

This frame is not command authorization. Before future controls submit anything,
their binding must still match the captured host/viewer epoch, current session,
revision, decision and engine action/option token, and the channel must permit
submission. An old immutable frame can outlive its valid decision. Incomplete or
empty action lists do not imply passing is safe. Family/label/card text does not
establish targets, costs, mana-source eligibility or other Magic legality. This
increment implements no command builder, auto-pass, default selection or UI panel.

The presentation limit is 4096 entries each for actions, options and amount
constraints, in addition to existing message/card limits. This is a supported UI
collection bound, not a rule or player-count maximum. Oversized projections fail
with DECISION_PROJECTION_LIMIT; the receive bridge revokes rather than exposing a
partially projected frame. No unsupported fields or constraints are silently fixed.

ViewerSessionReceiver now projects cards and decisions from the same validated
snapshot tree. A nonduplicate snapshot/result update carries a Decision frame;
events, receipts and duplicate notifications have no decision frame. An absent
frame on such a notification is distinct from a snapshot whose Decision is null.
The ordered queue still does not coalesce these updates. Packet byte budgets
remain packet-buffer budgets; immutable projection records add bounded managed
overhead rather than promising a total heap-byte ceiling.

TryTake transfers update ownership to its worker consumer. The consumer may pass
the immutable decision slice to a future properly scoped UI binding; raw packet
JSON still stays off the rendering thread. Disposing an update releases its own
decision reference and clears its packet bytes. Retained immutable frames/strings
are caller-owned and cannot be forcibly erased; UI bindings must release them on
revocation, newer decisions, terminal state and seat changes. Existing event
watermarks, receipt uncertainty and result summaries remain separate authorities.

Local evidence: 361 Unity EditMode checks including Java preflight and 56
graphics-enabled PlayMode checks passed with no graphics skips. New checks cover
the shared positive/negative receive corpus, exact token/context copying,
read-only nested collections, nullable/default/signed-64-bit values, unknown
families, ordered amount constraints, a fifth viewer ID, collection limits,
excluded reveal/identity payloads and no invented binding without a decision.
Receive integration checks verify typed frames on snapshots/results, absence on
events/receipts, and reference release on update disposal. No full application
suite or visible fixture change. G0/G1 and real-engine gameplay remain open.
CI review remains every third commit, next at 0.5.102.

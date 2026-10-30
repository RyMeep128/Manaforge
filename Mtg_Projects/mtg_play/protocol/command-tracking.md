# Client command acknowledgement tracking — G1 increment

Status: Unity/C# transport bookkeeping and local focused tests implemented.
No gameplay rules, engine execution, new public wire fields or automatic retry.
The Java peer/ACK schema remains unchanged. G1 is still open.

## Register before sending

Create one `CommandTracker` for an authenticated session/viewer. `Begin` validates
an existing supported decision-family command, binds its session/viewer and reserves its correlation
ID before the transport writes any bytes. Send exactly that immutable command
text. Any potentially partial write, timeout or lost connection must close the
transport and call `Disconnect`; never resubmit because a write failed.

Only one command may be in flight for this viewer. This is serialized client
transport behavior, not a Magic action/priority limit. Engine decision freshness
and legality still belong to the gateway/XMage. The tracker does not authorize
a command from a click, invent an action ID or check card rules.

## Outcomes and uncertainty

| Current state | Receipt/event | Result |
| --- | --- | --- |
| AwaitingAck | submitted | Remain pending as Submitted |
| AwaitingAck/Submitted | confirmed or rejected | Terminal receipt; release slot |
| AwaitingAck/Submitted | uncertain or disconnect | Uncertain; keep slot blocked |
| Uncertain | submitted | Stay uncertain |
| Uncertain | correlated confirmed/rejected after authenticated reconnect | Resolve that command; release slot |
| Terminal | identical duplicate terminal receipt | No state change |
| Terminal | contradictory receipt | Fault connection; block further submission |

Accepting a confirmed receipt records what the authenticated gateway reported;
it does not independently establish engine evidence. A game result, snapshot or
revision change is never used as a substitute for a correlated command outcome.
An explicit close/disconnect can leave a command uncertain even when the fixture
session displayed a terminal result.

`AuthenticatedReconnect` must be called only after a new connection passes mutual
authentication. It retains history and uncertainty, so reconnect alone cannot
unlock/replay a command. A terminal receipt is allowed to resolve uncertainty
only through the future gateway's trusted command reconciliation. No network
reconnection or reconciliation service is implemented by this class.

## Correlation and bounded lifetime

`Accept` validates the ACK body and requires its session, viewer, command ID and
request revision to match a registered command. Malformed, unknown, mismatched
or contradictory receipts fault the connection and mark an active command
uncertain. Faults cannot be reset by the reconnect method. The caller must close
the transport and preserve blocked state rather than silently replace the tracker
for the same live session.

An old identical terminal receipt does not release a newer active command.
Command IDs cannot be reused during the tracker lifetime. History is bounded
(default 4096 records; configurable 1–65536). At capacity it fails closed instead
of evicting old IDs to permit reuse. This is an operational foundation limit,
not a Magic rule or an accepted Commander-session capacity. Before long-session
acceptance, design bounded gateway reconciliation/history compaction without
weakening duplicate protection. Never recreate a tracker simply to bypass the
limit in the same session.

All methods serialize access, including concurrent submissions. Exposed
`TrackedCommand` values are immutable snapshots; they do not change when a later
receipt arrives. The tracker stores IDs/revisions/outcomes only, not raw commands,
card data, textures or credentials. Dispose clears records and prevents reuse;
managed strings/context are not guaranteed memory erasure. Viewer handoff must
also close the owned connection and clear scene/asset state separately.

## Actual validation

Eleven focused tests cover pending versus confirmed, uncertain ACKs, disconnect
before ACK, late submitted receipts, wrong viewer/revision/unknown/malformed
ACKs, duplicate/conflicting old receipts, ID reuse, bounded capacity, concurrent
begin calls and disposal. Existing body-schema tests remain unchanged.

The actual Java↔Unity dummy exchange now registers commands before writes and
passes matched rejection/submitted receipts through this tracker. It verifies
that the fixture-only terminal snapshot does not confirm a pending action and
that disconnect leaves it uncertain. The harness also sends one deliberate raw
protocol probe outside normal submission to test the Java peer's own pending
rejection; this is test-only traffic and is not a product bypass.

Local evidence: 53 Unity EditMode checks passed, including the owned Java process
scenarios. The Java protocol corpora also passed during fixture preparation. No
full suite, actual engine, screenshot or packaged UI is claimed. CI for this
increment is pending; next scheduled review is every third commit without waits.
Qt CI investigation is outside the current Unity/Java scope at owner direction.

Remaining: gateway-side command deduplication/reconciliation and authoritative
confirmation, live choice dispatch, actual transport cancellation/queue
policy, product bootstrap/lifecycle, immutable renderer projection and licensed
Unity CI. No fallback retirement or G1 completion is claimed.

# Bounded viewer receive history — P1.2/G1

Status: Java/C# ordered-stream admission and shared sequence checks pass locally.
G1 remains open. This adds no game-state fields, engine rules or persistent model.

## Ordered stream contract

After mutual authentication, create one ReceiveHistory for the trusted session,
viewer and fixture mode. Pass snapshot/event/result envelopes through Accept on
a transport worker. The existing receive-body validator still checks every packet,
including duplicates, for schema, explicit concealment, mode and viewer/session.
Never take the expected context or fixture permission from an incoming packet.

The gateway must emit these data messages in nondecreasing engine revision order.
Events may share a revision with snapshots or other events. Revision gaps are
allowed; revisions are not event sequence numbers. An engine event batch for an
older revision must be sent before newer state, not relabelled to invent engine
state. This is a proposed transport emission contract, still to be demonstrated
against the real adapter during parity; the history does not rewrite revisions.

Message IDs must be unique across new data messages for this viewer history.
Reuse an ID only for a semantic retry of exactly the same message. Do not issue
new IDs merely to replay an already delivered observation or animation.

The caller must dispatch in wire order; a lock does not reorder concurrent messages.
Admission is serialized with a lock:

1. Validate the complete received body against the authenticated context.
2. Compute a SHA-256 digest of an internally normalized JSON tree. Object key
   order/whitespace do not matter; arrays preserve order. Digests are local
   bookkeeping, not a new wire checksum or authentication mechanism.
3. An existing ID with the same digest returns null: discard the duplicate.
   Changed contents under that ID fail HISTORY_ID_CONFLICT.
4. New data after a result fails HISTORY_TERMINAL. Exact historical duplicates
   remain discardable after the result and even at history capacity.
5. A new ID below the accepted revision fails RECEIVE_REVISION. Equal revisions
   and forward gaps remain valid. No Magic turn/priority/legality is inferred.
6. Reserve the ID/digest, advance the revision and return the validated tree.

A result terminates new data admission, not ACK/error/shutdown processing on their
separate routes. A finished snapshot may still be followed by its explicit result.
An accepted result is not confirmation of an unrelated pending command.

## Bounds, privacy and failure

Default capacity is 4096 IDs, configurable within 1–65536. Full history fails
HISTORY_FULL rather than evicting IDs and allowing replay. The existing per-frame
1 MiB/depth bounds still apply. This is not an unbounded replay log or an event
queue. A future retention/checkpoint design must explicitly preserve duplicate
protection before longer sessions can exceed that capacity.

Only IDs and 32-byte digests are retained. Raw snapshots, printing IDs and private
observations are not cached by the history. Dispose clears the digest byte arrays
and ID dictionary and refuses further admission with HISTORY_CLOSED. Returned
JSON trees belong to the caller; they remain mutable intermediates, not immutable
renderer projections. Mutating one cannot change the retained duplicate identity.
Downstream queues and scene/private texture cleanup still need their own bounds
and ownership. Never log or transmit history digests or raw validated messages.

Any invalid input or admission failure faults this history. Further calls fail
HISTORY_FAULTED; no reset/eviction/reconnect method bypasses that state. Keep one
history for the session stream rather than constructing a new one to accept a
replay. A new connection needs explicit recovery semantics, not assumed freshness.
The owner must close/cancel the failed receive path, mark pending commands
uncertain through the command tracker, and clear viewer UI/resources. This class
does not own a socket, command tracker or runtime process.

## Evidence and remaining work

`fixtures/receive-history-v1.json` has ten shared sequences covering semantic
retries/key ordering, changed ID contents, rollback, equal revisions, revision
gaps, capacity without eviction, terminal results, concealed identity, wrong
viewer and fixture-mode spoofing. Java/C# also check returned-tree mutation,
eight concurrent duplicate submissions, invalid capacity and disposal.

The authenticated dummy Java peer deliberately sends its snapshot twice. All
C# process scenarios route snapshot/event/result through ReceiveHistory and
verify the second snapshot is dropped before the next event. Success, terminal
error, wrong-key exclusion, duplicate command conflict and owner EOF remain
fixture scenarios; no real XMage runtime is started.

Local evidence: 86 focused EditMode checks, all Java corpora including the ten
sequences, eight focused Python schema checks, model-generation drift and lint
passed. No full application suite ran. These checks do not prove event loss
detection, relative order of distinct same-revision events, replay persistence,
rejoin/resynchronization, bounded renderer queues, real visibility filtering or
complete Java parity. G1 freeze and licensed Unity CI remain pending.

Scheduled CI snapshot: protocol runs for `3ef4c38`
(https://github.com/RyMeep128/Manaforge/actions/runs/41107418177) and `daac5b7`
(https://github.com/RyMeep128/Manaforge/actions/runs/41104134788) passed. They cover
Java fixtures/model generation, not licensed C# or real-engine gameplay. No new
CI result is claimed for this increment. Review continues every third commit;
Qt CI was not investigated.

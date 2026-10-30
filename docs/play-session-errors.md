# Terminal viewer-channel errors — P1.2/G1

Status: shared schema/readers and actual Java-dummy failure exchange validated
locally. This is protocol failure handling, not engine integration or G1 freeze.

## Contract

`wire-errors-v1.schema.json` defines an existing version-1 `error` envelope. The
body has exactly session_id, viewer_id, terminal=true and one fixed code:

| Code | Channel failure category |
|---|---|
| PROTOCOL_INCOMPATIBLE | Established channel cannot continue with the negotiated contract |
| SESSION_CLOSED | Session channel has closed unexpectedly |
| SESSION_FAILED | Session can no longer continue |
| ENGINE_UNAVAILABLE | Required engine runtime is unavailable |
| RECEIVE_OVERFLOW | Receiver cannot safely retain/process the bounded stream |
| INTERNAL_ERROR | Other internal failure; details stay out of the public payload |

These codes describe termination of the authenticated viewer channel. They do not
say who won, whether a submitted action executed, or whether owned engine processes
have finished cleanup. They do not prescribe retries. Command-specific rejections
remain correlated ACKs. Authoritative game outcomes remain result snapshots.
Orderly viewer shutdown retains its separate existing message.

Java and C# `SessionErrors` use the strict envelope parser, enforce exact types,
keys/opaque ID syntax and trusted session/viewer binding, then return only the
validated fixed category string. No mutable peer body is retained. Unknown codes,
nonterminal packets, additional fields and incompatible versions fail closed.
There are no free-text messages, raw exceptions, card names, printing IDs,
command IDs, revisions, diagnostic paths or retry instructions in this body.
Future additions require an explicit compatibility change and shared tests.

These messages are gateway-to-viewer only after mutual authentication. Initial
handshake/pin/key failures still close without session data; no pre-auth error
oracle is introduced. Error validation does not itself authenticate a socket,
prove engine state, enforce queue limits or clean up runtime children.

## Pending commands and failure handling

C# `CommandTracker.AcceptSessionError` serializes error handling with submission
and receipt handling. Valid terminal errors fault the tracker and preserve an
active submission as COMMAND_UNCERTAIN. Malformed/misrouted terminal error input
also faults the connection before raising a safe category. A previously returned
receipt remains immutable; no pending command is silently confirmed or rejected.
Reconnection and new submissions through this tracker are refused. History is
retained until its owner disposes the session tracker. Never create a fresh
tracker for the same failed session merely to replay an uncertain action.

The transport owner must close the failed channel, cancel receive work, clear
viewer resources and run owned lifecycle cleanup. The parser/tracker does not own
sockets or processes. Production bootstrap, bounded event queues and durable
reconciliation remain separate pending requirements. No new UI recovery flow or
Java XMage gateway is enabled by this increment.

## Shared and cross-process evidence

The public synthetic corpus has six accepted categories and 23 rejected cases:
missing/extra fields, raw/private text, command/retry fields, wrong types,
nonterminal values, unsupported types, malformed IDs, wrong session/viewer and
invalid trusted context. Python validates shape separately from context. Both
Java/C# reject with fixed safe codes and never reflect the offending payload.

A test-only Java dummy mode sends a submitted ACK, then a validated SESSION_FAILED
packet and closes normally. The authenticated C# worker consumes that error,
preserves the exact pending command as uncertain, refuses reconnect, observes EOF
and checks owned child exit. It receives no fixture game result in that scenario.
The existing four success/authentication/owner-EOF/duplicate scenarios remain.
No XMage process or real deck is involved.

Local validation: 80 focused Unity EditMode checks (including five actual Java
process scenarios), all Java shared corpora, seven focused Python schema checks,
model-generation drift check and Python lint passed. No full local suite ran.
The hosted protocol helper now runs the new Java corpus; licensed Unity CI is
still needed for C# process evidence. CI review remains on the owner's third-commit
cadence, with running checks deferred; no CI pass is claimed for this increment.
G0/G1 remain open and the bulk P2 port remains gated.

# Viewer authentication v1 — G1 primitive, bootstrap delivery pending

Status: shared hello schema, HMAC known-answer vectors and single-use verifiers
implemented in Java/C#. The later dummy exchange and bounded client handoff now
exercise actual peer authentication; product credential delivery, launcher and
engine startup remain pending. G1 is still open.

## Separate credentials and audiences

The future trusted launch owner must create a fresh independent 32-byte viewer
key per seat per launch using a cryptographic random generator. Deliver only that
seat's key and permitted compatibility/session/endpoint context to Unity through
its private inherited channel. Gateway gets the corresponding seat credential
through the owner channel. Owner credentials and the native all-decks manifest
stay gateway-only. Never reuse an owner key as a viewer key or share viewer keys
across seats. No seat count is encoded in this contract.

No credential goes in command lines, environment variables, filenames, URLs,
logs, screenshots or artifacts. Committed vectors use an explicitly public
synthetic test key, fake pins and fake session/seat IDs. They are not runtime
configuration. This increment does not generate keys, define owner bootstrap
payloads or authorize their storage on disk.

## Hello and proof

`viewer-auth-v1.schema.json` specializes the existing `hello` envelope. Its body
has exactly protocol_version (1), engine_version, artifact_manifest_sha256,
session_id, viewer_id, server_nonce, client_nonce, role and proof. Nonces and
proof are 32 bytes written as lowercase hex. Role is `client` or `gateway`.
The engine pin/hash and protocol must match trusted launch expectations; merely
parsing a compatible-looking version does not prove the installed engine.

Both peers must use fresh independent 32-byte cryptographic nonces for each
connection attempt. The gateway challenge and client nonce exchange still need
bounded framed message contracts. Each peer signs its role and both nonces with
HMAC-SHA256 using its inherited viewer key. The transcript is ordered UTF-8
strings, each prefixed with the same four-byte unsigned big-endian byte length
as TextFrame:

1. `manaforge-play-viewer-auth-v1`
2. `1` (wire version)
3. envelope message_id
4. protocol_version (`1`)
5. engine_version
6. artifact_manifest_sha256
7. session_id
8. viewer_id
9. server_nonce
10. client_nonce
11. role

`proof` itself is excluded. Encoding fields separately avoids concatenation
ambiguity; JSON property order/spacing is irrelevant. Role binding prevents
reflection of a valid gateway proof into a client-proof check. The proof is
sensitive authentication material: never persist or log a real hello.

## Verification and lifecycle

`ComputeProof/computeProof` validates a hello template (use a 64-zero proof
placeholder) and computes the proof. `Verifier` is constructed from **trusted
expected fields**, including the expected remote role, both exact nonces,
message ID, session/viewer and compatibility pins. Never construct it by copying
those expectations from an unverified incoming hello. Expected nonces arise from
the owner's connection state and the peer challenge exchange, not saved records.

A verifier compares the expected transcript and HMAC against the incoming hello.
Proof bytes use a fixed-length comparison without an early exit on differing
bytes. An instance accepts at most one verification attempt, including malformed
or failed attempts. Concurrent calls are serialized; only one can succeed.
Dispose/close consumes the instance and clears retained proof/transcript arrays.
Fresh connections require fresh nonces and a new verifier, not a retry of an old
challenge. Stored immutable strings/library-internal buffers are not guaranteed
secure memory erasure; callers own the original key buffer and its lifetime.

Both directions must pass before session data, actions, snapshots or readiness.
On failure, close the connection with safe generic authentication failure; do not
reflect proof or detailed mismatch data. Format readers may expose the safe
AUTH_MESSAGE_INVALID category, never raw input. A proof success is not a game
result, process-ownership proof or authorization for another viewer/session.

These primitives are for authenticated local loopback. They do not encrypt or
integrity-protect subsequent frames, defeat compromise of the same user account,
or satisfy future remote-transport requirements. Never expose local IPC on a
public interface. Network play needs its own secured transport and ownership
review as already required by P7.

## Actual evidence and next integration

The shared corpus contains two independently calculated Python-standard-library
HMAC vectors and 14 binding/tamper cases, including valid proofs for the wrong
seat and reflected role. Both Java/C# also test wrong keys, consumed/closed
verifiers and concurrent attempts. Python schema checks distinguish malformed
hello shapes from valid-looking messages that cryptographic checks must reject.

Local evidence: Java auth and existing protocol corpora passed; 37 Unity EditMode
checks and three focused Python schema checks passed. No full suite was run.
The hosted Java helper now includes authentication fixtures; CI for this commit
is pending. This is one increment after the previous scheduled CI review, so
unfinished runs will be reviewed at the next third-commit checkpoint.

Next implement bounded challenge/private bootstrap delivery and an actual dummy
Java↔Unity loopback exchange with timeouts/cancellation and clean shutdown. Keep
credentials out of diagnostics; correlate acknowledgements and enforce viewer-safe
snapshot/result bodies before dispatch. Windows process containment, owner
lifeline/orphan handling and real pinned-engine integration remain pending.


## Bounded client handoff follow-up

[ClientHandshake.Open](client-handshake.md) now signs/verifies against trusted
expectations within one total budget and returns a session owner only after
success. It closes failed attempts, clears its key clone and prevents reattempts
on the same socket. Sixteen new checks and two Java-process cases pass within
220 focused local EditMode checks. Private product bootstrap, artifact verification
and Java-side total handshake budgets remain pending. This needs no UI verification.

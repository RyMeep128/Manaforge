# Bounded client authentication handoff — P1.2/P1.4/G1

Status: C# authentication-to-session handoff tested locally. No rendered UI changes
or hands-on UI acceptance are required for this increment. G0/G1 remain open.

ClientHandshake.Open takes a connected loopback socket owner, trusted client and
expected-gateway hello templates, the seat's 32-byte viewer key and one total
1–60,000 ms budget. Invalid budget arguments precede ownership transfer. Once an
attempt starts, failure closes the transport; success transfers it into the returned
ClientSessionChannel. All work belongs on a worker.

The templates must originate from trusted launch/challenge state. The helper
validates matching protocol, engine pin/hash, session, viewer and both nonces,
with distinct client/gateway roles. It signs the client hello and verifies the
reply using the existing single-use gateway verifier. Incoming fields never replace
expected pins or viewer context. A valid-looking snapshot instead of a gateway
proof cannot open a session. Proof possession binds the declared context; it does
not verify installed artifacts or prove which engine the peer actually loaded.

One monotonic budget spans template/proof work, client write and gateway read.
Remaining time is passed to the existing bounded frame operations rather than
resetting the full budget at each step. Cancellation/deadline is checked again
before session construction. Failures report only AUTH_FAILED, AUTH_TIMEOUT or
AUTH_CANCELLED without mismatch details, payloads or proof text. A transport may
attempt this handshake once; its attempt marker is not authentication proof.

The helper clones and clears its key buffer. The caller still owns the original
key and must clear it when finished. Verifier-owned mutable proof/transcript arrays
are disposed. Immutable strings and library-internal copies are not guaranteed
secure erasure. Never log real hellos, keys or proof data. Each connection still
requires fresh nonces and independent viewer credentials; the per-socket guard
does not enforce nonce freshness across different sockets.

Fixture permission remains an explicit trusted caller argument, default false.
Successful authentication does not enable fixture mode based on peer data. The
lower-level session constructor remains available for trusted tests/integration;
it does not authenticate by itself. Product callers should use this handoff.

Sixteen new focused loopback checks cover success/key ownership, invalid proofs,
validly signed wrong pin/viewer context, reflection, data-before-proof, held-proof
timeout/cancellation, inconsistent expected templates, pre-cancellation, invalid
keys/budgets, repeat attempts and fixture-mode refusal. Two new actual Java process
cases use the helper: successful authentication through coordinated gameplay
fixtures/shutdown, and a delayed gateway proof that times out before session entry.
The delayed case closes the owner pipe and verifies clean child exit.

Local evidence: 220 focused Unity EditMode checks, including eighteen authenticated
process scenarios, plus the Java protocol corpora and 16 read/14 write socket
checks passed. No full application suite ran. This is fixture evidence, not a
live-engine game or product launch acceptance.

Still required: versioned private bootstrap/challenge delivery, connect/startup
and Java-side total authentication budgets, trusted artifact verification, product
worker/process ownership and renderer handoff. This helper starts no process,
reads no deck manifest and performs no automatic engine upgrade. Java/XMage
behavior parity remains Phase 2/G2 work after G0/G1. CI follows the owner's
third-commit cadence; no new CI pass is claimed here. Qt CI was not investigated.


## Java authentication follow-up — October 30, 2026

The [Java gateway handshake](gateway-handshake.md) now enforces a total deadline,
closes failed attempts, clears its cloned key and returns a trusted viewer context
only after proof validation and reply completion. The ordinary dummy uses it;
the delayed-proof negative fixture remains deliberate. Local validation passed:
16 new Java authentication cases and 221 Unity EditMode checks, including 19 Java
process scenarios. Product bootstrap/ownership, artifact verification and licensed
CI remain open. No UI verification was needed.

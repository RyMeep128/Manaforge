# Bounded Java gateway authentication

`GatewayHandshake.accept` consumes trusted client/gateway templates and a 32-byte
viewer key on an already connected, owned loopback transport. One monotonic
1–60000 ms budget covers client proof receipt, validation, gateway proof writing
and the final cancellation/deadline check. It returns an immutable ViewerContext
only after success, populated from trusted expectations rather than peer claims.

Invalid budget arguments precede ownership transfer. Once accepted, failure,
timeout, cancellation or interruption closes the transport and returns a fixed
AUTH_FAILED, AUTH_TIMEOUT or AUTH_CANCELLED code without private details. A
connection allows one attempt. The helper wipes its cloned key; the caller owns
its original key and must dispose the transport after successful use. Java
strings and caller-held templates are not guaranteed to be erased.

The context binds session, viewer and declared engine/artifact pins. It does not
verify installed artifacts or create a gameplay session. This helper creates no
listener, process, challenge, deck or engine. Trusted bootstrap must supply fresh
nonces and keys; the connection marker does not prevent replay across separately
created connections using reused bootstrap material.

The ordinary Java dummy now authenticates through this boundary before fixture
traffic. The delayed-proof mode intentionally retains manual authentication as a
negative client-timeout fixture. A separate idle-client mode demonstrates Java
closing the unauthenticated socket without emitting proof or game data.

Local evidence: 16 dedicated Java loopback authentication cases, existing protocol
corpora and 16 read/14 write checks passed. All 221 focused Unity EditMode checks
passed, including 19 Java process scenarios. No full application suite ran and no
UI verification is required by this protocol-only change. CI has not been checked
for this increment under the owner's every-third-commit cadence.

Private bootstrap, verified artifacts, product process/worker ownership, Java
session ownership and renderer handoff remain open. G0/G1 remain open; bulk Java
engine migration and real XMage parity belong to Phase 2/G2 after those gates.


## Authentication framing regression coverage — October 30, 2026

Six additional cases at each public authentication entry point cover stalled
partial headers, stalled partial payloads, oversized lengths, invalid UTF-8,
truncated payload EOF and EOF before a proof. Stalled frames must time out;
malformed/truncated frames must fail. Neither path may return a session/context,
and every accepted failed attempt closes its owned transport. Java additionally
asserts the peer receives no proof or game data on these failures.

Local validation passed: 227 focused Unity EditMode checks and 22 Java handshake
cases, alongside the Java protocol corpora and socket checks. No full application
suite or UI verification was needed. This adds regression evidence without
changing production authentication behavior or completing G0/G1.

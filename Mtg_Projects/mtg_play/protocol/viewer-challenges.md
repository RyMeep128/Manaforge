# Fresh viewer challenge exchange v1

Status: Java gateway and C# client worker wrappers at 0.5.95-alpha.1. The real
launcher/session scene and pinned-engine integration remain unmounted; G1 is open.

The exchange uses existing bounded UTF-8 framing and `hello` envelopes. It has a
separate auth_exchange_version of 1 and strict shared schema/fixtures. It changes
no wire envelope type or game snapshot model. Old peers fail closed; the new
wrappers never fall back to saved nonce templates or the legacy exchange.

| Order | Message ID | Body |
| --- | --- | --- |
| Gateway → client | auth-challenge | auth_exchange_version, stage=gateway_challenge, server_nonce |
| Client → gateway | auth-nonce | auth_exchange_version, stage=client_nonce, echoed server_nonce, client_nonce |
| Client → gateway | auth-client | Existing viewer-auth-v1 signed client hello |
| Gateway → client | auth-gateway | Existing viewer-auth-v1 signed gateway hello |

The gateway generates a fresh independent 32-byte nonce with SecureRandom for
each connection attempt. The client generates its own with RandomNumberGenerator.
Nonce encoding is exactly 64 lowercase hexadecimal characters. The gateway checks
the response against its current challenge before entering the signed-hello
stage. Challenge bodies contain no session, viewer, engine pin, credential, deck
or gameplay information. Unknown fields, invalid stages/versions/IDs and malformed
nonce encodings fail. The challenge message limit is 4096 UTF-8 bytes after the
generic framed reader's existing 1 MiB bound; this does not reduce that reader's
initial allocation bound to 4096 bytes.

Each peer builds the signed transcript from its own trusted context and the
connection's two nonces. No peer-provided identity/pin can become a trusted
expectation. The existing role-bound HMAC verifier performs authentication; the
unsigned challenge exchange alone proves nothing. On the client, context comes
from the private ViewerBootstrap. On Java, accept receives trusted client/gateway
hello templates with matching identity/pin fields and canonical message IDs.
Their prior nonce/proof placeholders are replaced for this attempt; never supply
templates copied from incoming network traffic.

`ViewerChallengeHandshake.Open` returns the existing ClientSessionChannel only
after verified gateway proof. Java `ViewerChallengeHandshake.accept` returns the
existing authenticated ViewerContext after verifying the client proof and writing
its gateway proof. Failed attempts close their owned transport. A challenge
reservation prevents another challenge attempt on that connection; no retry or
automatic reconnection occurs. Legacy direct hello helpers remain for existing
fixtures, not as a downgrade path in these wrappers.

One monotonic budget covers challenge and signed hello reads/writes. Invalid
budgets precede ownership transfer. Remaining time is passed to the existing
bounded transport/hello helpers, and checked again before success. Cancellation
and transport timeouts produce fixed AUTH_CANCELLED/AUTH_TIMEOUT codes; other
runtime failures become AUTH_FAILED. Run on connection workers, not Unity's
rendering thread. This is cooperative cancellation/deadline checking, not a hard
real-time guarantee for OS scheduling or cryptographic-provider calls.

The client takes its bootstrap key at most once after initial cancellation
checks and clears the transferred buffer on completion/failure. Java clones the
caller-owned key and clears its copy. Managed strings retain the existing
secure-erasure limitations. Never log or persist live challenges, proofs or keys.
Expected pin agreement is not verification of installed artifacts. Local HMAC
authentication provides neither frame encryption nor a remote-network transport.

Focused local evidence: 344 Unity EditMode checks including Java preflight passed.
Both languages consume two public positive and ten negative challenge fixtures;
Python validates their shared schema. Java runs four additional real-loopback
cases for fresh gateway nonces, wrong-challenge response, timeout and cancellation.
C# checks fresh client nonces, replayed proofs, a valid proof for the wrong pin,
timeout/key ownership and cancellation. Two real Java-process/C# cases authenticate
and complete the existing coordinated dummy session or reject a wrong viewer key.
All fixture data is synthetic; no XMage game or private user deck is involved.
No full application suite or visual change. CI review remains every third commit,
next at 0.5.96. No owner UI review is needed for this worker-only increment.

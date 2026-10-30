# Owned Java↔Unity dummy exchange — local G1 evidence

Status: test-only Java loopback peer and Unity EditMode client exchange real
framed messages. Local checks pass; licensed CI, full wire-body validation and
production launch integration remain pending. This is not XMage gameplay.

## What actually runs

`DummyExchangeTests` owns one `java manaforge.protocol.DummyGateway` child per
scenario. The Java peer binds only IPv4 `127.0.0.1` on an OS-assigned port. No
public interface, fixed port, engine, account, saved deck or all-seat manifest
is used. The C# test acts as launch owner and viewer client for this fixture.
Python compiles/prepares the Java classes once before Unity starts; it does not
relay authentication, snapshots, commands or results.

A fresh random 32-byte viewer key and client nonce travel through the child's
inherited stdin. The test-only bootstrap contains exactly fixture_only=true,
viewer_key_hex, client_nonce, session_id, viewer_id, engine_version and
artifact_manifest_sha256. Real owner credentials are never created or sent.
Java generates its own fresh cryptographic server nonce, then returns host,
port and server_nonce through its inherited stdout. Command arguments contain
only classpath and public fixture path; no credentials or game data.

The C# TCP client and Java gateway exchange role-bound HMAC hello proofs using
those trusted bootstrap fields. No session frame is sent before client proof
verification; C# verifies the gateway proof before accepting the next frame.
Private pipe readiness is not itself gameplay readiness or engine attestation.
Engine/version/hash values are explicitly fake fixture pins.

After mutual proof, the successful scenario demonstrates:

1. A viewer-scoped mock snapshot deserialized through existing generated C# DTOs,
   with concealed identities absent, a decision ID and one synthetic legal action.
2. A stale-revision command receiving a correlated rejected/STALE_REVISION ACK.
3. A current command receiving submitted with null code, not confirmed.
4. An explicit fixture_only result (`fixture_complete`), not a real game outcome.
5. Another action while pending receiving rejected/COMMAND_PENDING.
6. A viewer-bound shutdown request/response, socket EOF and normal child exit 0.

Separate scenarios verify that a wrong viewer key gets EOF before any hello
response or snapshot (normal fixture rejection exit 2), and owner stdin EOF
stops the listener with exit 0 even before a TCP connection is established.
The test never kills by process name or adopts an unrelated process/occupied port.

## Bounded ownership and test lifecycle

The peer accepts one connection, applies an eight-second accept timeout and
five-second socket read timeout, and caps its post-authentication loop at eight
requests. The private stdin lifeline closes owned socket/listener on EOF.
Bootstrap pipe reads are bounded by the owning C# test's overall deadline, not
by a production bootstrap reader. The C# test runs blocking pipe/TCP work on a
worker while yielding Unity frames, with a 25-second overall deadline.

Cleanup closes the owned socket and stdin, then waits two seconds for the direct
child before force-stopping that owned process if necessary. Normal scenarios
explicitly assert normal exits before fallback cleanup. These test children create
no descendant processes; this is not Windows Job Object containment proof or a
replacement for the existing LaunchOwner work. Worker shutdown is checked after
failure cleanup. Product orphan recovery, diagnostics and cancellation still
need their own integration.

Java emits only framed private readiness or a fixed DUMMY_FAILED diagnostic,
never an exception stack/raw bootstrap. Test assertions do not print keys,
proofs or hello objects. Secret strings/library buffers are not guaranteed secure
memory erasure; the test clears its key array and persists no credential files.
The public scenario fixture and compiled classes contain no generated secrets.

## Repeat and inspect

```powershell
./tools/unity-play.ps1 -Mode EditMode
```

This prepares current Java classes using `tools/check_play_java_protocol.py`,
then runs the focused Unity tests. Requires Python and JDK `java`/`javac` on PATH.
The existing hash-pinned Gson is used; if unavailable, explicitly allow its
existing Maven download with `-DownloadGson`. The test-only class files, jar and
public scenario copy stay under ignored `Artifacts/JavaDummy`. Nothing from that
directory is included in the product or uploaded by the licensed workflow.

The helper's optional `--dummy-output` only exports under Unity Artifacts, rejects
linked output paths and never recursively deletes user content. `unity-play.ps1`
verifies the cached jar hash on each preparation and requires at least 40
EditMode results. The manual licensed workflow now sets up Python 3.12 and the
same pinned Temurin JDK as the hosted protocol workflow, allowing only the
existing pinned Gson download. No Unity activation/license flow is changed.

Local evidence: 40 Unity EditMode tests passed, including three real Java-process
scenarios; existing Java contract/authentication corpora and four focused Python
schema checks passed. The mock snapshot validates against the original DTO
schema. Reports are ignored `Artifacts/editmode.xml` and `EditMode.log`; no new
screenshot or packaged-player claim. CI is unverified and will be reviewed at the
next scheduled third-commit checkpoint without waiting for unfinished runs.

## Remaining G1 boundaries

This is an EditMode client, not a packaged Unity player or UI match. Snapshot/event/result bodies now use the [generated receive boundary](receive-boundary.md)
before DTO deserialization, including expected viewer/session, fixture mode and
explicit concealed-field checks. This is still not a production engine privacy
filter or a frozen protocol. The Java dummy performs
opaque ID comparisons only and emits no engine-confirmed outcome.

Still required: finalized public snapshot/event/result/compatibility body schemas,
remaining choice/action families, replay/idempotency and pending/uncertain
tracking, compatibility with actual pin metadata, private product bootstrap,
owner/seat authorization, robust transport cancellation/queue limits, lifecycle
containment and actual licensed CI. Keep G1 and G0 open; the bulk Java/XMage port
and retirement of Python/Qt remain gated.


The receive-boundary follow-up adds an event with a different actor and represents
the fixture-only result as a terminal GameSnapshot. It retains the same dummy
outcome label and does not confirm an engine action. Current focused totals are
42 Unity EditMode and five Python schema checks; original counts above record
the earlier increment. No new packaged-player or real-engine evidence is added.


The submission-ledger follow-up adds a cached identical retry and a separate
changed-payload ID-conflict scenario. Four owned-process scenarios now pass within
57 local EditMode checks. These deliberate raw probes bypass normal client ID
prevention only in the test harness. No engine is involved and a duplicate
submission reservation never produces a second fixture result. See the
[ledger guide](submission-ledger.md) for scope and limits.


## Terminal error follow-up

The test-only `session-error` mode now closes after a submitted ACK and validated
SESSION_FAILED message. The authenticated C# test keeps the current command
uncertain, rejects reconnect and verifies EOF plus owned child exit. It receives
no result in this mode. See [session errors](../../../docs/play-session-errors.md)
for schema/safe-code requirements. Five owned-process scenarios now pass locally;
this remains a fixture, not proof of a real engine failure or product cleanup.


### Receive history follow-up

The peer deliberately repeats the initial snapshot. Authenticated C# clients now
use [ReceiveHistory](receive-history.md) to drop the duplicate, then admit the
same-revision event and later result. This exercises receive idempotency through
the actual pipe/bootstrap/loopback path without adding a second game model.
All five existing process scenarios continue to pass locally.


### Bounded inbox follow-up

The C# worker now routes data through [ReceiveInbox](receive-inbox.md), drops the
repeated snapshot without using a queue slot, then takes/disposes each packet
before validating/deserializing it. Five owned-process scenarios pass within 101
focused local EditMode checks. This test immediately drains packets; overflow,
consumer races and cancellation are covered separately by focused inbox checks,
not claimed as real socket-pump or renderer behavior.


### Partial-frame deadline follow-up

Client socket reads now use [LoopbackFrameReader](frame-read-deadlines.md).
A sixth mode authenticates and then sends only two header bytes. The client
observes its total frame deadline, confirms the owned socket is closed and
closes the private owner pipe; the Java child exits cleanly. Other scenarios
still pass. This is not a real engine timeout or proof of product lifecycle
coordination. The subsequent Java follow-up below upgrades inbound frames to absolute deadlines.


### Java whole-frame deadline follow-up

The Java peer now owns its accepted socket through LoopbackFrameReader, and its
owner-EOF lifeline closes through that same reader. All inbound TCP frames use a
whole-frame budget, while private stdin/bootstrap remains separately owned.
A seventh scenario authenticates, reads its fixture and then sends two client
header bytes. Java times out, closes and exits with the expected fixed failure
status; C# observes EOF. Sixteen Java real-loopback cases and all seven process
scenarios pass locally, within 118 focused EditMode checks. This remains a protocol
fixture, not a Java XMage gateway or production cleanup proof.


### Bounded C# write follow-up

Normal client TCP sends now use the existing owned socket's
[bounded Write method](frame-write-deadlines.md), including hello, tracked commands
and shutdown. Registration still precedes sending, with tracking disconnected on
write failure. Deliberate malformed two-byte probes and private bootstrap pipes
remain separate test paths. Seven scenarios and 130 focused EditMode checks pass
locally; no Java outbound deadline or production session coordinator is implied.


### Java write deadline follow-up

Normal Java TCP sends now use the same owned socket's
[bounded write method](frame-write-deadlines.md). An eighth mode authenticates,
then writes a maximum-size public stress frame to a client that stops reading.
Java verifies FRAME_WRITE_TIMEOUT and exits cleanly; C# checks exit and closes its
owned socket. No result/command acceptance is inferred from that failure. Private
readiness pipes and deliberate two-byte malformed probes remain separate test
paths. All eight scenarios pass within 131 focused local EditMode checks.

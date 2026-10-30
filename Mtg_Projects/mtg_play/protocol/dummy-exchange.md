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

This is an EditMode client, not a packaged Unity player or UI match. Snapshot and
result transport bodies are deliberately test-only and do not yet have a final
public wire validator. DTO deserialization and explicit concealed-field checks
are fixture evidence, not a production privacy filter. The Java dummy performs
opaque ID comparisons only and emits no engine-confirmed outcome.

Still required: finalized public snapshot/event/result/compatibility body schemas,
remaining choice/action families, replay/idempotency and pending/uncertain
tracking, compatibility with actual pin metadata, private product bootstrap,
owner/seat authorization, robust transport cancellation/queue limits, lifecycle
containment and actual licensed CI. Keep G1 and G0 open; the bulk Java/XMage port
and retirement of Python/Qt remain gated.

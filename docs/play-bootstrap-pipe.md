# Private bootstrap pipe and owner lifeline

Status: Windows reader primitive at 0.5.92-alpha.1. Product launcher delivery,
packaged Unity stdin verification, owner-to-UI shutdown wiring, authentication
challenge exchange and OS child containment remain open. No G0/G1 acceptance claim.

Python `frame_viewer_bootstrap` prefixes the existing private bootstrap payload
with a four-byte unsigned big-endian length. It bounds payloads at 16 KiB without
logging, file access or gameplay traffic. The launcher worker must write/flush
that one frame to the child's inherited stdin and keep the writer open. This
helper only frames bytes: bounded/cancellable writing and owned-child cleanup
still belong to the launch controller. Do not send a second frame or heartbeat.

Unity's `ViewerBootstrapPipe.FromStandardInput` duplicates its inherited pipe
handle into an owned non-inheritable handle. `FromInheritedHandle` supports an
explicit trusted pipe handle; the original remains caller-owned. No credential
appears in arguments, environment variables, filenames or named IPC endpoints.
The pipe must have exactly one reader, including outside this object; never read
the caller's original handle concurrently with the owned duplicate.

`ReadBootstrapAsync` runs on a worker. It peeks available bytes before reading
only that amount, avoiding an indefinitely blocked anonymous-pipe read under
the single-consumer contract. Empty input is polled every 10 ms. One monotonic
startup budget (1–60000 ms, default 5000) covers header, payload and parsing, and
starts when requested. Scheduler delays count against that budget once the worker
runs; this is not a real-time worker scheduling guarantee. Length is checked
before allocating payload storage. Truncation, EOF, malformed content, cancellation
and timeout retire the reader with fixed diagnostic codes and clear owned raw
buffers. Managed parser strings retain the limitations described in the bootstrap
contract; no complete secure-memory-erasure claim is made.

After successful bootstrap, call `WaitForOwnerCloseAsync` once. Its worker waits
for owner EOF without imposing the startup deadline on an active game. EOF is
normal completion of the lifeline task; extra bytes are a fixed protocol failure.
Cancellation or Dispose retires waiting workers. The methods are single-use and
serialized by state. Dispose closes only the duplicate. The caller must close its
original inherited read handle when appropriate; host code must preserve exclusive
read ownership and release its handles at shutdown.

The host must observe lifeline completion/failure, revoke the viewer, cancel
session/asset work and marshal Unity shutdown to the rendering thread. This
primitive does not invoke Unity APIs, kill processes, infer a game result or
authenticate the pipe's parent. Bootstrap transport ownership must come from the
trusted launcher. Real peer proofs and pin validation remain required.

Focused local evidence: 20 Python checks and 334 Unity EditMode checks, including
existing Java protocol preflight. Real Windows anonymous-pipe tests cover
fragmented delivery, EOF before/inside a frame, oversize/invalid content, stalled
header/payload deadlines, cancellation, disposal, single-consumer state, owner EOF
and unexpected lifeline data. A Python child-process test receives the actual
frame over inherited stdin and observes EOF with only a fixed public status
output. The C# tests use real OS pipes in-process, not a launched Unity player;
packaged stdin handle availability still requires separate evidence.

No full application suite or visual scene change. No new owner UI review needed.
CI review remains on the third-commit cadence, next at 0.5.93.

The subsequent [launch-owned writer](play-owned-bootstrap-write.md) now delivers
this frame through the owned client's stdin with a bounded nonblocking write.
The combined path still needs packaged Unity and owner-to-UI cleanup evidence.

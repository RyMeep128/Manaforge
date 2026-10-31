# Launch-owned private bootstrap writing

Status: launch coordinator delivery at 0.5.93-alpha.1. Packaged Unity startup,
owner-loss UI cleanup, fresh challenge exchange and OS containment remain open.

`LaunchOwner.start_client(..., viewer_bootstrap=payload)` now frames and writes
one private payload to the stdin pipe of the client process it just created.
Use output from `export_viewer_bootstrap`; no credential, owner manifest or deck
information is added to the child command or environment. Existing starts without
bootstrap remain supported for lifecycle fixtures. This is not a new Qt launch
flow and does not yet start a packaged Unity session from saved decks.

The launch worker uses nonblocking `os.write`, handling partial writes and full
pipes with a 10 ms cancellation wait. No writer thread or buffered write can stay
blocked on an unresponsive client. The default write budget is five seconds,
bounded additionally by the existing client startup deadline; an explicit positive
budget up to 60 seconds is supported. The owned stdin is left nonblocking and
open as the owner lifeline. No later payload writes are permitted for that pipe.
This requires runtime nonblocking-pipe support, verified on the installed Windows
Python runtime. Unsupported setup fails closed with a fixed code.

Before creating the client, invalid payload sizes/types and write budgets are
rejected. While writing, existing health checks detect cancellation, startup
timeout or owned-child exit. A stalled pipe or write failure closes owned children
in reverse order and retains cleanup evidence. The write budget bounds delivery;
cleanup has its own existing bounded process-stop waits. No engine descendant
cleanup is inferred from root exit. Unconfirmed cleanup still blocks replacement
launches on that owner.

`client_bootstrap_written` records a complete timely write while owned health was
valid. It is not a client acknowledgement, peer proof, snapshot or readiness.
The state remains STARTING_CLIENT until a separately verified client-ready event.
A false flag does not prove zero bytes were delivered: failures may leave a
partial or uncertain frame. Never replay on the same child. Close and confirm
cleanup before a fresh launch with new credentials/context.

The coordinator clears its mutable framed copy on success or failure. Caller
payload bytes and temporary immutable framing copies retain managed-memory
limitations; no secure erasure guarantee is claimed. Failures expose fixed codes
and cleanup reports contain no payload, credential or raw exception details.
Python coordinates this one-time delivery only; Java/Unity still own gameplay.

Focused local evidence: 67 Python lifecycle/bootstrap checks passed. New real-child
cases cover three-byte partial writes, complete frame parsing, retained lifeline
and graceful EOF cleanup, a full unconsumed pipe timing out, cancellation during
a full pipe, and sanitized nonblocking-setup failure. Invalid budgets/payloads
create no client. Existing cleanup, unrelated-process and immutable-report checks
remain active. These children create no descendants, so their test-only cleanup
proof is not valid for XMage. No full application suite ran.

The public Unity scene is unchanged; no new owner UI review needed. The next
integration proof must launch an actual packaged Unity reader and verify its
inherited handle, owner-loss behavior and sanitized acknowledgement. OS containment
and real authentication still gate product readiness. Relevant CI is reviewed at
this third-commit checkpoint without waiting for unfinished runs; local evidence
does not imply CI success or G0/G1 acceptance.

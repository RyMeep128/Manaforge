# XMage session storage

Connection checks and engine proofs use a fresh server workspace under
`play-components/sessions` in Manaforge's data directory (by default
`%LOCALAPPDATA%/PrintProxyPrep` on Windows). Historical development runs also
used `Mtg_Projects/mtg_play/.runtime`.

Before and after a connection check, while holding the cross-process gameplay
operation lock, Manaforge maintains completed sessions:

- Keep the latest 20 completed result files and diagnostic folders.
- Cap each retained compile, server, bridge and event log at its last 1 MiB.
- Remove disposable classes, bridge files and private session inputs.
- Keep at most one initialized server among those completed sessions, so local
  XMage catalog inspection still works. Remove other server databases and libraries.

The retained initialized server is typically a few hundred MiB. Completed sessions
no longer accumulate hundreds of duplicate card databases. Retention applies to
failed checks too, once every started compiler, bridge, server and peer has a
confirmed shutdown. Existing completed sessions are maintained on the next check.

Missing, malformed, oversized or incomplete process records are preserved rather
than treated as proof that a process stopped. Interrupted sessions may therefore
require manual maintenance after verifying their processes have exited. Linked
session directories are never followed. Cleanup failures are reported in the
connection result as `storage_cleanup_failed`; they do not replace gameplay errors.

Unity game sessions use their separate temporary-directory cleanup and bounded
`mtg_core/logs/unity-sessions` archive. Installed engine payloads and downloads are
separate from this session retention policy.

Regression coverage is in `mtg_play/tests/test_session_storage.py`, collected by
the GitHub Actions Tests workflow. Per the development workflow, do not run this
Python suite locally.

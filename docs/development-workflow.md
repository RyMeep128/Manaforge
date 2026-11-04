# Development on main

Work directly on `main` in `C:/Users/ryanm/Proxy App/branch_print-proxy-prep-QtPort`.
Do not create another branch unless the user explicitly requests it. Other retained
worktree directories are historical workspaces, not active development locations.
This supersedes the previous development-branch promotion and three-commit cadence.

Preserve uncommitted work before switching or consolidating workspaces. Never
force-push shared history or bypass repository protection. Follow the prerelease
versioning rules in `AGENTS.md` before each requested commit.

Use GitHub Actions exclusively for test suites. After pushing, inspect checks for
the exact committed SHA. Python/Core, Java/XMage, Unity, protocol, packaging and
playable human-versus-AI acceptance coverage must be considered when applicable.
Opening or fixture success alone does not establish playable acceptance. Missing,
skipped, cancelled, unavailable or incomplete checks do not count as passing.
Report code failures and runner, licensing or infrastructure blocks accurately.
See [hosted Unity setup](unity-ci.md) for the Windows runner and Personal license secrets.

The old `tools/ci_checkpoint.py` promotion helper and its Git-directory audit record
are retained as historical tooling and evidence; they are no longer required for
the main-only workflow. Do not overwrite the prior audit record.

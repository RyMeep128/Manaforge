# Development on main

Work directly on `main` in `C:/Users/ryanm/Proxy App/branch_print-proxy-prep-QtPort`.
Do not create another branch unless the user explicitly requests it. Other retained
worktree directories are historical workspaces, not active development locations.
This supersedes the previous development-branch promotion and three-commit cadence.

Preserve uncommitted work before switching or consolidating workspaces. Never
force-push shared history or bypass repository protection. Follow the prerelease
versioning rules in `AGENTS.md` before each requested commit.

Always rebuild the local Unity Windows player after Unity changes with
`./tools/unity-play.ps1 -Mode Build`. This build is required even when hosted
checks are unavailable; it does not replace CI or visual acceptance.

Run Unity validation directly on the owner's Windows desktop with
`./tools/validate_unity_local.ps1`. This includes EditMode, graphics-enabled
PlayMode, the Windows player build, screenshots, public artwork, real-engine
payment and choice checks, human-versus-AI play, concession, authenticated UI,
and two-seat multiplayer acceptance. See [local Unity validation](unity-ci.md)
for prerequisites, evidence, and release packaging.

Keep Python/Core, Java/XMage, protocol, and other non-Unity test suites on GitHub
Actions. After pushing, inspect checks for the exact committed SHA. Local Unity
results and hosted non-Unity results are separate evidence requirements.
Opening or fixture success alone does not establish playable acceptance. Missing,
skipped, cancelled, unavailable or incomplete checks do not count as passing.
Report code failures and environment blocks accurately.

Full CI can take 30–40 minutes. Start the requested workflows and report their
links; the owner will notify the agent when execution is complete. Do not poll or
wait for completion unless the owner asks for a CI check. Report any blocked
acceptance separately from local rebuild status.

The old `tools/ci_checkpoint.py` promotion helper and its Git-directory audit record
are retained as historical tooling and evidence; they are no longer required for
the main-only workflow. Do not overwrite the prior audit record.

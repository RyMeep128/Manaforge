# Continuous development

The active branch is `codex/play-live-first-land`. `AGENTS.md` governs future
sessions. Use GitHub Actions exclusively for tests. No new test infrastructure
or background polling is introduced by this workflow.

## Persistent checkpoint record

Run `python tools/ci_checkpoint.py status` at session start. The helper stores
`manaforge-ci-checkpoint.json` in the Git common directory, shared by worktrees
and preserved across sessions without adding bookkeeping commits to the counter.
Back up this file when moving to a new clone; it contains no credentials.
The record includes the active branch, cadence anchor, exact pending SHA,
workflow run IDs/attempts, job/step evidence, superseded candidates and promotions.
Only one session should update it at a time. Writes use atomic replacement.

After each commit run `python tools/ci_checkpoint.py checkpoint`. Before baseline
acceptance it immediately freezes a baseline candidate; afterwards it schedules
every three commits. With a pending candidate it refreshes only that candidate,
once, regardless of how far development has advanced. `status` is offline.
`checkpoint` requires authenticated GitHub CLI (`gh auth login`) with Actions
read access; missing CLI/API access is recorded as blocked, never green.

Use `checkpoint --replace-failed` only after committing a correction or necessary
integration/version change. It archives the previous evidence and freezes current
HEAD. It does not erase the baseline gate. Review the reason in the audit record.
Do not replace a running candidate merely because development advanced.

## Required evidence

Determine applicability from the entire current `origin/main..candidate` range,
not just the final commit or workflow path filters. The helper conservatively
captures all runs for the exact SHA, with paginated jobs and individual steps;
its output is evidence for review, never an automatic green/merge decision.
Review the latest attempt of the appropriate event for each applicable workflow.
PR synthetic merge SHAs are different candidates and require separate evidence.

| Area | Existing workflow and gates |
| --- | --- |
| Python desktop, Core, regression | `tests.yml`: Windows / Python 3.12 and 3.13, application tests, lint and formatting |
| Java/XMage, playable 1vAI | `tests.yml`: force `verify_xmage=true`; inspect prepare, public-adapter and Manaforge-controls acceptance steps and report artifacts; `play-live-opening.yml`: pinned-human-ai-opening |
| Native payment | `play-payment-native.yml`: pinned-native-payment |
| Shared Java/CSharp protocol | `play-protocol.yml`: java-fixture-consumer |
| Desktop/Unity preview contracts | `play-preview.yml`: preview-contract-and-ownership |
| Unity client/build | `unity-play.yml`: foundation, manual-only licensed self-hosted runner; inspect EditMode, PlayMode, build and packaged smoke evidence |
| Packaging/infrastructure | `tests.yml`: dispatch `build_windows=true`, require Optional Windows application bundle and its packaged verification; never set skip_tests or publish inputs |
| Feedback relay | `feedback-relay.yml`: relay-tests |

All applicable jobs and required steps must succeed. Optional release/dataset jobs
may be skipped only when outside the change scope; document why. A workflow-level
success can conceal skipped acceptance steps. Inspect artifacts and existing
[local game requirements](play-local-game.md),
[Unity acceptance roadmap](play-unity-java-roadmap.md), and
[XMage status](play-xmage-fork.md). Full-match/owner acceptance is currently
documented as pending; do not infer it from opening or protocol fixtures.

Dispatch existing workflows at a ref that resolves to the frozen SHA, then verify
the resulting run's `head_sha`. If development has advanced, use a temporary
candidate-only branch pointing at that SHA where necessary; keep the active
development branch. This is checkpoint isolation, not a branch per story. Observe
the trusted-code restriction on the owner-controlled Unity runner. Do not dispatch
untrusted PR code there. Record any licensing, access or runner blocker.

`tests.yml` currently cancels older runs on the same ref. A cancelled run is not
success: dispatch on an isolated candidate ref if continued pushes cancel it.
No workflow changes or duplicated tests are needed.

## Promotion checklist

1. Prepare the required minor version/reset patch on development before freezing
   the candidate. If this changes a previously green candidate, validate the new
   SHA. Ordinary implementation/documentation commits increment patch instead.
2. Fetch `origin main` and the active branch. Verify candidate identity, remote
   availability, full change scope and `git merge-base --is-ancestor origin/main
   CANDIDATE`. Unexpected divergence blocks promotion. Integrate current main on
   development if needed, then validate the resulting new candidate.
3. Inspect exact-SHA runs/jobs/steps, required status checks, repository rules,
   required reviews and acceptance artifacts. Diagnose failures using Actions job
   logs; record the cause and correction. Missing required evidence blocks merging.
4. Use a clean separate worktree for integration if development has dirty work.
   Where protection permits fast-forward, push only the explicit candidate SHA
   to main without force. If main moves, stop and repeat ancestry/gate review.
   Otherwise open the approved PR from a candidate-only branch pinned to that SHA;
   never open a moving development HEAD for an older checkpoint. Preserve reviews
   and protection. If the PR method creates a new integration commit, validate
   that result before allowing it onto main; use an approved merge queue if
   available, or remain blocked if repository policy cannot support this guarantee.
5. Confirm remote main contains the candidate and the promoted result is verified.
   Run `python tools/ci_checkpoint.py record-promotion --evidence "REVIEW URLS AND
   ACCEPTANCE RECORD"`. For the first baseline also pass `--baseline-accepted`.
   This records an already completed promotion, not permission to merge. The
   helper does not push, merge, publish, delete branches or bypass protection.

At resolution the cadence anchor becomes the current development HEAD. Thus a
checkpoint at commit 3 resolved after commit 4 schedules the next at commit 7.
Keep the pending record when a session ends. If no useful next task exists,
report pending/blocked evidence and end the session rather than polling.

## Initial adoption status

Policy implementation does not establish the playable baseline. Existing local
gameplay changes must first be integrated deliberately and committed by their
owner. GitHub CLI is not installed in the adoption environment. Install and
authenticate it (or use the connected GitHub tools to inspect and preserve the
same exact-SHA evidence), arrange the licensed Unity runner, and resolve the
documented full-match/owner acceptance gaps before any baseline promotion.

# Development integration checkpoint — 2026-11-03

This checkpoint consolidates the repository's committed branch histories for
`0.6.0-alpha.1`. It includes work in progress at the owner's explicit request;
it does not certify complete gameplay or fork acceptance.

## Included snapshots

- Consolidated Play history: `2871b44`.
- Independent local-game history: `6e8111e`. Its concession/deadlock fix was
  already applied as `1cc908e`; the merge retains newer terminal-result handling.
- XMage fork, rules identity, Unity transport and project WIP: `116a810`.
- Feedback 6–10 and automatic Unity priority WIP: `b7a7bc9`.

The WIP snapshots exclude generated root `Artifacts/` and installed runtimes.
Edits made in the original worktrees after these snapshots remain there for
continued development. Existing branches and worktrees are retained.

## Integration adjustments

Both idle-reader interfaces are preserved in Java and CSharp. Authenticated
owner-lifetime waits retain partial-frame deadlines; bounded gameplay waits
retain the six-hour session limit. Authentication and write deadlines remain
bounded. Both branches' regression cases are retained.

The integration also formats Python files covered by CI, refreshes the adapter
fixture provenance hash, updates an artwork test for the intentional engine-text
display, and allows optional asset skips in the Unity runner while requiring
enough executed passes and zero failures. Graphics PlayMode still requires no
skips. Test-only process exit budgets allow Windows reaping latency; production
cleanup and bootstrap deadlines are unchanged.

## Validation

- Python 3.13 application suite: **2,265 passed**.
- Ruff lint/format and protocol inventory/schema/fixture/model checks: passed.
- Java protocol checks: passed, including 25 real-loopback deadline checks,
  773 opening projection checks and 17 Unity priority projection checks.
- Private Java launch/rejections and pinned XMage API/helper checks: passed;
  current bridge compiled, 11 API classes verified and 155 native helper checks.
- Unity 6000.6.7f1 graphics EditMode: **466 passed**, three optional local asset
  tests skipped, zero failures.
- Graphics PlayMode: **111 passed**, zero skips.
- Windows player build, GPU player smoke, packaged deck preview and authenticated
  Java/Unity decision fixture: passed.
- Real stock-XMage first-land probe: passed with authenticated input and cleanup.

## Known unfinished acceptance

The real-engine combat probe with `--first-creature --native-metadata
--select-attacker --finish-selected-attack --declared-priority --combat-damage
--complete-combat` fails with **`LIVE_COMBAT_CLEANUP_UNPROVEN`**. Reproduce using
`tools/check_play_live_opening.py` with those switches, an installed stock bundle
via `--xmage-root`, JDK 23 via `--jdk-path`, and a new report path under Unity
`Artifacts/` via `--output`.

The native trace reaches the combat-cleanup check. The interaction with the newly
enabled priority stops needs investigation; this cause is not yet established.
Complete saved-deck/fork matches and owner visual acceptance remain unfinished.

This integration is local only. No push, tag, release, installation or publication
is part of this checkpoint.

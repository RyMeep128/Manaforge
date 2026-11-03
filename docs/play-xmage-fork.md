# Manaforge XMage downstream

Dedicated local fork: `C:/Users/ryanm/Source/Manaforge-XMage`.
Integration: `manaforge/integration`; untouched remote: `upstream` (`magefree/mage`).
The fork has not been published. Hosted branch protection and Actions results are pending.

## Source provenance

Baseline: `eb69d05b88142b5c4eec4869bcb23a0fec13c091` (`xmage_1.4.62V1`).
The installed JAR records a 2026-10-03 build date and Java 8, but no Git revision.
Exact correspondence between the binary and its declared source tag is unproven.
The untouched source baseline built successfully before adding cards.

The fork's `manaforge/changes.json` records baseline evidence, Forge script hashes,
feature identifiers, dependencies, tests, and upstream disposition. Source commits:

- `93b50a0f`: provenance, archive timestamps, update policy.
- `d819d975`: Feather, Radiant Arbiter with focused tests.
- `e5628f78`: Immortal Obligation with counter-bound combat tests.
- `d8e0fbb3`: artifact revision stamps and fork CI.
- `04f8e2ba`: deterministic test mana and complete assembly packaging; current pin.

Forge at `C:/Users/ryanm/ForgeMTG` is a behavior reference, not a dependency.
The implementations use XMage APIs; Forge scripts and artwork are not copied.
The optional London mulligan patch remains separate and is not included.

## Reproduce and stage

Use Maven 3.9.9 and JDK 23.0.2, producing Java 8 bytecode. The local Maven archive
is SHA512-verified. The build tool pins archive timestamps to the source commit
and stamps engine JAR manifests with its revision. Staging rejects mixed/stale
engine JARs and existing destinations.

```powershell
python tools/manage_xmage_fork.py build --maven C:/Users/ryanm/Source/.manaforge-tools/apache-maven-3.9.9/bin/mvn.cmd
python tools/manage_xmage_fork.py test --maven C:/Users/ryanm/Source/.manaforge-tools/apache-maven-3.9.9/bin/mvn.cmd
python tools/manage_xmage_fork.py stage --base-bundle Mtg_Projects/mtg_play/mage-full_1.4.62-dev_2026-10-03_20-47 --output NEW_BUNDLE
python tools/manage_xmage_fork.py verify --output NEW_BUNDLE --lock NEW_BUNDLE/manaforge-engine-lock.json
```

Complete Maven server/client assemblies supply engine modules. Only the bundled
Java runtime is reused. No previous engine JARs or catalog databases are copied.
Preserve engine/dependency notices. The source lock, artifact hashes and previous
bundle provide explicit upgrade/rollback points.

Before acceptance, pin the reviewed bundle marker as `mtg_play/engine-lock.json`.
A bundle cannot approve itself: its marker must byte-match the app-owned lock.
When the approved revision is installed under `.engines/<commit>`, new sessions
use it by default. A source checkout without that installed bundle retains the
stock path. An installed candidate with a missing/mismatched marker fails closed.
Legacy bundles retain their original `artifacts.json`. Gateway launch manifests,
viewer bootstraps, and adapter compatibility use the selected manifest's digest.
Fork identity is separate from the `1.4.62-V1` protocol compatibility identifier.

```powershell
python tools/check_play_unity_game.py --format commander --human-deck DECK --ai-deck DECK --xmage-root NEW_BUNDLE --output NEW_REPORT_DIRECTORY
```

This is the explicit acceptance harness. Normal play uses engine-owned choices.
Add `--startup-only` to check authenticated opening-hand startup and cancel after
ten seconds without submitting gameplay choices; this does not verify a full match.
Rollback selects the previous immutable bundle; running sessions never switch
engine versions. Deck artwork IDs remain independent of engine printing selection.

## Coverage and upstream maintenance

```powershell
python tools/check_xmage_cards.py --all-cards --output NEW_COVERAGE_DIRECTORY
python tools/build_xmage_backlog.py --coverage NEW_COVERAGE_DIRECTORY/report.json --source C:/Users/ryanm/Source/Manaforge-XMage --upstream upstream/master --output NEW_BACKLOG_DIRECTORY
python tools/manage_xmage_fork.py candidate --upstream UPSTREAM_COMMIT --output NEW_WORKTREE
```

The backlog records canonical Oracle IDs, identity matches, source registrations,
Forge hashes, required mechanics, dependencies and regression-test slots. Tokens,
novelty cards, digital cards, and non-game objects are separate. Commented-out
registrations and missing source files do not establish upstream support.
`catalog_and_class_present` is weaker than verified behavioral support.

Initial corrected paper triage: 926 missing names plus 279 upstream registrations.
These are provisional findings. Deliver the two Blame Game cards first, then saved
deck needs, shared mechanics, and remaining paper cards by set/name. One delivered
batch does not complete the full coverage program.

For updates, fetch upstream, create an isolated worktree, reconcile the ledger,
and replay retained commits in dependency order. Keep tests when upstream replaces
local code; never overwrite integration or automatically discard conflicting work.
An update rehearsal checkout exists at
`C:/Users/ryanm/Source/Manaforge-XMage-UpdateRehearsal`, based on upstream
`1acac4aa7f69e44dcbb7b1d8bd7a5b7eae68d22e`.

Promotion gates: clean module build; focused card tests; broad engine tests in CI;
adapter/authentication/privacy/cleanup compatibility; fresh catalog; packaged
Blame Game launch and card interactions; update and rollback evidence; owner review.
The fork CI workflow builds matching assemblies and offers optional broad tests.
GitHub Actions and owner acceptance remain pending until executed/reviewed.

## Delivered batch and evidence

Current source pin: `04f8e2ba0dbda21bd0ed6cbd1ec6e233073624f1`.
The locally installed bundle is under `mtg_play/.engines/<commit>`; the original
downloaded bundle remains unchanged. Recovery patch: `Artifacts/Manaforge-XMage-local-changes.patch`.

- Both new cards have registered implementations and 16 passing rules tests.
- Both server/client assembly ZIPs reproduced byte-for-byte using the pinned source/toolchain.
- Fresh catalog: both cards available; saved Blame Game: 88 available entries, one skipped display commander.
- Native connection, identity/privacy, optional-payment, and stock rollback checks passed.
- Packaged Blame Game authenticated startup passed, cancelled with no gameplay choices submitted.
- All 16 card tests passed after replay onto newer upstream in the isolated rehearsal checkout. That upgrade is not promoted.
- Java protocol/projection checks cover the ambiguous-artwork safeguard: identical rules entries with different selected artworks use fallback rendering rather than choosing an arbitrary printing.

Structured evidence: `Artifacts/XmageFork-Verification.json`. The delivery backlog
is `Artifacts/XmageFork-DeliveryBacklog/backlog.json`; it records two engine-tested
implementations, 924 missing paper names, and 279 newer-upstream registrations.
These remaining counts are triage findings, not a completed coverage claim.

The backlog accepts `--engine-lock PATH --junit SUREFIRE_DIRECTORY` to associate
passing card tests with the exact source revision and catalog JAR hash. Mismatched
or failed evidence cannot mark a card verified. Saved-deck priority uses canonical
Oracle identities and ignores display copies. Owner acceptance remains separate.

### Outstanding gates and manual review

- [ ] Publish the source fork and enable protected-branch required checks when publication is requested.
- [ ] Run broad engine and Manaforge CI; no GitHub Actions success is claimed here.
- [ ] Complete a packaged Blame Game match, exercising Feather copies/payment and Immortal Obligation's duty-counter restrictions.
- [ ] Review selected artwork, hovering/inspection, mixed-art fallback, targeting and cleanup in the normal UI.
- [ ] Capture unobstructed representative gameplay and result screenshots; the current opening capture is partially covered by a Windows Firewall prompt, which automation did not operate.
- [ ] Investigate the `FRAME_TIMEOUT` seen in the first unattended 60-second startup check; the shorter startup check passes, but idle/full-match behavior is not certified.
- [ ] Owner review and final acceptance.

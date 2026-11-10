# Release versioning

- Manaforge is in prerelease development. Keep new versions labelled `-alpha.1` (or `-beta.1` once the user chooses beta); do not publish a stable release without explicit instruction.
- Before each requested implementation/documentation commit, increment the patch component of `APP_VERSION` in `Mtg_Projects/mtg_proxy/constants.py` and include it in that commit. For example, `0.2.1-alpha.1` becomes `0.2.2-alpha.1`.
- When merging a development branch into `main`, increment the minor component and reset patch to zero, retaining the prerelease label. For example, `0.2.3-alpha.1` becomes `0.3.0-alpha.1`. Include the version update in the merge work before pushing.
- The first prerelease commit after `0.1.1` is `0.1.2-alpha.1`. Do not retroactively change existing tags or releases.
- A version bump does not authorize creating a GitHub release or tag. If publishing is requested, mark alpha/beta releases as prereleases.

# Development workspace

- Always work directly on `main`. Do not create development, integration, feature, or release branches unless the user explicitly requests one.
- The canonical workspace is `C:/Users/ryanm/Proxy App/branch_print-proxy-prep-QtPort`.
- Preserve existing work and shared Git history. Never force-push or bypass repository protection.
- Always rebuild the local Unity Windows player after Unity changes using `./tools/unity-play.ps1 -Mode Build`. Report build failures explicitly; a CI run does not replace the local rebuild.
- Use GitHub Actions for test suites; do not run local test suites. Report unavailable or incomplete checks accurately.
- Follow [the workflow guide](docs/development-workflow.md) for CI evidence. The former development-branch promotion cadence is retired.

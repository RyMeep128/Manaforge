# Release versioning

- Manaforge is in prerelease development. Keep new versions labelled `-alpha.1` (or `-beta.1` once the user chooses beta); do not publish a stable release without explicit instruction.
- Before each requested implementation/documentation commit, increment the patch component of `APP_VERSION` in `Mtg_Projects/mtg_proxy/constants.py` and include it in that commit. For example, `0.2.1-alpha.1` becomes `0.2.2-alpha.1`.
- When merging a development branch into `main`, increment the minor component and reset patch to zero, retaining the prerelease label. For example, `0.2.3-alpha.1` becomes `0.3.0-alpha.1`. Include the version update in the merge work before pushing.
- The first prerelease commit after `0.1.1` is `0.1.2-alpha.1`. Do not retroactively change existing tags or releases.
- A version bump does not authorize creating a GitHub release or tag. If publishing is requested, mark alpha/beta releases as prereleases.

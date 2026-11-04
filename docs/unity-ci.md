# Hosted Unity checks

`Unity Play feasibility` runs on GitHub-hosted Windows 2025, on relevant `main`
pushes and manual dispatch. It does not depend on a self-hosted runner. Per-ref
concurrency replaces obsolete runs with the latest commit.

Configure these repository [Actions secrets](https://github.com/RyMeep128/Manaforge/settings/secrets/actions):

- `UNITY_LICENSE`: the complete valid Personal license ULF file, obtained using
  Unity's supported licensing process.
- `UNITY_EMAIL`: the associated Unity account email.
- `UNITY_PASSWORD`: the associated Unity account password.

Keep credentials out of chat, repository files, and artifacts. The setup step fails
explicitly if a secret is absent. A secret name alone does not activate Unity;
Unity must accept the supplied license on the hosted machine. See the
[Unity manual activation documentation](https://docs.unity.com/en-us/engine/6000.7/manual/get-started/install-and-upgrade/licenses-and-activation/manual-license-activation/manual-activation-cmd-win).

`tools/setup_unity_ci.ps1` refuses to run outside hosted Windows Actions. It
downloads the editor pinned in ProjectVersion.txt, checks the official release
integrity digest and Windows publisher signature, installs silently, and imports
the license. Update its installer URL, digest, and version guard together when
upgrading Unity. License files and private activation logs are deleted, and are
never uploaded. The installed editor is passed to the existing Unity tooling.

The job retains EditMode, graphics-enabled PlayMode (skips fail), Windows player
build, packaged smoke capture, theme fixtures, public artwork preview, and
authenticated decision fixtures. Windows-specific pipe and ownership checks run
on their supported platform. Graphics failures on hosted infrastructure remain
failures; headless execution does not substitute for visual evidence.

Artifacts include test XML, screenshots, fixture reports, player build, and the
exact source SHA. Inspect the workflow run for that SHA before reporting success.
Missing licenses, incomplete jobs, and skipped checks are not passing evidence.

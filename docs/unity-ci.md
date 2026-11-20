# Hosted Unity checks

`Unity Play feasibility` runs on GitHub-hosted Windows 2025, on relevant `main`
pushes and manual dispatch. It does not depend on a self-hosted runner. Per-ref
concurrency replaces obsolete runs with the latest commit.

The current setup script uses license-file activation. It is not a working
unattended setup for the owner's current Unity Personal named-user license.
Unity Personal activates through Unity Hub; its entitlement XML is not a ULF
file and must not be substituted for one. Email and password secrets alone do
not resolve this. A supported CI licensing setup is required before publication;
do not skip the Unity checks or treat a local build as hosted acceptance.

For a license that supports this file-based activation, the script expects these
repository [Actions secrets](https://github.com/RyMeep128/Manaforge/settings/secrets/actions):

- `UNITY_LICENSE`: the complete valid license ULF file, obtained using
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

## Optional Personal license runner

The Unity validation workflow exposes a manual `use_personal_runner` input,
disabled by default. It selects an explicitly
approved Windows Actions runner labelled `manaforge-personal-unity`, running
under the same desktop account that activated the pinned editor in Unity Hub.
The runner is used only for repository-owner manual dispatches of `main`.
Pushes, pull requests and other actors cannot select this runner through these
workflows. `tools/use_personal_unity_ci.ps1` independently enforces that boundary.
It uses an existing Python 3.12/3.13 installation and JDK 23.0.2+7, with Python
dependencies isolated in a temporary virtual environment. It does not run the
hosted Python or Java installers on the owner's PC.

Registering a runner gives repository jobs access to the Windows account's
machine and files. Obtain the owner's explicit approval before registering it.
Use a temporary runner for Unity validation, remove it afterward, and never
install a persistent runner service. No Unity
password, local entitlement file or license is uploaded to GitHub. Builds,
graphics checks and test suites still run as GitHub Actions jobs; successful
exact-revision checks remain mandatory before publishing an alpha prerelease.

The Windows packaging workflow can set `use_verified_unity_player` to download
the player artifact from a successful Unity validation run at the exact same
commit. It verifies the run and all job results, artifact digest, and source
revision before extraction. Packaging stays on GitHub-hosted Windows, including
installer compilation and complete packaged gameplay acceptance. No installer
compiler or packaging service needs to be installed on the owner's PC.

The job retains EditMode, graphics-enabled PlayMode (skips fail), Windows player
build, packaged smoke capture, theme fixtures, public artwork preview, and
authenticated decision fixtures. Windows-specific pipe and ownership checks run
on their supported platform. Graphics failures on hosted infrastructure remain
failures; headless execution does not substitute for visual evidence.

Artifacts include test XML, screenshots, fixture reports, player build, and the
exact source SHA. Inspect the workflow run for that SHA before reporting success.
Missing licenses, incomplete jobs, and skipped checks are not passing evidence.

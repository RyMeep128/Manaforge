"""Build, stage, verify and rehearse updates for the separate XMage source fork."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Mtg_Projects"))
from mtg_play.engine_fork import git, source_revision, read_lock, verify_artifacts, validate_toolchain  # noqa: E402

MODULES = "Mage.Server,Mage.Client,Mage.Tests"
FOCUSED = "FeatherRadiantArbiterTest,ImmortalObligation*Test,HitItTest,MjolnirHammerOfThorTest"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def extract(archive, destination):
    from mtg_play.ci_prepare import extract as checked_extract
    checked_extract(archive, dict(prefix="", destination=""), destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "test", "stage", "verify", "candidate", "activate"))
    parser.add_argument("--source", type=Path, default=Path.home() / "Source/Manaforge-XMage")
    parser.add_argument("--maven", default="mvn")
    parser.add_argument("--jdk", type=Path, default=Path("C:/Program Files/Java/jdk-23"))
    parser.add_argument("--base-bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--upstream", help="Exact fetched upstream revision for a candidate worktree")
    parser.add_argument("--ci-archive", type=Path, help="GitHub Actions artifact ZIP containing complete server/client assemblies")
    parser.add_argument("--ci-sha256", help="Expected GitHub artifact digest; required for --ci-archive")
    parser.add_argument("--variant", action="store_true", help="Give this build an immutable ID based on its source and runtime-file hashes")
    args = parser.parse_args()
    if args.operation == "activate":
        if not args.output:
            parser.error("activate requires --output pointing to a staged immutable bundle")
        marker = args.output / "manaforge-engine-lock.json"
        raw = marker.read_bytes()
        lock = read_lock(marker)
        approved = ROOT / "Mtg_Projects/mtg_play/engine-lock.json"
        expected = approved.parent / ".engines" / lock.get("bundle_id", lock["fork_commit"])
        if args.output.resolve() != expected.resolve():
            raise ValueError("Install the candidate under .engines/<fork_commit> before activation")
        verify_artifacts(args.output, lock)
        history = approved.parent / ".engines/pins"
        history.mkdir(parents=True, exist_ok=True)
        if approved.is_file():
            previous = approved.read_bytes()
            backup = history / (hashlib.sha256(previous).hexdigest() + ".json")
            if not backup.exists():
                backup.write_bytes(previous)
        temporary = approved.with_name("engine-lock." + uuid.uuid4().hex + ".tmp")
        temporary.write_bytes(raw)
        temporary.replace(approved)
        print("Development engine selected for new sessions: " + lock["fork_commit"])
        print("Previous pin retained; active sessions and existing bundles are unchanged. Owner acceptance remains pending.")
        return
    if args.operation == "verify":
        if not args.output or not args.lock:
            parser.error("verify requires --output BUNDLE and --lock")
        verify_artifacts(args.output, read_lock(args.lock))
        print("All pinned engine artifacts verified")
        return
    revision = source_revision(args.source)
    if args.operation in ("build", "test"):
        env = dict(os.environ, JAVA_HOME=str(args.jdk), MAVEN_OPTS="-Xmx6g -Dfile.encoding=UTF-8")
        java = args.jdk / "bin" / ("java.exe" if os.name == "nt" else "java")
        java_version = subprocess.run([str(java), "-version"], capture_output=True, text=True, check=True)
        maven_version = subprocess.run([args.maven, "-version"], env=env, capture_output=True, text=True, check=True)
        validate_toolchain(java_version.stdout + java_version.stderr, maven_version.stdout + maven_version.stderr)
        timestamp = git(args.source, "show", "-s", "--format=%cI", "HEAD")
        command = [args.maven, "-B", "-ntp", "-Dmanaforge.revision=" + revision, "-Dproject.build.outputTimestamp=" + timestamp, "-pl", MODULES, "-am"]
        if args.operation == "build":
            command += ["clean", "install", "-DskipTests"]
        else:
            command += ["test", "-Dtest=" + FOCUSED, "-Dsurefire.failIfNoSpecifiedTests=false"]
        subprocess.run(command, cwd=args.source, env=env, check=True)
        if args.operation == "build":
            subprocess.run([args.maven, "-B", "-ntp", "-Dmanaforge.revision=" + revision, "-Dproject.build.outputTimestamp=" + timestamp, "-pl", "Mage.Server,Mage.Client", "package", "assembly:single", "-DskipTests"], cwd=args.source, env=env, check=True)
        print("Source revision: " + revision)
        return
    if args.operation == "candidate":
        if not args.output or not args.upstream:
            parser.error("candidate requires --output and --upstream exact revision")
        upstream = git(args.source, "rev-parse", args.upstream + "^{commit}")
        subprocess.run(["git", "-C", str(args.source), "worktree", "add", "--detach", str(args.output.resolve()), upstream], check=True)
        print("Candidate created without modifying integration; replay ledger commits, reconcile upstream equivalents, then build and test")
        return
    if not args.base_bundle:
        parser.error("stage requires --base-bundle")
    automatic_output = args.output is None
    engine_area = ROOT / "Mtg_Projects/mtg_play/.engines"
    if automatic_output:
        args.output = engine_area / (".stage-" + uuid.uuid4().hex)
    if args.output.exists():
        raise ValueError("Staging destination must not exist; working bundles are never overwritten")
    # Use complete Maven assemblies. No engine JARs are inherited from the old bundle.
    archives = {name: args.source / module / "target" / (name + ".zip") for name, module in (("mage-server", "Mage.Server"), ("mage-client", "Mage.Client"))}
    ci_workspace = None
    if args.ci_archive:
        if not args.ci_sha256 or digest(args.ci_archive) != args.ci_sha256:
            raise ValueError("CI artifact checksum is missing or mismatched")
        area = ROOT / "Artifacts"
        area.mkdir(exist_ok=True)
        ci_workspace = tempfile.TemporaryDirectory(prefix="xmage-ci-import-", dir=area)
        workspace = Path(ci_workspace.name).resolve()
        if not workspace.is_relative_to(area.resolve()):
            raise ValueError("CI import directory escaped the artifact workspace")
        with zipfile.ZipFile(args.ci_archive) as outer:
            for name, module in (("mage-server", "Mage.Server"), ("mage-client", "Mage.Client")):
                wanted = module + "/target/" + name + ".zip"
                if outer.namelist().count(wanted) != 1:
                    raise ValueError("CI artifact lacks one unambiguous assembly: " + wanted)
                target = workspace / (name + ".zip")
                target.write_bytes(outer.read(wanted))
                archives[name] = target
    for archive in archives.values():
        if not archive.is_file():
            raise ValueError("Missing assembly; run Maven assembly:single after build: " + str(archive))
    args.output.mkdir(parents=True)
    for name, archive in archives.items():
        destination = args.output / "xmage" / name
        destination.mkdir(parents=True)
        extract(archive, destination)
        if len(list((destination / "lib").glob(name + "-*.jar"))) != 1:
            raise ValueError("Assembly is missing its own module JAR; run package assembly:single together")
        if (destination / "db").exists():
            raise ValueError("New assembly unexpectedly contains a catalog; stage a database-free build")
    shutil.copytree(args.base_bundle / "java", args.output / "java")
    ledger_path = args.source / "manaforge/changes.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    for jar in (args.output / "xmage").rglob("mage-*.jar"):
        with zipfile.ZipFile(jar) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8").replace("\r\n ", "")
            if "Manaforge-Revision: " + revision not in manifest:
                raise ValueError("Engine JAR was not built from this source revision: " + str(jar))
    (args.output / "SOURCE.txt").write_bytes(("XMage source: " + revision + "\nUpstream: " + ledger["upstream_commit"] + "\n").encode("utf-8"))
    shutil.copy2(args.output / "xmage/mage-server/LICENSE.txt", args.output / "XMAGE-LICENSE.txt")
    artifacts = {p.relative_to(args.output).as_posix(): digest(p) for p in sorted(args.output.rglob("*")) if p.is_file()}
    lock = dict(lock_version=1, engine="1.4.62-V1", distribution="manaforge-xmage", upstream_repository="https://github.com/magefree/mage.git", upstream_commit=ledger["upstream_commit"], fork_commit=revision, local_changes=ledger["changes"], toolchain=dict(maven="3.9.9", jdk="23", release=8), assemblies={name: digest(path) for name, path in archives.items()}, artifacts=artifacts, acceptance="pending")
    lock["build_origin"] = "ci_archive" if args.ci_archive else "local_source_build"
    if args.ci_archive:
        lock["ci_artifact_sha256"] = args.ci_sha256
    if args.variant or args.ci_archive:
        content = hashlib.sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
        lock["bundle_id"] = revision + "-" + content
    raw = json.dumps(lock, indent=2) + "\n"
    (args.output / "manaforge-engine-lock.json").write_text(raw, encoding="utf-8")
    verify_artifacts(args.output, lock)
    if automatic_output:
        destination = engine_area / lock.get("bundle_id", revision)
        if not args.output.resolve().is_relative_to(engine_area.resolve()) or not destination.resolve().is_relative_to(engine_area.resolve()):
            raise ValueError("Immutable bundle move escaped the engine directory")
        if destination.exists():
            raise ValueError("Build variant already exists; no existing bundle overwritten")
        args.output.rename(destination)
        args.output = destination
    if ci_workspace is not None:
        ci_workspace.cleanup()
    print("Staged candidate: " + str(args.output.resolve()))
    print("Review the lock and pin it in Manaforge before acceptance. Existing bundles remain unchanged.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))

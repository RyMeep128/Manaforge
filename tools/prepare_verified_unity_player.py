"""Archive local Unity evidence, or verify and import it for hosted packaging."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "Mtg_Projects/mtg_play_unity"
REQUIRED_STAGES = json.loads((ROOT / "tools/unity_local_stages.json").read_text())
MAX_ARCHIVE = 2 * 1024**3
MAX_PAYLOAD = 4 * 1024**3


def read_report(report, commit, allow_unvalidated=False):
    if allow_unvalidated and report.get("scope") == "build-only":
        if (report.get("schema") != 1 or report.get("commit") != commit
                or report.get("dirty") is not False or report.get("status") != "built"
                or report.get("tests") != "skipped"):
            raise ValueError("Exact-revision clean local build receipt required")
        return
    if (
        report.get("schema") != 1
        or report.get("commit") != commit
        or report.get("dirty") is not False
        or report.get("status") != "passed"
    ):
        raise ValueError(
            "Exact-revision successful local Unity validation from a clean workspace required"
        )
    stages = report.get("stages", [])
    if (
        not stages
        or any(s.get("status") != "passed" for s in stages)
        or not set(REQUIRED_STAGES).issubset({s.get("name") for s in stages})
    ):
        raise ValueError("Local Unity validation stages are incomplete")


def create(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    read_report(report, report["commit"])
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        text=True,
    )
    if commit != report["commit"] or dirty:
        raise ValueError("Commit or workspace changed after local Unity validation")
    started = datetime.fromisoformat(report["started"]).timestamp()
    finished = datetime.fromisoformat(report["finished"]).timestamp()
    files = {}
    for path in (PROJECT / "Builds/Windows").rglob("*"):
        if path.is_file():
            files[path.relative_to(PROJECT).as_posix()] = path
    patterns = json.loads((ROOT / "tools/unity_local_evidence.json").read_text())
    for pattern in patterns:
        for path in PROJECT.glob(pattern):
            candidates = path.rglob("*") if path.is_dir() else [path]
            for candidate in candidates:
                if candidate.is_file() and candidate.stat().st_mtime >= started:
                    files[candidate.relative_to(PROJECT).as_posix()] = candidate
    if not {
        "Builds/Windows/ManaforgePlay.exe",
        "Builds/Windows/UnityPlayer.dll",
        "Artifacts/editmode.xml",
        "Artifacts/playmode.xml",
    }.issubset(files):
        raise ValueError("Player or test evidence is missing")
    if any(path.stat().st_mtime > finished + 1 for path in files.values()):
        raise ValueError("Unity payload changed after local validation")
    report["files"] = {}
    for name, path in files.items():
        with path.open("rb") as stream:
            report["files"][name] = hashlib.file_digest(stream, "sha256").hexdigest()
    archive = report_path.parent / ("unity-local-" + report["commit"] + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr("validation.json", json.dumps(report, indent=2))
        for name, path in files.items():
            target.write(path, name)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n")
    print(f"Validated local player: {archive}\nSHA256: {digest}")


def safe_name(name):
    path = PurePosixPath(name)
    return (
        name == path.as_posix()
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
        and ":" not in name
        and all(part and not part.endswith((".", " ")) for part in path.parts)
    )


def create_build(destination):
    """Explicit unvalidated prerelease input; never represents test acceptance."""
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, text=True):
        raise ValueError("A clean committed workspace is required")
    files = {p.relative_to(PROJECT).as_posix(): p for p in (PROJECT / "Builds/Windows").rglob("*") if p.is_file()}
    if not {"Builds/Windows/ManaforgePlay.exe", "Builds/Windows/UnityPlayer.dll"}.issubset(files):
        raise ValueError("Windows player build missing")
    report = dict(schema=1, commit=commit, dirty=False, scope="build-only", status="built", tests="skipped", files={})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            with path.open("rb") as stream:
                report["files"][name] = hashlib.file_digest(stream, "sha256").hexdigest()
            archive.write(path, name)
        archive.writestr("validation.json", json.dumps(report, indent=2))
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    destination.with_suffix(".zip.sha256").write_text(digest + "  " + destination.name + "\n")
    print(f"UNVALIDATED local player: {destination}\nSHA256: {digest}")


def extract(archive, commit, destination, allow_unvalidated=False):
    if destination.exists():
        raise ValueError("Use a fresh Unity player destination")
    with zipfile.ZipFile(archive) as source:
        entries = [entry for entry in source.infolist() if not entry.is_dir()]
        names = [entry.filename for entry in entries]
        if (
            len(names) != len(set(n.casefold() for n in names))
            or any(not safe_name(n) for n in names)
            or any((e.external_attr >> 16) & 0o170000 == 0o120000 for e in entries)
            or sum(e.file_size for e in entries) > MAX_PAYLOAD
        ):
            raise ValueError("Unsafe or oversized local Unity archive")
        if source.getinfo("validation.json").file_size > 16 * 1024**2:
            raise ValueError("Oversized validation manifest")
        report = json.loads(source.read("validation.json"))
        read_report(report, commit, allow_unvalidated)
        files = report.get("files", {})
        if set(names) != set(files) | {"validation.json"}:
            raise ValueError("Unity archive file inventory differs from manifest")
        required = {
            "Builds/Windows/ManaforgePlay.exe",
            "Builds/Windows/UnityPlayer.dll",
            "Artifacts/editmode.xml",
            "Artifacts/playmode.xml",
        }
        if allow_unvalidated and report.get("scope") == "build-only":
            required = {"Builds/Windows/ManaforgePlay.exe", "Builds/Windows/UnityPlayer.dll"}
        if not required.issubset(files):
            raise ValueError("Player or test evidence is missing")
        for name, digest in files.items():
            with source.open(name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError("Unity payload checksum mismatch")
        # Validate everything before creating the destination. Only player files are imported.
        for entry in entries:
            if not entry.filename.startswith("Builds/Windows/"):
                continue
            target = destination / entry.filename[len("Builds/Windows/") :]
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output)
        (destination / "local-validation.json").write_text(json.dumps(report, indent=2))
    print(f"Imported local Unity {'build only; tests skipped' if report.get('scope') == 'build-only' else 'validation'} for {commit}")


def prepare(url, digest, commit, destination, allow_unvalidated=False):
    if not url.startswith("https://") or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ValueError("An HTTPS local Unity archive URL and SHA256 are required")
    with tempfile.TemporaryDirectory(prefix="manaforge-local-unity-") as temporary:
        archive = Path(temporary) / "unity.zip"
        with (
            urllib.request.urlopen(url, timeout=120) as response,
            archive.open("wb") as output,
        ):
            if not response.url.startswith("https://"):
                raise ValueError("Unity archive redirect must use HTTPS")
            size = 0
            while chunk := response.read(1024**2):
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError("Unity archive exceeds size limit")
                output.write(chunk)
        with archive.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest.lower():
                raise ValueError("Unity archive checksum mismatch")
        extract(archive, commit, destination, allow_unvalidated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", type=Path)
    parser.add_argument("--create-build", type=Path, help="Archive a clean local build with tests explicitly skipped")
    parser.add_argument("--allow-unvalidated", action="store_true", help="Allow a build-only receipt for an explicitly untested prerelease")
    parser.add_argument("--url")
    parser.add_argument("--sha256")
    parser.add_argument("--commit")
    args = parser.parse_args()
    if args.create_build:
        create_build(args.create_build)
    elif args.create:
        create(args.create)
    elif args.url and args.sha256 and args.commit:
        prepare(args.url, args.sha256, args.commit, PROJECT / "Builds/Windows", args.allow_unvalidated)
    else:
        parser.error("Supply --create REPORT or --url URL --sha256 DIGEST --commit SHA")

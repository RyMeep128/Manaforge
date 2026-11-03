"""Pinned source-build provenance for the optional Manaforge XMage fork."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def validate_toolchain(java_version, maven_version):
    if not re.search(r'version "23\.0\.2(?:["+])', java_version):
        raise ValueError("Engine builds require JDK 23.0.2")
    if not re.search(r"Apache Maven 3\.9\.9(?:\s|$)", maven_version):
        raise ValueError("Engine builds require Maven 3.9.9")


def git(source, *args):
    return subprocess.check_output(
        ["git", "-C", str(source), *args], encoding="utf-8"
    ).strip()


def source_revision(source, expected=None):
    revision = git(source, "rev-parse", "HEAD")
    if git(source, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Engine checkout must be clean before building or staging")
    if expected and revision != expected:
        raise ValueError("Engine source revision differs from lock")
    return revision


def installation_manifest(bundle, legacy_manifest=None):
    """A bundle cannot bless itself: require the app's identical approved lock."""
    marker = Path(bundle) / "manaforge-engine-lock.json"
    if not marker.is_file():
        return Path(legacy_manifest or HERE / "artifacts.json")
    approved = HERE / "engine-lock.json"
    raw = marker.read_bytes()
    if approved.is_file() and raw == approved.read_bytes():
        return approved
    historical = HERE / ".engines/pins" / (hashlib.sha256(raw).hexdigest() + ".json")
    if historical.is_file() and historical.read_bytes() == raw:
        return historical
    raise ValueError("Fork bundle is not pinned by this Manaforge checkout")


def manifest_digest(bundle):
    return hashlib.sha256(installation_manifest(bundle).read_bytes()).hexdigest()


def verify_artifacts(bundle, manifest):
    root = Path(bundle).resolve()
    for relative, expected in manifest["artifacts"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Missing or unsafe engine artifact: " + relative)
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("Engine artifact hash mismatch: " + relative)


def read_lock(path):
    lock = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        lock.get("lock_version") != 1
        or not lock.get("fork_commit")
        or not lock.get("artifacts")
    ):
        raise ValueError("Invalid engine lock")
    revision = lock["fork_commit"]
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
    ):
        raise ValueError("Invalid pinned fork revision")
    identity = lock.get("bundle_id", revision)
    if not isinstance(identity, str) or not re.fullmatch(
        re.escape(revision) + r"(?:-[0-9a-f]{12})?", identity
    ):
        raise ValueError("Invalid engine build variant")
    return lock


def selected_bundle(legacy):
    """Use an installed approved fork; a source-only checkout keeps its stock path."""
    approved = HERE / "engine-lock.json"
    if not approved.is_file():
        return Path(legacy)
    revision = read_lock(approved)["fork_commit"]
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
    ):
        raise ValueError("Invalid pinned fork revision")
    candidate = HERE / ".engines" / read_lock(approved).get("bundle_id", revision)
    if not candidate.is_dir():
        return Path(legacy)
    if not (candidate / "manaforge-engine-lock.json").is_file():
        raise ValueError("Installed fork bundle is not pinned")
    installation_manifest(candidate)
    return candidate

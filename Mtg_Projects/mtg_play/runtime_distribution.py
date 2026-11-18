"""Immutable gameplay payloads and cross-process activation/session ownership."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import threading
from functools import wraps

from mtg_core.downloads import atomic_json
from mtg_core.paths import data_root

_mutex = threading.RLock()
_depth = threading.local()


def component_root():
    return data_root() / "play-components"


def owned(function):
    @wraps(function)
    def call(*args, **kwargs):
        with ownership():
            return function(*args, **kwargs)

    return call


def bundled_root():
    return Path(__file__).resolve().parent / "distribution"


def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def safe_path(root, relative):
    parts = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or parts.is_absolute()
        or any(
            not p or p in ("..", ".") or p.endswith((".", " "))
            for p in relative.split("/")
        )
    ):
        raise ValueError("Unsafe gameplay payload path")
    root = Path(root).resolve()
    path = root.joinpath(*parts.parts)
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink() or (
            hasattr(candidate, "is_junction") and candidate.is_junction()
        ):
            raise ValueError("Linked gameplay payload path")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Gameplay payload escaped its directory")
    return path


def read_manifest(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid gameplay component manifest")
    if (
        value.get("schema") != 1
        or value.get("platform") != "windows-x64"
        or not re.fullmatch(r"[0-9a-f]{64}", value.get("bridge_fingerprint", ""))
        or not re.fullmatch(
            r"[0-9a-f]{40}(?:-[0-9a-f]{12})?", value.get("bundle_id", "")
        )
        or not isinstance(value.get("files"), dict)
        or not value["files"]
        or not isinstance(value.get("compatible_app_versions"), list)
        or not value["compatible_app_versions"]
        or not re.fullmatch(
            r"\d+\.\d+\.\d+-(?:alpha|beta)\.1", value.get("component_version", "")
        )
        or not re.fullmatch(r"[0-9a-f]{64}", value.get("payload_sha256", ""))
        or type(value.get("size")) is not int
        or value["size"] <= 0
    ):
        raise ValueError("Invalid gameplay component manifest")
    for name, expected in value["files"].items():
        safe_path(Path(path).parent, name)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid gameplay component hash")
    for required in (
        "manaforge-engine-lock.json",
        "bridge/classes/ManaforgeBridge.class",
        "java/jre1.8.0_201/bin/java.exe",
    ):
        if required not in value["files"]:
            raise ValueError("Incomplete gameplay component inventory")
    return value


def verify(root, manifest):
    root = Path(root)
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual - {"component.json"} != set(manifest["files"]):
        raise ValueError("Unexpected or missing gameplay payload files")
    for name, expected in manifest["files"].items():
        path = safe_path(root, name)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError("Gameplay payload hash mismatch: " + name)
    lock = json.loads(
        (Path(root) / "manaforge-engine-lock.json").read_text(encoding="utf-8")
    )
    if lock.get("bundle_id", lock.get("fork_commit")) != manifest["bundle_id"]:
        raise ValueError("Gameplay engine identity mismatch")
    for name, expected in lock["artifacts"].items():
        if manifest["files"].get(name) != expected:
            raise ValueError("Engine lock and component inventory disagree: " + name)


@contextmanager
def ownership():
    """One owner across launch, gameplay, health checks, rollback and activation."""
    if not _mutex.acquire(blocking=False):
        raise ValueError(
            "A game or XMage operation is active. Retry after it finishes."
        )
    handle = None
    try:
        if not getattr(_depth, "value", 0):
            component_root().mkdir(parents=True, exist_ok=True)
            handle = (component_root() / "operation.lock").open("a+b")
            if handle.seek(0, 2) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError(
                    "A game or XMage operation is active. Retry after it finishes."
                ) from error
        _depth.value = getattr(_depth, "value", 0) + 1
        try:
            yield
        finally:
            _depth.value -= 1
    finally:
        if handle:
            handle.close()
        _mutex.release()


def compatible(manifest):
    from mtg_proxy.constants import APP_VERSION

    baseline = bundled_root() / "xmage/component.json"
    return (
        baseline.is_file()
        and APP_VERSION in manifest["compatible_app_versions"]
        and not ("-beta." in APP_VERSION and "-alpha." in manifest["component_version"])
        and manifest["bridge_fingerprint"]
        == read_manifest(baseline)["bridge_fingerprint"]
    )


def approved_record(root):
    """Authority lives outside the downloaded bundle, written after verification."""
    root = Path(root).resolve()
    if root.parent != (component_root() / "installed").resolve():
        return None
    receipt = component_root() / "approved" / (root.name + ".json")
    if not receipt.is_file():
        return None
    manifest = read_manifest(receipt)
    if root.name != manifest["bundle_id"] + "-" + manifest["payload_sha256"][:12]:
        raise ValueError("Invalid approved component location")
    if not compatible(manifest):
        return None
    return manifest


def selected_engine(*, verify_payload=True):
    state = component_root() / "active.json"
    if state.is_file():
        try:
            record = json.loads(state.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                record = {}
        except (OSError, ValueError):
            record = {}
        for key in ("active", "previous") if record.get("active") is not None else ():
            identity = record.get(key)
            if not isinstance(identity, str) or not re.fullmatch(
                r"[0-9a-f-]+", identity
            ):
                continue
            root = component_root() / "installed" / identity
            try:
                manifest = approved_record(root)
                if manifest:
                    if verify_payload:
                        verify(root, manifest)
                    return root
            except (OSError, ValueError, KeyError):
                continue
    root = bundled_root() / "xmage"
    return root if root.is_dir() else None


def player_path(legacy):
    path = bundled_root() / "unity/ManaforgePlay.exe"
    if getattr(sys, "frozen", False) and not path.is_file():
        raise ValueError("Bundled Unity player is missing. Reinstall Manaforge.")
    return path if path.is_file() else legacy


def bridge_classes(bundle):
    root = Path(bundle)
    manifest = approved_record(root)
    if manifest is None and root.resolve() == (bundled_root() / "xmage").resolve():
        manifest = read_manifest(root / "component.json")
    if manifest is None:
        return None
    verify(root, manifest)
    return root / "bridge/classes"


def verify_bundled():
    from mtg_proxy.constants import APP_VERSION

    root = bundled_root()
    manifest = read_manifest(root / "xmage/component.json")
    if APP_VERSION not in manifest["compatible_app_versions"]:
        raise ValueError("Bundled engine does not match this Manaforge version")
    verify(root / "xmage", manifest)
    inventory = json.loads((root / "unity.json").read_text(encoding="utf-8"))
    for name, expected in inventory["files"].items():
        if sha256(safe_path(root / "unity", name)) != expected:
            raise ValueError("Bundled Unity player is damaged")
    if "ManaforgePlay.exe" not in inventory["files"]:
        raise ValueError("Bundled Unity player is missing")


def activate(identity):
    state = component_root() / "active.json"
    selected = selected_engine()
    previous = None
    if (
        selected is not None
        and selected.parent.resolve() == (component_root() / "installed").resolve()
    ):
        if selected.name == identity:
            try:
                if (
                    json.loads(state.read_text(encoding="utf-8")).get("active")
                    == identity
                ):
                    return
            except (OSError, ValueError, AttributeError):
                pass
        else:
            previous = selected.name
    atomic_json(state, dict(active=identity, previous=previous))

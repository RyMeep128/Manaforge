"""Install-state and immutable dataset generations, using the existing SQLite engine.

Only the active pointer changes on activation. Readers can keep the previous
generation open, including on Windows. User decks/preferences are never replaced.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import threading
import time
import uuid
import zipfile

from .downloads import (
    DownloadCancelled,
    check_space,
    file_sha256,
    get_download_manager,
    validate_url,
)
from .paths import core_data_root


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value
    ):
        raise ValueError("Invalid dataset identifier/version")
    return value


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    version: str
    schema_version: int
    url: str
    sha256: str
    size: int
    category: str = "recommendations"
    required: bool = True
    format: str = "file"
    expanded_size: int = 0

    def __post_init__(self):
        _identifier(self.dataset_id)
        _identifier(self.version)
        validate_url(self.url)
        if not isinstance(self.sha256, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", self.sha256
        ):
            raise ValueError("Invalid dataset SHA-256 checksum")
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise ValueError("Invalid dataset schema version")
        if any(type(v) is not int or v < 0 for v in (self.size, self.expanded_size)):
            raise ValueError("Invalid dataset sizes")
        if self.category not in ("cards", "recommendations") or self.format not in (
            "file",
            "zip",
        ):
            raise ValueError("Unsupported dataset category/format")
        if type(self.required) is not bool:
            raise ValueError("Invalid dataset required flag")
        if self.format == "zip" and self.expanded_size <= 0:
            raise ValueError("ZIP datasets require a positive expanded size limit")

    def require_compatible(self, supported_schemas):
        if self.schema_version not in supported_schemas.get(self.dataset_id, ()):
            raise ValueError(
                f"Unsupported schema for {self.dataset_id}: {self.schema_version}"
            )


def parse_manifest(document):
    """No network side effects; unknown manifest/schema formats fail explicitly."""
    if (
        not isinstance(document, dict)
        or type(document.get("manifest_version")) is not int
        or document["manifest_version"] != 1
    ):
        raise ValueError("Unsupported dataset manifest version")
    if not isinstance(document.get("datasets"), list):
        raise ValueError("Manifest datasets must be a list")
    try:
        entries = [DatasetManifest(**item) for item in document["datasets"]]
    except TypeError as exc:
        raise ValueError("Invalid dataset manifest entry") from exc
    if len({item.dataset_id for item in entries}) != len(entries):
        raise ValueError("Duplicate dataset identifiers")
    return entries


class InstallationState:
    """Small durable state DB, separate from catalogs, user decks, and preferences."""

    def __init__(self, path=None):
        self.path = Path(path or core_data_root() / "installation.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported installation-state schema")
            db.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            db.execute("""CREATE TABLE IF NOT EXISTS installed (
                dataset_id TEXT PRIMARY KEY, manifest TEXT NOT NULL,
                path TEXT NOT NULL, previous TEXT, updated REAL NOT NULL)""")
            if version == 0:
                db.execute("PRAGMA user_version=1")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def get(self, key, default=None):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        if key == "artwork_mode" and value not in ("on_demand", "full_offline"):
            raise ValueError("Unsupported artwork mode")
        if key == "setup_complete" and type(value) is not bool:
            raise ValueError("Setup completion must be a boolean")
        if key in ("cards_root", "recommendations_root", "artwork_root"):
            value = str(Path(value).expanduser().resolve())
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES (?, ?)",
                (key, json.dumps(value)),
            )

    def storage_root(self, category):
        if category not in ("cards", "recommendations", "artwork"):
            raise ValueError("Unsupported storage category")
        return Path(
            self.get(category + "_root", str(core_data_root() / "datasets" / category))
        )

    def installed(self, dataset_id):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM installed WHERE dataset_id=?", (dataset_id,)
            ).fetchone()
        return dict(row) if row else None

    def activate(self, manifest, path):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT path FROM installed WHERE dataset_id=?", (manifest.dataset_id,)
            ).fetchone()
            db.execute(
                "INSERT OR REPLACE INTO installed VALUES (?, ?, ?, ?, ?)",
                (
                    manifest.dataset_id,
                    json.dumps(asdict(manifest)),
                    str(path),
                    previous[0] if previous else None,
                    time.time(),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES (?, ?)",
                ("last_successful_dataset_update", json.dumps(time.time())),
            )


class DatasetInstaller:
    """Download -> verify -> stage -> validate -> atomically activate a generation.

    A caller supplies the dataset-specific semantic validator and schema allowlist.
    This does not schedule updates or collect/publish recommendation data.
    """

    def __init__(self, state=None, downloader=None):
        self.state = state or InstallationState()
        self.downloader = downloader or get_download_manager()
        self._lock = threading.Lock()

    def install(
        self, manifest, *, supported_schemas, validate, cancel=None, progress=None
    ):
        manifest.require_compatible(supported_schemas)
        cancel = cancel or threading.Event()
        with self._lock:
            current = self.state.installed(manifest.dataset_id)
            if (
                current
                and json.loads(current["manifest"]) == asdict(manifest)
                and Path(current["path"]).exists()
            ):
                try:
                    validate(Path(current["path"]))
                except (ValueError, OSError):
                    pass  # Repair damaged installed data through a new generation.
                else:
                    return Path(current["path"])
            root = self.state.storage_root(manifest.category) / manifest.dataset_id
            root.mkdir(parents=True, exist_ok=True)
            check_space(
                root / "generation",
                manifest.size
                + (
                    manifest.expanded_size
                    if manifest.format == "zip"
                    else manifest.size
                ),
            )
            archive = root / (manifest.version + ".download")
            if cancel.is_set():
                raise DownloadCancelled("Dataset installation cancelled")
            if not (
                archive.exists()
                and archive.stat().st_size == manifest.size
                and file_sha256(archive) == manifest.sha256.lower()
            ):
                self.downloader.download(
                    manifest.url,
                    archive,
                    sha256=manifest.sha256,
                    size=manifest.size,
                    cancel=cancel,
                    progress=progress,
                )
            generation = root / (manifest.version + "-" + uuid.uuid4().hex)
            generation.mkdir()
            try:
                if manifest.format == "zip":
                    self._extract(
                        archive, generation, manifest.expanded_size, cancel, progress
                    )
                    result = generation
                else:
                    result = generation / "payload"
                    with archive.open("rb") as source, result.open("xb") as output:
                        while chunk := source.read(1024 * 1024):
                            if cancel.is_set():
                                raise DownloadCancelled("Dataset staging cancelled")
                            check_space(result, len(chunk))
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if file_sha256(result) != manifest.sha256.lower():
                        raise ValueError("Staged dataset checksum mismatch")
                if cancel.is_set():
                    raise DownloadCancelled("Dataset installation cancelled")
                if progress:
                    from .downloads import DownloadProgress

                    progress(DownloadProgress(0, None, 0, "initializing"))
                validate(result)
                if cancel.is_set():
                    raise DownloadCancelled("Dataset installation cancelled")
                self.state.activate(manifest, result)
            except BaseException:
                # Only remove the newly allocated directory owned by this call.
                if generation.resolve().parent == root.resolve():
                    shutil.rmtree(generation)
                raise
            # Keep the archive/checkpoint for reuse if cleanup cannot run; it is
            # never an installed dataset and no previous generation is deleted.
            try:
                archive.unlink(missing_ok=True)
            except OSError:
                pass
            return result

    @staticmethod
    def _extract(archive, destination, limit, cancel, progress):
        from .downloads import DownloadProgress

        written = 0
        seen = set()
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                name = entry.filename
                if "\\" in entry.orig_filename or "\x00" in entry.orig_filename:
                    raise ValueError("Unsafe original dataset archive path")
                parts = PurePosixPath(name).parts
                # Windows paths, device names, ADS, links and case collisions
                # must be rejected even when validation runs on another OS.
                if (
                    not parts
                    or name.startswith("/")
                    or "\\" in name
                    or any(
                        p in (".", "..")
                        or ":" in p
                        or p.endswith((".", " "))
                        or re.fullmatch(
                            r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?", p
                        )
                        for p in parts
                    )
                    or stat.S_ISLNK(entry.external_attr >> 16)
                ):
                    raise ValueError("Unsafe dataset archive path")
                key = name.rstrip("/").casefold()
                if key in seen or len(seen) >= 100000:
                    raise ValueError("Duplicate paths or too many archive entries")
                seen.add(key)
                target = destination.joinpath(*parts)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Dataset archive escapes staging directory")
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if written + entry.file_size > limit:
                    raise ValueError("Dataset exceeds expanded size limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        if cancel.is_set():
                            raise DownloadCancelled("Dataset extraction cancelled")
                        written += len(chunk)
                        if written > limit:
                            raise ValueError("Dataset exceeds expanded size limit")
                        check_space(target, len(chunk))
                        output.write(chunk)
                        if progress:
                            progress(DownloadProgress(written, limit, 0, "extracting"))
                    output.flush()
                    os.fsync(output.fileno())

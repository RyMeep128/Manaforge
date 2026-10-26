"""First-run and monthly data orchestration, independent of Qt."""

from contextlib import closing
from dataclasses import dataclass
import json
import gzip
from pathlib import Path
import sqlite3
import threading
import time
import urllib.parse
import zlib

from .artwork_downloads import fill_artwork, artwork_usage, clear_optional_artwork
from .bulk_install import cancelled, import_cards, import_rulings
from .datasets import InstallationState, parse_manifest
from .downloads import check_space, get_download_manager
from .paths import core_data_root
from .recommendation_distribution import (
    DEFAULT_MANIFEST_URL,
    RecommendationDistribution,
)
from .services import CardService
from .sync import fetch_json


MONTH = 30 * 24 * 60 * 60
OFFLINE_ESTIMATE = 200 * 1024**3


@dataclass(frozen=True)
class InstallPlan:
    bulk: dict
    recommendations: dict
    download_bytes: int
    required_bytes: int
    artwork_bytes: int


def bulk_url(metadata):
    url = metadata.get("jsonl_download_uri") or metadata.get("download_uri")
    parsed = urllib.parse.urlsplit(url or "")
    if (
        parsed.scheme != "https"
        or not (parsed.hostname or "").endswith(".scryfall.io")
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Scryfall did not provide a valid bulk download URL")
    return url


class InstallationEngine:
    def __init__(
        self, state=None, *, service=None, fetch_metadata=None, downloader=None
    ):
        self.state = state or InstallationState()
        self._service = service
        self.fetch = fetch_metadata or fetch_json
        self.downloader = downloader or get_download_manager()
        self.distribution = RecommendationDistribution(self.state, self.downloader)
        self._lock = threading.Lock()

    @property
    def service(self):
        if self._service is None:
            path = self.state.get(
                "catalog_path", str(core_data_root() / "card_data.sqlite3")
            )
            self._service = CardService(db_path=path)
        artwork = self.state.get("artwork_root")
        if artwork:
            self._service.image_root = artwork
            self._service.database.image_storage_root = Path(artwork) / "assets"
        return self._service

    def configure(self, location, mode):
        if not str(location).strip():
            raise ValueError("Choose a data storage location")
        root = Path(location).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        # Test permissions with an application-owned probe, never a user file.
        from tempfile import TemporaryFile

        with TemporaryFile(dir=root):
            pass
        self.state.set("artwork_mode", mode)
        self.state.set("data_location", str(root))
        for category in ("cards", "recommendations", "artwork"):
            self.state.set(category + "_root", str(root / category))
        if not self.state.get("catalog_path"):
            old = core_data_root() / "card_data.sqlite3"
            # Existing catalogs also contain favorites/preferences. Keep them
            # in place; upgrades must never silently substitute an empty catalog.
            self.state.set(
                "catalog_path",
                str(old if old.exists() else root / "cards" / "card_data.sqlite3"),
            )
        return root

    def has_catalog(self):
        path = Path(
            self.state.get("catalog_path", str(core_data_root() / "card_data.sqlite3"))
        )
        if not path.exists():
            return False
        try:
            with closing(
                sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            ) as db:
                return bool(db.execute("SELECT 1 FROM prints LIMIT 1").fetchone())
        except sqlite3.DatabaseError:
            return False

    def needs_update(self, now=None):
        now = time.time() if now is None else now
        return (
            self.state.get("setup_complete", False)
            and (
                self.state.get("update_pending", False)
                or now - self.state.get("last_complete_update_check", 0) >= MONTH
            )
            and now - self.state.get("last_update_attempt", 0) >= 24 * 60 * 60
        )

    def plan(self, *, cancel, report, mode=None):
        cancelled(cancel)
        bulk = {}
        for kind in ("default_cards", "rulings"):
            report(
                dict(
                    operation="Checking " + kind.replace("_", " "),
                    phase="checking",
                    current=0,
                    total=None,
                )
            )
            metadata = self.fetch("https://api.scryfall.com/bulk-data/" + kind)
            if metadata.get("type") != kind or not isinstance(
                metadata.get("updated_at"), str
            ):
                raise ValueError("Invalid Scryfall bulk metadata")
            bulk_url(metadata)
            bulk[kind] = metadata
            cancelled(cancel)
        report(
            dict(
                operation="Checking recommendation datasets",
                phase="checking",
                current=0,
                total=None,
            )
        )
        manifest_path = self.state.path.parent / "setup-recommendations.json"
        self.downloader.download(
            DEFAULT_MANIFEST_URL,
            manifest_path,
            max_bytes=1024**2,
            cancel=cancel,
            validate=lambda p: parse_manifest(
                json.loads(p.read_text(encoding="utf-8"))
            ),
        )
        recommendations = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries, _ = self.distribution.available(recommendations)
        all_entries = parse_manifest(recommendations)
        if not any(
            e.dataset_id
            in (
                "recommendations-edhrec",
                "recommendations-archidekt",
                "recommendations-moxfield",
            )
            and e.schema_version == 1
            for e in all_entries
        ):
            raise ValueError("No compatible recommendation datasets are available")
        downloads = sum(
            int(m.get("compressed_size") or m.get("size") or 150 * 1024**2)
            for m in bulk.values()
        )
        downloads += sum(e.size for e in entries)
        # Allow room for retained generations, expanded archives, the staged
        # catalog and transactional index work. These are estimates, not promises.
        expanded = sum(e.expanded_size for e in entries)
        card_bytes = int(
            bulk["default_cards"].get("compressed_size")
            or bulk["default_cards"].get("size")
            or 150 * 1024**2
        )
        artwork = (
            OFFLINE_ESTIMATE
            if (mode or self.state.get("artwork_mode", "on_demand")) == "full_offline"
            else 0
        )
        self.state.set("last_complete_update_check", time.time())
        self.state.set("last_successful_update_check", time.time())
        return InstallPlan(
            bulk,
            recommendations,
            downloads,
            downloads + expanded + card_bytes * 30 + 1024**3 + artwork,
            artwork,
        )

    def _version(self, kind):
        if kind == "default_cards":
            row = self.service.database.get_sync_state("installed-default_cards")
            return row["version"] if row else None
        path = Path(self.service.rulings_path)
        if not path.exists():
            return None
        try:
            with closing(
                sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            ) as db:
                row = db.execute("SELECT version FROM dataset_metadata").fetchone()
                return row[0] if row else None
        except sqlite3.DatabaseError:
            return None

    def run(self, *, cancel, report, plan=None, setup=False, artwork_only=False, repair_cards=False):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A data update is already running")
        try:
            self.state.set("last_update_attempt", time.time())
            if artwork_only:
                return fill_artwork(
                    self.service,
                    self.state,
                    cancel=cancel,
                    report=report,
                    downloader=self.downloader,
                )
            if not repair_cards:
                self.state.set("update_pending", True)
            plan = plan or self.plan(cancel=cancel, report=report)
            mode = self.state.get("artwork_mode", "on_demand")
            root = self.state.storage_root("cards")
            root.mkdir(parents=True, exist_ok=True)
            # Existing installs check per-transfer/stage space incrementally;
            # first-run preflight reserves the full selected installation estimate.
            if setup:
                used = (
                    artwork_usage(self.service, cancel=cancel)["bytes"]
                    if plan.artwork_bytes
                    else 0
                )
                check_space(
                    root / "installation",
                    max(0, plan.required_bytes - min(used, plan.artwork_bytes)),
                )
            changed = False
            for index, (kind, metadata) in enumerate(plan.bulk.items()):
                cancelled(cancel)
                version = metadata["updated_at"]
                if not (repair_cards and kind == "default_cards") and self._version(kind) == version:
                    continue
                name = (
                    kind + "-" + version.replace(":", "-").replace("/", "-") + ".bulk"
                )
                path = root / name
                expected = metadata.get("compressed_size")
                expected = expected if type(expected) is int and expected >= 0 else None
                if (
                    path.exists()
                    and expected is not None
                    and path.stat().st_size != expected
                ):
                    path.unlink()
                if not path.exists():
                    self.downloader.download(
                        bulk_url(metadata),
                        path,
                        cancel=cancel,
                        size=expected,
                        progress=lambda p, k=kind, i=index: report(
                            dict(
                                operation="Downloading " + k.replace("_", " "),
                                phase=p.phase,
                                current=p.downloaded,
                                total=p.total,
                                speed=p.bytes_per_second,
                                remaining=p.remaining_seconds,
                                step=i,
                                steps=6,
                            )
                        ),
                    )
                report(
                    dict(
                        operation="Preparing " + kind.replace("_", " "),
                        phase="initializing",
                        current=0,
                        total=None,
                    )
                )
                try:
                    if kind == "default_cards":
                        import_cards(
                            path,
                            self.service.database,
                            version,
                            cancel=cancel,
                            report=report,
                            preserve_favorites=repair_cards,
                        )
                        self.service._printings_refreshed.clear()
                        self.state.set("cached_artwork_refresh_pending", True)
                        changed = True
                    else:
                        import_rulings(
                            path, self.service, version, cancel=cancel, report=report
                        )
                except (ValueError, EOFError, gzip.BadGzipFile, zlib.error):
                    path.unlink(missing_ok=True)
                    raise
                versions = self.state.get("bulk_versions", {})
                versions[kind] = version
                self.state.set("bulk_versions", versions)
            entries, _ = self.distribution.available(plan.recommendations)
            for index, entry in enumerate(entries):
                cancelled(cancel)
                self.distribution.install(
                    entry,
                    cancel=cancel,
                    progress=lambda p, e=entry, i=index: report(
                        dict(
                            operation="Installing "
                            + e.dataset_id.replace("recommendations-", "").title()
                            + " recommendations",
                            phase=p.phase,
                            current=p.downloaded,
                            total=p.total,
                            speed=p.bytes_per_second,
                            remaining=p.remaining_seconds,
                            step=2 + i,
                            steps=6,
                        )
                    ),
                )
            if mode == "full_offline" and not repair_cards:
                fill_artwork(
                    self.service,
                    self.state,
                    cancel=cancel,
                    report=lambda p: report(dict(p, step=5, steps=6)),
                    downloader=self.downloader,
                )
            elif not repair_cards and (changed or self.state.get("cached_artwork_refresh_pending", False)):
                self.refresh_cached(cancel=cancel, report=report)
                self.state.set("cached_artwork_refresh_pending", False)
            cancelled(cancel)
            if not repair_cards:
                from .precons import refresh_catalog

                try:
                    report(
                        dict(
                            operation="Refreshing preconstructed deck catalog",
                            phase="precons",
                            current=0,
                            total=1,
                            step=6,
                            steps=6,
                        )
                    )
                    refresh_catalog(self.fetch)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    from .diagnostics import get_logger

                    get_logger(__name__).warning(
                        "Precon refresh failed; retaining existing catalog: %s", exc
                    )
                cancelled(cancel)
                self.state.set("last_successful_dataset_update", time.time())
                self.state.set("update_pending", False)
            if setup:
                self.state.set("setup_complete", True)
            report(
                dict(
                    operation="Ready",
                    phase="completed",
                    current=1,
                    total=1,
                    step=6,
                    steps=6,
                )
            )
            return self.state.get("bulk_versions", {})
        finally:
            self._lock.release()

    def refresh_cached(self, *, cancel, report):
        last = ""
        while True:
            with closing(self.service.database.connect()) as db:
                batch = db.execute(
                    "SELECT DISTINCT card_id FROM image_manifest WHERE source='scryfall' AND card_id>? ORDER BY card_id LIMIT 100",
                    (last,),
                ).fetchall()
            if not batch:
                return
            for (card_id,) in batch:
                cancelled(cancel)
                with closing(self.service.database.connect()) as db:
                    variants = [
                        r[0]
                        for r in db.execute(
                            "SELECT variant FROM image_manifest WHERE card_id=? AND source='scryfall'",
                            (card_id,),
                        )
                    ]
                for variant in variants:
                    face = (
                        0
                        if variant == "default"
                        else 1
                        if variant == "back"
                        else int(variant[5:])
                        if variant.startswith("face-") and variant[5:].isdigit()
                        else None
                    )
                    if face is not None:
                        self.service.cache_artwork(
                            card_id,
                            face,
                            cancel=cancel,
                            refresh=True,
                            downloader=self.downloader,
                        )
                last = card_id
                report(
                    dict(
                        operation="Refreshing changed cached artwork",
                        phase="artwork",
                        current=0,
                        total=None,
                    )
                )

    def usage(self, *, cancel):
        return artwork_usage(self.service, cancel=cancel)

    def clear_optional(self, *, cancel, report):
        return clear_optional_artwork(self.service, cancel=cancel, report=report)

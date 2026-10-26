"""Public recommendation bundle contracts and installation over shared infrastructure."""

from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import time

from .datasets import DatasetInstaller, InstallationState, parse_manifest
from .downloads import file_sha256
from .paths import core_data_root


APPROVED_SOURCES = ("archidekt", "edhrec", "moxfield")
SUPPORTED_SCHEMAS = {f"recommendations-{source}": {1} for source in APPROVED_SOURCES}
DEFAULT_MANIFEST_URL = "https://github.com/RyMeep128/Manaforge/releases/download/recommendation-data-latest-alpha.1/manifest.json"
FILES = {
    "archidekt": {"aggregates.sqlite3"},
    "moxfield": {"aggregates.sqlite3"},
    "edhrec": {"edhrec.sqlite3", "edhrec-cohorts.sqlite3", "edhrec-discovery.sqlite3"},
}
TABLES = {
    "aggregates.sqlite3": {
        "metadata",
        "popularity",
        "cohorts",
        "commander_members",
        "counts",
        "pairs",
    },
    "edhrec.sqlite3": {"pages"},
    "edhrec-cohorts.sqlite3": {"cohorts"},
    "edhrec-discovery.sqlite3": {
        "themes",
        "commanders",
        "commander_members",
        "theme_commanders",
    },
}
COLUMNS = {
    "aggregates.sqlite3": {
        "metadata": "source_id,decks,imported",
        "popularity": "oracle_id,decks",
        "cohorts": "cohort,sample",
        "commander_members": "cohort,oracle_id",
        "counts": "cohort,oracle_id,decks",
        "pairs": "a,b,decks",
    },
    "edhrec.sqlite3": {"pages": "commander,payload,imported"},
    "edhrec-cohorts.sqlite3": {
        "cohorts": "commander,kind,value,label,payload,imported"
    },
    "edhrec-discovery.sqlite3": {
        "themes": "slug,name",
        "commanders": "commander_key,name,slug,sample,imported",
        "commander_members": "commander_key,oracle_id",
        "theme_commanders": "theme_slug,commander_key,num_decks",
    },
}


def validate_bundle(path, source=None):
    """Reject unexpected files/tables and corrupt or incompatible SQLite snapshots."""
    path = Path(path)
    metadata = json.loads((path / "bundle.json").read_text(encoding="utf-8"))
    source = source or metadata.get("source_id")
    if (
        source not in FILES
        or metadata.get("source_id") != source
        or metadata.get("schema_version") != 1
        or not metadata.get("files")
    ):
        raise ValueError("Unsupported recommendation bundle")
    if set(metadata) != {"schema_version", "source_id", "generated_at", "files"}:
        raise ValueError("Unexpected recommendation bundle metadata")
    names = set(metadata["files"])
    if not names <= FILES[source] or (
        source == "edhrec" and "edhrec.sqlite3" not in names
    ):
        raise ValueError("Unexpected recommendation bundle files")
    if {p.name for p in path.iterdir()} != names | {"bundle.json"}:
        raise ValueError("Unlisted files in recommendation bundle")
    for name, info in metadata["files"].items():
        item = path / name
        if item.stat().st_size != info["size"] or file_sha256(item) != info["sha256"]:
            raise ValueError("Recommendation bundle checksum/size mismatch")
        with closing(
            sqlite3.connect(item.resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            objects = db.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if {n for t, n in objects if t == "table"} != TABLES[name] or any(
                t not in ("table", "index") for t, n in objects
            ):
                raise ValueError(
                    "Unsupported recommendation tables or executable schema"
                )
            for table, columns in COLUMNS[name].items():
                if [
                    row[1] for row in db.execute(f"PRAGMA table_info({table})")
                ] != columns.split(","):
                    raise ValueError("Unexpected recommendation columns")
            if name in ("edhrec.sqlite3", "edhrec-cohorts.sqlite3"):
                from .recommendation_packaging import public_page

                table = "pages" if name == "edhrec.sqlite3" else "cohorts"
                for (payload,) in db.execute(f"SELECT payload FROM {table}"):
                    data = json.loads(payload)
                    if public_page(data) != data:
                        raise ValueError(
                            "Unexpected fields in normalized recommendations"
                        )
            if (
                db.execute("PRAGMA user_version").fetchone()[0] != 1
                or db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
            ):
                raise ValueError("Invalid recommendation SQLite dataset")
    return metadata


def installed_bundle(source, *, state=None):
    if state is None:
        state_path = core_data_root() / "installation.sqlite3"
        if not state_path.exists():
            return None
        state = InstallationState(state_path)
    entry = state.installed("recommendations-" + source)
    if not entry:
        return None
    manifest = json.loads(entry["manifest"])
    if manifest.get("schema_version") != 1:
        return None
    path = Path(entry["path"])
    return path if (path / "bundle.json").is_file() else None


def released_file(root, source, filename, *, state=None):
    """Explicit collected files take precedence; arbitrary test roots are isolated."""
    root = Path(root)
    if (root / filename).exists():
        return root / filename
    if (
        state is None
        and root.resolve() != (core_data_root() / "recommendations").resolve()
    ):
        return None
    bundle = installed_bundle(source, state=state)
    return bundle / filename if bundle and (bundle / filename).is_file() else None


class RecommendationDistribution:
    def __init__(self, state=None, downloader=None):
        self.installer = DatasetInstaller(state, downloader)
        self.state = self.installer.state

    def check(self, url=DEFAULT_MANIFEST_URL, *, cancel=None, progress=None):
        """Bounded manifest retrieval; failed checks preserve active generations."""
        destination = self.state.path.parent / "recommendation-manifest.json"

        def validate(path):
            document = json.loads(path.read_text(encoding="utf-8"))
            parse_manifest(document)
            self.available(document)

        self.installer.downloader.download(
            url,
            destination,
            max_bytes=1024 * 1024,
            cancel=cancel,
            progress=progress,
            validate=validate,
        )
        document = json.loads(destination.read_text(encoding="utf-8"))
        self.state.set("last_successful_update_check", time.time())
        return document, self.available(document)

    def available(self, manifest):
        entries = parse_manifest(manifest)
        compatible, unavailable = [], []
        for entry in entries:
            if (
                entry.dataset_id not in SUPPORTED_SCHEMAS
                or entry.schema_version not in SUPPORTED_SCHEMAS[entry.dataset_id]
            ):
                if entry.required:
                    raise ValueError(
                        f"Unsupported required dataset: {entry.dataset_id}"
                    )
                unavailable.append(entry.dataset_id)
                continue
            current = self.state.installed(entry.dataset_id)
            if (
                not current
                or json.loads(current["manifest"]) != asdict(entry)
                or not Path(current["path"]).exists()
            ):
                compatible.append(entry)
        return compatible, unavailable

    def install(self, entry, *, cancel=None, progress=None):
        source = entry.dataset_id.removeprefix("recommendations-")
        if (
            source not in APPROVED_SOURCES
            or entry.category != "recommendations"
            or entry.format != "zip"
        ):
            raise ValueError("Unsupported recommendation dataset")
        return self.installer.install(
            entry,
            supported_schemas=SUPPORTED_SCHEMAS,
            validate=lambda path: validate_bundle(path, source),
            cancel=cancel,
            progress=progress,
        )

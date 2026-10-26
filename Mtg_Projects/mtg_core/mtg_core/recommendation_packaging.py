"""Build public, aggregate-only release assets from existing private collectors.

This module never copies a source database wholesale or starts network collection.
"""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import uuid
import zipfile

from .downloads import atomic_json, file_sha256
from .recommendation_distribution import APPROVED_SOURCES, FILES


STAT_SCHEMA = """
CREATE TABLE metadata(source_id TEXT, decks INTEGER, imported REAL);
CREATE TABLE popularity(oracle_id TEXT PRIMARY KEY, decks INTEGER NOT NULL);
CREATE TABLE cohorts(cohort TEXT PRIMARY KEY, sample INTEGER NOT NULL);
CREATE TABLE commander_members(cohort TEXT, oracle_id TEXT, PRIMARY KEY(cohort,oracle_id));
CREATE INDEX commander_oracle ON commander_members(oracle_id,cohort);
CREATE TABLE counts(cohort TEXT, oracle_id TEXT, decks INTEGER, PRIMARY KEY(cohort,oracle_id));
CREATE TABLE pairs(a TEXT,b TEXT,decks INTEGER,PRIMARY KEY(a,b));
CREATE INDEX pairs_reverse ON pairs(b,a);
PRAGMA user_version=1;
"""
DISCOVERY_SCHEMA = """
CREATE TABLE themes(slug TEXT PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE commanders(commander_key TEXT PRIMARY KEY,name TEXT,slug TEXT,sample INTEGER,imported REAL);
CREATE TABLE commander_members(commander_key TEXT,oracle_id TEXT,PRIMARY KEY(commander_key,oracle_id));
CREATE TABLE theme_commanders(theme_slug TEXT,commander_key TEXT,num_decks INTEGER,PRIMARY KEY(theme_slug,commander_key));
PRAGMA user_version=1;
"""
PAGE_FIELDS = {
    "commander",
    "commanders",
    "slug",
    "sample",
    "results",
    "unresolved",
    "cohort",
    "source_path",
}
ROW_FIELDS = {
    "oracle_id",
    "inclusion",
    "score",
    "sample",
    "num_decks",
    "baseline",
    "synergy",
    "commander",
    "commanders",
    "categories",
    "edhrec_synergy",
    "statistics_source",
    "edhrec_cohort",
}


def _uuid(value):
    if str(uuid.UUID(value)) != value:
        raise ValueError("Recommendation data requires canonical Scryfall Oracle UUIDs")
    return value


def public_page(data):
    """Only normalized recommendation fields can cross the publication boundary."""
    clean = {key: value for key, value in data.items() if key in PAGE_FIELDS}
    ids = clean["commanders"]
    if not 1 <= len(ids) <= 2 or clean["commander"] != "|".join(sorted(set(ids))):
        raise ValueError("Invalid commander identities")
    for identity in ids:
        _uuid(identity)
    for value in clean.get("unresolved", []):
        if not isinstance(value, str) or len(value) > 500:
            raise ValueError("Invalid unresolved card name")
    if (
        not re.fullmatch(r"[a-z0-9-]+", clean["slug"])
        or type(clean["sample"]) is not int
        or clean["sample"] <= 0
    ):
        raise ValueError("Invalid normalized EDHREC page")
    if "source_path" in clean and not re.fullmatch(
        r"commanders/[a-z0-9-]+(?:/[a-z0-9-]+)?", clean["source_path"]
    ):
        raise ValueError("Invalid public EDHREC provenance")
    if "cohort" in clean:
        clean["cohort"] = {
            key: clean["cohort"][key] for key in ("kind", "value", "label")
        }
    clean["results"] = [
        {key: value for key, value in row.items() if key in ROW_FIELDS}
        for row in clean["results"]
    ]
    for row in clean["results"]:
        _uuid(row["oracle_id"])
        if (
            type(row["sample"]) is not int
            or type(row["num_decks"]) is not int
            or not 0 <= row["num_decks"] <= row["sample"]
            or row["sample"] <= 0
        ):
            raise ValueError("Invalid recommendation denominators")
        if row.get("commander") != clean["commander"]:
            raise ValueError("Recommendation commander does not match its page")
        if row.get("commanders") != ids or row.get("statistics_source") != "edhrec":
            raise ValueError("Invalid recommendation provenance")
        if any(
            not isinstance(value, str) or len(value) > 500
            for value in row.get("categories", [])
        ):
            raise ValueError("Invalid recommendation categories")
        for key in ("score", "inclusion", "baseline", "synergy", "edhrec_synergy"):
            value = row.get(key)
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value)
            ):
                raise ValueError("Invalid recommendation score")
        if "edhrec_cohort" in row:
            row["edhrec_cohort"] = {
                key: row["edhrec_cohort"][key] for key in ("kind", "value", "label")
            }
    return clean


def _read(path):
    db = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30
    )
    db.execute("BEGIN")
    return db


def export_statistics(source, destination, source_id, report=print):
    with (
        closing(_read(source)) as original,
        closing(sqlite3.connect(destination)) as output,
    ):
        total, imported = original.execute(
            "SELECT count(*),coalesce(max(imported),0) FROM decks"
        ).fetchone()
        if not total:
            raise ValueError(f"No collected {source_id} decks")
        output.executescript(STAT_SCHEMA)
        with output:
            output.execute(
                "INSERT INTO metadata VALUES (?,?,?)", (source_id, total, imported)
            )
            seeds = []
            for identity, count in original.execute(
                "SELECT oracle_id,decks FROM popularity ORDER BY oracle_id"
            ):
                _uuid(identity)
                if not 0 < count <= total:
                    raise ValueError("Invalid popularity count")
                seeds.append(identity)
                output.execute("INSERT INTO popularity VALUES (?,?)", (identity, count))
            # Private identifiers are used only in local TEMP joins. They are
            # never written to the output or any release asset.
            original.execute("""CREATE TEMP TABLE cohort_for_deck AS SELECT deck_id,group_concat(oracle_id,'|') AS cohort
                FROM (SELECT deck_id,oracle_id FROM members WHERE commander=1 ORDER BY deck_id,oracle_id) GROUP BY deck_id""")
            original.execute(
                "CREATE INDEX temp.cohort_deck ON cohort_for_deck(deck_id)"
            )
            for cohort, sample in original.execute(
                "SELECT cohort,count(*) FROM cohort_for_deck GROUP BY cohort ORDER BY cohort"
            ):
                ids = cohort.split("|")
                if not 1 <= len(ids) <= 2:
                    raise ValueError("Unsupported commander cohort")
                output.execute("INSERT INTO cohorts VALUES (?,?)", (cohort, sample))
                output.executemany(
                    "INSERT INTO commander_members VALUES (?,?)",
                    [(cohort, _uuid(oid)) for oid in ids],
                )
            output.executemany(
                "INSERT INTO counts VALUES (?,?,?)",
                original.execute("""
                SELECT d.cohort,m.oracle_id,count(*) FROM cohort_for_deck d JOIN members m USING(deck_id)
                GROUP BY d.cohort,m.oracle_id ORDER BY d.cohort,m.oracle_id"""),
            )
            for index, seed in enumerate(seeds):
                output.executemany(
                    "INSERT INTO pairs VALUES (?,?,?)",
                    (
                        (seed, oid, count)
                        for oid, count in original.execute(
                            """SELECT c.oracle_id,count(*)
                        FROM members s JOIN members c ON c.deck_id=s.deck_id
                        WHERE s.oracle_id=? AND c.oracle_id>? GROUP BY c.oracle_id ORDER BY c.oracle_id""",
                            (seed, seed),
                        )
                    ),
                )
                if index % 250 == 0:
                    report(
                        f"{source_id}: aggregate associations {index}/{len(seeds)}",
                        flush=True,
                    )
        return imported


def export_edhrec(source, destination):
    name = Path(source).name
    with (
        closing(_read(source)) as original,
        closing(sqlite3.connect(destination)) as output,
    ):
        latest = 0
        with output:
            if name == "edhrec-discovery.sqlite3":
                output.executescript(DISCOVERY_SCHEMA)
                for table, columns in (
                    ("themes", "slug,name"),
                    ("commanders", "commander_key,name,slug,sample,imported"),
                    ("commander_members", "commander_key,oracle_id"),
                    ("theme_commanders", "theme_slug,commander_key,num_decks"),
                ):
                    count = len(columns.split(","))
                    output.executemany(
                        f"INSERT INTO {table} VALUES ({','.join('?' for _ in range(count))})",
                        original.execute(f"SELECT {columns} FROM {table} ORDER BY 1,2"),
                    )
                latest = original.execute(
                    "SELECT coalesce(max(imported),0) FROM commanders"
                ).fetchone()[0]
            elif name == "edhrec.sqlite3":
                output.execute(
                    "CREATE TABLE pages(commander TEXT PRIMARY KEY,payload TEXT NOT NULL,imported REAL NOT NULL)"
                )
                for key, payload, imported in original.execute(
                    "SELECT commander,payload,imported FROM pages ORDER BY commander"
                ):
                    clean = public_page(json.loads(payload))
                    if key != clean["commander"]:
                        raise ValueError("EDHREC page identity mismatch")
                    output.execute(
                        "INSERT INTO pages VALUES (?,?,?)",
                        (
                            key,
                            json.dumps(clean, sort_keys=True, separators=(",", ":")),
                            imported,
                        ),
                    )
                    latest = max(latest, imported)
            else:
                output.execute(
                    "CREATE TABLE cohorts(commander TEXT,kind TEXT,value TEXT,label TEXT,payload TEXT NOT NULL,imported REAL NOT NULL,PRIMARY KEY(commander,kind,value))"
                )
                for key, kind, value, label, payload, imported in original.execute(
                    "SELECT commander,kind,value,label,payload,imported FROM cohorts ORDER BY commander,kind,value"
                ):
                    clean = public_page(json.loads(payload))
                    if key != clean["commander"] or clean.get("cohort") != dict(
                        kind=kind, value=value, label=label
                    ):
                        raise ValueError("EDHREC cohort identity mismatch")
                    output.execute(
                        "INSERT INTO cohorts VALUES (?,?,?,?,?,?)",
                        (
                            key,
                            kind,
                            value,
                            label,
                            json.dumps(clean, sort_keys=True, separators=(",", ":")),
                            imported,
                        ),
                    )
                    latest = max(latest, imported)
            output.execute("PRAGMA user_version=1")
        return latest


def build_distribution(
    root, output, version, *, repository="RyMeep128/Manaforge", sources=APPROVED_SOURCES
):
    if not re.fullmatch(r"[0-9][A-Za-z0-9.-]*-(?:alpha|beta)\.1", version):
        raise ValueError("Use an alpha.1 or beta.1 dataset version")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository")
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / ".build-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    document = dict(
        manifest_version=1,
        version=version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        datasets=[],
        sources={},
    )
    for source in sources:
        if source not in APPROVED_SOURCES:
            raise ValueError(f"No redistribution approval recorded for {source}")
        names = sorted(FILES[source]) if source == "edhrec" else [source + ".sqlite3"]
        inputs = [root / name for name in names if (root / name).exists()]
        if not inputs or (
            source == "edhrec" and not (root / "edhrec.sqlite3").exists()
        ):
            document["sources"][source] = dict(
                status="unavailable", reason="No collected source dataset"
            )
            continue
        # Include WAL changes; checkpoint churn may cause a safe extra rebuild,
        # but unchanged inputs reuse completed archives without recomputation.
        fingerprints = [(path.name, file_sha256(path)) for path in inputs]
        fingerprints += [
            (path.name + "-wal", file_sha256(str(path) + "-wal"))
            for path in inputs
            if Path(str(path) + "-wal").exists()
        ]
        fingerprint = hashlib.sha256(json.dumps(fingerprints).encode()).hexdigest()
        cached = state.get(source, {})
        archive = output / (source + "-" + fingerprint[:16] + ".zip")
        if (
            cached.get("fingerprint") == fingerprint
            and archive.exists()
            and file_sha256(archive) == cached["sha256"]
        ):
            size, expanded, checksum, generated = (
                cached[k] for k in ("size", "expanded_size", "sha256", "generated_at")
            )
            print(f"{source}: unchanged; reusing {archive.name}", flush=True)
        else:
            with TemporaryDirectory(prefix="stage-", dir=output) as staging:
                stage = Path(staging)
                latest = 0
                for item in inputs:
                    print(f"{source}: processing {item.name}", flush=True)
                    if source == "edhrec":
                        latest = max(latest, export_edhrec(item, stage / item.name))
                    else:
                        latest = export_statistics(
                            item, stage / "aggregates.sqlite3", source
                        )
                generated = datetime.fromtimestamp(latest, timezone.utc).isoformat()
                metadata = dict(
                    schema_version=1, source_id=source, generated_at=generated, files={}
                )
                for item in sorted(stage.iterdir()):
                    metadata["files"][item.name] = dict(
                        size=item.stat().st_size, sha256=file_sha256(item)
                    )
                atomic_json(stage / "bundle.json", metadata)
                expanded = sum(p.stat().st_size for p in stage.iterdir())
                temporary = archive.with_suffix(".zip.tmp")
                with zipfile.ZipFile(
                    temporary,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=6,
                    allowZip64=True,
                ) as package:
                    for item in sorted(stage.iterdir()):
                        info = zipfile.ZipInfo(
                            item.name, date_time=(1980, 1, 1, 0, 0, 0)
                        )
                        info.compress_type = zipfile.ZIP_DEFLATED
                        with (
                            item.open("rb") as stream,
                            package.open(info, "w", force_zip64=True) as target,
                        ):
                            while chunk := stream.read(1024 * 1024):
                                target.write(chunk)
                temporary.replace(archive)
                size, checksum = archive.stat().st_size, file_sha256(archive)
                if size >= 2**31:
                    raise ValueError(
                        "Dataset exceeds GitHub per-asset size limit; split the source bundle"
                    )
            state[source] = dict(
                fingerprint=fingerprint,
                sha256=checksum,
                size=size,
                expanded_size=expanded,
                generated_at=generated,
            )
            atomic_json(state_path, state)
        document["datasets"].append(
            dict(
                dataset_id="recommendations-" + source,
                version=version,
                schema_version=1,
                category="recommendations",
                required=False,
                url=f"https://github.com/{repository}/releases/download/recommendations-{version}/{archive.name}",
                sha256=checksum,
                size=size,
                format="zip",
                expanded_size=expanded,
            )
        )
        document["sources"][source] = dict(
            status="available",
            generated_at=generated,
            identifiers="Scryfall Oracle UUIDs",
        )
    if not document["datasets"]:
        raise ValueError("No redistributable source datasets are available")
    atomic_json(output / "manifest.json", document)
    return document

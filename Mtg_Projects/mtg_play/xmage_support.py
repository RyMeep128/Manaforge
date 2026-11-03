"""Read-only local XMage catalog coverage; no launch, network or card substitution."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import zipfile
from .rules_identity import (
    name_key,
    engine_rule_name,
    identity_hint_key,
    configured_catalog as configured_catalog,
)  # noqa: F401 (public compatibility export)

AVAILABLE = {"available"}
PLAY_SECTIONS = {"mainboard", "commander", "sideboard"}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def find_server(play_root, bundle):
    """Prefer a completed server using this installed build, never an arbitrary old catalog."""
    bundle = Path(bundle)
    installed = bundle / "xmage/mage-server"
    if not installed.is_dir():
        installed = bundle / "mage-server"
    if not installed.is_dir():
        installed = bundle
    sets = list((installed / "lib").glob("mage-sets-*.jar"))
    if len(sets) != 1:
        raise ValueError("Cannot locate one installed mage-sets JAR; pass --server-dir")
    expected = sha256(sets[0])
    candidates = sorted(
        (Path(play_root) / ".runtime").glob("*/result.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for result in candidates:
        server = result.parent / "server"
        if not (server / "db/cards.h2.mv.db").is_file():
            continue
        jars = list((server / "lib").glob("mage-sets-*.jar"))
        if len(jars) == 1 and sha256(jars[0]) == expected:
            return server
    if (installed / "db/cards.h2.mv.db").is_file():
        return installed
    raise ValueError(
        "No initialized matching server catalog. Pass --server-dir pointing to an existing server with db/cards.h2.mv.db; one is created by a normal Manaforge Play launch."
    )


def read_engine_catalog(server, java, probe):
    server = Path(server).resolve()
    database = server / "db/cards.h2.mv.db"
    if not database.is_file():
        raise ValueError("Missing existing server database: " + str(database))
    dependencies = []
    for pattern in ("h2-*.jar", "gson-*.jar"):
        found = list((server / "lib").glob(pattern))
        if len(found) != 1:
            raise ValueError("Expected one installed dependency: " + pattern)
        dependencies.extend(found)
    import os

    command = [
        str(java),
        "-Dfile.encoding=UTF-8",
        "--class-path",
        os.pathsep.join(map(str, dependencies)),
        str(Path(probe).resolve()),
        str(server / "db/cards.h2"),
    ]
    before = sha256(database)
    process = subprocess.run(
        command, capture_output=True, encoding="utf-8", timeout=120, check=False
    )
    if process.returncode:
        raise ValueError(
            "Read-only XMage catalog query failed; close an active match or choose a completed server catalog.\n"
            + process.stderr[-4000:]
        )
    try:
        rows = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(
            "XMage query returned invalid JSON; no missing-card classifications were made"
        ) from error
    if not isinstance(rows, list) or not rows:
        raise ValueError("XMage catalog is empty or malformed")
    if sha256(database) != before:
        raise ValueError(
            "XMage catalog changed during the check; choose a closed server catalog"
        )
    classes = set()
    jars = list((server / "lib").glob("*.jar")) + list(
        (server / "plugins").glob("*.jar")
    )
    for jar in jars:
        with zipfile.ZipFile(jar) as archive:
            classes.update(
                name[:-6].replace("/", ".")
                for name in archive.namelist()
                if name.startswith("mage/cards/") and name.endswith(".class")
            )
    for row in rows:
        if not all(
            isinstance(row.get(key), str)
            for key in ("name", "set_code", "collector_number", "class_name")
        ):
            raise ValueError("Malformed XMage catalog record")
        row["class_available"] = row["class_name"] in classes
    metadata = {
        "server_directory": str(server),
        "database": str(database),
        "database_sha256": before,
        "catalog_printings": len(rows),
        "catalog_names": len({row["name"] for row in rows}),
        "sets_jars": [
            {"file": jar.name, "sha256": sha256(jar)}
            for jar in jars
            if jar.name.startswith("mage-sets-")
        ],
    }
    return rows, metadata


def deck_requests(document, source):
    deck = document.get("deck")
    if not isinstance(deck, dict) or not isinstance(deck.get("entries"), list):
        raise ValueError("Expected a native Manaforge deck document: " + str(source))
    results = []
    for entry in deck["entries"]:
        row = {
            "deck": deck.get("name", ""),
            "source": str(source),
            "entry_id": entry.get("entry_id"),
            "name": entry.get("name"),
            "set_code": entry.get("set_code"),
            "collector_number": entry.get("collector_number"),
            "printing_id": entry.get("card_id"),
            "oracle_id": entry.get("oracle_id"),
            "section": entry.get("section", "mainboard"),
            "quantity": entry.get("quantity", 1),
        }
        if row["section"] not in PLAY_SECTIONS or row["quantity"] == 0:
            row["skip_reason"] = "Non-playing section or zero quantity"
        results.append(row)
    return results


def compare(requests, catalog):
    names, hints = defaultdict(list), defaultdict(set)
    for card in catalog:
        names[name_key(card["name"])].append(card)
        hint = identity_hint_key(card["name"])
        if card["class_available"] and hint:
            hints[hint].add(card["name"])
        for related in card.get("related_names", []):
            # These relationships come from XMage, not a guessed front-face match.
            names[name_key(card["name"] + " // " + related)].append(card)
            names[name_key(related)].append(card)
    results = []
    for request in requests:
        row = dict(request)
        name = row.get("name")
        matching = names.get(name_key(name), []) if isinstance(name, str) else []
        if not matching and isinstance(name, str):
            matching = names.get(
                name_key(engine_rule_name(name, row.get("oracle_id"))), []
            )
        implemented = [card for card in matching if card["class_available"]]
        candidates = (
            sorted(hints.get(identity_hint_key(name), []))
            if isinstance(name, str) and not matching
            else []
        )
        if row.get("skip_reason"):
            status, reason = "skipped", row["skip_reason"]
        elif not isinstance(name, str) or not name.strip():
            status, reason = "invalid_metadata", "No card name to compare"
        elif row.get("layout") in {"token", "double_faced_token", "emblem"}:
            status, reason = (
                "token_dependency",
                "A token/emblem is a generated game object, not evidence of an uncoded deck card",
            )
        elif not matching and candidates:
            status, reason = (
                "identity_mismatch",
                "Similar registered engine names exist; identity review is required, and no rules substitution was made",
            )
        elif not matching:
            status, reason = (
                "missing_card",
                "No card-name or recorded face relationship in this XMage catalog",
            )
        elif not implemented:
            status, reason = (
                "missing_implementation",
                "Catalog name exists, but its recorded implementation classes are absent from installed JARs",
            )
        else:
            status, reason = (
                "available",
                "Card name and implementation class found; deck printing is irrelevant",
            )
        row.update(
            status=status,
            reason=reason,
            engine_classes=sorted({card["class_name"] for card in implemented}),
            engine_name_candidates=candidates,
        )
        results.append(row)
    return results


def catalog_requests(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Local Core catalog does not exist: " + str(path))
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        return [
            {"name": row[0], "source": str(path)}
            for row in connection.execute(
                "SELECT DISTINCT name FROM cards_oracle ORDER BY name"
            )
        ]


def csv_value(value):
    if isinstance(value, str) and value.startswith(
        ("=", "+", "-", "@", "\t", "\r", "\n")
    ):
        return "'" + value
    return value


def write_reports(output, rows, metadata):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    counts = dict(sorted(Counter(row["status"] for row in rows).items()))
    report = {
        "report_version": 2,
        "scope": "Card rules catalog and class availability, independent of deck printing; not a gameplay/legality guarantee. Case and apostrophe variants are normalized; multi-face matches require XMage-recorded relationships.",
        "engine": metadata,
        "total_entries": len(rows),
        "unique_card_names": len(
            {
                row["name"]
                for row in rows
                if isinstance(row.get("name"), str) and row["status"] != "skipped"
            }
        ),
        "counts": counts,
        "results": rows,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fields = [
        "deck",
        "entry_id",
        "name",
        "source_name",
        "oracle_id",
        "identity_status",
        "layout",
        "set_code",
        "collector_number",
        "printing_id",
        "section",
        "quantity",
        "status",
        "reason",
        "engine_classes",
        "engine_name_candidates",
    ]
    groups = {
        "available.csv": lambda row: row["status"] in AVAILABLE,
        "missing.csv": lambda row: (
            row["status"] in {"missing_card", "missing_implementation"}
        ),
        "invalid.csv": lambda row: row["status"] == "invalid_metadata",
        "identity_issues.csv": lambda row: row["status"] == "identity_mismatch",
        "skipped.csv": lambda row: row["status"] == "skipped",
        "token_dependencies.csv": lambda row: row["status"] == "token_dependency",
    }
    for name, include in groups.items():
        with (output / name).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                if include(row):
                    writer.writerow(
                        {
                            key: csv_value(
                                " | ".join(value) if isinstance(value, list) else value
                            )
                            for key, value in row.items()
                        }
                    )
    for filename, status in (
        ("cards-not-in-xmage.txt", "missing_card"),
        ("cards-in-xmage.txt", "available"),
    ):
        names = sorted({row["name"] for row in rows if row["status"] == status})
        (output / filename).write_text("\n".join(names) + "\n", encoding="utf-8")
    summary = (
        "XMage catalog coverage\n"
        + "\n".join(f"{key}: {value}" for key, value in counts.items())
        + "\n"
    )
    (output / "summary.txt").write_text(summary, encoding="utf-8")
    return counts

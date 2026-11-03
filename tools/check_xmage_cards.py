"""Report installed XMage card rules coverage without modifying decks or starting a game."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Mtg_Projects"), str(ROOT / "Mtg_Projects/mtg_core")]
from mtg_core.paths import data_root  # noqa: E402
from mtg_play import xmage_support as support  # noqa: E402
from mtg_play.connection_proof import DEFAULT_BUNDLE, DEFAULT_JDK  # noqa: E402


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", type=Path, action="append", default=[], help="Native .manaforge.json deck; repeat to compare multiple decks")
    parser.add_argument("--name", action="append", default=[], help="Exact catalog card name; repeat as needed")
    parser.add_argument("--all-cards", action="store_true", help="Compare all unique names in the installed Core catalog")
    parser.add_argument("--catalog-db", type=Path, help="Optional Core SQLite catalog for --all-cards")
    parser.add_argument("--data-root", type=Path, default=data_root(), help="Manaforge data directory; default inputs are its saved decks")
    parser.add_argument("--server-dir", type=Path, help="Initialized XMage server directory containing db/cards.h2.mv.db and lib")
    parser.add_argument("--xmage-dir", type=Path, default=DEFAULT_BUNDLE, help="Installed bundle used to select a matching completed server catalog")
    parser.add_argument("--java", type=Path, help="Java 11+ executable; defaults to the configured pinned JDK, then PATH")
    parser.add_argument("--output", type=Path, default=ROOT / "Artifacts" / ("XmageCardSupport-" + uuid.uuid4().hex[:8]), help="Directory for JSON, summary and four CSV reports")
    parser.add_argument("--fail-on-missing", action="store_true", help="Exit 1 if any non-skipped entry has a card support issue")
    args = parser.parse_args(argv)
    if args.catalog_db and not args.all_cards:
        parser.error("--catalog-db requires --all-cards")
    try:
        server = args.server_dir or support.find_server(ROOT / "Mtg_Projects/mtg_play", args.xmage_dir)
        java = args.java
        if java is None:
            candidate = DEFAULT_JDK / "bin/java.exe"
            java = candidate if candidate.is_file() else shutil.which("java")
        if not java:
            raise ValueError("Java is required; supply --java")
        requests, warnings = [], []
        for path in args.deck:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
            requests.extend(support.deck_requests(document, path.resolve()))
        requests.extend({"name": name, "source": "--name"} for name in args.name)
        if args.all_cards:
            requests.extend(support.catalog_requests(args.catalog_db or support.configured_catalog(args.data_root)))
        if not args.deck and not args.name and not args.all_cards:
            from mtg_play.setup import saved_decks

            decks, warnings = saved_decks(args.data_root)
            for deck in decks:
                requests.extend(support.deck_requests(deck.document.to_dict(), deck.path or deck.key))
        if not requests:
            raise ValueError("No input cards found; supply --deck, --name or --all-cards")
        from mtg_play.rules_identity import canonical_cards, canonicalize_requests
        requests = canonicalize_requests(requests, canonical_cards((row.get("oracle_id") for row in requests), args.catalog_db or support.configured_catalog(args.data_root)))
        print("Reading installed XMage catalog and implementation classesâ€¦", flush=True)
        catalog, metadata = support.read_engine_catalog(server, java, ROOT / "tools/java/XmageCatalogProbe.java")
        rows = support.compare(requests, catalog)
        metadata["input_warnings"] = warnings
        counts = support.write_reports(args.output, rows, metadata)
        print("Catalog: " + metadata["database"])
        for status, count in counts.items():
            print(f"{status}: {count}")
        problems = [row for row in rows if row["status"] not in support.AVAILABLE | {"skipped"}]
        for row in problems[:30]:
            print(f"  {row.get('deck', '')}: {row.get('name')} â€” {row['status']}")
        if len(problems) > 30:
            print(f"  â€¦ {len(problems) - 30} more issues in the reports")
        for warning in warnings:
            print("Input warning: " + str(warning))
        print("Reports: " + str(args.output.resolve()))
        return 1 if args.fail_on_missing and problems else 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        print("XMage check failed: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

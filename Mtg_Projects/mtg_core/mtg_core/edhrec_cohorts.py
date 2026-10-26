"""Separate EDHREC cohorts and a resumable, single-worker expansion collector."""

import argparse
from contextlib import closing
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import urllib.error

from .edhrec import normalize
from .edhrec_ingest import Downloader, MAX_BYTES, catalog_index, collector_lock, write_json
from .paths import core_data_root


BRACKETS = {"1": "exhibition", "2": "core", "3": "upgraded", "4": "optimized", "5": "cedh"}


def cohort_path(page):
    if not isinstance(page, str) or not re.fullmatch(
        r"commanders/[a-z0-9-]+(?:/[a-z0-9-]+)?\.json", page
    ):
        raise ValueError(f"Unexpected EDHREC cohort path: {page!r}")
    return page


class CohortDownloader(Downloader):
    validate_page = staticmethod(cohort_path)


def variants(payload):
    """Only nonempty source-advertised filters; no speculative combinations."""
    tags = payload.get("tag_counts", payload.get("panels", {}).get("taglinks", []))
    for tag in tags:
        if type(tag.get("count")) is int and tag["count"] > 0:
            yield "theme", tag["slug"], tag["value"]
    for number, count in payload.get("bracket_counts", {}).items():
        if number in BRACKETS and type(count) is int and count > 0:
            value = BRACKETS[number]
            yield "bracket", value, f"Bracket {number}: {value.title()}"
    for value, count in payload.get("budget_counts", {}).items():
        if value in {"budget", "expensive"} and type(count) is int and count > 0:
            yield "budget", value, value.title()


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1):
        db.close()
        raise ValueError("Unsupported EDHREC cohort database version")
    db.execute("CREATE TABLE IF NOT EXISTS crawl (path TEXT PRIMARY KEY, slug TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', error TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS cohorts (commander TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL, label TEXT NOT NULL, payload TEXT NOT NULL, imported REAL NOT NULL, PRIMARY KEY(commander,kind,value))")
    db.execute("CREATE TABLE IF NOT EXISTS seeds (slug TEXT PRIMARY KEY)")
    db.execute("CREATE INDEX IF NOT EXISTS crawl_status ON crawl(status)")
    db.execute("PRAGMA user_version=1")
    db.commit()
    return db


def cohort_options(path):
    """Read published choices without creating a missing database."""
    if not Path(path).exists():
        from .recommendation_distribution import released_file
        released = released_file(Path(path).parent, 'edhrec', 'edhrec-cohorts.sqlite3')
        if released is None:
            return []
        path = released
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute("SELECT kind,value,min(label) FROM cohorts GROUP BY kind,value ORDER BY kind,min(label)").fetchall()


def collect(root, catalog, *, max_pages=250000, max_gb=20):
    root = Path(root)
    state_path = root / "cohort-state.json"
    downloader = CohortDownloader(root)
    checkpoint = json.loads((root / "state.json").read_text(encoding="utf-8"))
    names, _ = catalog_index(catalog)
    target = root.parent / "edhrec-cohorts.sqlite3"
    state = dict(status="indexing", imported=0, skipped=0, pending=0, current=None)
    cache_bytes = sum(path.stat().st_size for path in (root / "responses").glob("*.json.gz"))

    with closing(connect(target)) as db:
        def save(status, **updates):
            state.update(updates, status=status, updated=time.time(), cache_bytes=cache_bytes)
            state["imported"] = db.execute("SELECT count(*) FROM crawl WHERE status='complete'").fetchone()[0]
            state["skipped"] = db.execute("SELECT count(*) FROM crawl WHERE status='skipped'").fetchone()[0]
            state["pending"] = db.execute("SELECT count(*) FROM crawl WHERE status='pending'").fetchone()[0]
            write_json(state_path, state)

        try:
            seeded = {row[0] for row in db.execute("SELECT slug FROM seeds")}
            for slug in checkpoint["completed"]:
                downloader.wait(0)
                if slug in seeded:
                    continue
                # Read the original source response, not a synthesized recommendation page.
                page = cohort_path(f"commanders/{slug}.json")
                cached = root / "responses" / (hashlib.sha256(page.encode()).hexdigest() + ".json.gz")
                with gzip.open(cached, "rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Oversized cached commander page")
                payload = json.loads(raw)
                with db:
                    for kind, value, label in variants(payload):
                        path = cohort_path(f"commanders/{slug}/{value}.json")
                        db.execute("INSERT OR IGNORE INTO crawl(path,slug,kind,value,label) VALUES (?,?,?,?,?)", (path, slug, kind, value, label))
                    db.execute("INSERT INTO seeds VALUES (?)", (slug,))
                if db.execute("SELECT count(*) FROM seeds").fetchone()[0] % 100 == 0:
                    save("indexing", current=slug)
            save("running", current=None, last_error=None)
            while True:
                downloader.wait(0)
                if state["imported"] >= max_pages or cache_bytes >= max_gb * 1024**3:
                    save("bounded")
                    break
                item = db.execute("SELECT path,slug,kind,value,label FROM crawl WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
                if item is None:
                    save("complete", current=None)
                    break
                page, slug, kind, value, label = item
                save("running", current=page)
                cached = root / "responses" / (hashlib.sha256(page.encode()).hexdigest() + ".json.gz")
                previous_bytes = cached.stat().st_size if cached.exists() else 0
                try:
                    payload = downloader.fetch(page)
                    source_path = page.removesuffix(".json")
                    if not any(
                        isinstance(crumb, dict) and "/" + source_path in crumb
                        for crumb in payload["container"]["breadcrumb"]
                    ):
                        raise ValueError("Response does not identify the requested filtered cohort")
                    data = normalize(payload, lambda name: names.get(name.casefold()), slug)
                    # A child page must resolve to its original exact commander/pair.
                    base = db.execute("SELECT 1 FROM seeds WHERE slug=?", (slug,)).fetchone()
                    with closing(sqlite3.connect((root.parent / "edhrec.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as general:
                        parent = general.execute("SELECT payload FROM pages WHERE commander=?", (data["commander"],)).fetchone()
                    if not base or parent is None or json.loads(parent[0])["slug"] != slug:
                        raise ValueError("Cohort does not match its cached commander identity")
                    data.update(cohort=dict(kind=kind, value=value, label=label), source_path=source_path)
                    for row in data["results"]:
                        row["edhrec_cohort"] = data["cohort"]
                except urllib.error.HTTPError as exc:
                    if exc.code not in (404, 410):
                        raise
                    with db:
                        db.execute("UPDATE crawl SET status='skipped',error=? WHERE path=?", (str(exc), page))
                except (ValueError, KeyError, TypeError) as exc:
                    with db:
                        db.execute("UPDATE crawl SET status='skipped',error=? WHERE path=?", (str(exc), page))
                else:
                    with db:
                        db.execute("INSERT OR REPLACE INTO cohorts VALUES (?,?,?,?,?,?)", (data["commander"], kind, value, label, json.dumps(data), time.time()))
                        db.execute("UPDATE crawl SET status='complete',error=NULL WHERE path=?", (page,))
                if cached.exists():
                    cache_bytes += cached.stat().st_size - previous_bytes
                save("running")
                print(f"EDHREC cohorts: {state['imported']} imported, {state['skipped']} skipped, {state['pending']} pending", flush=True)
        except (InterruptedError, KeyboardInterrupt) as exc:
            save("paused", last_error=str(exc))
        except Exception as exc:
            save("error", last_error=f"{type(exc).__name__}: {exc}")
            raise
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=core_data_root() / "recommendations" / "edhrec-run")
    parser.add_argument("--catalog", type=Path, default=core_data_root() / "card_data.sqlite3")
    parser.add_argument("--max-pages", type=int, default=250000)
    parser.add_argument("--max-gb", type=float, default=20)
    args = parser.parse_args()
    if args.max_pages <= 0 or not 0 < args.max_gb < float("inf"):
        parser.error("Collection bounds must be positive and finite")
    with collector_lock(args.root):
        print(json.dumps(collect(args.root, args.catalog, max_pages=args.max_pages, max_gb=args.max_gb), indent=2))


if __name__ == "__main__":
    main()

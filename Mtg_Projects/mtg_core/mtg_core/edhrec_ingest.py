"""Explicit, resumable one-time EDHREC download, independent of Archidekt."""

import argparse
from contextlib import closing, contextmanager
import gzip
import hashlib
import http.client
import json
from pathlib import Path
import re
import sqlite3
import shutil
import time
import uuid
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

from .edhrec import cardlists, normalize, save_page
from .paths import core_data_root

BASE = "https://json.edhrec.com/pages/"
MAX_BYTES = 8 * 1024**2


@contextmanager
def collector_lock(root):
    """Share the collector's exclusive lock with explicit offline UI imports."""
    import sys

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "collector.lock", "a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "The EDHREC collector or another import is using this cache. Retry after it finishes."
            ) from exc
        yield


def page_path(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"commanders/[a-z0-9-]+\.json", value
    ):
        raise ValueError(f"Unexpected EDHREC page path: {value!r}")
    return value


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def name_index(rows):
    """Exact names outrank front-face aliases (including reversible art cards)."""
    exact, aliases = {}, {}
    for oid, name in rows:
        key = name.casefold()
        exact[key] = oid if key not in exact or exact[key] == oid else None
        front = key.split(" // ")[0]
        aliases[front] = oid if front not in aliases or aliases[front] == oid else None
    return {**aliases, **exact}


def catalog_index(catalog):
    with closing(
        sqlite3.connect(Path(catalog).resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        columns = {r[1] for r in db.execute("PRAGMA table_info(cards_oracle)")}
        query = (
            "SELECT oracle_id, name"
            + (", layout" if "layout" in columns else "")
            + " FROM cards_oracle"
        )
        rows = [
            r[:2]
            for r in db.execute(query)
            if not r[0].startswith("proxy-oracle-")
            and (
                len(r) < 3
                or r[2] not in {"art_series", "token", "double_faced_token", "emblem"}
            )
        ]
    names = name_index(rows)
    candidates = {}
    for oid, name in rows:
        for key in {name.casefold(), name.casefold().split(" // ")[0]}:
            candidates.setdefault(key, set()).add(oid)
    return names, {
        key: sorted(ids) for key, ids in candidates.items() if names.get(key) is None
    }


def reprocess_cached(root, catalog):
    """Offline rebuild; caller holds collector.lock, just as for collect()."""
    root = Path(root)
    state_path = root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    names, ambiguities = catalog_index(catalog)
    target = root.parent / "edhrec.sqlite3"
    temporary = root / ("rebuild-" + uuid.uuid4().hex + ".sqlite3")
    report = dict(
        status="running",
        imported=0,
        ambiguous=0,
        invalid=0,
        missing_cache=0,
        unresolved=0,
        pages={},
        previous_imported=state.get("imported", 0),
    )
    completed, skipped = [], {}

    def check_stop():
        if (root / "STOP").exists():
            raise InterruptedError("STOP file present")

    try:
        check_stop()
        for slug in dict.fromkeys(state["slugs"]):
            check_stop()
            page = page_path(f"commanders/{slug}.json")
            cached = (
                root
                / "responses"
                / (hashlib.sha256(page.encode()).hexdigest() + ".json.gz")
            )
            category, reason, candidates = None, None, {}
            if not cached.exists():
                category, reason = "missing_cache", "Cached response missing"
            else:
                try:
                    with gzip.open(cached, "rb") as stream:
                        raw = stream.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("EDHREC response exceeds size limit")
                    payload = json.loads(raw)
                    name = payload["container"]["json_dict"]["card"]["name"]
                    candidates = {
                        n: ambiguities[n.casefold()]
                        for n in [name, *name.split(" // ")]
                        if n.casefold() in ambiguities
                    }
                    data = normalize(payload, lambda n: names.get(n.casefold()), slug)
                    save_page(temporary, data, time.time())
                except (OSError, EOFError, KeyError, TypeError, ValueError) as exc:
                    reason = str(exc)
                    category = (
                        ("ambiguous" if candidates else "unresolved")
                        if reason.startswith("Unresolved commander:")
                        else "invalid"
                    )
            if category:
                report[category] += 1
                skipped[slug] = reason
                report["pages"][slug] = dict(
                    category=category, reason=reason, candidates=candidates
                )
            else:
                completed.append(slug)
                report["imported"] += 1
        # Do not replace a usable cache with missing/corrupt data or lost pages.
        if (
            report["missing_cache"]
            or report["invalid"]
            or not set(state.get("completed", [])).issubset(completed)
        ):
            raise ValueError(
                "Rebuild validation failed; existing database and checkpoint preserved"
            )
        if not temporary.exists():
            raise ValueError("No usable pages to publish")
        with closing(sqlite3.connect(temporary)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Rebuilt database failed integrity check")
            report["unique_cohorts"] = db.execute(
                "SELECT COUNT(*) FROM pages"
            ).fetchone()[0]
        check_stop()
        backup = root / ("backup-" + uuid.uuid4().hex)
        backup.mkdir()
        shutil.copy2(state_path, backup / "state.json")
        if target.exists():
            with (
                closing(sqlite3.connect(target)) as source,
                closing(sqlite3.connect(backup / target.name)) as dest,
            ):
                source.backup(dest)
        report["backup"] = str(backup)
        state.update(
            status="complete",
            completed=completed,
            skipped=skipped,
            imported=len(completed),
            current=None,
            last_error=None,
        )
        try:
            temporary.replace(target)
            write_json(state_path, state)
        except BaseException:
            if (backup / target.name).exists():
                shutil.copy2(backup / target.name, target)
            elif target.exists():
                target.unlink()
            shutil.copy2(backup / "state.json", state_path)
            raise
        report["status"] = "complete"
    except BaseException as exc:
        report.update(status="stopped", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        temporary.unlink(missing_ok=True)
        write_json(root / "reprocess-report.json", report)
    return report


class Downloader:
    def __init__(self, root, delay=6):
        self.root = Path(root)
        self.delay = max(6, delay)
        self.last = 0.0
        (self.root / "responses").mkdir(parents=True, exist_ok=True)

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while True:
            if (self.root / "STOP").exists():
                raise InterruptedError("STOP file present")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(1, remaining))

    def download(self, request):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        backoff = 30
        while True:
            self.wait(max(0, self.delay - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                with urllib.request.build_opener(NoRedirect).open(
                    request, timeout=45
                ) as response:
                    return response.read(MAX_BYTES + 1)
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
            ) as exc:
                retry_after = 0
                if isinstance(exc, urllib.error.HTTPError):
                    if exc.code not in (408, 429) and not 500 <= exc.code < 600:
                        exc.close()
                        raise
                    header = exc.headers.get("Retry-After", "")
                    try:
                        retry_after = float(header)
                    except ValueError:
                        try:
                            retry_after = (
                                parsedate_to_datetime(header).timestamp() - time.time()
                            )
                        except (ValueError, TypeError, OverflowError):
                            pass
                    exc.close()
                wait = max(backoff, retry_after)
                print(
                    f"EDHREC retry in {wait:.0f}s: {request.full_url}: {exc}",
                    flush=True,
                )
                self.wait(wait)
                backoff = min(backoff * 2, 900)

    def fetch(self, page):
        page_path(page)
        if (self.root / "STOP").exists():
            raise InterruptedError("STOP file present")
        path = (
            self.root
            / "responses"
            / (hashlib.sha256(page.encode()).hexdigest() + ".json.gz")
        )
        if path.exists():
            with gzip.open(path, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        else:
            request = urllib.request.Request(
                BASE + page,
                headers={"User-Agent": "Manaforge/EDHREC personal offline snapshot"},
            )

            raw = self.download(request)
            if len(raw) > MAX_BYTES:
                raise ValueError("EDHREC response exceeds size limit")
            json.loads(raw)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(gzip.compress(raw))
            temporary.replace(path)
        if len(raw) > MAX_BYTES:
            raise ValueError("EDHREC response exceeds size limit")
        return json.loads(raw)


def collect(root, catalog, *, max_commanders=10000, delay=6):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "state.json"
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else dict(status="new", completed=[], skipped={}, imported=0)
    )
    if state["status"] == "complete":
        return state
    state.setdefault("started_at", time.time())
    downloader = Downloader(root, delay)
    try:
        names, _ = catalog_index(catalog)

        def resolve(name):
            return names.get(name.casefold())

        if "slugs" not in state:
            page, visited, slugs = "commanders/year.json", set(), []
            while page:
                if page in visited or len(visited) >= 200:
                    raise ValueError("Repeated or excessive index pagination")
                visited.add(page)
                state.update(status="indexing", current=page, index_pages=len(visited))
                write_json(state_path, state)
                payload = downloader.fetch(page)
                group = cardlists(payload)[0] if "container" in payload else payload
                for item in group["cardviews"]:
                    slug = item.get("slug", item.get("sanitized"))
                    page_path(f"commanders/{slug}.json")
                    if slug not in slugs:
                        slugs.append(slug)
                page = group.get("more")
            state["slugs"] = slugs
        state.update(status="running", last_error=None)
        write_json(state_path, state)
        done = set(state["completed"]) | set(state["skipped"])
        for slug in state["slugs"]:
            if slug in done:
                continue
            if state["imported"] >= max_commanders:
                state["status"] = "bounded"
                break
            state["current"] = slug
            write_json(state_path, state)
            try:
                payload = downloader.fetch(f"commanders/{slug}.json")
                data = normalize(payload, resolve, slug)
            except urllib.error.HTTPError as exc:
                if exc.code not in (404, 410):
                    raise
                state["skipped"][slug] = str(exc)
            except (KeyError, TypeError, ValueError) as exc:
                state["skipped"][slug] = str(exc)
            else:
                save_page(root.parent / "edhrec.sqlite3", data, time.time())
                state["completed"].append(slug)
                state["imported"] += 1
            write_json(state_path, state)
            print(
                f"EDHREC {state['imported']} imported, {len(state['skipped'])} skipped / {len(state['slugs'])}",
                flush=True,
            )
        else:
            state["status"] = "complete"
        state["current"] = None
    except Exception as exc:
        state.update(status="stopped", last_error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        write_json(state_path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=core_data_root() / "recommendations" / "edhrec-run"
    )
    parser.add_argument(
        "--catalog", type=Path, default=core_data_root() / "card_data.sqlite3"
    )
    parser.add_argument("--max-commanders", type=int, default=10000)
    parser.add_argument(
        "--reprocess-cached",
        action="store_true",
        help="Rebuild from cached pages without network requests",
    )
    parser.add_argument(
        "--build-discovery",
        action="store_true",
        help="Build the offline theme/commander index from explicit cached tag counts; no network requests",
    )
    parser.add_argument(
        "--with-discovery",
        action="store_true",
        help="Build discovery after the normal resumable commander collection",
    )
    args = parser.parse_args()
    if args.build_discovery and (args.reprocess_cached or args.with_discovery):
        parser.error("--build-discovery is an independent offline operation")
    with collector_lock(args.root):
        if args.build_discovery:
            from .edhrec_discovery_ingest import build_discovery

            result = build_discovery(args.root, args.catalog)
            print(
                json.dumps(
                    {
                        k: v
                        for k, v in result.items()
                        if k not in ("completed", "invalid", "unresolved")
                    },
                    indent=2,
                )
            )
        elif args.reprocess_cached:
            result = reprocess_cached(args.root, args.catalog)
            print(
                json.dumps({k: v for k, v in result.items() if k != "pages"}, indent=2)
            )
        else:
            collect(args.root, args.catalog, max_commanders=args.max_commanders)
        if args.with_discovery:
            from .edhrec_discovery_ingest import build_discovery

            build_discovery(args.root, args.catalog)


if __name__ == "__main__":
    main()

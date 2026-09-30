"""Explicit, resumable one-time EDHREC download, independent of Archidekt."""

import argparse
from contextlib import closing
import gzip
import hashlib
import http.client
import json
from pathlib import Path
import re
import sqlite3
import time
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime

from .edhrec import cardlists, normalize, save_page
from .paths import core_data_root

BASE = "https://json.edhrec.com/pages/"
MAX_BYTES = 8 * 1024**2


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
            except (urllib.error.URLError, TimeoutError, ConnectionError,
                    http.client.IncompleteRead, http.client.RemoteDisconnected) as exc:
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
                            retry_after = parsedate_to_datetime(header).timestamp() - time.time()
                        except (ValueError, TypeError, OverflowError):
                            pass
                    exc.close()
                wait = max(backoff, retry_after)
                print(f"EDHREC retry in {wait:.0f}s: {request.full_url}: {exc}", flush=True)
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
        with closing(
            sqlite3.connect(Path(catalog).resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            names = name_index(db.execute("SELECT oracle_id, name FROM cards_oracle"))

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
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    with open(args.root / "collector.lock", "a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        import sys

        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        collect(args.root, args.catalog, max_commanders=args.max_commanders)


if __name__ == "__main__":
    main()

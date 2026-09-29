"""Conservative one-time Archidekt collection under the user's personal-use permission.

No scheduler, authentication, private-deck access, or raw-data redistribution.
"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
from pathlib import Path
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .paths import core_data_root
from .recommendations import RecommendationStore


BASE = "https://archidekt.com"
ORDERS = ("-viewCount", "-updatedAt", "-createdAt", "createdAt")


def api_url(value):
    parsed = urllib.parse.urlsplit(urllib.parse.urljoin(BASE, value))
    if (
        parsed.hostname != "archidekt.com"
        or parsed.port not in (None, 443, 80)
        or not parsed.path.startswith("/api/decks/")
        or parsed.username
    ):
        raise ValueError("Unexpected pagination/API URL")
    return urllib.parse.urlunsplit(
        ("https", "archidekt.com", parsed.path, parsed.query, "")
    )


def normalize_deck(payload):
    if (
        payload.get("private") is not False
        or payload.get("unlisted") is not False
        or payload.get("deckFormat") != 3
    ):
        raise ValueError("Not a listed public Commander deck")
    categories = {c["name"]: c for c in payload.get("categories", [])}
    members = {}
    size = 0
    for entry in payload.get("cards", []):
        if entry.get("deletedAt"):
            continue
        names = entry.get("categories") or []
        lowered = {name.casefold() for name in names}
        if lowered & {"sideboard", "maybeboard", "considering", "excluded"}:
            continue
        if names and not any(
            categories.get(name, {}).get("includedInDeck", True) for name in names
        ):
            continue
        qty = int(entry.get("quantity") or 0)
        if qty <= 0:
            continue
        oracle = entry["card"]["oracleCard"]
        oid = str(uuid.UUID(oracle["uid"]))
        commander = "commander" in lowered or any(
            categories.get(name, {}).get("isPremier") for name in names
        )
        members[oid] = max(members.get(oid, 0), int(commander))
        size += qty
    if size != 100 or not 1 <= sum(members.values()) <= 2:
        raise ValueError(
            "Require 100 mainboard/commander cards and one or two commanders"
        )
    return members


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    temporary.replace(path)


class Collector:
    def __init__(self, root, *, interval=6, max_hours=24, max_decks=20000, max_gb=10):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.interval = max(6, interval)
        self.max_hours, self.max_decks = max_hours, max_decks
        self.max_bytes = max_gb * 1024**3
        self.state_path = self.root / "state.json"
        self.state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else dict(
                version=1,
                started=time.time(),
                requests=0,
                imported=0,
                rejected=0,
                unavailable=0,
                orders_done=[],
                next_url=None,
                queue=[],
                seen=[],
                pages=[],
                status="ready",
                last_request=0,
                permission="User reports permission for one personal/noncommercial rate-limited run; cache responses; no raw redistribution.",
            )
        )
        if self.state["version"] != 1:
            raise ValueError("Unsupported checkpoint version")
        self.store = RecommendationStore(self.root.parent / "archidekt.sqlite3")
        with closing(self.store.connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            self.state["imported"] = db.execute(
                "SELECT count(*) FROM decks"
            ).fetchone()[0]
        self.seen = set(self.state["seen"])
        self.cache_bytes = sum(p.stat().st_size for p in self.root.glob("*.json.gz"))

    def save(self, status="running", **updates):
        self.state.update(
            updates, status=status, updated=time.time(), cache_bytes=self.cache_bytes
        )
        self.state["seen"] = sorted(self.seen)
        atomic_json(self.state_path, self.state)

    def check_stop(self):
        if (self.root / "STOP").exists():
            raise InterruptedError("Stopped by STOP file")
        if time.time() >= self.state["started"] + self.max_hours * 3600:
            raise InterruptedError("One-time run reached its time limit")
        if self.state["imported"] >= self.max_decks:
            raise InterruptedError("One-time run reached its deck limit")
        if self.cache_bytes >= self.max_bytes:
            raise InterruptedError("Cache size limit reached")

    def pause(self, seconds):
        until = time.time() + seconds
        while time.time() < until:
            self.check_stop()
            time.sleep(min(1, max(0, until - time.time())))

    def fetch(self, url):
        url = api_url(url)
        path = self.root / (hashlib.sha256(url.encode()).hexdigest() + ".json.gz")
        if path.exists():
            return json.loads(gzip.decompress(path.read_bytes()))
        for attempt in range(5):
            self.check_stop()
            self.pause(
                max(0, self.interval - (time.time() - self.state["last_request"]))
                + random.uniform(0, 1)
            )
            self.state["requests"] += 1
            self.save(last_request=time.time(), current_url=url)
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Manaforge/0.1 personal-research (single-worker cached import)",
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(request, timeout=45) as response:
                    if api_url(response.url) != url:
                        raise ValueError("Unexpected API redirect")
                    raw = response.read(16 * 1024**2 + 1)
                if len(raw) > 16 * 1024**2:
                    raise ValueError("Oversized API response")
                result = json.loads(raw)
                compressed = gzip.compress(raw)
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(compressed)
                temporary.replace(path)
                self.cache_bytes += len(compressed)
                return result
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise InterruptedError(
                        f"Access denied ({exc.code}); stopped without bypass attempts"
                    ) from exc
                if exc.code in (404, 410):
                    return None
                if exc.code != 429 and exc.code < 500:
                    raise
                if attempt == 4:
                    raise
                retry = exc.headers.get("Retry-After", "")
                try:
                    delay = float(retry)
                except ValueError:
                    try:
                        delay = (
                            parsedate_to_datetime(retry) - datetime.now(timezone.utc)
                        ).total_seconds()
                    except (ValueError, TypeError):
                        delay = 0
                self.save("backoff", last_error=f"HTTP {exc.code}")
                self.pause(max(delay, 60 * 2**attempt))
            except (urllib.error.URLError, TimeoutError):
                if attempt == 4:
                    raise
                self.pause(60 * 2**attempt)

    def run(self):
        if self.state["status"] == "complete":
            return
        try:
            while True:
                self.check_stop()
                if self.state["queue"]:
                    deck_id = self.state["queue"][0]
                    payload = self.fetch(f"{BASE}/api/decks/{deck_id}/")
                    if payload is None:
                        self.state["unavailable"] += 1
                    else:
                        try:
                            members = normalize_deck(payload)
                        except (ValueError, KeyError, TypeError) as exc:
                            self.state["rejected"] += 1
                            self.state["last_rejection"] = str(exc)
                        else:
                            digest = hashlib.sha256(
                                json.dumps(members, sort_keys=True).encode()
                            ).hexdigest()
                            if self.store.ingest_members(
                                str(deck_id), digest, f"{BASE}/decks/{deck_id}", members
                            ):
                                self.state["imported"] += 1
                    self.seen.add(deck_id)
                    self.state["queue"].pop(0)
                    self.save()
                    continue
                order = next(
                    (o for o in ORDERS if o not in self.state["orders_done"]), None
                )
                if order is None:
                    self.save("complete")
                    return
                if self.state.get("order") != order:
                    self.state["order"] = order
                    self.state["next_url"] = (
                        f"{BASE}/api/decks/v3/?"
                        + urllib.parse.urlencode(dict(deckFormat=3, orderBy=order))
                    )
                url = self.state["next_url"]
                if not url:
                    self.state["orders_done"].append(order)
                    self.save()
                    continue
                if url in self.state["pages"]:
                    raise ValueError("Repeated pagination URL; stopped to avoid a loop")
                listing = self.fetch(url)
                if not isinstance(listing, dict) or not isinstance(
                    listing.get("results"), list
                ):
                    raise ValueError("Unexpected listing schema")
                queue = []
                for deck in listing["results"]:
                    deck_id = int(deck["id"])
                    if (
                        deck_id not in self.seen
                        and deck.get("private") is False
                        and deck.get("unlisted") is False
                        and deck.get("deckFormat") == 3
                        and 100 <= int(deck.get("size", 0)) <= 250
                    ):
                        queue.append(deck_id)
                self.state["queue"] = list(dict.fromkeys(queue))
                self.state["pages"].append(url)
                self.state["next_url"] = (
                    api_url(listing["next"]) if listing.get("next") else None
                )
                self.save()
        except (InterruptedError, KeyboardInterrupt) as exc:
            self.save("paused", last_error=str(exc))
        except Exception as exc:
            self.save("error", last_error=f"{type(exc).__name__}: {exc}")
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=core_data_root() / "recommendations" / "archidekt-run",
    )
    parser.add_argument("--max-hours", type=float, default=24)
    parser.add_argument("--max-decks", type=int, default=20000)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    # OS-held lock is released after crashes; no second request stream can start.
    with open(args.root / "collector.lock", "a+b") as lock:
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        collector = Collector(
            args.root, max_hours=args.max_hours, max_decks=args.max_decks
        )
        collector.run()
        print(
            json.dumps(
                {
                    key: collector.state[key]
                    for key in ("status", "imported", "requests", "rejected")
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()

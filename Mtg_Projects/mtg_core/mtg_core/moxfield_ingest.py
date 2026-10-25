"""Explicit, resumable collection of public Moxfield Commander decks."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .archidekt_ingest import atomic_json
from .edhrec_ingest import collector_lock, catalog_index, Downloader, MAX_BYTES
from .paths import core_data_root
from .recommendations import RecommendationStore


BASE = "https://api2.moxfield.com"


def deck_id(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Expected a Moxfield public deck ID, not a URL")
    return value


def normalize_deck(payload, names):
    """Resolve Oracle identities locally; Moxfield card IDs are not Oracle IDs."""
    if not isinstance(payload, dict) or payload.get("format") != "commander":
        raise ValueError("Not a Commander deck")
    if payload.get("visibility") != "public":
        raise ValueError("Not an explicitly public deck")
    boards = payload["boards"]
    members, size = {}, 0
    for section in ("mainboard", "commanders"):
        for entry in boards[section]["cards"].values():
            quantity = entry["quantity"]
            if type(quantity) is not int or quantity <= 0:
                raise ValueError("Invalid included quantity")
            card = entry["card"]
            oracle = card.get("oracle_id") or card.get("oracleId")
            if oracle:
                oracle = str(uuid.UUID(oracle))
            else:
                oracle = names.get(card["name"].casefold())
                if not oracle:
                    raise ValueError(f"Unresolved or ambiguous card: {card['name']}")
                oracle = str(uuid.UUID(oracle))
            members[oracle] = max(members.get(oracle, 0), int(section == "commanders"))
            size += quantity
    if size != 100 or not 1 <= sum(members.values()) <= 2:
        raise ValueError("Require 100 included cards and one or two commanders")
    return members


class Collector:
    def __init__(self, root, catalog, *, user_agent, max_decks=20000, max_pages=200):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.downloader = Downloader(self.root, source="Moxfield")
        self.user_agent = user_agent
        self.max_decks, self.max_pages = max_decks, max_pages
        self.names, _ = catalog_index(catalog)
        self.store = RecommendationStore(self.root.parent / "moxfield.sqlite3")
        self.path = self.root / "state.json"
        self.state = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else dict(version=1, status="ready", queue=[], seen=[], listings={},
                      imported=0, rejected=0, unavailable=0)
        )
        if self.state["version"] != 1:
            raise ValueError("Unsupported checkpoint version")

    def save(self, status="running", **updates):
        self.state.update(updates, status=status, updated=time.time())
        atomic_json(self.path, self.state)

    def fetch(self, path, params=None):
        url = BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        cache = self.root / "responses" / (
            hashlib.sha256(url.encode()).hexdigest() + ".json.gz"
        )
        self.downloader.wait(0)
        if cache.exists():
            with gzip.open(cache, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        else:
            if sum(p.stat().st_size for p in cache.parent.glob("*.json.gz")) >= 10 * 1024**3:
                raise InterruptedError("Compressed response cache reached 10 GiB")
            raw = self.downloader.download(urllib.request.Request(
                url, headers={"User-Agent": self.user_agent, "Accept": "application/json"}
            ))
            if len(raw) > MAX_BYTES:
                raise ValueError("Moxfield response exceeds size limit")
            json.loads(raw)
            temporary = cache.with_suffix(".tmp")
            temporary.write_bytes(gzip.compress(raw))
            temporary.replace(cache)
        if len(raw) > MAX_BYTES:
            raise ValueError("Moxfield response exceeds size limit")
        return json.loads(raw)

    def run(self, deck_ids=(), usernames=(), search=False):
        seen = set(self.state["seen"])
        pending = set(self.state["queue"])
        for value in deck_ids:
            value = deck_id(value)
            if value not in seen and value not in pending:
                self.state["queue"].append(value)
                pending.add(value)
        for username in usernames:
            path = "/v2/users/" + urllib.parse.quote(username, safe="") + "/decks"
            self.state["listings"].setdefault(path, dict(page=1, done=False))
        if search:
            self.state["listings"].setdefault("/v2/decks/search", dict(page=1, done=False))
        self.save()
        try:
            while True:
                self.downloader.wait(0)
                if self.state["imported"] >= self.max_decks:
                    self.save("bounded")
                    return self.state
                if self.state["queue"]:
                    value = self.state["queue"][0]
                    try:
                        payload = self.fetch("/v3/decks/all/" + deck_id(value))
                    except urllib.error.HTTPError as exc:
                        if exc.code not in (404, 410):
                            raise
                        self.state["unavailable"] += 1
                    else:
                        try:
                            members = normalize_deck(payload, self.names)
                        except (ValueError, TypeError, KeyError, AttributeError) as exc:
                            self.state["rejected"] += 1
                            self.state["last_rejection"] = str(exc)
                        else:
                            digest = hashlib.sha256(
                                json.dumps(members, sort_keys=True).encode()
                            ).hexdigest()
                            self.store.ingest_members(
                                value, digest, "https://moxfield.com/decks/" + value, members
                            )
                            self.state["imported"] += 1
                    seen.add(value)
                    self.state["seen"] = sorted(seen)
                    self.state["queue"].pop(0)
                    self.save()
                    continue
                listing = next(
                    ((path, progress) for path, progress in self.state["listings"].items()
                     if not progress["done"]), None
                )
                if listing is None:
                    self.save("complete")
                    return self.state
                path, progress = listing
                if progress["page"] > self.max_pages:
                    self.save("bounded")
                    return self.state
                payload = self.fetch(path, dict(
                    pageNumber=progress["page"], pageSize=64, fmt="commander",
                    sortType="updated", sortDirection="Descending",
                ))
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise ValueError("Unexpected Moxfield listing schema")
                ids = list(dict.fromkeys(deck_id(item["publicId"]) for item in payload["data"]))
                signature = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
                signatures = progress.setdefault("signatures", [])
                if ids and signature in signatures:
                    raise ValueError("Repeated listing page; stopped to avoid pagination loops")
                signatures.append(signature)
                self.state["queue"] = [value for value in ids if value not in seen]
                progress["done"] = not ids
                progress["page"] += 1
                self.save()
        except (InterruptedError, KeyboardInterrupt) as exc:
            self.save("paused", last_error=str(exc))
        except Exception as exc:
            self.save("error", last_error=f"{type(exc).__name__}: {exc}")
            raise
        return self.state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=core_data_root() / "recommendations" / "moxfield-run")
    parser.add_argument("--catalog", type=Path, default=core_data_root() / "card_data.sqlite3")
    parser.add_argument("--deck-id", action="append", default=[])
    parser.add_argument("--username", action="append", default=[])
    parser.add_argument("--search", action="store_true", help="Collect public Commander search results")
    parser.add_argument("--user-agent", default="Manaforge/Moxfield personal cached collection")
    parser.add_argument("--max-decks", type=int, default=20000)
    parser.add_argument("--max-pages", type=int, default=200)
    args = parser.parse_args()
    if args.max_decks <= 0 or args.max_pages <= 0:
        parser.error("Collection limits must be positive")
    for value in args.deck_id:
        try:
            deck_id(value)
        except ValueError as exc:
            parser.error(str(exc))
    if any(not value.strip() for value in args.username):
        parser.error("Usernames must not be empty")
    with collector_lock(args.root):
        collector = Collector(
            args.root, args.catalog, user_agent=args.user_agent,
            max_decks=args.max_decks, max_pages=args.max_pages,
        )
        state = collector.run(args.deck_id, args.username, args.search)
        print(json.dumps({key: state[key] for key in (
            "status", "imported", "rejected", "unavailable"
        )}, indent=2))


if __name__ == "__main__":
    main()

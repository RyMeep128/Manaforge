"""Manual public dataset collection; only complete Commander samples are ranked."""

import argparse
from contextlib import closing
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

from .archidekt_ingest import atomic_json, normalize_deck as normalize_archidekt
from .edhrec_ingest import catalog_index, collector_lock, Downloader
from .moxfield_ingest import normalize_deck as normalize_moxfield
from .paths import core_data_root
from .public_deck_datasets import DATASET_LABELS
from .recommendations import RecommendationStore


PRECONS = "https://raw.githubusercontent.com/taw/magic-preconstructed-decks-data/master/decks_v2.json"
METAGAME = "https://raw.githubusercontent.com/t-my/metagame-decks/main/"
PLAYGROUP = "https://playgroup.gg/api/public/v1/"
MAX_BYTES = 64 * 1024**2


def normalize_rows(rows, names):
    """Count copies for completeness, but count each Oracle identity once in stats."""
    members, size = {}, 0
    for name, quantity, commander in rows:
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Included quantities must be positive integers")
        oracle = names.get(name.casefold())
        if not oracle:
            raise ValueError(f"Unresolved or ambiguous card: {name}")
        oracle = str(uuid.UUID(oracle))
        if commander and quantity != 1:
            raise ValueError("A commander must have exactly one copy")
        members[oracle] = max(members.get(oracle, 0), int(commander))
        size += quantity
    if size != 100 or not 1 <= sum(members.values()) <= 2:
        raise ValueError("Require 100 included cards and one or two commanders")
    return members


def text_rows(text, *, commanders=(), sideboard_commanders=False):
    """Strict MTGO text; sideboard-as-commanders is specific to t-my's format."""
    rows, section, started = [], "mainboard", False
    headings = {
        "deck": "mainboard", "mainboard": "mainboard", "main": "mainboard",
        "commander": "commander", "commanders": "commander",
        "sideboard": "sideboard", "maybeboard": "excluded",
        "considering": "excluded", "companion": "excluded",
    }
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line:
            if started and section == "mainboard":
                section = "sideboard"
            continue
        heading = line.casefold().rstrip(":")
        if heading in headings:
            section = headings[heading]
            continue
        if line.startswith(("#", "//")):
            continue
        prefix = re.match(r"^(SB|CMDR|COMMANDER):\s*", line, re.IGNORECASE)
        target = section
        if prefix:
            target = "sideboard" if prefix[1].upper() == "SB" else "commander"
            line = line[prefix.end():]
        if target == "excluded" or (target == "sideboard" and not sideboard_commanders):
            continue
        match = re.fullmatch(r"(\d+)x?\s+(.+?)(?:\s+\([A-Za-z0-9]+\)\s+\S+)?", line)
        if not match:
            raise ValueError(f"Unrecognized decklist line: {raw}")
        name = match[2].strip()
        commander = target == "commander" or (target == "sideboard" and sideboard_commanders)
        if "#!Commander" in name:
            commander = True
            name = name.replace("#!Commander", "").strip()
        rows.append((name, int(match[1]), commander))
        started = True
    requested = {name.casefold() for name in commanders}
    if requested:
        found = {name.casefold() for name, _, _ in rows} & requested
        if found != requested:
            raise ValueError("Every --commander must already occur in the included export")
        rows = [(name, qty, flag or name.casefold() in requested) for name, qty, flag in rows]
    return rows


class Collector:
    def __init__(self, source, root, catalog, *, user_agent, max_decks=20000):
        self.source, self.root = source, Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.downloader = Downloader(self.root, source=DATASET_LABELS[source], max_bytes=MAX_BYTES)
        self.user_agent, self.max_decks = user_agent, max_decks
        self.names, _ = catalog_index(catalog)
        self.store = RecommendationStore(self.root.parent / f"{source}.sqlite3")
        self.path = self.root / "state.json"
        self.state = (
            json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists()
            else dict(version=1, source=source, status="ready", inputs=[], completed=[], rejected={}, unavailable={})
        )
        if self.state.get("version") != 1 or self.state.get("source") != source:
            raise ValueError("Unsupported or mismatched dataset checkpoint")
        with closing(self.store.connect()) as db:
            self.state["imported"] = db.execute("SELECT count(*) FROM decks").fetchone()[0]
        self.cache_bytes = sum(p.stat().st_size for p in (self.root / "responses").glob("*.gz"))

    def save(self, status="running", **updates):
        self.state.update(updates, status=status, updated=time.time())
        atomic_json(self.path, self.state)

    def fetch(self, url):
        """Only internally constructed, fixed-host URLs reach this downloader."""
        self.downloader.wait(0)
        cache = self.root / "responses" / (hashlib.sha256(url.encode()).hexdigest() + ".gz")
        if cache.exists():
            with gzip.open(cache, "rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        else:
            if self.cache_bytes >= 10 * 1024**3:
                raise InterruptedError("Compressed response cache reached 10 GiB")
            self.save(current_url=url)
            raw = self.downloader.download(urllib.request.Request(
                url, headers={"User-Agent": self.user_agent, "Accept": "application/json, text/plain"}
            ))
            if len(raw) > MAX_BYTES:
                raise ValueError("Dataset response exceeds 64 MiB")
            compressed = gzip.compress(raw)
            temporary = cache.with_suffix(".tmp")
            temporary.write_bytes(compressed)
            temporary.replace(cache)
            self.cache_bytes += len(compressed)
        if len(raw) > MAX_BYTES:
            raise ValueError("Cached dataset response exceeds 64 MiB")
        return raw.decode("utf-8-sig")

    def samples(self):
        if self.source == "preconstructed":
            payload = json.loads(self.fetch(PRECONS))
            if not isinstance(payload, list):
                raise ValueError("Expected the decks_v2 JSON array")
            for deck in payload:
                self.downloader.wait(0)
                if deck.get("format") != "commander":
                    continue
                identity = json.dumps([deck["set_code"], deck["name"], deck["release_date"]])
                key = hashlib.sha256(identity.encode()).hexdigest()
                yield key, PRECONS, deck
        elif self.source == "metagame":
            manifest = json.loads(self.fetch(METAGAME + "manifest.json"))
            formats = manifest["formats"]
            if not isinstance(formats, list):
                raise ValueError("Expected a formats array in the metagame manifest")
            for group in formats:
                if group["id"] != "commander":
                    continue
                for deck in group["decks"]:
                    filename = deck["file"]
                    if not re.fullmatch(r"[A-Za-z0-9_-]+\.txt", filename):
                        raise ValueError("Unexpected metagame deck filename")
                    url = METAGAME + "decks/commander/" + filename
                    yield filename, url, url
        elif self.source == "playgroup":
            for item in self.state["inputs"]:
                self.downloader.wait(0)
                kind, value = item["kind"], item["value"]
                url = PLAYGROUP + (f"users/{value}/decks" if kind == "user" else f"decks/{value}")
                try:
                    payload = json.loads(self.fetch(url))
                except urllib.error.HTTPError as exc:
                    if exc.code not in (404, 410):
                        raise
                    self.state["unavailable"][url] = str(exc)
                    self.save()
                    continue
                records = payload if kind == "user" else [payload]
                if not isinstance(records, list):
                    raise ValueError("Expected a Playgroup deck array")
                for deck in records:
                    if not isinstance(deck, dict):
                        raise ValueError("Unexpected Playgroup deck record")
                    # Deduplicate records pointing at the same underlying hosted deck.
                    link = deck.get("decklist_url") or ""
                    match = re.fullmatch(r"https://(?:www\.)?(archidekt|moxfield)\.com/decks/([A-Za-z0-9_-]+)(?:[/?#].*)?", link)
                    key = f"{match[1]}:{match[2]}" if match else f"playgroup:{deck['id']}"
                    yield key, url, deck
        else:
            for item in self.state["inputs"]:
                # Absolute paths are kept so running from another directory resumes correctly.
                yield item["value"], item["url"], item

    def normalize(self, payload):
        if self.source == "preconstructed":
            rows = [(card["name"], card["count"], flag)
                    for field, flag in (("cards", False), ("commander", True))
                    for card in payload[field]]
            return normalize_rows(rows, self.names)
        if self.source == "metagame":
            return normalize_rows(text_rows(self.fetch(payload), sideboard_commanders=True), self.names)
        if self.source == "playgroup":
            if payload.get("archived") is True:
                raise ValueError("Archived Playgroup deck")
            link = payload.get("decklist_url") or ""
            match = re.fullmatch(r"https://(?:www\.)?(archidekt|moxfield)\.com/decks/([A-Za-z0-9_-]+)(?:[/?#].*)?", link)
            if not match:
                raise ValueError("Playgroup record has no supported public Archidekt/Moxfield decklist URL")
            host, value = match.groups()
            if host == "archidekt":
                if not value.isdigit():
                    raise ValueError("Invalid Archidekt deck ID")
                return normalize_archidekt(json.loads(self.fetch(f"https://archidekt.com/api/decks/{value}/")))
            return normalize_moxfield(json.loads(self.fetch(f"https://api2.moxfield.com/v3/decks/all/{value}")), self.names)
        path = Path(payload["value"])
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Export exceeds 64 MiB")
        rows = text_rows(raw.decode("utf-8-sig"), commanders=payload["commanders"])
        return normalize_rows(rows, self.names)

    def run(self, inputs):
        for item in inputs:
            if item not in self.state["inputs"]:
                self.state["inputs"].append(item)
        self.save()
        done = set(self.state["completed"]) | set(self.state["rejected"]) | set(self.state["unavailable"])
        try:
            iterator = iter(self.samples())
            while True:
                self.downloader.wait(0)
                if self.state["imported"] >= self.max_decks:
                    self.save("bounded")
                    return self.state
                sample = next(iterator, None)
                if sample is None:
                    self.save("complete", current=None)
                    return self.state
                key, provenance, payload = sample
                if key in done:
                    continue
                self.save(current=key)
                try:
                    members = self.normalize(payload)
                except urllib.error.HTTPError as exc:
                    if exc.code not in (404, 410):
                        raise
                    self.state["unavailable"][key] = str(exc)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    self.state["rejected"][key] = str(exc)
                else:
                    digest = hashlib.sha256(json.dumps(members, sort_keys=True).encode()).hexdigest()
                    self.store.ingest_members(key, digest, provenance, members)
                    self.state["completed"].append(key)
                    with closing(self.store.connect()) as db:
                        self.state["imported"] = db.execute("SELECT count(*) FROM decks").fetchone()[0]
                done.add(key)
                self.save()
        except (InterruptedError, KeyboardInterrupt) as exc:
            self.save("paused", last_error=str(exc))
        except Exception as exc:
            self.save("error", last_error=f"{type(exc).__name__}: {exc}")
            raise
        return self.state


def main(source):
    parser = argparse.ArgumentParser(description=f"Collect {DATASET_LABELS[source]} Commander recommendation samples")
    parser.add_argument("--root", type=Path, default=core_data_root() / "recommendations" / f"{source}-run")
    parser.add_argument("--catalog", type=Path, default=core_data_root() / "card_data.sqlite3")
    parser.add_argument("--max-decks", type=int, default=20000)
    parser.add_argument("--user-agent", default="Manaforge/public-deck-collection (personal cached import)")
    if source == "playgroup":
        parser.add_argument("--deck-id", type=int, action="append", default=[])
        parser.add_argument("--user-id", type=int, action="append", default=[])
    elif source in {"deckstats", "mtggoldfish"}:
        parser.add_argument("--file", type=Path, action="append", default=[])
        parser.add_argument("--commander", action="append", default=[])
        parser.add_argument("--source-url", help="Original public deck URL (one file per invocation)")
    args = parser.parse_args()
    if args.max_decks <= 0:
        parser.error("--max-decks must be positive")
    inputs = []
    if source == "playgroup":
        for kind, values in (("deck", args.deck_id), ("user", args.user_id)):
            for value in values:
                if value <= 0:
                    parser.error("IDs must be positive")
                inputs.append(dict(kind=kind, value=str(value)))
    elif source in {"deckstats", "mtggoldfish"}:
        if args.source_url:
            parsed = urllib.parse.urlsplit(args.source_url)
            expected = "deckstats.net" if source == "deckstats" else "mtggoldfish.com"
            if (len(args.file) != 1 or parsed.scheme != "https" or parsed.hostname not in {expected, "www." + expected}
                    or parsed.username or parsed.port not in (None, 443)):
                parser.error("--source-url requires one file and an HTTPS URL on the source's own host")
        for path in args.file:
            if not path.is_file():
                parser.error(f"Export not found: {path}")
            path = path.resolve()
            inputs.append(dict(kind="file", value=str(path), commanders=args.commander,
                               url=args.source_url or path.as_uri()))
    with collector_lock(args.root):
        collector = Collector(source, args.root, args.catalog, user_agent=args.user_agent, max_decks=args.max_decks)
        state = collector.run(inputs)
        print(json.dumps(dict(status=state["status"], imported=state["imported"],
                              rejected=len(state["rejected"]), unavailable=len(state["unavailable"])), indent=2))

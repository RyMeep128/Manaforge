"""Versioned personal aggregate archives. Never export raw decks or source URLs."""

from contextlib import closing
from collections import Counter
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid


MAX_BYTES = 40 * 1024**2
MIN_COHORT = 15


def validate(data):
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data.get("schema_version") != 1
        or data.get("source_id") != "archidekt"
    ):
        raise ValueError("Unsupported aggregate cache schema/source")
    if set(data) != {
        "schema_version",
        "source_id",
        "created_at",
        "decks",
        "popularity",
        "cohorts",
    }:
        raise ValueError(
            "Unexpected cache fields; only anonymous aggregates are supported"
        )
    total = data["decks"]
    if type(total) is not int or total < MIN_COHORT:
        raise ValueError("A personal aggregate cache requires at least 15 decks")
    if (
        not isinstance(data["created_at"], (int, float))
        or not 0 < data["created_at"] <= time.time() + 86400
    ):
        raise ValueError("Invalid aggregate creation time")

    def counts(values, maximum):
        if not isinstance(values, dict):
            raise ValueError("Invalid aggregate counts")
        for oid, count in values.items():
            if (
                not isinstance(oid, str)
                or str(uuid.UUID(oid)) != oid
                or type(count) is not int
                or not 0 < count <= maximum
            ):
                raise ValueError("Invalid Oracle identity or count")

    counts(data["popularity"], total)
    if not isinstance(data["cohorts"], list):
        raise ValueError("Invalid cohorts")
    seen, samples = set(), 0
    combined = Counter()
    for cohort in data["cohorts"]:
        if not isinstance(cohort, dict) or set(cohort) != {
            "commanders",
            "sample",
            "counts",
        }:
            raise ValueError("Unexpected cohort fields")
        commanders = cohort["commanders"]
        sample = cohort["sample"]
        if (
            not isinstance(commanders, list)
            or not 1 <= len(commanders) <= 2
            or not all(isinstance(c, str) for c in commanders)
            or len(set(commanders)) != len(commanders)
        ):
            raise ValueError("Invalid commander cohort")
        key = tuple(sorted(commanders))
        if key in seen or type(sample) is not int or not MIN_COHORT <= sample <= total:
            raise ValueError("Invalid/duplicate cohort sample")
        seen.add(key)
        samples += sample
        counts(cohort["counts"], sample)
        combined.update(cohort["counts"])
        for commander in commanders:
            if cohort["counts"].get(commander) != sample:
                raise ValueError("Commander sample does not match cohort")
        if any(
            count > data["popularity"].get(oid, 0)
            for oid, count in cohort["counts"].items()
        ):
            raise ValueError("Cohort count exceeds global count")
    if samples > total:
        raise ValueError("Cohort samples exceed dataset size")
    if any(count > data["popularity"].get(oid, 0) for oid, count in combined.items()):
        raise ValueError("Combined cohort counts exceed global counts")
    return data


def write_cache(path, data):
    validate(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Aggregate cache exceeds supported size")
    compressed = gzip.compress(raw, mtime=0)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(compressed)
    temporary.replace(path)
    return hashlib.sha256(compressed).hexdigest()


def read_cache(path):
    with gzip.open(path, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Expanded aggregate cache exceeds supported size")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid aggregate document")
    return validate(data)


def export_cache(store, path):
    with closing(store.connect()) as db:
        db.execute("BEGIN")
        total = db.execute("SELECT count(*) FROM decks").fetchone()[0]
        popularity = dict(db.execute("SELECT oracle_id, decks FROM popularity"))
        cohort_sql = """WITH cohorts AS (
            SELECT deck_id, group_concat(oracle_id, '+') AS commanders FROM (
                SELECT deck_id, oracle_id FROM members WHERE commander=1 ORDER BY deck_id, oracle_id
            ) GROUP BY deck_id)"""
        samples = dict(
            db.execute(
                cohort_sql
                + " SELECT commanders, count(*) FROM cohorts GROUP BY commanders"
            )
        )
        cohorts = {
            key: dict(commanders=key.split("+"), sample=sample, counts={})
            for key, sample in samples.items()
            if sample >= MIN_COHORT
        }
        for row in db.execute(
            cohort_sql
            + """ SELECT c.commanders, m.oracle_id, count(*) AS count
            FROM cohorts c JOIN members m ON m.deck_id=c.deck_id
            GROUP BY c.commanders, m.oracle_id"""
        ):
            if row[0] in cohorts and row[2] >= 3:
                cohorts[row[0]]["counts"][row[1]] = row[2]
    return write_cache(
        path,
        dict(
            schema_version=1,
            source_id="archidekt",
            created_at=time.time(),
            decks=total,
            popularity=popularity,
            cohorts=list(cohorts.values()),
        ),
    )


def download_cache(url, digest, destination):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "Use an HTTPS aggregate-cache URL without embedded credentials"
        )
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise ValueError("Provide the expected SHA-256 checksum")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Manaforge personal aggregate cache"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if urllib.parse.urlsplit(response.url).scheme != "https":
            raise ValueError("Aggregate download redirected away from HTTPS")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != digest.lower():
        raise ValueError("Aggregate cache size/checksum validation failed")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    try:
        temporary.write_bytes(raw)
        data = read_cache(temporary)
        write_cache(destination, data)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class AggregateSource:
    path: Path
    source_id: str = "archidekt"
    role: str = "primary"

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        data = read_cache(self.path)
        selected = set(commanders)
        matching = [
            c for c in data["cohorts"] if selected and selected <= set(c["commanders"])
        ]
        sample = sum(c["sample"] for c in matching)
        results = []
        excluded = set(exclude)
        for oid, count in data["popularity"].items():
            if oid in excluded:
                continue
            baseline = count / data["decks"]
            inclusion = (
                sum(c["counts"].get(oid, 0) for c in matching) / sample if sample else 0
            )
            synergy = inclusion - baseline if sample else 0
            results.append(
                dict(
                    oracle_id=oid,
                    baseline=baseline,
                    inclusion=inclusion,
                    synergy=synergy,
                    sample=sample,
                    commander=" + ".join(sorted(selected)) or None,
                    score=inclusion + 0.5 * synergy + 0.25 * baseline
                    if sample
                    else baseline,
                )
            )
        results.sort(key=lambda row: (-row["score"], row["oracle_id"]))
        return dict(
            version=1,
            source="archidekt",
            decks=data["decks"],
            relevant_decks=sample,
            results=results[: max(0, limit)],
            sources=[
                dict(source="Personal aggregate archive", imported=data["created_at"])
            ],
            status="portable cache; cohorts <15 and cells <3 suppressed; no deck-card co-occurrence signal",
            formula="inclusion + 0.5 × (inclusion - baseline) + 0.25 × baseline; baseline alone without cohort samples",
        )


def set_mode(root, mode):
    if mode not in ("live", "portable", "disabled", "edhrec"):
        raise ValueError("Unknown primary source mode")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "source-settings.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(primary=mode)), encoding="utf-8")
    temporary.replace(target)

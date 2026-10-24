"""Offline EDHREC recommendation adapter. Never performs network requests."""

from contextlib import closing
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


def cardlists(payload):
    return payload["container"]["json_dict"]["cardlists"]


def commander_key(commanders):
    return "|".join(sorted(set(commanders)))


def normalize(payload, resolve, slug):
    """Resolve names through our Oracle catalog, not EDHREC printing IDs."""
    page = payload["container"]["json_dict"]
    card = page["card"]
    commander = resolve(card["name"])
    commanders = [commander] if commander else []
    if not commanders:
        parts = card["name"].split(" // ")
        if len(parts) == 2:
            commanders = [resolve(part) for part in parts]
        if (
            not commanders
            or not all(commanders)
            or len(set(commanders)) != len(commanders)
        ):
            raise ValueError(f"Unresolved commander: {card['name']}")
    commander = commander_key(commanders)
    sample = card["num_decks"]
    if type(sample) is not int or sample <= 0:
        raise ValueError("Invalid commander deck count")
    rows, unresolved = {}, set()
    for group in cardlists(payload):
        for item in group["cardviews"]:
            # Some lists contain commanders or links rather than recommendations.
            if "potential_decks" not in item or "num_decks" not in item:
                continue
            count, potential = item["num_decks"], item["potential_decks"]
            if type(count) is not int or type(potential) is not int:
                raise ValueError("Invalid recommendation counts")
            if potential == 0 and count == 0:
                continue
            if not 0 <= count <= potential:
                raise ValueError("Invalid recommendation denominator")
            oid = resolve(item["name"])
            if not oid:
                unresolved.add(item["name"])
                continue
            category = group.get("header", group.get("tag", ""))
            if oid in rows:
                if category not in rows[oid]["categories"]:
                    rows[oid]["categories"].append(category)
                continue
            inclusion = count / potential
            rows[oid] = dict(
                oracle_id=oid,
                inclusion=inclusion,
                score=inclusion,
                sample=potential,
                num_decks=count,
                baseline=0.0,
                synergy=0.0,
                commander=commander,
                commanders=sorted(commanders),
                categories=[category],
                edhrec_synergy=item.get("synergy"),
                statistics_source="edhrec",
            )
    if not rows:
        raise ValueError("No resolved recommendation rows")
    return dict(
        commander=commander,
        commanders=sorted(commanders),
        slug=slug,
        sample=sample,
        results=list(rows.values()),
        unresolved=sorted(unresolved),
    )


def save_page(path, data, imported):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS pages (commander TEXT PRIMARY KEY, payload TEXT NOT NULL, imported REAL NOT NULL)"
        )
        db.execute(
            "INSERT OR REPLACE INTO pages VALUES (?, ?, ?)",
            (data["commander"], json.dumps(data), imported),
        )


@dataclass
class EdhrecSource:
    path: Path
    source_id: str = "edhrec"
    role: str = "public"

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        result = dict(
            version=1,
            source=self.source_id,
            decks=0,
            relevant_decks=0,
            results=[],
            sources=[],
            status="No cached EDHREC page for this commander.",
            formula="EDHREC card inclusion = num_decks / potential_decks; no global baseline or co-occurrence",
        )
        selected = set(commanders)
        if len(selected) == 2:
            result["status"] = (
                "No exact cached pair cohort available. Individual commander pages were not combined."
            )
        if not 1 <= len(selected) <= 2:
            result["status"] = (
                "EDHREC cache requires one commander or an exact cached commander pair."
            )
            return result
        if not Path(self.path).exists():
            return result
        with closing(
            sqlite3.connect(Path(self.path).resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            row = db.execute(
                "SELECT payload, imported FROM pages WHERE commander=?",
                (commander_key(selected),),
            ).fetchone()
        if row is None:
            return result
        data = json.loads(row[0])
        excluded = set(exclude)
        rows = sorted(
            (r for r in data["results"] if r["oracle_id"] not in excluded),
            key=lambda r: (-r["score"], r["oracle_id"]),
        )
        result.update(
            decks=data["sample"],
            relevant_decks=data["sample"],
            results=rows[: max(0, limit)],
            sources=[
                dict(
                    source="https://edhrec.com/commanders/" + data["slug"],
                    imported=row[1],
                )
            ],
            status=f"Offline EDHREC {'exact cached pair cohort' if len(selected) == 2 else 'commander page'}; {len(data['unresolved'])} unresolved card names omitted; category lists may be incomplete.",
        )
        return result

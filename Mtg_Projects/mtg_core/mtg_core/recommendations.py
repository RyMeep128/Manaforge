"""Offline inclusion statistics from explicitly imported, user-owned decks."""

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from .decks import DeckDocument
from .sections import DeckSection


class RecommendationStore:
    """Separate versioned dataset; never changes the user's card catalog."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported recommendation dataset version")
            for sql in (
                "CREATE TABLE IF NOT EXISTS decks (deck_id TEXT PRIMARY KEY, digest TEXT NOT NULL, source TEXT NOT NULL, imported REAL NOT NULL)",
                "CREATE TABLE IF NOT EXISTS members (deck_id TEXT, oracle_id TEXT, commander INTEGER, PRIMARY KEY(deck_id, oracle_id))",
                "CREATE INDEX IF NOT EXISTS members_oracle ON members(oracle_id, deck_id)",
                "CREATE TABLE IF NOT EXISTS popularity (oracle_id TEXT PRIMARY KEY, decks INTEGER NOT NULL)",
                "CREATE TABLE IF NOT EXISTS inclusion (commander TEXT, oracle_id TEXT, decks INTEGER NOT NULL, PRIMARY KEY(commander, oracle_id))",
            ):
                db.execute(sql)
            db.execute("PRAGMA user_version = 1")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def ingest_members(self, deck_id, digest, source, members):
        """Atomically replace one normalized sample and update compact counts."""
        if not members or not any(members.values()):
            raise ValueError("A sample requires card identities and a commander")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT digest FROM decks WHERE deck_id=?", (deck_id,)
            ).fetchone()
            if previous and previous["digest"] == digest:
                return False
            old = dict(
                db.execute(
                    "SELECT oracle_id, commander FROM members WHERE deck_id=?",
                    (deck_id,),
                )
            )
            for oid in old:
                db.execute(
                    "UPDATE popularity SET decks=decks-1 WHERE oracle_id=?", (oid,)
                )
            for commander, enabled in old.items():
                if enabled:
                    db.executemany(
                        "UPDATE inclusion SET decks=decks-1 WHERE commander=? AND oracle_id=?",
                        [(commander, oid) for oid in old],
                    )
            db.execute("DELETE FROM popularity WHERE decks<=0")
            db.execute("DELETE FROM inclusion WHERE decks<=0")
            db.execute("DELETE FROM members WHERE deck_id=?", (deck_id,))
            db.execute(
                "INSERT OR REPLACE INTO decks VALUES (?, ?, ?, ?)",
                (deck_id, digest, source, time.time()),
            )
            db.executemany(
                "INSERT INTO members VALUES (?, ?, ?)",
                [
                    (deck_id, oid, int(bool(commander)))
                    for oid, commander in members.items()
                ],
            )
            db.executemany(
                "INSERT INTO popularity VALUES (?, 1) ON CONFLICT(oracle_id) DO UPDATE SET decks=decks+1",
                [(oid,) for oid in members],
            )
            for commander, enabled in members.items():
                if enabled:
                    db.executemany(
                        "INSERT INTO inclusion VALUES (?, ?, 1) ON CONFLICT(commander, oracle_id) DO UPDATE SET decks=decks+1",
                        [(commander, oid) for oid in members],
                    )
        return True

    def import_files(self, paths, *, should_cancel=lambda: False):
        """Commit each native deck and its aggregates atomically; reimports resume.

        Deck IDs deduplicate moved/copied files. Quantities do not inflate inclusion.
        Unknown Oracle identities are omitted and reported, never guessed.
        """
        result = dict(
            imported=0, unchanged=0, missing_identities=0, errors=[], cancelled=False
        )
        for path in paths:
            if should_cancel():
                result["cancelled"] = True
                break
            try:
                raw = Path(path).read_bytes()
                payload = json.loads(raw)
                if (
                    not isinstance(payload, dict)
                    or not isinstance(payload.get("deck"), dict)
                    or not payload["deck"].get("deck_id")
                ):
                    raise ValueError(
                        "Expected a native Manaforge deck with a stable deck_id"
                    )
                document = DeckDocument.from_dict(payload)
                if (
                    document.deck.format.casefold() != "commander"
                    and not document.deck.commander_entry_ids
                    and not any(
                        e.section == DeckSection.COMMANDER
                        for e in document.deck.entries
                    )
                ):
                    raise ValueError("Recommendation imports require Commander decks")
                digest = sha256(raw).hexdigest()
                members = {}
                missing = 0
                for entry in document.deck.entries:
                    if entry.quantity <= 0 or entry.section not in (
                        DeckSection.MAINBOARD,
                        DeckSection.COMMANDER,
                    ):
                        continue
                    if not entry.oracle_id:
                        missing += 1
                        continue
                    commander = (
                        entry.entry_id in document.deck.commander_entry_ids
                        or entry.section == DeckSection.COMMANDER
                    )
                    members[entry.oracle_id] = max(
                        members.get(entry.oracle_id, 0), int(commander)
                    )
                with closing(self.connect()) as db, db:
                    db.execute("BEGIN IMMEDIATE")
                    previous = db.execute(
                        "SELECT digest FROM decks WHERE deck_id=?",
                        (document.deck.deck_id,),
                    ).fetchone()
                    if previous and previous["digest"] == digest:
                        result["unchanged"] += 1
                        result["missing_identities"] += missing
                        continue
                    if not members:
                        raise ValueError(
                            "No mainboard/commander Oracle identities to aggregate"
                        )
                    db.execute(
                        "INSERT OR REPLACE INTO decks VALUES (?, ?, ?, ?)",
                        (
                            document.deck.deck_id,
                            digest,
                            str(Path(path).resolve()),
                            time.time(),
                        ),
                    )
                    db.execute(
                        "DELETE FROM members WHERE deck_id=?", (document.deck.deck_id,)
                    )
                    db.executemany(
                        "INSERT INTO members VALUES (?, ?, ?)",
                        [
                            (document.deck.deck_id, oid, cmdr)
                            for oid, cmdr in sorted(members.items())
                        ],
                    )
                    # Readers see a complete prior or new snapshot, never stale counts.
                    db.execute("DELETE FROM popularity")
                    db.execute(
                        "INSERT INTO popularity SELECT oracle_id, count(*) FROM members GROUP BY oracle_id"
                    )
                    db.execute("DELETE FROM inclusion")
                    db.execute("""INSERT INTO inclusion SELECT c.oracle_id, m.oracle_id, count(*)
                        FROM members c JOIN members m ON c.deck_id=m.deck_id
                        WHERE c.commander=1 GROUP BY c.oracle_id, m.oracle_id""")
                result["imported"] += 1
                result["missing_identities"] += missing
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result["errors"].append(f"{Path(path).name}: {exc}")
        return result

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        """Read compact aggregates only; synergy is inclusion minus baseline.

        Commander pairs use their exact joint cohort. Scores and sample sizes
        are exposed for inspection; baseline is the full imported corpus.
        """
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            total = db.execute("SELECT count(*) FROM decks").fetchone()[0]
            commander_ids = sorted(set(commanders))
            relevant = 0
            if commander_ids:
                placeholders = ",".join("?" for _ in commander_ids)
                relevant = db.execute(
                    f"""SELECT count(*) FROM (
                    SELECT deck_id FROM members WHERE commander=1 AND oracle_id IN ({placeholders})
                    GROUP BY deck_id HAVING count(*)=?)""",
                    (*commander_ids, len(commander_ids)),
                ).fetchone()[0]
            sources = [
                dict(row)
                for row in db.execute(
                    "SELECT source, imported FROM decks ORDER BY source"
                )
            ]
            populations = {
                row["oracle_id"]: row["decks"]
                for row in db.execute("SELECT * FROM popularity")
            }
            signals = {}
            if commander_ids and relevant:
                cohort = f"""SELECT deck_id FROM members WHERE commander=1
                    AND oracle_id IN ({placeholders}) GROUP BY deck_id HAVING count(*)=?"""
                if len(commander_ids) == 1:
                    rows = db.execute(
                        "SELECT oracle_id, decks FROM inclusion WHERE commander=?",
                        commander_ids,
                    )
                else:
                    rows = db.execute(
                        f"""SELECT oracle_id, count(*) AS decks FROM members
                        WHERE deck_id IN ({cohort}) GROUP BY oracle_id""",
                        (*commander_ids, len(commander_ids)),
                    )
                for row in rows:
                    signals[row["oracle_id"]] = dict(
                        inclusion=row["decks"] / relevant,
                        sample=relevant,
                        commander=" + ".join(commander_ids),
                    )
            excluded = set(exclude)
            results = []
            for oid, count in populations.items():
                if oid in excluded:
                    continue
                baseline = count / total if total else 0
                signal = signals.get(
                    oid,
                    dict(
                        inclusion=0,
                        sample=relevant,
                        commander=" + ".join(commander_ids) or None,
                    ),
                )
                synergy = signal["inclusion"] - baseline if signal["sample"] else 0
                score = (
                    signal["inclusion"] + 0.5 * synergy + 0.25 * baseline
                    if signal["sample"]
                    else baseline
                )
                results.append(
                    dict(
                        oracle_id=oid,
                        baseline=baseline,
                        synergy=synergy,
                        score=score,
                        **signal,
                    )
                )
            results.sort(key=lambda row: (-row["score"], row["oracle_id"]))
            return dict(
                version=1,
                source="User-imported Manaforge decks",
                decks=total,
                relevant_decks=relevant,
                sources=sources,
                results=results[: max(0, limit)],
                formula="inclusion + 0.5 × (inclusion - baseline) + 0.25 × baseline; baseline alone without commander samples",
            )

    def associations(self, seeds, candidates):
        """Bounded indexed co-occurrence aggregates, computed in the background.

        Return conditional inclusion with each known seed, never raw deck lists.
        """
        seeds = sorted(set(seeds))[:200]
        candidates = sorted(set(candidates))[:2000]
        if not seeds or not candidates:
            return {}
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            seed_marks = ",".join("?" for _ in seeds)
            candidate_marks = ",".join("?" for _ in candidates)
            sizes = dict(
                db.execute(
                    f"SELECT oracle_id, decks FROM popularity WHERE oracle_id IN ({seed_marks})",
                    seeds,
                )
            )
            rows = db.execute(
                f"""SELECT s.oracle_id AS seed, c.oracle_id AS candidate, count(*) AS decks
                FROM members s JOIN members c ON c.deck_id=s.deck_id
                WHERE s.oracle_id IN ({seed_marks}) AND c.oracle_id IN ({candidate_marks})
                GROUP BY s.oracle_id, c.oracle_id""",
                (*seeds, *candidates),
            )
            result = {
                oid: dict(value=0.0, seeds=len(sizes), matches=[]) for oid in candidates
            }
            for row in rows:
                sample = sizes[row["seed"]]
                rate = row["decks"] / sample
                result[row["candidate"]]["value"] += rate / len(sizes)
                result[row["candidate"]]["matches"].append(
                    dict(
                        oracle_id=row["seed"],
                        count=row["decks"],
                        sample=sample,
                        inclusion=rate,
                    )
                )
            return result

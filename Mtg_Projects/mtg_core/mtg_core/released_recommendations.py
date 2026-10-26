"""Read-only aggregate datasets; no raw deck membership or collector dependencies."""

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3


def connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


@dataclass
class ReleasedRecommendationSource:
    path: Path
    source_id: str
    role: str = "public"

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        selected = sorted(set(commanders))
        with closing(connect(self.path)) as db:
            total, imported = db.execute(
                "SELECT decks, imported FROM metadata"
            ).fetchone()
            populations = dict(db.execute("SELECT oracle_id, decks FROM popularity"))
            signals, relevant = {}, 0
            if selected:
                marks = ",".join("?" for _ in selected)
                cohort_sql = f"""SELECT cohort FROM commander_members WHERE oracle_id IN ({marks})
                    GROUP BY cohort HAVING count(*)=?"""
                params = (*selected, len(selected))
                relevant = db.execute(
                    f"SELECT coalesce(sum(sample),0) FROM cohorts WHERE cohort IN ({cohort_sql})",
                    params,
                ).fetchone()[0]
                signals = dict(
                    db.execute(
                        f"SELECT oracle_id,sum(decks) FROM counts WHERE cohort IN ({cohort_sql}) GROUP BY oracle_id",
                        params,
                    )
                )
        rows, excluded = [], set(exclude)
        for oid, count in populations.items():
            if oid in excluded:
                continue
            baseline = count / total if total else 0
            inclusion = signals.get(oid, 0) / relevant if relevant else 0
            synergy = inclusion - baseline if relevant else 0
            rows.append(
                dict(
                    oracle_id=oid,
                    baseline=baseline,
                    inclusion=inclusion,
                    synergy=synergy,
                    score=inclusion + 0.5 * synergy + 0.25 * baseline
                    if relevant
                    else baseline,
                    sample=relevant,
                    commander=" + ".join(selected) or None,
                )
            )
        rows.sort(key=lambda row: (-row["score"], row["oracle_id"]))
        return dict(
            version=1,
            source=self.source_id,
            decks=total,
            relevant_decks=relevant,
            results=rows[: max(0, limit)],
            sources=[
                dict(source=f"Published {self.source_id} aggregates", imported=imported)
            ],
            status="Installed recommendation dataset; no user-side collection",
            formula="inclusion + 0.5 × (inclusion - baseline) + 0.25 × baseline; baseline alone without commander samples",
        )

    def commanders_using(self, oracle_id, *, should_cancel=None):
        with closing(connect(self.path)) as db:
            if should_cancel:
                db.set_progress_handler(lambda: int(should_cancel()), 1000)
            return [
                dict(commanders=[row[0]], count=row[1], sample=row[2])
                for row in db.execute(
                    """WITH sizes AS (
                        SELECT m.oracle_id,sum(c.sample) sample FROM commander_members m
                        JOIN cohorts c USING(cohort) GROUP BY m.oracle_id)
                    SELECT m.oracle_id,sum(n.decks),s.sample
                    FROM commander_members m JOIN sizes s ON s.oracle_id=m.oracle_id
                    JOIN counts n USING(cohort) WHERE n.oracle_id=?
                    GROUP BY m.oracle_id ORDER BY sum(n.decks) DESC,m.oracle_id LIMIT 100""",
                    (oracle_id,),
                )
            ]

    def associations(self, seeds, candidates):
        seeds, candidates = sorted(set(seeds))[:200], sorted(set(candidates))[:2000]
        if not seeds or not candidates:
            return {}
        with closing(connect(self.path)) as db:
            sizes = dict(
                db.execute(
                    f"SELECT oracle_id,decks FROM popularity WHERE oracle_id IN ({','.join('?' for _ in seeds)})",
                    seeds,
                )
            )
            total = db.execute("SELECT decks FROM metadata").fetchone()[0]
            populations = dict(
                db.execute(
                    f"SELECT oracle_id,decks FROM popularity WHERE oracle_id IN ({','.join('?' for _ in candidates)})",
                    candidates,
                )
            )
            result = {
                oid: dict(
                    value=0.0,
                    seeds=len(sizes) - int(oid in sizes),
                    matches=[],
                    baseline=populations.get(oid, 0) / total if total else 0,
                )
                for oid in candidates
            }
            marks = ",".join("?" for _ in candidates)
            for seed, sample in sizes.items():
                for candidate, count in db.execute(
                    f"""SELECT b,decks FROM pairs WHERE a=? AND b IN ({marks})
                    UNION ALL SELECT a,decks FROM pairs WHERE b=? AND a IN ({marks})""",
                    (seed, *candidates, seed, *candidates),
                ):
                    rate = count / sample
                    result[candidate]["value"] += rate / result[candidate]["seeds"]
                    result[candidate]["matches"].append(
                        dict(oracle_id=seed, count=count, sample=sample, inclusion=rate)
                    )
            return result

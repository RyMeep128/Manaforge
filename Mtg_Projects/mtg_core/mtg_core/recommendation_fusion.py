"""Deterministic fusion of compact ranked rows, independent of score scales."""

import math

PUBLIC_SOURCE_WEIGHTS = {"archidekt": 1.0, "edhrec": 1.0}
RRF_K = 60
CANDIDATE_LIMIT = 2000


def ranked_rows(rows, *, exclude=(), limit=CANDIDATE_LIMIT):
    excluded = set(exclude)
    unique = {}
    for row in rows:
        oid = row["oracle_id"]
        value = float(row.get("score", row.get("raw_score", 0)))
        if not isinstance(oid, str) or not oid or not math.isfinite(value):
            raise ValueError("Invalid recommendation identity/score")
        if oid in excluded:
            continue
        key = (float(row["rank"]), oid) if "rank" in row else (-value, oid)
        if "rank" in row and (not math.isfinite(key[0]) or key[0] < 1):
            raise ValueError("Invalid source rank")
        if oid not in unique or key < unique[oid][0]:
            unique[oid] = (key, row)
    return [row for _, row in sorted(unique.values(), key=lambda item: item[0])[:limit]]


def fuse_public_recommendations(snapshots, *, weights=None, limit=CANDIDATE_LIMIT):
    """snapshots maps source ID to snapshot; ranks start at one after deduplication."""
    weights = PUBLIC_SOURCE_WEIGHTS if weights is None else weights
    active = {
        key: data
        for key, data in sorted(snapshots.items())
        if data.get("results") and weights.get(key, 1.0) > 0
    }
    maximum = sum(weights.get(key, 1.0) / (RRF_K + 1) for key in active)
    rows = {}
    for source_id, data in active.items():
        weight = weights.get(source_id, 1.0)
        for rank, evidence in enumerate(ranked_rows(data["results"]), 1):
            oid = evidence["oracle_id"]
            row = rows.setdefault(
                oid,
                dict(
                    oracle_id=oid,
                    public_rrf=0.0,
                    source_evidence={},
                    sources_present=[],
                ),
            )
            contribution = weight / (RRF_K + rank)
            row["public_rrf"] += contribution
            row["sources_present"].append(source_id)
            row["source_evidence"][source_id] = dict(
                evidence,
                rank=rank,
                raw_score=evidence.get("score", evidence.get("raw_score", 0)),
                rrf_contribution=contribution,
            )
    for row in rows.values():
        row["public_score"] = min(1.0, row["public_rrf"] / maximum)
    return sorted(
        rows.values(), key=lambda row: (-row["public_score"], row["oracle_id"])
    )[: max(0, limit)]

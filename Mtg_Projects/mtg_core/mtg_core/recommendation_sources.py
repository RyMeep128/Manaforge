"""Pluggable aggregate sources; public recommendations lead, local data supplements."""

from dataclasses import dataclass
from typing import Protocol


class RecommendationSource(Protocol):
    source_id: str
    role: str

    def snapshot(self, commanders=(), *, exclude=(), limit=200) -> dict:
        """Return version, provenance, sample counts, status, and scored rows."""
        ...


@dataclass
class CachedSource:
    source_id: str
    role: str
    store: object

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        return dict(
            self.store.snapshot(commanders, exclude=exclude, limit=limit),
            source=self.source_id,
            status="cached",
        )

    def associations(self, seeds, candidates):
        return self.store.associations(seeds, candidates)


@dataclass
class UnavailableSource:
    source_id: str
    role: str
    reason: str

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        return dict(
            version=1,
            source=self.source_id,
            decks=0,
            relevant_decks=0,
            sources=[],
            results=[],
            status=self.reason,
        )


def default_sources(local_store):
    from .recommendations import RecommendationStore
    from .recommendation_cache import AggregateSource, source_settings
    from .edhrec import EdhrecSource

    root = local_store.path.parent
    config = source_settings(root)
    sources = []
    for source_id in ("archidekt", "edhrec"):
        if not config[source_id]["enabled"]:
            sources.append(
                UnavailableSource(source_id, "public", "Disabled in source settings")
            )
            continue
        try:
            if source_id == "edhrec":
                source = EdhrecSource(root / "edhrec.sqlite3")
            elif config["archidekt"]["cache"] == "portable":
                source = AggregateSource(root / "archidekt.aggregate.json.gz")
            elif (root / "archidekt.sqlite3").exists():
                source = CachedSource(
                    "archidekt",
                    "public",
                    RecommendationStore(root / "archidekt.sqlite3"),
                )
            else:
                source = UnavailableSource(
                    "archidekt", "public", "No collected Archidekt cache available"
                )
        except Exception as exc:
            source = UnavailableSource(
                source_id, "public", f"Source error: {type(exc).__name__}: {exc}"
            )
        sources.append(source)
    return [
        *sources,
        UnavailableSource(
            "blueprintmtg", "public", "Unavailable; optional future source"
        ),
        CachedSource("local", "local", local_store),
    ]


def recommend(
    sources, commanders=(), *, exclude=(), limit=200, seeds=(), use_local=True
):
    """Fuse public ranks, then optionally blend normalized personal ranking evidence."""
    from .recommendation_fusion import (
        CANDIDATE_LIMIT,
        RRF_K,
        fuse_public_recommendations,
        ranked_rows,
    )

    commanders, exclude, seeds = tuple(commanders), tuple(exclude), tuple(seeds)
    snapshots, statuses = [], []
    seen = set()
    for source in sorted(sources, key=lambda item: item.source_id):
        if source.source_id in seen:
            continue
        seen.add(source.source_id)
        try:
            data = source.snapshot(commanders, exclude=exclude, limit=CANDIDATE_LIMIT)
            if (
                data.get("error")
                or data.get("state") == "error"
                or str(data.get("status", ""))
                .lower()
                .startswith(("error", "source error"))
            ):
                raise ValueError(
                    str(data.get("error") or data.get("status") or "Source error")
                )
            data = dict(data, results=ranked_rows(data["results"], exclude=exclude))
            status = data.get("status", "cached" if data["results"] else "No results")
            state = (
                "error"
                if status.startswith("Source error:")
                else "active"
                if data["results"]
                else "unavailable"
            )
        except Exception as exc:
            data = dict(results=[], sources=[], decks=0, relevant_decks=0)
            status, state = f"Source error: {type(exc).__name__}: {exc}", "error"
        snapshots.append((source, data))
        statuses.append(
            dict(
                source=source.source_id,
                role=source.role,
                status=status,
                state=state,
                decks=data.get("decks", 0),
                relevant_decks=data.get("relevant_decks", 0),
            )
        )
    # Legacy role names are accepted only at the adapter boundary.
    public = {
        source.source_id: data
        for source, data in snapshots
        if source.role in {"public", "primary", "secondary"} and data["results"]
    }
    rows = fuse_public_recommendations(public)
    local = next((data for source, data in snapshots if source.role == "local"), {})
    local_count = local.get("relevant_decks", 0)
    eligible = local_count >= 15 and bool(rows)
    enabled = use_local and eligible
    local_rows = {
        row["oracle_id"]: (RRF_K + 1) / (RRF_K + rank)
        for rank, row in enumerate(local.get("results", []), 1)
    }
    for row in rows:
        local_score = local_rows.get(row["oracle_id"], 0)
        row.update(
            local_score=local_score,
            local_enabled=enabled,
            local_eligible=eligible,
            local_relevant=local_count,
            source_status=statuses,
            statistical_score=0.8 * row["public_score"] + 0.2 * local_score
            if enabled
            else row["public_score"],
        )
        row["score"] = row["statistical_score"]
        # Compatibility fields for older consumers; fusion never reads these.
        row["primary_score"] = row["public_score"]
        if len(row["source_evidence"]) == 1:
            evidence = next(iter(row["source_evidence"].values()))
            for key in ("sample", "inclusion", "baseline", "synergy", "commander"):
                if key in evidence:
                    row[key] = evidence[key]
    for status in statuses:
        if status["role"] == "local" and status["state"] != "error":
            why = (
                "supplement active"
                if enabled
                else "disabled by preference"
                if not use_local
                else "below 15-deck threshold"
                if local_count < 15
                else "no public candidates"
            )
            status["status"] = f"{local_count} relevant decks; {why}"
    rows.sort(key=lambda row: (-row["score"], row["oracle_id"]))
    associations, provider_id = {}, None
    if seeds and rows:
        for source, data in sorted(snapshots, key=lambda pair: pair[0].source_id):
            if source.source_id not in public or not callable(
                getattr(source, "associations", None)
            ):
                continue
            try:
                associations = source.associations(
                    seeds, [row["oracle_id"] for row in rows]
                )
                provider_id = source.source_id
                break
            except Exception as exc:
                status = next(s for s in statuses if s["source"] == source.source_id)
                status["association_error"] = str(exc)
                status["status"] += f"; association evidence unavailable: {exc}"
    for row in rows:
        association = dict(associations.get(row["oracle_id"], {}))
        if association:
            association["source"] = provider_id
            association.setdefault(
                "baseline",
                row["source_evidence"].get(provider_id, {}).get("baseline", 0),
            )
        row["association"] = association
    provenance = [
        dict(item, source_id=source_id)
        for source_id, data in sorted(public.items())
        for item in data.get("sources", [])
    ]
    only = next(iter(public.values())) if len(public) == 1 else {}
    return dict(
        version=2,
        source="Combined public recommendations",
        public_sources=sorted(public),
        source_status=statuses,
        sources=provenance,
        source_samples={
            key: dict(
                decks=data.get("decks", 0), relevant_decks=data.get("relevant_decks", 0)
            )
            for key, data in public.items()
        },
        decks=only.get("decks", 0),
        relevant_decks=only.get("relevant_decks", 0),
        results=rows[: max(0, min(limit, CANDIDATE_LIMIT))],
        local_relevant=local_count,
        local_enabled=enabled,
        local_eligible=eligible,
        status="Cached public rank fusion"
        if rows
        else "No public recommendation data available for this deck.",
        formula="Public ranking uses reciprocal-rank fusion (k=60), normalized across active sources; "
        "eligible enabled local decks contribute 20% of the statistical signal (80% public); otherwise 100% public.",
    )

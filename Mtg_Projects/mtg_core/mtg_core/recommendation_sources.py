"""Pluggable aggregate sources; public recommendations lead, local data supplements."""

from dataclasses import dataclass
import json
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
    from .recommendation_cache import AggregateSource

    root = local_store.path.parent
    settings_path = root / "source-settings.json"
    mode = (
        json.loads(settings_path.read_text(encoding="utf-8")).get("primary", "live")
        if settings_path.exists()
        else "live"
    )
    public_path = root / "archidekt.sqlite3"
    primary = (
        CachedSource("archidekt", "primary", RecommendationStore(public_path))
        if mode == "live" and public_path.exists()
        else UnavailableSource(
            "archidekt",
            "primary",
            "No cached primary dataset. Run the authorized one-time importer to populate it.",
        )
    )
    if mode == "portable":
        primary = AggregateSource(root / "archidekt.aggregate.json.gz")
    elif mode == "disabled":
        primary = UnavailableSource(
            "archidekt",
            "primary",
            "Primary recommendations disabled in cache settings.",
        )
    elif mode != "live":
        raise ValueError("Unknown recommendation source mode")
    return [
        primary,
        UnavailableSource(
            "blueprintmtg",
            "secondary",
            "Optional source: API/data-reuse terms unverified; disabled.",
        ),
        CachedSource("local", "local", local_store),
    ]


def recommend(sources, commanders=(), *, exclude=(), limit=200, seeds=()):
    """Use a primary dataset; never silently substitute local-only suggestions.

    Local relevance requires all selected commanders in at least 15 distinct
    imported decks. Eligible local scores contribute 20%, primary scores 80%.
    Secondary sources are exposed for inspection; blending needs its own policy.
    """
    snapshots = [
        (source, source.snapshot(commanders, exclude=exclude, limit=limit))
        for source in sources
    ]
    primary = next(
        (data for source, data in snapshots if source.role == "primary"), None
    )
    primary = primary or dict(
        results=[], decks=0, sources=[], source="No primary source"
    )
    local = next((data for source, data in snapshots if source.role == "local"), {})
    local_count = local.get("relevant_decks", 0)
    local_enabled = local_count >= 15 and bool(primary["results"])
    local_rows = {row["oracle_id"]: row for row in local.get("results", [])}
    rows = []
    for original in primary["results"]:
        row = dict(original)
        local_score = local_rows.get(row["oracle_id"], {}).get("score", 0)
        row.update(
            primary_score=row["score"],
            local_score=local_score,
            local_enabled=local_enabled,
        )
        if local_enabled:
            row["score"] = 0.8 * row["primary_score"] + 0.2 * local_score
        rows.append(row)
    rows.sort(key=lambda row: (-row["score"], row["oracle_id"]))
    rows = rows[: max(0, limit)]
    primary_source = next(
        (source for source, _ in snapshots if source.role == "primary"), None
    )
    associations = (
        primary_source.associations(seeds, [row["oracle_id"] for row in rows])
        if seeds and hasattr(primary_source, "associations")
        else {}
    )
    for row in rows:
        row["association"] = associations.get(row["oracle_id"], {})
    return dict(
        primary,
        results=rows[:limit],
        local_relevant=local_count,
        local_enabled=local_enabled,
        source_status=[
            dict(
                source=source.source_id,
                status=data.get("status", "cached"),
                decks=data["decks"],
            )
            for source, data in snapshots
        ],
        formula=primary.get("formula", "Primary dataset unavailable")
        + (
            "; blend = 80% public + 20% local"
            if local_enabled
            else "; local signal inactive"
        ),
    )

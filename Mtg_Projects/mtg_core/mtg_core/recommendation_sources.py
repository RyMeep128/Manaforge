"""Pluggable aggregate sources; public recommendations lead, local data supplements."""

from dataclasses import dataclass
import sqlite3
from typing import Protocol
from .public_deck_datasets import DATASET_LABELS, SOURCE_LABELS


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

    def commanders_using(self, oracle_id, *, should_cancel=None):
        return self.store.commanders_using(oracle_id, should_cancel=should_cancel)


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


def source_signature(root):
    """Cheap publication signature, checked on user actions rather than polling."""
    from pathlib import Path

    root = Path(root)
    paths = [root / "source-settings.json", root / "archidekt.aggregate.json.gz"]
    from .library.recommendations import cache_path
    paths.append(cache_path())
    if cache_path().exists():
        from contextlib import closing
        import sqlite3
        import time
        try:
            with closing(sqlite3.connect(cache_path())) as db:
                access_state = tuple(db.execute('SELECT server, expires>? FROM access ORDER BY server', (time.time(),)))
        except sqlite3.Error:
            access_state = ()
    else:
        access_state = ()
    from .paths import core_data_root

    if root.resolve() == (core_data_root() / "recommendations").resolve():
        paths.append(core_data_root() / "installation.sqlite3")
    for name in (
        "local",
        "archidekt",
        "edhrec",
        "edhrec-cohorts",
        "moxfield",
        *DATASET_LABELS,
    ):
        paths.extend(root / f"{name}.sqlite3{suffix}" for suffix in ("", "-wal"))
    signature = []
    for path in paths:
        try:
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(path), None, None))
    return (*signature, ('library-access', access_state))


def default_sources(local_store, *, document=None, distribution_state=None):
    from .recommendations import RecommendationStore
    from .recommendation_cache import AggregateSource, source_settings
    from .edhrec import EdhrecSource
    from .recommendation_distribution import released_file
    from .released_recommendations import ReleasedRecommendationSource

    root = local_store.path.parent
    config = source_settings(root)
    sources = []
    for source_id in ("archidekt", "edhrec", "moxfield", *DATASET_LABELS):
        if not config[source_id]["enabled"]:
            sources.append(
                UnavailableSource(source_id, "public", "Disabled in source settings")
            )
            continue
        try:
            if source_id == "edhrec":
                from .discovery_starter import snapshot_path

                cohort = (
                    document.editor_preferences.get("edhrec_cohort", "inherit")
                    if document is not None
                    else "inherit"
                )
                if cohort == "inherit":
                    cohort = config["edhrec"].get("cohort", "auto")
                note = ""
                automatic = cohort == "auto"
                if automatic:
                    discovery = (
                        document.editor_preferences.get("discovery", {})
                        if document is not None
                        else {}
                    )
                    theme = (discovery.get("theme_option") or {}).get(
                        "slug"
                    ) or discovery.get("theme")
                    if (discovery.get("theme_option") or {}).get("origin") == "custom":
                        theme = None
                    cohort = f"theme:{theme}" if theme else "general"
                    if not theme:
                        note = "Automatic: no saved theme; using general. "
                source = EdhrecSource(
                    released_file(
                        root, "edhrec", "edhrec.sqlite3", state=distribution_state
                    )
                    or snapshot_path(root, "edhrec.sqlite3"),
                    cohort=cohort,
                    cohort_database=released_file(
                        root,
                        "edhrec",
                        "edhrec-cohorts.sqlite3",
                        state=distribution_state,
                    )
                    or root / "edhrec-cohorts.sqlite3",
                    selection_note=note,
                    allow_general_fallback=automatic,
                )
            elif (
                source_id == "archidekt" and config["archidekt"]["cache"] == "portable"
            ):
                source = AggregateSource(root / "archidekt.aggregate.json.gz")
            elif (root / f"{source_id}.sqlite3").exists():
                source = CachedSource(
                    source_id,
                    "public",
                    RecommendationStore(root / f"{source_id}.sqlite3"),
                )
            elif source_id in ("archidekt", "moxfield") and (
                released := released_file(
                    root, source_id, "aggregates.sqlite3", state=distribution_state
                )
            ):
                source = ReleasedRecommendationSource(released, source_id)
            else:
                source = UnavailableSource(
                    source_id,
                    "public",
                    f"No collected {SOURCE_LABELS[source_id]} cache available",
                )
        except Exception as exc:
            source = UnavailableSource(
                source_id, "public", f"Source error: {type(exc).__name__}: {exc}"
            )
        sources.append(source)
    from .library.recommendations import LibraryRecommendations, cache_path
    try:
        libraries = [LibraryRecommendations(document=document)] if cache_path().exists() else []
    except (OSError, sqlite3.Error):
        libraries = [UnavailableSource('library', 'library', 'Shared recommendation cache unavailable')]
    return [
        *sources,
        *libraries,
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
    shared = next((data for source, data in snapshots if source.role == 'library'), {})
    by_identity = {row['oracle_id']: row for row in rows}
    for item in shared.get('results', []):
        oid = item['oracle_id']
        row = by_identity.get(oid)
        if row is None:
            row = dict(oracle_id=oid, public_score=0.0, public_rrf=0.0,
                       source_evidence={}, sources_present=[])
            rows.append(row)
            by_identity[oid] = row
        row['library_score'] = 0.2 * max(0, min(1, item['score']))
        row['source_evidence']['library'] = dict(item)
        row['sources_present'].append('library')
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
        row['statistical_score'] += row.get('library_score', 0)
        row['score'] = row['statistical_score']
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
        "eligible enabled local decks contribute 20% of the statistical signal (80% public); otherwise 100% public. "
        "Permitted shared-library evidence adds at most 0.2, discounted for small cohorts.",
    )

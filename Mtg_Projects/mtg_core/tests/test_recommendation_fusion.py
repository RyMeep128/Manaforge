import json
from types import SimpleNamespace

import pytest

from mtg_core.recommendation_fusion import fuse_public_recommendations
from mtg_core.recommendation_sources import recommend, default_sources
from mtg_core.recommendation_cache import (
    source_settings,
    save_source_settings,
    set_mode,
)
from mtg_core.recommendations import RecommendationStore
from mtg_core.edhrec import EdhrecSource, save_page


def source(name, rows=(), *, role="public", relevant=0, fail=False):
    def snapshot(*args, **kwargs):
        assert kwargs["limit"] == 2000
        if fail:
            raise ValueError("broken cache")
        return dict(
            results=[dict(oracle_id=oid, score=value) for oid, value in rows],
            decks=100,
            relevant_decks=relevant,
            sources=[dict(source=name, imported=1)],
        )

    return SimpleNamespace(source_id=name, role=role, snapshot=snapshot)


def test_union_consensus_and_score_scale_independence():
    arch = source(
        "archidekt", [("a", 0.03), ("both", 0.02), ("low", 0.01), ("both", 0.015)]
    )
    edh = source("edhrec", [("b", 0.9), ("both", 0.8), ("low", 0.7)])
    first = recommend([arch, edh])
    assert {r["oracle_id"] for r in first["results"]} == {"a", "b", "both", "low"}
    assert first["results"][0]["oracle_id"] == "both"
    assert first["results"][1]["oracle_id"] == "low"
    both = first["results"][0]
    assert both["public_score"] == pytest.approx(61 / 62)
    assert both["source_evidence"]["archidekt"]["rank"] == 2
    assert both["source_evidence"]["edhrec"]["raw_score"] == 0.8
    changed = recommend(
        [source("edhrec", [("b", 900), ("both", 800), ("low", 700)]), arch]
    )
    assert [(r["oracle_id"], r["score"]) for r in first["results"]] == [
        (r["oracle_id"], r["score"]) for r in changed["results"]
    ]
    assert first["decks"] == 0  # Never sum overlapping corpora.
    assert len(first["sources"]) == 2


@pytest.mark.parametrize(
    "a,b", [(True, True), (True, False), (False, True), (False, False)]
)
def test_availability(a, b):
    sources = [
        source("archidekt", [("a", 1)] if a else []),
        source("edhrec", [("b", 1)] if b else []),
    ]
    result = recommend(sources)
    assert len(result["results"]) == int(a) + int(b)
    assert all(0 <= row["public_score"] <= 1 for row in result["results"])


def test_error_isolation_and_local_cannot_replace_public():
    local = source("local", [("local-only", 999)], role="local", relevant=20)
    result = recommend(
        [source("archidekt", fail=True), source("edhrec", [("b", 1)]), local]
    )
    assert [r["oracle_id"] for r in result["results"]] == ["b"]
    assert result["source_status"][0]["state"] == "error"
    assert not recommend([source("archidekt", fail=True), local])["results"]


@pytest.mark.parametrize("count,enabled", [(14, False), (15, True)])
def test_local_normalization_threshold_toggle(count, enabled):
    sources = [
        source("archidekt", [("a", 0.001), ("b", 0.0001)]),
        source(
            "local", [("local-only", 9999), ("b", 2000)], role="local", relevant=count
        ),
    ]
    result = recommend(sources)
    rows = {r["oracle_id"]: r for r in result["results"]}
    assert set(rows) == {"a", "b"}
    assert result["local_enabled"] == enabled
    assert rows["b"]["local_score"] == pytest.approx(61 / 62)
    assert rows["b"]["statistical_score"] == pytest.approx(
        0.8 * rows["b"]["public_score"] + 0.2 * (61 / 62)
        if enabled
        else rows["b"]["public_score"]
    )
    off = recommend(sources, use_local=False)
    assert all(row["score"] == row["public_score"] for row in off["results"])


def test_large_inputs_deterministic_bounded_and_excluded():
    rows = [(f"c-{i:05}", i % 17) for i in range(6000)]
    a = recommend(
        [source("a", rows), source("b", list(reversed(rows)))],
        limit=9000,
        exclude=["c-00016"],
    )
    b = recommend(
        [source("b", rows), source("a", list(reversed(rows)))],
        limit=9000,
        exclude=["c-00016"],
    )
    assert a["results"] == b["results"]
    assert len(a["results"]) == 2000
    assert "c-00016" not in {r["oracle_id"] for r in a["results"]}


@pytest.mark.parametrize("mode", ["live", "portable", "edhrec", "disabled"])
def test_legacy_settings_migration(tmp_path, mode):
    RecommendationStore(tmp_path / "archidekt.sqlite3")
    (tmp_path / "edhrec.sqlite3").touch()
    (tmp_path / "source-settings.json").write_text(json.dumps(dict(primary=mode)))
    settings = source_settings(tmp_path)
    assert settings["version"] == 2
    assert settings["archidekt"]["enabled"] == (mode != "disabled")
    assert settings["edhrec"]["enabled"] == (mode != "disabled")
    assert settings["archidekt"]["cache"] == (
        "portable" if mode == "portable" else "live"
    )
    assert source_settings(tmp_path) == settings


def test_independent_settings_and_corrupt_cache(tmp_path):
    config = source_settings(tmp_path)
    config["edhrec"]["enabled"] = False
    save_source_settings(tmp_path, config)
    set_mode(tmp_path, "portable")
    assert not source_settings(tmp_path)["edhrec"]["enabled"]
    set_mode(tmp_path, "edhrec")
    assert source_settings(tmp_path)["archidekt"]["cache"] == "portable"
    config = source_settings(tmp_path)
    config["archidekt"].update(cache="live", enabled=True)
    save_source_settings(tmp_path, config)
    (tmp_path / "archidekt.sqlite3").write_bytes(b"corrupt")
    local = RecommendationStore(tmp_path / "local.sqlite3")
    result = recommend(default_sources(local))
    assert result["source_status"][0]["state"] == "error"
    config["archidekt"]["enabled"] = False
    save_source_settings(tmp_path, config)
    assert "Disabled" in recommend(default_sources(local))["source_status"][0]["status"]


def test_exact_pair_fusion_and_no_individual_fallback(tmp_path):
    path = tmp_path / "edhrec.sqlite3"

    def data(key, commanders):
        return dict(
            commander=key,
            commanders=commanders,
            slug="fixture",
            sample=20,
            unresolved=[],
            results=[dict(oracle_id="candidate", score=0.5, categories=["Top Cards"])],
        )

    save_page(path, data("a", ["a"]), 1)
    source_edh = EdhrecSource(path)
    arch = source("archidekt", [("candidate", 0.01)])
    assert recommend([arch, source_edh], ["a", "b"])["public_sources"] == ["archidekt"]
    save_page(path, data("a|b", ["a", "b"]), 1)
    first = recommend([arch, source_edh], ["a", "b"])
    assert first == recommend([arch, source_edh], ["b", "a"])
    assert first["public_sources"] == ["archidekt", "edhrec"]
    assert first["results"][0]["source_evidence"]["edhrec"]["categories"] == [
        "Top Cards"
    ]
    assert not source_edh.snapshot(["a", "missing"])["results"]


def test_capability_associations_and_failure_fallback():
    a = source("a", [("a", 1)])
    a.associations = lambda *args: (_ for _ in ()).throw(
        ValueError("broken associations")
    )
    b = source("b", [("b", 1)])
    b.associations = lambda seeds, candidates: {
        oid: dict(value=0.5, seeds=1, baseline=0.1) for oid in candidates
    }
    result = recommend([a, b], seeds=["seed"])
    assert all(r["association"]["source"] == "b" for r in result["results"])
    assert result["source_status"][0]["association_error"]
    assert (
        recommend([source("edhrec", [("b", 1)])], seeds=["seed"])["results"][0][
            "association"
        ]
        == {}
    )


def test_weights_and_explicit_ranks():
    result = fuse_public_recommendations(
        {
            "a": {"results": [dict(oracle_id="x", rank=1, raw_score=99)]},
            "b": {"results": [dict(oracle_id="y", score=1)]},
        },
        weights={"a": 2, "b": 1},
    )
    assert result[0]["oracle_id"] == "x"
    assert result[0]["public_score"] == pytest.approx(2 / 3)
    assert result[0]["source_evidence"]["a"]["raw_score"] == 99


@pytest.mark.parametrize("cache", ["live", "portable"])
def test_existing_live_and_portable_caches_fuse_without_regeneration(
    tmp_path, monkeypatch, cache
):
    import uuid
    from mtg_core.recommendation_cache import export_cache

    monkeypatch.setattr(
        "socket.socket.connect", lambda *args: pytest.fail("Network access")
    )
    commander, common, unique = [str(uuid.UUID(int=i)) for i in (1, 2, 3)]
    store = RecommendationStore(tmp_path / "archidekt.sqlite3")
    for i in range(15):
        store.ingest_members(str(i), str(i), "fixture", {commander: 1, common: 0})
    export_cache(store, tmp_path / "archidekt.aggregate.json.gz")
    save_page(
        tmp_path / "edhrec.sqlite3",
        dict(
            commander=commander,
            commanders=[commander],
            sample=25,
            slug="fixture",
            unresolved=[],
            results=[dict(oracle_id=unique, score=0.5)],
        ),
        1,
    )
    settings = source_settings(tmp_path)
    settings["archidekt"]["cache"] = cache
    save_source_settings(tmp_path, settings)
    result = recommend(
        default_sources(RecommendationStore(tmp_path / "local.sqlite3")),
        [commander],
        exclude=[commander],
    )
    assert result["public_sources"] == ["archidekt", "edhrec"]
    assert {r["oracle_id"] for r in result["results"]} == {common, unique}


def test_returned_error_status_is_isolated():
    broken = SimpleNamespace(
        source_id="broken",
        role="public",
        snapshot=lambda *a, **k: dict(status="error: unreadable", results=[]),
    )
    result = recommend([broken, source("working", [("x", 1)])])
    assert result["public_sources"] == ["working"]
    assert result["source_status"][0]["state"] == "error"

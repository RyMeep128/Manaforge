import json
from types import SimpleNamespace

import pytest

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.recommendations import RecommendationStore
from mtg_core.recommendation_sources import CachedSource, default_sources, recommend


def deck_file(tmp_path, number, commander="cmdr", card="card"):
    doc = DeckDocument()
    doc.deck.deck_id = str(number)
    doc.deck.format = "Commander"
    doc.deck.entries = [
        DeckEntry("c", "Commander", oracle_id=commander, section="commander"),
        DeckEntry("a", "Card", quantity=5, oracle_id=card),
        DeckEntry("b", "Card copy", oracle_id=card),
    ]
    path = tmp_path / f"deck-{number}.json"
    path.write_text(json.dumps(doc.to_dict()), encoding="utf-8")
    return path


def test_import_resume_deduplicate_update_and_population_counts(tmp_path):
    store = RecommendationStore(tmp_path / "recs.sqlite3")
    first = deck_file(tmp_path, 1)
    other = deck_file(tmp_path, 2, commander="other", card="different")
    assert store.import_files([first, other])["imported"] == 2
    assert store.import_files([first])["unchanged"] == 1
    snap = store.snapshot(["cmdr"], exclude=["cmdr"])
    row = next(r for r in snap["results"] if r["oracle_id"] == "card")
    assert snap["decks"] == 2 and snap["relevant_decks"] == 1
    assert row["inclusion"] == 1 and row["baseline"] == 0.5 and row["synergy"] == 0.5
    first = deck_file(tmp_path, 1, card="replacement")
    assert store.import_files([first])["imported"] == 1
    assert "card" not in {r["oracle_id"] for r in store.snapshot()["results"]}
    assert store.import_files([first], should_cancel=lambda: True)["cancelled"]
    assert store.snapshot()["decks"] == 2


@pytest.mark.parametrize("count,active", [(14, False), (15, True)])
def test_local_signal_requires_fifteen_relevant_decks_and_primary(
    tmp_path, count, active
):
    store = RecommendationStore(tmp_path / "recs.sqlite3")
    store.import_files([deck_file(tmp_path, i) for i in range(count)])
    store.import_files([deck_file(tmp_path, 999, commander="unrelated")])
    local = CachedSource("local", "local", store)
    primary = SimpleNamespace(
        source_id="fixture-public",
        role="primary",
        snapshot=lambda *a, **k: dict(
            results=[dict(oracle_id="card", score=1)],
            decks=100,
            sources=[],
            source="fixture-public",
        ),
    )
    result = recommend([primary, local], ["cmdr"])
    assert result["local_relevant"] == count and result["local_enabled"] == active
    assert recommend(default_sources(store), ["cmdr"])["results"] == []
    assert not recommend([primary, local], ["cmdr", "partner"])["local_enabled"]


def test_bad_import_does_not_destroy_prior_aggregates(tmp_path):
    store = RecommendationStore(tmp_path / "recs.sqlite3")
    path = deck_file(tmp_path, 1)
    store.import_files([path])
    path.write_text("not json")
    assert store.import_files([path])["errors"]
    assert store.snapshot()["decks"] == 1


def test_partner_cohort_and_cooccurrence_do_not_use_individual_samples(tmp_path):
    store = RecommendationStore(tmp_path / "recs.sqlite3")
    store.ingest_members("pair", "1", "fixture", {"a": 1, "b": 1, "x": 0, "seed": 0})
    store.ingest_members("solo", "2", "fixture", {"a": 1, "y": 0, "seed": 0})
    store.ingest_members("other", "3", "fixture", {"b": 1, "y": 0})
    rows = {r["oracle_id"]: r for r in store.snapshot(["a", "b"])["results"]}
    assert rows["x"]["sample"] == 1 and rows["x"]["inclusion"] == 1
    assert rows["y"]["sample"] == 1 and rows["y"]["inclusion"] == 0
    assert rows["y"]["score"] < 0
    association = store.associations(["seed", "seed", "missing"], ["x", "y"])
    assert association["x"]["seeds"] == 1
    assert association["x"]["value"] == 0.5
    assert association["y"]["value"] == 0.5
    assert store.associations(["missing"], ["x"])["x"]["value"] == 0
    assert store.associations(["seed"], ["seed"])["seed"]["value"] == 0
    assert store.associations(["seed"], ["seed"])["seed"]["seeds"] == 0

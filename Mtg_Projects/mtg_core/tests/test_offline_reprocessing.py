import gzip
import hashlib
import json
import sqlite3
import urllib.request

import pytest

from mtg_core import edhrec_ingest as ingest
from mtg_core.edhrec import EdhrecSource, normalize, save_page
from mtg_core.recommendation_sources import recommend
from mtg_core import archidekt_ingest as arch


def page(name="Front", slug="front"):
    return {"container": {"json_dict": {
        "card": {"name": name, "num_decks": 10},
        "cardlists": [{"header": "Top", "cardviews": [
            {"name": "Other", "num_decks": 2, "potential_decks": 10}]}]}}}


def setup_cache(tmp_path):
    catalog = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(catalog) as db:
        db.execute("CREATE TABLE cards_oracle (oracle_id TEXT, name TEXT, layout TEXT)")
        db.executemany("INSERT INTO cards_oracle VALUES (?,?,?)", [
            ("front", "Front // Back", "transform"),
            ("art", "Front // Front", "art_series"),
            ("token", "Front", "token"),
            ("other", "Other", "normal"),
            ("proxy-oracle-fake", "Other", "normal"),
            ("a", "Ambiguous", "normal"), ("b", "Ambiguous", "normal")])
    root = tmp_path / "run"
    (root / "responses").mkdir(parents=True)
    state = dict(status="complete", imported=0, completed=[], skipped={}, slugs=["front", "pair", "ambiguous"])
    (root / "state.json").write_text(json.dumps(state))
    for slug, name in [("front", "Front"), ("pair", "Front // Other"), ("ambiguous", "Ambiguous")]:
        path = root / "responses" / (hashlib.sha256(f"commanders/{slug}.json".encode()).hexdigest() + ".json.gz")
        path.write_bytes(gzip.compress(json.dumps(page(name)).encode()))
    return root, catalog


def test_filtered_names_pairs_and_offline_idempotency(tmp_path, monkeypatch):
    root, catalog = setup_cache(tmp_path)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: pytest.fail("network attempted"))
    names, ambiguous = ingest.catalog_index(catalog)
    assert names["front"] == "front" and names["other"] == "other"
    assert ambiguous["ambiguous"] == ["a", "b"]
    data = normalize(page("Front // Back"), lambda n: names.get(n.casefold()), "front")
    assert data["commanders"] == ["front"]
    for _ in range(2):
        report = ingest.reprocess_cached(root, catalog)
        assert (report["imported"], report["ambiguous"], report["unique_cohorts"]) == (2, 1, 2)
        assert report["pages"]["ambiguous"]["candidates"] == {"Ambiguous": ["a", "b"]}
    source = EdhrecSource(tmp_path / "edhrec.sqlite3")
    assert source.snapshot(["other", "front"]) == source.snapshot(["front", "other"])
    assert recommend([source], ["front", "other"])["results"]
    assert source.snapshot(["front"])["results"]
    assert not source.snapshot(["front", "missing"])["results"]


@pytest.mark.parametrize("failure", ["missing", "corrupt", "stop", "mid_stop", "publish"])
def test_failed_rebuild_preserves_database_and_state(tmp_path, monkeypatch, failure):
    root, catalog = setup_cache(tmp_path)
    names, _ = ingest.catalog_index(catalog)
    target = tmp_path / "edhrec.sqlite3"
    save_page(target, normalize(page(), lambda n: names.get(n.casefold()), "front"), 1)
    before_db, before_state = target.read_bytes(), (root / "state.json").read_bytes()
    with sqlite3.connect(target) as db:
        before_rows = db.execute("SELECT * FROM pages").fetchall()
    cached = next((root / "responses").iterdir())
    if failure == "missing":
        cached.unlink()
    elif failure == "corrupt":
        cached.write_bytes(b"bad gzip")
    elif failure == "stop":
        (root / "STOP").touch()
    elif failure == "mid_stop":
        original = ingest.save_page
        def stop_after_page(*args):
            original(*args)
            (root / "STOP").touch()
        monkeypatch.setattr(ingest, "save_page", stop_after_page)
    else:
        original = ingest.write_json
        def fail_state(path, value):
            if path.name == "state.json":
                raise OSError("publish failed")
            original(path, value)
        monkeypatch.setattr(ingest, "write_json", fail_state)
    with pytest.raises((ValueError, InterruptedError, OSError)):
        ingest.reprocess_cached(root, catalog)
    if failure != "publish":
        assert target.read_bytes() == before_db
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT * FROM pages").fetchall() == before_rows
    assert (root / "state.json").read_bytes() == before_state
    assert json.loads((root / "reprocess-report.json").read_text())["status"] == "stopped"


def test_legacy_single_page(tmp_path):
    data = normalize(page(), lambda n: n.lower(), "front")
    del data["commanders"]
    save_page(tmp_path / "edhrec.sqlite3", data, 1)
    assert EdhrecSource(tmp_path / "edhrec.sqlite3").snapshot(["front"])["results"]


def test_previously_completed_page_cannot_be_lost(tmp_path):
    root, catalog = setup_cache(tmp_path)
    state = json.loads((root / "state.json").read_text())
    state["completed"] = ["ambiguous"]
    (root / "state.json").write_text(json.dumps(state))
    before = (root / "state.json").read_bytes()
    with pytest.raises(ValueError, match="validation failed"):
        ingest.reprocess_cached(root, catalog)
    assert (root / "state.json").read_bytes() == before
    assert not (tmp_path / "edhrec.sqlite3").exists()


def test_archidekt_audit_and_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network attempted"))
    oid = "00000000-0000-0000-0000-000000000001"
    deck = dict(id=1, private=False, unlisted=False, deckFormat=3,
                categories=[dict(name="Leader", isPremier=True), dict(name="Out", includedInDeck=False)],
                cards=[dict(quantity=100, categories=["Leader"], card=dict(oracleCard=dict(uid=oid))),
                       dict(quantity=2, categories=["Out"]), dict(deletedAt="date"),
                       dict(quantity=2, categories=["Sideboard"])])
    root = tmp_path / "run"
    root.mkdir()
    for name in ["one", "duplicate"]:
        (root / f"{name}.json.gz").write_bytes(gzip.compress(json.dumps(deck).encode()))
    report = arch.audit_cached(root)
    assert report["accepted"] == 1 and report["duplicates"] == 1
    assert report["decks"]["1"]["excluded"] == dict(category_not_in_deck=1, deleted=1, excluded_section=1)
    assert report["decks"]["1"]["size"] == 100
    assert arch.audit_cached(root, replay=True)["replayed"] == 1
    assert arch.audit_cached(root, replay=True)["unchanged"] == 1

import gzip
import json
import sqlite3
import time

import pytest

from mtg_core.edhrec import EdhrecSource, normalize, save_page
from mtg_core.edhrec_ingest import Downloader, collect, page_path, name_index
from mtg_core.recommendation_cache import set_mode
from mtg_core.recommendation_sources import default_sources, recommend
from mtg_core.recommendations import RecommendationStore


def payload():
    row = dict(
        name="Card",
        id="printing-not-oracle",
        num_decks=25,
        potential_decks=50,
        synergy=0.2,
    )
    return {
        "container": {
            "json_dict": {
                "card": {"name": "Commander", "num_decks": 100},
                "cardlists": [
                    {"header": "New", "cardviews": [row]},
                    {"header": "Top", "cardviews": [row, dict(row, name="Unknown")]},
                ],
            }
        }
    }


def resolve(name):
    return {"Commander": "commander-oracle", "Card": "card-oracle"}.get(name)


def test_exact_names_outrank_art_card_aliases():
    names = name_index(
        [
            ("real", "Edgar Markov"),
            ("art", "Edgar Markov // Edgar Markov"),
            ("modal", "Front // Back"),
            ("ambiguous", "Front // Other"),
            ("unique", "Unique // Reverse"),
        ]
    )
    assert names["edgar markov"] == "real"
    assert names["edgar markov // edgar markov"] == "art"
    assert names["front"] is None
    assert names["unique"] == "unique"


def test_normalize_and_offline_source(tmp_path):
    data = normalize(payload(), resolve, "commander")
    assert data["unresolved"] == ["Unknown"]
    assert len(data["results"]) == 1
    row = data["results"][0]
    assert row["oracle_id"] == "card-oracle"
    assert row["score"] == 0.5  # Uses per-card denominator, not page deck count.
    assert row["categories"] == ["New", "Top"]
    assert row["synergy"] == 0 and row["edhrec_synergy"] == 0.2
    save_page(tmp_path / "edhrec.sqlite3", data, time.time())
    set_mode(tmp_path, "edhrec")
    sources = default_sources(RecommendationStore(tmp_path / "local.sqlite3"))
    snapshot = recommend(sources, ["commander-oracle"])
    assert snapshot["source"] == "edhrec"
    assert snapshot["decks"] == 100
    assert snapshot["results"][0]["score"] == 0.5
    assert snapshot["results"][0]["association"] == {}
    assert not (tmp_path / "archidekt.sqlite3").exists()
    source = sources[0]
    assert not source.snapshot(["commander-oracle"], exclude=["card-oracle"])["results"]
    assert not source.snapshot(["commander-oracle", "partner"])["results"]
    assert not source.snapshot()["results"]
    assert not source.snapshot(["missing"])["results"]


def test_network_error_records_stop_without_touching_other_sources(
    tmp_path, monkeypatch
):
    catalog = tmp_path / "cards.sqlite3"
    with sqlite3.connect(catalog) as db:
        db.execute("CREATE TABLE cards_oracle (oracle_id TEXT, name TEXT)")
    sentinel = tmp_path / "archidekt.sqlite3"
    sentinel.write_bytes(b"untouched")
    settings = tmp_path / "source-settings.json"
    settings.write_text('{"primary":"live"}')

    def fail(self, page):
        raise OSError("network unavailable")

    monkeypatch.setattr(Downloader, "fetch", fail)
    root = tmp_path / "edhrec-run"
    with pytest.raises(OSError):
        collect(root, catalog)
    state = json.loads((root / "state.json").read_text())
    assert state["status"] == "stopped"
    assert "network unavailable" in state["last_error"]
    assert sentinel.read_bytes() == b"untouched"
    assert settings.read_text() == '{"primary":"live"}'


def test_missing_cache_and_invalid_counts(tmp_path):
    assert not EdhrecSource(tmp_path / "absent").snapshot(["commander"])["results"]
    data = payload()
    data["container"]["json_dict"]["cardlists"][0]["cardviews"][0]["num_decks"] = 51
    with pytest.raises(ValueError):
        normalize(data, resolve, "commander")


@pytest.mark.parametrize(
    "path",
    [
        "https://other.test/a.json",
        "commanders/../a.json",
        "commanders/a/b.json",
        "//other.test/a.json",
    ],
)
def test_reject_foreign_or_unexpected_paths(path):
    with pytest.raises(ValueError):
        page_path(path)


def test_download_cache_and_stop(tmp_path, monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b'{"ok":true}'

    class Opener:
        def open(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    downloader = Downloader(tmp_path)
    assert downloader.fetch("commanders/a.json") == {"ok": True}
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *args: pytest.fail("cache attempted network"),
    )
    assert downloader.fetch("commanders/a.json") == {"ok": True}
    assert json.loads(
        gzip.decompress(next((tmp_path / "responses").iterdir()).read_bytes())
    ) == {"ok": True}
    (tmp_path / "STOP").touch()
    with pytest.raises(InterruptedError):
        downloader.fetch("commanders/a.json")


def test_resume_and_completion_do_not_redownload(tmp_path, monkeypatch):
    catalog = tmp_path / "cards.sqlite3"
    with sqlite3.connect(catalog) as db:
        db.execute("CREATE TABLE cards_oracle (oracle_id TEXT, name TEXT)")
        db.executemany(
            "INSERT INTO cards_oracle VALUES (?, ?)",
            [("commander-oracle", "Commander"), ("card-oracle", "Card")],
        )
    calls = []

    def fetch(self, page):
        calls.append(page)
        if page == "commanders/year.json":
            return {
                "container": {
                    "json_dict": {
                        "cardlists": [
                            {
                                "cardviews": [{"slug": "commander"}],
                                "more": "commanders/year-1.json",
                            }
                        ]
                    }
                }
            }
        if page == "commanders/year-1.json":
            return {"cardviews": [{"slug": "commander"}], "more": None}
        return payload()

    monkeypatch.setattr(Downloader, "fetch", fetch)
    root = tmp_path / "edhrec-run"
    assert collect(root, catalog, max_commanders=0)["status"] == "bounded"
    assert collect(root, catalog)["status"] == "complete"
    assert calls == [
        "commanders/year.json",
        "commanders/year-1.json",
        "commanders/commander.json",
    ]
    assert collect(root, catalog)["imported"] == 1
    assert len(calls) == 3
    assert not (tmp_path / "archidekt.sqlite3").exists()

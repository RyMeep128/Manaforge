import io
import json
import urllib.error

import pytest

from mtg_core import archidekt_ingest as ingest
from mtg_core.recommendations import RecommendationStore
from mtg_core.recommendation_sources import default_sources


COMMANDER = "00000000-0000-0000-0000-000000000001"
CARD = "00000000-0000-0000-0000-000000000002"


def payload():
    return dict(
        id=1,
        private=False,
        unlisted=False,
        deckFormat=3,
        categories=[
            dict(name="Commander", isPremier=True, includedInDeck=True),
            dict(name="Main", includedInDeck=True),
            dict(name="Maybeboard", includedInDeck=False),
        ],
        cards=[
            dict(
                quantity=1,
                categories=["Commander"],
                card=dict(oracleCard=dict(uid=COMMANDER)),
            ),
            dict(
                quantity=99, categories=["Main"], card=dict(oracleCard=dict(uid=CARD))
            ),
            dict(quantity=10, categories=["Maybeboard"]),
            dict(quantity=5, categories=["Sideboard"]),
        ],
    )


def test_normalization_counts_identities_once_and_ignores_other_sections():
    assert ingest.normalize_deck(payload()) == {COMMANDER: 1, CARD: 0}


@pytest.mark.parametrize(
    "field,value", [("private", True), ("unlisted", True), ("deckFormat", 2)]
)
def test_nonpublic_or_noncommander_decks_are_rejected(field, value):
    deck = payload()
    deck[field] = value
    with pytest.raises(ValueError):
        ingest.normalize_deck(deck)


def test_incomplete_or_unidentified_decks_are_rejected():
    deck = payload()
    deck["cards"][1]["quantity"] = 98
    with pytest.raises(ValueError, match="100"):
        ingest.normalize_deck(deck)
    deck = payload()
    deck["cards"][1]["card"]["oracleCard"]["uid"] = "not-an-oracle-id"
    with pytest.raises(ValueError):
        ingest.normalize_deck(deck)


def test_cache_prevents_duplicate_requests_and_429_honors_retry_after(
    tmp_path, monkeypatch
):
    collector = ingest.Collector(tmp_path / "run")
    delays, requests = [], []
    monkeypatch.setattr(collector, "pause", delays.append)
    url = "https://archidekt.com/api/decks/1/"

    def fetch(request, timeout):
        requests.append(request.full_url)
        if len(requests) == 1:
            raise urllib.error.HTTPError(
                url, 429, "slow down", {"Retry-After": "120"}, None
            )
        response = io.BytesIO(json.dumps(payload()).encode())
        response.url = url
        return response

    monkeypatch.setattr(ingest.urllib.request, "urlopen", fetch)
    assert collector.fetch(url) == payload()
    assert collector.fetch(url) == payload()
    assert len(requests) == 2 and collector.state["requests"] == 2
    assert 120 in delays
    assert len(list(collector.root.glob("*.json.gz"))) == 1


def test_access_denial_stops_instead_of_bypassing(tmp_path, monkeypatch):
    collector = ingest.Collector(tmp_path / "run")
    monkeypatch.setattr(collector, "pause", lambda seconds: None)

    def denied(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, None)

    monkeypatch.setattr(ingest.urllib.request, "urlopen", denied)
    with pytest.raises(InterruptedError, match="Access denied"):
        collector.fetch("https://archidekt.com/api/decks/1/")
    assert collector.state["requests"] == 1


def test_collection_deduplicates_pages_and_finished_run_never_restarts(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(ingest, "ORDERS", ("-createdAt",))
    collector = ingest.Collector(tmp_path / "run")
    calls = []

    def fetch(url):
        calls.append(url)
        if "/v3/" in url:
            return dict(
                next=None,
                results=[
                    dict(id=1, private=False, unlisted=False, deckFormat=3, size=100)
                ]
                * 2,
            )
        return payload()

    monkeypatch.setattr(collector, "fetch", fetch)
    collector.run()
    assert collector.state["status"] == "complete"
    assert collector.state["imported"] == 1
    assert len(calls) == 2
    resumed = ingest.Collector(tmp_path / "run")
    monkeypatch.setattr(
        resumed, "fetch", lambda url: pytest.fail("Completed run must not fetch")
    )
    resumed.run()
    assert resumed.state["imported"] == 1
    local = RecommendationStore(tmp_path / "local.sqlite3")
    primary = default_sources(local)[0].snapshot([COMMANDER])
    assert primary["source"] == "archidekt" and primary["decks"] == 1


def test_incremental_replacement_removes_old_counts_and_preserves_other_decks(tmp_path):
    store = RecommendationStore(tmp_path / "recs.sqlite3")
    store.ingest_members(
        "a", "v1", "https://archidekt.com/decks/1", {COMMANDER: 1, CARD: 0}
    )
    store.ingest_members(
        "b", "v1", "https://archidekt.com/decks/2", {COMMANDER: 1, CARD: 0}
    )
    assert not store.ingest_members("a", "v1", "unused", {COMMANDER: 1, CARD: 0})
    store.ingest_members(
        "a", "v2", "https://archidekt.com/decks/1", {COMMANDER: 1, "replacement": 0}
    )
    rows = {row["oracle_id"]: row for row in store.snapshot([COMMANDER])["results"]}
    assert rows[CARD]["inclusion"] == 0.5
    assert rows["replacement"]["inclusion"] == 0.5
    assert rows[COMMANDER]["sample"] == 2


def test_pagination_allows_https_upgrade_but_not_other_hosts():
    assert ingest.api_url("http://archidekt.com/api/decks/v3/?page=2").startswith(
        "https://"
    )
    with pytest.raises(ValueError):
        ingest.api_url("https://other.example/api/decks/v3/")

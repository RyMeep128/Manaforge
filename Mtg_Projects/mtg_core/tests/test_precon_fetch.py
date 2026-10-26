"""Precon refresh must accept array JSON through the real shared fetcher."""

import json

import pytest

from mtg_core import sync
from mtg_core.precons import load_catalog, refresh_catalog


def test_refresh_catalog_uses_shared_json_fetcher(monkeypatch, tmp_path):
    payload = [
        {
            "name": "Starter deck",
            "set_name": "Starter set",
            "set_code": "tst",
            "release_date": "2026-01-01",
            "format": "commander",
            "cards": [{"name": "Forest", "count": 100}],
        }
    ]
    monkeypatch.setattr(
        sync, "read_response", lambda *a, **kw: json.dumps(payload).encode()
    )
    target = tmp_path / "precons.json"
    refresh_catalog(sync.fetch_json, target)
    record = load_catalog(target)[0]
    assert record["name"] == "Starter deck"
    assert record["entries"][0]["count"] == 100


def test_shared_fetcher_still_reports_scryfall_errors(monkeypatch):
    monkeypatch.setattr(
        sync,
        "read_response",
        lambda *a, **kw: b'{"object":"error","details":"No cards found"}',
    )
    with pytest.raises(ValueError, match="No cards found"):
        sync.fetch_json("https://api.scryfall.com/cards/named?exact=missing")

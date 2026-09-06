from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from mtg_core.services import CardService
from services import deck_import_service


def test_proxy_and_core_import_together_and_search_uses_shared_contract(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        if parse_qs(urlparse(url).query).get('q', [''])[0] in ('Lightning Bolt', '!"Lightning Bolt"'):
            return {
                "object": "list",
                "data": [
                    {
                        "id": "bolt-alpha",
                        "oracle_id": "oracle-bolt",
                        "name": "Lightning Bolt",
                        "set": "lea",
                        "set_name": "Limited Edition Alpha",
                        "collector_number": "161",
                        "released_at": "1993-08-05",
                        "image_uris": {"small": "small", "normal": "normal", "png": "png"},
                    }
                ],
                "has_more": False,
            }
        raise AssertionError(url)

    core = CardService(
        db_path=str(tmp_path / "integration.sqlite3"),
        image_root=str(tmp_path / "images"),
        fetch_json_fn=fake_fetch_json,
    )
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: core)
    page = deck_import_service.search_scryfall_card_page(
        "Lightning Bolt", fetch_json=fake_fetch_json, online_mode=True,
    )

    results = core.search_cards("Lightning Bolt", {"allow_remote": True})

    assert len(page.candidates) == 1
    assert len(results) == 1
    assert page.candidates[0].scryfall_id == results[0].card_id
    assert calls


def test_proxy_search_passes_token_syntax_through_core(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        assert "include=extras" in url
        assert "t%3Atoken" in url
        return {
            "object": "list",
            "data": [
                {
                    "id": "ooze-token",
                    "oracle_id": "oracle-ooze-token",
                    "name": "Ooze",
                    "set": "tmid",
                    "set_name": "Innistrad: Midnight Hunt Tokens",
                    "collector_number": "10",
                    "released_at": "2021-09-24",
                    "layout": "token",
                    "type_line": "Token Creature — Ooze",
                    "image_uris": {"small": "small", "normal": "normal", "png": "png"},
                }
            ],
            "has_more": False,
        }

    core = CardService(db_path=str(tmp_path / "tokens.sqlite3"),
                       image_root=str(tmp_path / "images"), fetch_json_fn=fake_fetch_json)
    monkeypatch.setattr(deck_import_service, "_build_card_service", lambda fetch_json=None: core)
    page = deck_import_service.search_scryfall_card_page(
        "t:token ooze",
        fetch_json=fake_fetch_json, online_mode=True,
    )

    assert [candidate.scryfall_id for candidate in page.candidates] == ["ooze-token"]
    assert calls

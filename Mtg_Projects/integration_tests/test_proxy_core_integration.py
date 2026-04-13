from __future__ import annotations

from pathlib import Path

from mtg_core.services import CardService
from services import deck_import_service


_PRODUCTS_ROOT = Path(__file__).resolve().parents[1]


def test_proxy_and_core_import_together_and_search_uses_shared_contract():
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        if 'q=%21%22Lightning+Bolt%22' in url:
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

    page = deck_import_service.search_scryfall_card_page(
        "Lightning Bolt",
        fetch_json=fake_fetch_json,
    )

    core = CardService(
        db_path=str(_PRODUCTS_ROOT / "mtg_core" / "integration_card_data.sqlite3"),
        image_root=str(_PRODUCTS_ROOT / "mtg_core" / "images"),
        fetch_json_fn=fake_fetch_json,
    )
    results = core.search_cards("Lightning Bolt", {"allow_remote": True})

    assert len(page.candidates) == 1
    assert len(results) == 1
    assert page.candidates[0].scryfall_id == results[0].card_id
    assert calls


def test_proxy_search_can_request_tokens_through_core_without_proxy_changes():
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

    page = deck_import_service.search_scryfall_card_page(
        "ooze token",
        fetch_json=fake_fetch_json,
    )

    assert [candidate.scryfall_id for candidate in page.candidates] == ["ooze-token"]
    assert calls

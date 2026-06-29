from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from mtg_editor.catalog import resolve_deck_entry, search_catalog_cards
from mtg_editor.decklist_io import DecklistEntry


@dataclass(frozen=True)
class FakeSearchResult:
    card_id: str
    oracle_id: str
    name: str
    set_code: str | None
    set_name: str | None
    collector_number: str | None
    preview_url: str | None
    thumbnail_url: str | None
    payload: dict


class FakeDatabase:
    def __init__(self):
        self.image_records = {
            "sf-bolt": SimpleNamespace(path="cache/bolt.png", asset_id="asset-bolt")
        }

    def get_image_record(self, card_id, variant="default"):
        return self.image_records.get(card_id)


class FakeCardService:
    def __init__(self):
        self.database = FakeDatabase()
        self.search_calls = []
        self.get_print_calls = []
        self.get_card_calls = []
        self.remote_result = None

    def get_print(self, *, set_code, collector_number):
        self.get_print_calls.append((set_code, collector_number))
        if set_code == "clu" and collector_number == "141":
            return _payload("sf-bolt", "Lightning Bolt", set_code="clu", collector_number="141")
        return None

    def get_card(self, *, exact_name=None, oracle_id=None, card_id=None):
        self.get_card_calls.append(exact_name)
        if exact_name == "Opt":
            return _payload("sf-opt", "Opt", set_code="eld", collector_number="59")
        return None

    def search_cards(self, query, filters=None):
        filters = filters or {}
        self.search_calls.append((query, dict(filters)))
        if filters.get("allow_remote"):
            return [
                FakeSearchResult(
                    card_id="sf-remote",
                    oracle_id="oracle-remote",
                    name="Remote Card",
                    set_code="rmt",
                    set_name="Remote Set",
                    collector_number="1",
                    preview_url="https://img.test/remote-normal.jpg",
                    thumbnail_url="https://img.test/remote-small.jpg",
                    payload=_payload("sf-remote", "Remote Card", set_code="rmt", collector_number="1"),
                )
            ]
        return []


def test_resolve_deck_entry_prefers_local_exact_print():
    service = FakeCardService()
    entry = DecklistEntry(1, "Lightning Bolt", set_code="clu", collector_number="141")

    candidate = resolve_deck_entry(entry, card_service=service)

    assert candidate.catalog_card_id == "sf-bolt"
    assert candidate.oracle_id == "oracle-sf-bolt"
    assert candidate.set_code == "clu"
    assert candidate.collector_number == "141"
    assert candidate.image_uri == "https://img.test/sf-bolt.png"
    assert candidate.local_image_path == "cache/bolt.png"
    assert candidate.image_asset_id == "asset-bolt"
    assert candidate.type_line == "Instant"
    assert candidate.mana_cost == "{R}"
    assert candidate.mana_value == 1.0
    assert candidate.colors == ["R"]
    assert candidate.color_identity == ["R"]
    assert candidate.card_types == ["Instant"]
    assert candidate.source == "local_exact_print"
    assert service.search_calls == []


def test_resolve_deck_entry_uses_local_exact_name_before_search():
    service = FakeCardService()

    candidate = resolve_deck_entry(DecklistEntry(4, "Opt"), card_service=service)

    assert candidate.catalog_card_id == "sf-opt"
    assert candidate.name == "Opt"
    assert candidate.source == "local_exact_name"
    assert service.search_calls == []


def test_search_catalog_cards_keeps_remote_disabled_by_default():
    service = FakeCardService()

    assert search_catalog_cards("Remote Card", card_service=service) == []

    assert service.search_calls == [
        ("Remote Card", {"set_filter": "", "allow_remote": False, "limit": 60})
    ]


def test_resolve_deck_entry_uses_remote_only_when_allowed():
    service = FakeCardService()

    assert resolve_deck_entry(DecklistEntry(1, "Remote Card"), card_service=service) is None
    candidate = resolve_deck_entry(
        DecklistEntry(1, "Remote Card"),
        card_service=service,
        allow_remote=True,
    )

    assert candidate.catalog_card_id == "sf-remote"
    assert [call[1]["allow_remote"] for call in service.search_calls] == [
        False,
        False,
        True,
    ]


def _payload(card_id, name, *, set_code, collector_number):
    return {
        "id": card_id,
        "oracle_id": f"oracle-{card_id}",
        "name": name,
        "set": set_code,
        "set_name": f"{set_code.upper()} Set",
        "collector_number": collector_number,
        "type_line": "Instant",
        "mana_cost": "{R}",
        "cmc": 1,
        "colors": ["R"],
        "color_identity": ["R"],
        "image_uris": {
            "png": f"https://img.test/{card_id}.png",
            "normal": f"https://img.test/{card_id}-normal.jpg",
            "small": f"https://img.test/{card_id}-small.jpg",
        },
    }

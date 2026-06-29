from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from mtg_editor.catalog import CatalogCardCandidate
from mtg_editor.models import DeckProject
from mtg_editor.quick_add import (
    QuickAddQuery,
    add_catalog_candidate,
    parse_quick_add_input,
    quick_add_card,
    search_printings,
)


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
    def get_image_record(self, card_id, variant="default"):
        if card_id == "sf-bolt-clu":
            return SimpleNamespace(path="cache/bolt.png", asset_id="asset-bolt")
        return None


class FakeCardService:
    def __init__(self):
        self.database = FakeDatabase()
        self.search_calls = []

    def get_print(self, *, set_code, collector_number):
        if set_code == "clu" and collector_number == "141":
            return _payload("sf-bolt-clu", "Lightning Bolt", set_code="clu", collector_number="141")
        return None

    def get_card(self, *, exact_name=None, oracle_id=None, card_id=None):
        if exact_name == "Opt":
            return _payload("sf-opt", "Opt", set_code="eld", collector_number="59")
        return None

    def search_cards(self, query, filters=None):
        filters = filters or {}
        self.search_calls.append((query, dict(filters)))
        if query == "Lightning" and not filters.get("allow_remote"):
            return [
                _search_result("sf-bolt-clu", "Lightning Bolt", "clu", "141"),
                _search_result("sf-bolt-2x2", "Lightning Bolt", "2x2", "117"),
            ]
        if query == "Remote Card" and filters.get("allow_remote"):
            return [_search_result("sf-remote", "Remote Card", "rmt", "1")]
        return []


def test_parse_quick_add_input_supported_shapes():
    assert parse_quick_add_input("Lightning Bolt") == QuickAddQuery("Lightning Bolt")
    assert parse_quick_add_input("4 Lightning Bolt") == QuickAddQuery("Lightning Bolt", quantity=4)
    assert parse_quick_add_input("4x Lightning Bolt") == QuickAddQuery("Lightning Bolt", quantity=4)
    assert parse_quick_add_input("Lightning Bolt (CLU) 141") == QuickAddQuery(
        "Lightning Bolt",
        set_code="clu",
        collector_number="141",
    )
    assert parse_quick_add_input("4 Lightning Bolt", quantity=2, section="Sideboard") == QuickAddQuery(
        "Lightning Bolt",
        quantity=2,
        section="sideboard",
    )


def test_quick_add_invalid_input_returns_invalid_result():
    project = DeckProject.new()

    blank = quick_add_card(project, "   ", card_service=FakeCardService())
    zero = quick_add_card(project, "0 Lightning Bolt", card_service=FakeCardService())

    assert blank.status == "invalid"
    assert zero.status == "invalid"
    assert project.cards == []


def test_quick_add_exact_local_print_adds_with_catalog_metadata():
    project = DeckProject.new()

    result = quick_add_card(
        project,
        "4 Lightning Bolt (CLU) 141",
        card_service=FakeCardService(),
    )

    card = project.get_card(result.card_id)
    assert result.status == "added"
    assert card.card_id != "sf-bolt-clu"
    assert card.catalog_card_id == "sf-bolt-clu"
    assert card.oracle_id == "oracle-sf-bolt-clu"
    assert card.quantity == 4
    assert card.set_code == "clu"
    assert card.collector_number == "141"
    assert card.image_asset_id == "asset-bolt"
    assert card.local_image_path == "cache/bolt.png"
    assert card.catalog_status == "resolved"
    assert card.type_line == "Instant"
    assert card.mana_cost == "{R}"
    assert card.mana_value == 1.0
    assert card.colors == ["R"]
    assert card.color_identity == ["R"]
    assert card.card_types == ["Instant"]


def test_quick_add_exact_local_name_uses_default_quantity():
    project = DeckProject.new()

    result = quick_add_card(project, "Opt", card_service=FakeCardService())

    card = project.get_card(result.card_id)
    assert result.status == "added"
    assert card.name == "Opt"
    assert card.quantity == 1
    assert card.catalog_card_id == "sf-opt"
    assert card.set_code == "eld"


def test_quick_add_ambiguous_search_returns_candidates_without_mutation():
    service = FakeCardService()
    project = DeckProject.new()

    result = quick_add_card(project, "Lightning", card_service=service)

    assert result.status == "needs_selection"
    assert [candidate.collector_number for candidate in result.candidates] == ["141", "117"]
    assert project.cards == []
    assert all(not call[1]["allow_remote"] for call in service.search_calls)


def test_quick_add_not_found_and_remote_gating():
    service = FakeCardService()
    project = DeckProject.new()

    local_result = quick_add_card(project, "Remote Card", card_service=service)
    remote_result = quick_add_card(project, "Remote Card", card_service=service, allow_remote=True)

    assert local_result.status == "not_found"
    assert remote_result.status == "needs_selection"
    assert [candidate.name for candidate in remote_result.candidates] == ["Remote Card"]
    assert any(call[1]["allow_remote"] for call in service.search_calls)
    assert project.cards == []


def test_search_printings_delegates_to_catalog_search():
    service = FakeCardService()

    candidates = search_printings("Lightning", card_service=service, limit=2)

    assert len(candidates) == 2
    assert service.search_calls == [
        ("Lightning", {"set_filter": "", "allow_remote": False, "limit": 2})
    ]


def test_add_catalog_candidate_adds_and_increments_existing_card_preserving_organization():
    project = DeckProject.new()
    candidate = CatalogCardCandidate(
        name="Lightning Bolt",
        catalog_card_id="sf-bolt-clu",
        oracle_id="oracle-sf-bolt-clu",
        set_code="clu",
        set_name="Commander Legends",
        collector_number="141",
        image_uri="https://img.test/bolt.png",
        type_line="Instant",
        mana_cost="{R}",
        mana_value=1,
        colors=["R"],
        color_identity=["R"],
        card_types=["Instant"],
        source="local",
    )

    first = add_catalog_candidate(project, candidate, quantity=2)
    burn_id = project.create_category("Burn")
    project.assign_category(first.card_id, burn_id)
    project.add_tag(first.card_id, "Removal")
    second = add_catalog_candidate(project, candidate, quantity=1)

    card = project.get_card(first.card_id)
    assert first.status == "added"
    assert second.status == "added"
    assert second.card_id == first.card_id
    assert card.quantity == 3
    assert card.primary_category == burn_id
    assert card.tags == ["Removal"]
    assert card.catalog_card_id == "sf-bolt-clu"
    assert card.card_types == ["Instant"]


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


def _search_result(card_id, name, set_code, collector_number):
    return FakeSearchResult(
        card_id=card_id,
        oracle_id=f"oracle-{card_id}",
        name=name,
        set_code=set_code,
        set_name=f"{set_code.upper()} Set",
        collector_number=collector_number,
        preview_url=f"https://img.test/{card_id}-normal.jpg",
        thumbnail_url=f"https://img.test/{card_id}-small.jpg",
        payload=_payload(card_id, name, set_code=set_code, collector_number=collector_number),
    )

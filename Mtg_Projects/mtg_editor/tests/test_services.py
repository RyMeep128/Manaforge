from __future__ import annotations

import pytest

from mtg_editor.models import DEFAULT_CATEGORY_ID, DeckProject
from mtg_editor.services import CardGroup, compute_deck_stats, group_cards, sort_cards


def _project():
    project = DeckProject.new("Service Test")
    project.add_card("Zebra", quantity=2, card_id="card-z", sort_index=0)
    project.add_card("Alpha", quantity=4, card_id="card-a", sort_index=1)
    project.add_card("Manta", quantity=1, card_id="card-m", sort_index=2)
    return project


def test_sort_cards_by_supported_modes():
    project = _project()

    assert [card.card_id for card in sort_cards(project, "alphabetical_az")] == [
        "card-a",
        "card-m",
        "card-z",
    ]
    assert [card.card_id for card in sort_cards(project, "alphabetical_za")] == [
        "card-z",
        "card-m",
        "card-a",
    ]
    assert [card.card_id for card in sort_cards(project, "quantity")] == [
        "card-a",
        "card-z",
        "card-m",
    ]
    assert [card.card_id for card in sort_cards(project, "import_order")] == [
        "card-z",
        "card-a",
        "card-m",
    ]


def test_sort_cards_rejects_unknown_mode():
    with pytest.raises(ValueError):
        sort_cards(_project(), "mana_value")


def test_group_cards_by_none():
    project = _project()

    assert group_cards(project, "none") == [
        CardGroup(
            key="all",
            label="All Cards",
            card_ids=["card-a", "card-m", "card-z"],
        )
    ]


def test_group_cards_by_category_in_category_order():
    project = _project()
    ramp_id = project.create_category("Ramp")
    draw_id = project.create_category("Draw")
    project.assign_category("card-z", ramp_id)
    project.assign_category("card-a", draw_id)

    groups = group_cards(project, "category")

    assert groups == [
        CardGroup(key=DEFAULT_CATEGORY_ID, label="Uncategorized", card_ids=["card-m"]),
        CardGroup(key=ramp_id, label="Ramp", card_ids=["card-z"]),
        CardGroup(key=draw_id, label="Draw", card_ids=["card-a"]),
    ]


def test_group_cards_by_section_and_import_section():
    project = _project()
    project.set_section("card-z", "sideboard")
    project.set_section("card-a", "main")
    project.set_section("card-m", "maybeboard")
    project.set_import_section("card-z", "Sideboard")
    project.set_import_section("card-a", "Mainboard")

    assert group_cards(project, "section") == [
        CardGroup(key="main", label="Main Deck", card_ids=["card-a"]),
        CardGroup(key="maybeboard", label="Maybeboard", card_ids=["card-m"]),
        CardGroup(key="sideboard", label="Sideboard", card_ids=["card-z"]),
    ]
    assert group_cards(project, "import_section") == [
        CardGroup(key="Mainboard", label="Mainboard", card_ids=["card-a"]),
        CardGroup(key="Unsectioned", label="Unsectioned", card_ids=["card-m"]),
        CardGroup(key="Sideboard", label="Sideboard", card_ids=["card-z"]),
    ]


def test_group_cards_uses_current_preference_sort_mode():
    project = _project()
    project.preferences.sort_mode = "quantity"

    groups = group_cards(project, "none")

    assert groups[0].card_ids == ["card-a", "card-z", "card-m"]


def test_group_cards_rejects_unknown_mode():
    with pytest.raises(ValueError):
        group_cards(_project(), "color")


def test_compute_deck_stats_counts_sections_categories_and_tags():
    project = DeckProject.new()
    project.add_card("Ramp", quantity=3, card_id="ramp")
    project.add_card("Draw", quantity=2, card_id="draw")
    project.add_card("Excluded", quantity=5, card_id="excluded")
    project.add_card("Zero", quantity=0, card_id="zero")
    ramp_id = project.create_category("Ramp")
    draw_id = project.create_category("Draw")
    project.assign_category("ramp", ramp_id)
    project.assign_category("draw", draw_id)
    project.assign_category("excluded", draw_id)
    project.add_tag("ramp", "Mana")
    project.add_tag("draw", "Card Advantage")
    project.add_tag("excluded", "Card Advantage")
    project.set_section("draw", "sideboard")
    project.set_section("excluded", "excluded")

    stats = compute_deck_stats(project)

    assert stats["total_unique_cards"] == 2
    assert stats["total_copies"] == 5
    assert stats["section_counts"] == {
        "main": {"unique": 1, "copies": 3},
        "sideboard": {"unique": 1, "copies": 2},
        "excluded": {"unique": 1, "copies": 5},
    }
    assert stats["category_counts"] == {
        ramp_id: {"unique": 1, "copies": 3},
        draw_id: {"unique": 2, "copies": 7},
    }
    assert stats["tag_counts"] == {
        "Mana": {"unique": 1, "copies": 3},
        "Card Advantage": {"unique": 2, "copies": 7},
    }

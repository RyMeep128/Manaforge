from __future__ import annotations

import pytest

from mtg_editor.models import DEFAULT_CATEGORY_ID, DeckEditorState
from mtg_editor.services import CardGroup, compute_deck_stats, group_cards, sort_card_names


def _project():
    return {
        "cards": {
            "__back.png": 0,
            "z-card.png": 2,
            "a-card.png": 4,
            "m-card.png": 1,
        },
        "card_metadata": {
            "z-card.png": {"name": "Zebra"},
            "a-card.png": {"name": "Alpha"},
            "m-card.png": {"name": "Manta"},
        },
    }


def test_sort_card_names_by_supported_modes():
    project = _project()
    state = DeckEditorState.from_project_dict(project)

    assert sort_card_names(state, project, "alphabetical_az") == [
        "a-card.png",
        "m-card.png",
        "z-card.png",
    ]
    assert sort_card_names(state, project, "alphabetical_za") == [
        "z-card.png",
        "m-card.png",
        "a-card.png",
    ]
    assert sort_card_names(state, project, "quantity") == [
        "a-card.png",
        "z-card.png",
        "m-card.png",
    ]
    assert sort_card_names(state, project, "import_order") == [
        "z-card.png",
        "a-card.png",
        "m-card.png",
    ]


def test_sort_card_names_rejects_unknown_mode():
    project = _project()
    state = DeckEditorState.from_project_dict(project)

    with pytest.raises(ValueError):
        sort_card_names(state, project, "mana_value")


def test_group_cards_by_none():
    project = _project()
    state = DeckEditorState.from_project_dict(project)

    assert group_cards(state, project, "none") == [
        CardGroup(
            key="all",
            label="All Cards",
            card_names=["a-card.png", "m-card.png", "z-card.png"],
        )
    ]


def test_group_cards_by_category_in_category_order():
    project = _project()
    state = DeckEditorState.from_project_dict(project)
    ramp_id = state.create_category("Ramp")
    draw_id = state.create_category("Draw")
    state.assign_category("z-card.png", ramp_id)
    state.assign_category("a-card.png", draw_id)

    groups = group_cards(state, project, "category")

    assert groups == [
        CardGroup(key=DEFAULT_CATEGORY_ID, label="Uncategorized", card_names=["m-card.png"]),
        CardGroup(key=ramp_id, label="Ramp", card_names=["z-card.png"]),
        CardGroup(key=draw_id, label="Draw", card_names=["a-card.png"]),
    ]


def test_group_cards_by_section_and_import_section():
    project = _project()
    state = DeckEditorState.from_project_dict(project)
    state.set_section("z-card.png", "sideboard")
    state.set_section("a-card.png", "main")
    state.set_section("m-card.png", "maybeboard")
    state.set_import_section("z-card.png", "Sideboard")
    state.set_import_section("a-card.png", "Mainboard")

    assert group_cards(state, project, "section") == [
        CardGroup(key="main", label="Main Deck", card_names=["a-card.png"]),
        CardGroup(key="maybeboard", label="Maybeboard", card_names=["m-card.png"]),
        CardGroup(key="sideboard", label="Sideboard", card_names=["z-card.png"]),
    ]
    assert group_cards(state, project, "import_section") == [
        CardGroup(key="Mainboard", label="Mainboard", card_names=["a-card.png"]),
        CardGroup(key="Unsectioned", label="Unsectioned", card_names=["m-card.png"]),
        CardGroup(key="Sideboard", label="Sideboard", card_names=["z-card.png"]),
    ]


def test_group_cards_uses_current_preference_sort_mode():
    project = _project()
    state = DeckEditorState.from_project_dict(project)
    state.preferences.sort_mode = "quantity"

    groups = group_cards(state, project, "none")

    assert groups[0].card_names == ["a-card.png", "z-card.png", "m-card.png"]


def test_group_cards_rejects_unknown_mode():
    project = _project()
    state = DeckEditorState.from_project_dict(project)

    with pytest.raises(ValueError):
        group_cards(state, project, "color")


def test_compute_deck_stats_counts_sections_categories_and_tags():
    project = {
        "cards": {
            "__back.png": 0,
            "ramp.png": 3,
            "draw.png": 2,
            "excluded.png": 5,
            "zero.png": 0,
        }
    }
    state = DeckEditorState.from_project_dict(project)
    ramp_id = state.create_category("Ramp")
    draw_id = state.create_category("Draw")
    state.assign_category("ramp.png", ramp_id)
    state.assign_category("draw.png", draw_id)
    state.assign_category("excluded.png", draw_id)
    state.add_tag("ramp.png", "Mana")
    state.add_tag("draw.png", "Card Advantage")
    state.add_tag("excluded.png", "Card Advantage")
    state.set_section("draw.png", "sideboard")
    state.set_section("excluded.png", "excluded")

    stats = compute_deck_stats(state, project)

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


def test_services_read_card_entries_when_present():
    project = {
        "cards": {"legacy-only.png": 9},
        "card_entries": [
            {"front_name": "second.png", "count": 1, "metadata": {"name": "Beta"}},
            {"front_name": "first.png", "count": 2, "metadata": {"name": "Alpha"}},
        ],
    }
    state = DeckEditorState.from_project_dict(project)

    assert sort_card_names(state, project, "import_order") == ["second.png", "first.png"]
    assert sort_card_names(state, project, "alphabetical_az") == ["first.png", "second.png"]
    assert compute_deck_stats(state, project)["total_copies"] == 3

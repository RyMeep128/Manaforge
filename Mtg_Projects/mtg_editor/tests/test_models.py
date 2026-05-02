from __future__ import annotations

from copy import deepcopy

import pytest

from mtg_editor.models import DEFAULT_CATEGORY_ID, DEFAULT_SECTION, DeckEditorState


def test_from_legacy_cards_project_creates_default_editor_state():
    project = {
        "cards": {
            "__back.png": 0,
            "scryfall_clu_141_lightning-bolt.png": 4,
            "scryfall_und_89_island.png": 0,
        },
        "card_metadata": {
            "scryfall_clu_141_lightning-bolt.png": {
                "name": "Lightning Bolt",
                "set_code": "clu",
                "collector_number": "141",
            }
        },
    }

    state = DeckEditorState.from_project_dict(project, display_name="Burn Box")

    assert state.metadata.deck_name == "Burn Box"
    assert state.metadata.format == "Custom"
    assert state.preferences.view_mode == "grid"
    assert state.preferences.group_mode == "none"
    assert state.preferences.sort_mode == "alphabetical_az"
    assert [category.to_dict() for category in state.categories] == [
        {"id": DEFAULT_CATEGORY_ID, "name": "Uncategorized"}
    ]
    assert set(state.cards) == {
        "scryfall_clu_141_lightning-bolt.png",
        "scryfall_und_89_island.png",
    }
    assert state.cards["scryfall_clu_141_lightning-bolt.png"].primary_category == DEFAULT_CATEGORY_ID
    assert state.cards["scryfall_clu_141_lightning-bolt.png"].section == DEFAULT_SECTION
    assert "__back.png" not in state.cards


def test_from_card_entries_project_creates_organization_records_for_cards():
    project = {
        "card_entries": [
            {"front_name": "__back.png", "count": 0},
            {
                "front_name": "scryfall_eld_59_opt.png",
                "count": 2,
                "metadata": {"name": "Opt"},
            },
            {
                "front_name": "scryfall_moc_166_acclaimed-contender.png",
                "count": 1,
                "metadata": {"name": "Acclaimed Contender"},
            },
        ]
    }

    state = DeckEditorState.from_project_dict(project)

    assert list(state.cards) == [
        "scryfall_eld_59_opt.png",
        "scryfall_moc_166_acclaimed-contender.png",
    ]
    assert state.cards["scryfall_eld_59_opt.png"].sort_index == 0
    assert state.cards["scryfall_moc_166_acclaimed-contender.png"].sort_index == 1


def test_from_project_dict_reads_existing_deck_editor_overlay():
    project = {
        "cards": {"opt.png": 1},
        "deck_editor": {
            "metadata": {
                "deck_name": "Spells",
                "format": "Commander",
                "description": "Cantrips everywhere",
                "tags": ["Blue", "Budget"],
                "created_at": "2026-05-01T10:00:00+00:00",
                "modified_at": "2026-05-02T10:00:00+00:00",
            },
            "preferences": {
                "view_mode": "text",
                "group_mode": "category",
                "sort_mode": "quantity",
                "active_filters": {"low_dpi": True},
            },
            "categories": [
                {"id": "draw", "name": "Draw"},
                {"id": DEFAULT_CATEGORY_ID, "name": "Uncategorized"},
            ],
            "cards": {
                "opt.png": {
                    "primary_category": "draw",
                    "tags": ["Cantrip"],
                    "section": "main",
                    "import_section": "Mainboard",
                    "sort_index": 12,
                }
            },
            "notes": "Need more lands.",
        },
    }

    state = DeckEditorState.from_project_dict(project)

    assert state.metadata.deck_name == "Spells"
    assert state.metadata.format == "Commander"
    assert state.metadata.tags == ["Blue", "Budget"]
    assert state.preferences.view_mode == "text"
    assert state.preferences.active_filters == {"low_dpi": True}
    assert [category.id for category in state.categories] == ["draw", DEFAULT_CATEGORY_ID]
    assert state.cards["opt.png"].primary_category == "draw"
    assert state.cards["opt.png"].tags == ["Cantrip"]
    assert state.cards["opt.png"].import_section == "Mainboard"
    assert state.cards["opt.png"].sort_index == 12
    assert state.notes == "Need more lands."


def test_unknown_card_category_falls_back_to_uncategorized():
    state = DeckEditorState.from_project_dict(
        {
            "cards": {"opt.png": 1},
            "deck_editor": {
                "categories": [{"id": "draw", "name": "Draw"}],
                "cards": {"opt.png": {"primary_category": "missing"}},
            },
        }
    )

    assert state.cards["opt.png"].primary_category == DEFAULT_CATEGORY_ID


def test_merge_into_project_dict_preserves_existing_print_fields():
    project = {
        "cards": {"opt.png": 2},
        "backsides": {"opt.png": "__back.png"},
        "backside_short_edge": {"opt.png": True},
        "oversized": {"opt.png": True},
        "card_metadata": {"opt.png": {"name": "Opt"}},
        "high_res_front_overrides": {"opt.png": {"identifier": "new-art"}},
    }
    original = deepcopy(project)
    state = DeckEditorState.from_project_dict(project, display_name="Cantrips")
    category_id = state.create_category("Draw")
    state.assign_category("opt.png", category_id)
    state.add_tag("opt.png", "Cantrip")

    merged = state.merge_into_project_dict(project)

    assert project == original
    for key, value in original.items():
        assert merged[key] == value
    assert merged["deck_editor"]["metadata"]["deck_name"] == "Cantrips"
    assert merged["deck_editor"]["cards"]["opt.png"]["primary_category"] == category_id
    assert merged["deck_editor"]["cards"]["opt.png"]["tags"] == ["Cantrip"]


def test_category_lifecycle_and_reorder():
    state = DeckEditorState.from_project_dict({"cards": {"rampant-growth.png": 1}})

    ramp_id = state.create_category("Ramp")
    draw_id = state.create_category("Draw")
    duplicate_id = state.create_category("Ramp")
    state.rename_category(draw_id, "Card Draw")
    state.reorder_category(draw_id, 0)
    state.assign_category("rampant-growth.png", ramp_id)

    assert duplicate_id == "ramp-2"
    assert [category.id for category in state.categories] == [
        draw_id,
        DEFAULT_CATEGORY_ID,
        ramp_id,
        duplicate_id,
    ]
    assert state.cards["rampant-growth.png"].primary_category == ramp_id

    state.delete_category(ramp_id)

    assert ramp_id not in [category.id for category in state.categories]
    assert state.cards["rampant-growth.png"].primary_category == DEFAULT_CATEGORY_ID


def test_default_category_cannot_be_deleted():
    state = DeckEditorState.from_project_dict({"cards": {"opt.png": 1}})

    with pytest.raises(ValueError):
        state.delete_category(DEFAULT_CATEGORY_ID)


def test_tags_and_sections_are_card_organization_only():
    state = DeckEditorState.from_project_dict({"cards": {"opt.png": 4}})

    state.add_tag("opt.png", "Cantrip")
    state.add_tag("opt.png", "cantrip")
    state.add_tag("opt.png", "Instant")
    state.remove_tag("opt.png", "CANTRIP")
    state.set_section("opt.png", "Sideboard")
    state.set_import_section("opt.png", "Mainboard")

    assert state.cards["opt.png"].tags == ["Instant"]
    assert state.cards["opt.png"].section == "sideboard"
    assert state.cards["opt.png"].import_section == "Mainboard"

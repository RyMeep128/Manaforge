from __future__ import annotations

import pytest

from mtg_editor.models import (
    DEFAULT_CATEGORY_ID,
    DEFAULT_SECTION,
    SCHEMA_VERSION,
    DeckProject,
)


def test_new_deck_project_defaults():
    project = DeckProject.new("Burn Box", "Commander")

    assert project.schema_version == SCHEMA_VERSION
    assert project.metadata.deck_name == "Burn Box"
    assert project.metadata.format == "Commander"
    assert project.preferences.view_mode == "grid"
    assert project.preferences.group_mode == "none"
    assert project.preferences.sort_mode == "alphabetical_az"
    assert [category.to_dict() for category in project.categories] == [
        {"id": DEFAULT_CATEGORY_ID, "name": "Uncategorized"}
    ]
    assert project.cards == []
    assert project.notes == ""


def test_deck_project_round_trips_native_json_shape():
    project = DeckProject.new("Spells", "Modern")
    project.metadata.description = "Cantrips everywhere"
    project.metadata.tags = ["Blue", "Budget"]
    project.preferences.view_mode = "text"
    project.preferences.group_mode = "category"
    project.preferences.sort_mode = "quantity"
    project.preferences.active_filters = {"low_dpi": True}
    draw_id = project.create_category("Draw")
    card_id = project.add_card(
        "Opt",
        quantity=4,
        card_id="card-opt",
        primary_category=draw_id,
        tags=["Cantrip"],
        set_code="eld",
        collector_number="59",
        import_section="Mainboard",
        image_uri="https://example.test/opt.png",
        catalog_card_id="scryfall-opt",
        oracle_id="oracle-opt",
        set_name="Throne of Eldraine",
        preview_uri="https://example.test/opt-normal.png",
        thumbnail_uri="https://example.test/opt-small.png",
        local_image_path="cache/opt.png",
        catalog_status="resolved",
        type_line="Instant",
        mana_cost="{U}",
        mana_value=1,
        colors=["U"],
        color_identity=["U"],
        card_types=["Instant"],
    )
    project.set_section(card_id, "Sideboard")
    project.notes = "Need more lands."

    payload = project.to_dict()
    restored = DeckProject.from_dict(payload)

    assert payload["schema_version"] == 1
    assert set(payload) == {
        "schema_version",
        "metadata",
        "preferences",
        "categories",
        "cards",
        "notes",
    }
    assert restored.to_dict() == payload
    assert restored.metadata.deck_name == "Spells"
    assert restored.preferences.active_filters == {"low_dpi": True}
    assert restored.cards[0].name == "Opt"
    assert restored.cards[0].quantity == 4
    assert restored.cards[0].primary_category == draw_id
    assert restored.cards[0].section == "sideboard"
    assert restored.cards[0].set_code == "eld"
    assert restored.cards[0].image_uri == "https://example.test/opt.png"
    assert restored.cards[0].card_id == "card-opt"
    assert restored.cards[0].catalog_card_id == "scryfall-opt"
    assert restored.cards[0].oracle_id == "oracle-opt"
    assert restored.cards[0].set_name == "Throne of Eldraine"
    assert restored.cards[0].preview_uri == "https://example.test/opt-normal.png"
    assert restored.cards[0].thumbnail_uri == "https://example.test/opt-small.png"
    assert restored.cards[0].local_image_path == "cache/opt.png"
    assert restored.cards[0].catalog_status == "resolved"
    assert restored.cards[0].type_line == "Instant"
    assert restored.cards[0].mana_cost == "{U}"
    assert restored.cards[0].mana_value == 1.0
    assert restored.cards[0].colors == ["U"]
    assert restored.cards[0].color_identity == ["U"]
    assert restored.cards[0].card_types == ["Instant"]
    assert restored.notes == "Need more lands."


def test_from_dict_rejects_missing_or_unsupported_schema_version():
    with pytest.raises(ValueError):
        DeckProject.from_dict({})

    with pytest.raises(ValueError):
        DeckProject.from_dict({"schema_version": 99})


def test_from_dict_rejects_malformed_cards_and_duplicates():
    with pytest.raises(ValueError):
        DeckProject.from_dict(
            {
                "schema_version": 1,
                "metadata": {},
                "preferences": {},
                "categories": [],
                "cards": [{"card_id": "card-a"}],
                "notes": "",
            }
        )

    with pytest.raises(ValueError):
        DeckProject.from_dict(
            {
                "schema_version": 1,
                "metadata": {},
                "preferences": {},
                "categories": [],
                "cards": [
                    {"card_id": "card-a", "name": "Alpha", "quantity": 1},
                    {"card_id": "card-a", "name": "Alpha Again", "quantity": 1},
                ],
                "notes": "",
            }
        )


def test_add_remove_and_update_card_quantities():
    project = DeckProject.new()

    card_id = project.add_card("Lightning Bolt", quantity=4, set_code="clu")
    second_id = project.add_card("Island", quantity=-1)
    project.set_quantity(card_id, 2)

    assert card_id.startswith("card-")
    assert project.get_card(card_id).name == "Lightning Bolt"
    assert project.get_card(card_id).quantity == 2
    assert project.get_card(card_id).set_code == "clu"
    assert project.get_card(second_id).quantity == 0

    project.remove_card(second_id)

    assert project.get_card(second_id) is None
    assert [card.card_id for card in project.cards] == [card_id]


def test_add_card_rejects_blank_name_duplicate_id_and_missing_category():
    project = DeckProject.new()

    with pytest.raises(ValueError):
        project.add_card(" ")

    project.add_card("Opt", card_id="card-opt")
    with pytest.raises(ValueError):
        project.add_card("Other Opt", card_id="card-opt")

    with pytest.raises(KeyError):
        project.add_card("Rampant Growth", primary_category="missing")


def test_category_lifecycle_and_reorder():
    project = DeckProject.new()
    card_id = project.add_card("Rampant Growth")

    ramp_id = project.create_category("Ramp")
    draw_id = project.create_category("Draw")
    duplicate_id = project.create_category("Ramp")
    project.rename_category(draw_id, "Card Draw")
    project.reorder_category(draw_id, 0)
    project.assign_category(card_id, ramp_id)

    assert duplicate_id == "ramp-2"
    assert [category.id for category in project.categories] == [
        draw_id,
        DEFAULT_CATEGORY_ID,
        ramp_id,
        duplicate_id,
    ]
    assert project.get_card(card_id).primary_category == ramp_id

    project.delete_category(ramp_id)

    assert ramp_id not in [category.id for category in project.categories]
    assert project.get_card(card_id).primary_category == DEFAULT_CATEGORY_ID


def test_default_category_cannot_be_deleted():
    project = DeckProject.new()

    with pytest.raises(ValueError):
        project.delete_category(DEFAULT_CATEGORY_ID)


def test_tags_sections_and_import_sections_target_card_id():
    project = DeckProject.new()
    card_id = project.add_card("Opt", quantity=4)

    project.add_tag(card_id, "Cantrip")
    project.add_tag(card_id, "cantrip")
    project.add_tag(card_id, "Instant")
    project.remove_tag(card_id, "CANTRIP")
    project.set_section(card_id, "Sideboard")
    project.set_import_section(card_id, "Mainboard")

    card = project.get_card(card_id)
    assert card.tags == ["Instant"]
    assert card.section == "sideboard"
    assert card.import_section == "Mainboard"


def test_unknown_category_from_file_falls_back_to_uncategorized():
    project = DeckProject.from_dict(
        {
            "schema_version": 1,
            "metadata": {},
            "preferences": {},
            "categories": [{"id": "draw", "name": "Draw"}],
            "cards": [
                {
                    "card_id": "card-opt",
                    "name": "Opt",
                    "quantity": 1,
                    "primary_category": "missing",
                }
            ],
            "notes": "",
        }
    )

    assert project.cards[0].primary_category == DEFAULT_CATEGORY_ID
    assert project.cards[0].section == DEFAULT_SECTION
    assert project.cards[0].type_line is None
    assert project.cards[0].mana_value is None
    assert project.cards[0].colors == []
    assert project.cards[0].color_identity == []
    assert project.cards[0].card_types == []

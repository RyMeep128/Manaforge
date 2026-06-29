from __future__ import annotations

from types import SimpleNamespace

from mtg_editor.decklist_io import (
    DecklistEntry,
    export_decklist,
    import_decklist,
    import_decklist_file,
    parse_decklist,
    read_decklist_file,
    write_decklist_file,
)
from mtg_editor.models import DeckProject


class FakeDatabase:
    def get_image_record(self, card_id, variant="default"):
        if card_id == "sf-bolt":
            return SimpleNamespace(path="cache/bolt.png", asset_id="asset-bolt")
        return None


class FakeCardService:
    def __init__(self):
        self.database = FakeDatabase()

    def get_print(self, *, set_code, collector_number):
        if set_code == "clu" and collector_number == "141":
            return _payload("sf-bolt", "Lightning Bolt", set_code="clu", collector_number="141")
        return None

    def get_card(self, *, exact_name=None, oracle_id=None, card_id=None):
        return None

    def search_cards(self, query, filters=None):
        return []


def test_parse_text_decklist_sections_prefixes_duplicates_and_unmatched():
    entries, unmatched = parse_decklist(
        """
        Commander:
        1 Atraxa, Praetors' Voice
        Sideboard:
        SB: 2 Negate
        Maybeboard:
        1 Opt (ELD) 59
        3 Opt (eld) 59
        this is not a card line
        """
    )

    assert entries == [
        DecklistEntry(1, "Atraxa, Praetors' Voice", section="commander", import_section="Commander"),
        DecklistEntry(2, "Negate", section="sideboard", import_section="Sideboard"),
        DecklistEntry(4, "Opt", set_code="eld", collector_number="59", section="maybeboard", import_section="Maybeboard"),
    ]
    assert unmatched == ["this is not a card line"]


def test_parse_csv_decklist_with_optional_fields_duplicates_and_invalid_rows():
    entries, unmatched = parse_decklist(
        "\n".join(
            [
                "count,name,set_code,collector_number,section",
                "2,Lightning Bolt,CLU,141,Mainboard",
                "1,Lightning Bolt,clu,141,main",
                "x,Missing Count,,,Sideboard",
                "1,Negate,,,Sideboard",
            ]
        )
    )

    assert entries == [
        DecklistEntry(3, "Lightning Bolt", set_code="clu", collector_number="141", section="main", import_section="Mainboard"),
        DecklistEntry(1, "Negate", section="sideboard", import_section="Sideboard"),
    ]
    assert unmatched == ["CSV row 4"]


def test_import_decklist_adds_resolved_and_unresolved_cards():
    project = DeckProject.new("Import Test")

    result = import_decklist(
        project,
        """
        2 Lightning Bolt (CLU) 141
        1 Unknown Card
        """,
        card_service=FakeCardService(),
    )

    assert len(result.added_card_ids) == 2
    assert result.updated_card_ids == []
    assert result.unresolved_entries == [DecklistEntry(1, "Unknown Card", import_section="Mainboard")]

    bolt = project.get_card(result.added_card_ids[0])
    unknown = project.get_card(result.added_card_ids[1])
    assert bolt.card_id != "sf-bolt"
    assert bolt.catalog_card_id == "sf-bolt"
    assert bolt.oracle_id == "oracle-sf-bolt"
    assert bolt.quantity == 2
    assert bolt.catalog_status == "resolved"
    assert bolt.local_image_path == "cache/bolt.png"
    assert bolt.image_asset_id == "asset-bolt"
    assert bolt.type_line == "Instant"
    assert bolt.mana_value == 1.0
    assert bolt.colors == ["R"]
    assert bolt.card_types == ["Instant"]
    assert unknown.name == "Unknown Card"
    assert unknown.quantity == 1
    assert unknown.catalog_status == "unresolved"


def test_import_decklist_merges_exact_existing_cards_and_preserves_organization():
    project = DeckProject.new()
    existing_id = project.add_card(
        "Lightning Bolt",
        quantity=1,
        set_code="clu",
        collector_number="141",
        card_id="editor-local-bolt",
    )
    project.add_tag(existing_id, "Burn")
    burn_id = project.create_category("Burn")
    project.assign_category(existing_id, burn_id)

    result = import_decklist(
        project,
        "2 Lightning Bolt (CLU) 141",
        card_service=FakeCardService(),
    )

    card = project.get_card(existing_id)
    assert result.added_card_ids == []
    assert result.updated_card_ids == [existing_id]
    assert card.quantity == 3
    assert card.tags == ["Burn"]
    assert card.primary_category == burn_id
    assert card.card_id == "editor-local-bolt"
    assert card.catalog_card_id == "sf-bolt"


def test_export_decklist_groups_sections_and_can_include_set_info():
    project = DeckProject.new()
    project.add_card("Atraxa, Praetors' Voice", quantity=1, set_code="2x2", collector_number="190", section="commander")
    project.add_card("Lightning Bolt", quantity=4, set_code="clu", collector_number="141", section="main")
    project.add_card("Negate", quantity=2, section="sideboard")
    project.add_card("Cut Card", quantity=1, section="excluded")

    assert export_decklist(project, include_set_info=True) == "\n".join(
        [
            "Commander:",
            "1 Atraxa, Praetors' Voice (2X2) 190",
            "",
            "Mainboard:",
            "4 Lightning Bolt (CLU) 141",
            "",
            "Sideboard:",
            "2 Negate",
        ]
    )
    assert "Cut Card" in export_decklist(project, include_excluded=True)
    assert export_decklist(project, include_sections=False) == "\n".join(
        [
            "1 Atraxa, Praetors' Voice",
            "4 Lightning Bolt",
            "2 Negate",
        ]
    )


def test_decklist_file_helpers_read_import_and_write(tmp_path):
    source = tmp_path / "source.txt"
    target = tmp_path / "exports" / "deck.txt"
    source.write_text("2 Lightning Bolt (CLU) 141", encoding="utf-8")
    project = DeckProject.new()

    result = import_decklist_file(project, source, card_service=FakeCardService())
    write_decklist_file(target, project, include_set_info=True)

    assert len(result.added_card_ids) == 1
    assert read_decklist_file(target) == "\n".join(
        [
            "Mainboard:",
            "2 Lightning Bolt (CLU) 141",
        ]
    )


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

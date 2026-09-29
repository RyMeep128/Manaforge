import json

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.decklists import parse_decklist
from mtg_core.sections import DeckSection


def test_section_values_keep_legacy_json_and_unknown_sections():
    document = DeckDocument()
    document.deck.entries = [
        DeckEntry("main", "Main"),
        DeckEntry("side", "Side", section=DeckSection.SIDEBOARD),
        DeckEntry(
            "custom",
            "Custom",
            section="extension-zone",
            extras={"extension_data": {"keep": True}},
        ),
    ]
    serialized = json.loads(json.dumps(document.to_dict()))
    assert [entry["section"] for entry in serialized["deck"]["entries"]] == [
        "mainboard",
        "sideboard",
        "extension-zone",
    ]
    restored = DeckDocument.from_dict(serialized)
    assert restored.to_dict() == serialized
    assert restored.deck.entries[0].section == DeckSection.MAINBOARD
    assert restored.deck.entries[2].extras == {"extension_data": {"keep": True}}


def test_import_aliases_keep_stable_section_values():
    entries, unmatched = parse_decklist(
        "Commander\n1 Leader\nSideboard\n1 Spare\nMaybeboard\n1 Maybe"
    )
    assert unmatched == []
    assert [entry.section for entry in entries] == [
        DeckSection.COMMANDER,
        DeckSection.SIDEBOARD,
        DeckSection.CONSIDERING,
    ]

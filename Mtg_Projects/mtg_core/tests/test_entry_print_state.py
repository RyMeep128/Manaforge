"""Typed print metadata retains the existing deck JSON representation."""
from copy import deepcopy

from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory, ENTRY_PRINT_FIELDS


def test_legacy_extras_and_json_load_into_typed_fields():
    metadata = dict(oversized=True, pre_cropped=False,
                    backside_pre_cropped=True, backside_asset_id="back",
                    extension={"keep": True})
    original = deepcopy(metadata)
    entry = DeckEntry("one", "Card", extras=metadata)
    assert metadata == original
    assert entry.extras == {"extension": {"keep": True}}
    for key in ENTRY_PRINT_FIELDS:
        assert getattr(entry, key) == metadata[key]
        assert entry.to_dict()[key] == metadata[key]
    restored = DeckEntry.from_dict(entry.to_dict())
    assert restored == entry


def test_absent_crop_flag_and_explicit_false_stay_distinct():
    absent = DeckEntry.from_dict({"entry_id": "one", "name": "Card"})
    assert absent.pre_cropped is None
    assert "pre_cropped" not in absent.to_dict()
    explicit = DeckEntry("two", "Card", pre_cropped=False,
                         extras={"pre_cropped": True})
    assert explicit.pre_cropped is False
    assert explicit.to_dict()["pre_cropped"] is False
    assert "pre_cropped" not in explicit.extras


def test_typed_edits_survive_history_and_override_legacy_print_flags():
    document = DeckDocument.from_legacy_proxy({"card_entries": [{
        "entry_id": "one", "front_name": "card.png", "count": 1,
        "oversized": True, "pre_cropped": True,
        "backside_pre_cropped": True, "backside_asset_id": "old-back",
    }]})
    before = document.to_dict()
    history = DeckHistory(document)

    def edit(value):
        entry = value.deck.entries[0]
        entry.oversized = False
        entry.pre_cropped = False
        entry.backside_pre_cropped = False
        entry.backside_asset_id = "new-back"

    assert history.execute(edit)
    after = document.to_dict()
    assert history.undo()
    assert document.to_dict() == before
    assert history.redo()
    assert document.to_dict() == after
    raw = document.apply_to_legacy_proxy()["card_entries"][0]
    assert raw["oversized"] is False
    assert raw["pre_cropped"] is False
    assert raw["backside_pre_cropped"] is False
    assert raw["backside_asset_id"] == "new-back"

"""Typed print metadata retains the existing deck JSON representation."""
from copy import deepcopy

from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory, ENTRY_PRINT_FIELDS
from mtg_core.artwork import HighResOverride


def test_artwork_legacy_loading_preserves_unknown_fields_without_aliasing():
    payload = {"identifier": "chosen", "dpi": 600, "future": {"items": [1]}}
    entry = DeckEntry("one", "Card", extras={"art_override": payload})
    assert isinstance(entry.art_override, HighResOverride)
    assert entry.art_override.identifier == "chosen"
    assert "art_override" not in entry.extras
    assert entry.to_dict()["art_override"] == payload
    restored = DeckEntry.from_dict(entry.to_dict())
    assert restored == entry
    entry.art_override.extras["future"]["items"].append(2)
    assert payload["future"]["items"] == [1]
    encoded = entry.to_dict()
    encoded["art_override"]["future"]["items"].append(3)
    assert entry.art_override.extras["future"]["items"] == [1, 2]


def test_empty_artwork_is_false_and_explicit_model_wins_over_legacy():
    entry = DeckEntry("one", "Card", art_override=HighResOverride(),
                      extras={"art_override": {"identifier": "old"}})
    assert not entry.art_override
    assert entry.to_dict()["art_override"] == {}
    assert DeckEntry.from_dict(entry.to_dict()).art_override is not None


def test_artwork_edit_round_trips_through_history_and_legacy_project():
    document = DeckDocument.from_legacy_proxy({
        "cards": {"card.png": 1},
        "high_res_front_overrides": {"card.png": {"identifier": "old"}},
    })
    history = DeckHistory(document)
    def edit(value):
        value.deck.entries[0].art_override.identifier = "new"
    assert history.execute(edit)
    assert document.apply_to_legacy_proxy()["high_res_front_overrides"]["card.png"]["identifier"] == "new"
    assert history.undo()
    assert document.deck.entries[0].art_override.identifier == "old"
    assert history.redo()
    assert document.deck.entries[0].art_override.identifier == "new"


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

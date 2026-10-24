from models import ProjectState


def test_zero_quantity_stays_zero_through_deck_and_proxy_roundtrip():
    state = ProjectState.from_dict({'card_entries': [
        {'entry_id': 'zero', 'front_name': 'zero.png', 'count': 0}]})
    restored = ProjectState.from_dict(state.to_persisted_dict())
    assert restored.get_card_count('zero.png') == 0
    assert restored.deck_document.deck.entries[0].quantity == 0


def test_legacy_project_gains_deck_document_without_losing_print_configuration():
    state = ProjectState.from_dict({
        "pagesize": "A4",
        "manual_layout": {"version": 1, "placements": []},
        "backside_offset": "2.25",
        "card_entries": [{
            "entry_id": "one", "front_name": "one.png", "count": 2,
            "oversized": True, "backside_name": "one-back.png",
            "metadata": {"name": "One", "set_code": "tst"},
        }],
    })

    persisted = state.to_persisted_dict()

    assert persisted["pagesize"] == "A4"
    assert persisted["backside_offset"] == "2.25"
    assert persisted["manual_layout"] == {"version": 1, "placements": []}
    assert persisted["card_entries"][0]["oversized"] is True
    assert persisted["deck_document"]["schema_version"] == 1
    assert persisted["deck_document"]["deck"]["entries"][0]["name"] == "One"
    assert persisted["deck_document"]["print_settings"] == {}


def test_deck_metadata_survives_proxy_quantity_and_art_updates():
    state = ProjectState.from_dict({
        "card_entries": [{"entry_id": "one", "front_name": "one.png", "count": 1,
                          "image_asset_id": "old", "metadata": {"name": "One"}}],
    })
    deck_entry = state.deck_document.deck.entries[0]
    deck_entry.category_ids = ["ramp"]
    deck_entry.tags = ["favorite"]
    deck_entry.notes = "Keep this printing"
    state.set_card_count("one.png", 3)
    state.set_card_image_refs("one.png", image_asset_id="new")

    restored = ProjectState.from_dict(state.to_persisted_dict())
    entry = restored.deck_document.deck.entries[0]
    assert entry.quantity == 3
    assert entry.image_asset_id == "new"
    assert entry.category_ids == ["ramp"]
    assert entry.tags == ["favorite"]
    assert entry.notes == "Keep this printing"

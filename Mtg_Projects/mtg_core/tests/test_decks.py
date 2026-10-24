from __future__ import annotations

import json

from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory, DeckStore


def _legacy_project():
    return {
        "project_version": 2,
        "pagesize": "A4",
        "manual_layout": {"version": 1, "placements": [{"copy_id": "bolt:1"}]},
        "backside_enabled": True,
        "backside_offset": "1.5",
        "high_res_front_overrides": {"bolt.png": {"identifier": "alt-1"}},
        "card_entries": [{
            "entry_id": "bolt-entry", "front_name": "bolt.png", "count": 4,
            "card_id": "printing-1", "oracle_id": "oracle-1", "image_asset_id": "img-1",
            "backside_name": "bolt-back.png", "backside_asset_id": "img-2",
            "backside_short_edge": True, "oversized": True, "do_not_print": True,
            "metadata": {"name": "Lightning Bolt", "set_code": "lea",
                         "collector_number": "161", "section": "Commander",
                         "custom": "preserved"},
        }],
    }


def test_legacy_proxy_migration_roundtrips_print_fields_and_deck_identity():
    legacy = _legacy_project()
    document = DeckDocument.from_legacy_proxy(legacy, name="Burn")
    assert document.deck.name == "Burn"
    assert document.deck.commander_entry_ids == ["bolt-entry"]
    entry = document.deck.entries[0]
    assert (entry.name, entry.quantity, entry.set_code) == ("Lightning Bolt", 4, "lea")
    assert entry.do_not_print is True

    restored = document.apply_to_legacy_proxy()
    assert restored["manual_layout"] == legacy["manual_layout"]
    assert restored["high_res_front_overrides"] == legacy["high_res_front_overrides"]
    assert restored["card_entries"][0]["backside_asset_id"] == "img-2"
    assert restored["card_entries"][0]["oversized"] is True
    assert restored["card_entries"][0]["metadata"]["custom"] == "preserved"


def test_deck_document_preserves_unknown_fields_for_forward_compatibility():
    document = DeckDocument.from_dict({
        "schema_version": 1, "future_document": {"enabled": True},
        "deck": {"name": "Future", "future_deck": 7,
                 "entries": [{"entry_id": "a", "name": "A", "future_entry": "yes"}]},
    })
    encoded = document.to_dict()
    assert encoded["future_document"] == {"enabled": True}
    assert encoded["deck"]["future_deck"] == 7
    assert encoded["deck"]["entries"][0]["future_entry"] == "yes"


def test_model_history_undoes_and_redoes_complete_edits():
    document = DeckDocument()
    history = DeckHistory(document)
    assert history.execute(lambda value: value.deck.entries.append(
        DeckEntry(entry_id="one", name="Sol Ring")))
    assert history.can_undo
    assert history.undo()
    assert document.deck.entries == []
    assert history.redo()
    assert document.deck.entries[0].name == "Sol Ring"


def test_deck_store_writes_atomically_and_keeps_bounded_recovery(tmp_path):
    path = tmp_path / "deck.manaforge.json"
    store = DeckStore(backup_limit=2)
    document = DeckDocument()
    store.save(path, document)
    for name in ("Second", "Third", "Fourth"):
        document.deck.name = name
        store.save(path, document)
    assert store.load(path).deck.name == "Fourth"
    assert len(store.recovery_paths(path)) == 2
    latest = json.loads(store.recovery_paths(path)[0].read_text(encoding="utf-8"))
    assert latest["deck"]["name"] == "Third"

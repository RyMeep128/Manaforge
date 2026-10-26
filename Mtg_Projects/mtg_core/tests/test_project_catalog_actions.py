import pytest

from mtg_core.decks import DeckDocument, DeckStore
from mtg_core.project_catalog import managed_deck_path, project_catalog, rename_deck


def test_rename_updates_saved_name_and_preserves_identity(tmp_path):
    store = DeckStore()
    document = DeckDocument()
    document.deck.name = 'Original'
    path = tmp_path / 'identity.manaforge.json'
    store.save(path, document)
    assert rename_deck(path, tmp_path, '  Renamed  ') == 'Renamed'
    loaded = store.load(path)
    assert loaded.deck.name == 'Renamed'
    assert loaded.deck.deck_id == document.deck.deck_id
    assert loaded.deck.extras['manual_name'] is True
    assert store.recovery_paths(path)
    assert project_catalog(tmp_path, tmp_path)[0][0]['name'] == 'Renamed'


def test_library_actions_reject_outside_files_and_empty_names(tmp_path):
    root = tmp_path / 'decks'
    root.mkdir()
    outside = tmp_path / 'outside.manaforge.json'
    DeckStore().save(outside, DeckDocument())
    with pytest.raises(ValueError):
        managed_deck_path(outside, root)
    inside = root / 'deck.manaforge.json'
    DeckStore().save(inside, DeckDocument())
    original = inside.read_bytes()
    with pytest.raises(ValueError):
        rename_deck(inside, root, '   ')
    assert inside.read_bytes() == original
    assert managed_deck_path(inside, root) == inside.resolve()

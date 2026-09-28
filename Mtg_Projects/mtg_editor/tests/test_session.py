"""Session regressions run without constructing Qt widgets."""
import json

import pytest

from mtg_editor.session import DeckSession


def test_history_preserves_preferences_and_print_link(tmp_path):
    session = DeckSession(tmp_path)
    document = session.document
    session.edit(lambda d: setattr(d.deck, 'name', 'Edited'))
    document.editor_preferences['view'] = 'Grid'
    document.extras['proxy_project_id'] = 'linked-project'
    assert session.undo()
    assert session.redo()
    assert session.document is document
    assert document.deck.name == 'Edited'
    assert document.editor_preferences['view'] == 'Grid'
    assert document.extras['proxy_project_id'] == 'linked-project'
    assert session.dirty


def test_save_new_open_and_failed_operations_preserve_state(tmp_path, monkeypatch):
    session = DeckSession(tmp_path)
    session.edit(lambda d: setattr(d.deck, 'name', 'Saved deck'))
    path = session.save()
    saved = session.saved
    session.new()
    assert session.path is None
    assert not session.history.can_undo
    session.open(path)
    assert session.document.to_dict() == saved
    assert not session.dirty
    session.edit(lambda d: setattr(d.deck, 'name', 'Unsaved edit'))
    document, history = session.document, session.history

    def fail(*args):
        raise OSError('disk unavailable')

    monkeypatch.setattr(session.store, 'save', fail)
    with pytest.raises(OSError):
        session.save()
    invalid = tmp_path / 'invalid.json'
    invalid.write_text('{', encoding='utf-8')
    with pytest.raises(ValueError):
        session.open(invalid)
    assert session.document is document
    assert session.history is history
    assert session.path == path
    assert session.saved == saved
    assert session.dirty


def test_proxy_import_saves_separately_and_preserves_extensions(tmp_path):
    session = DeckSession(tmp_path)
    session.document.extras['custom_extension'] = {'value': 42}
    raw = {'cards': {}, 'deck_document': session.document.to_dict()}
    source = tmp_path / 'proxy.json'
    contents = json.dumps(raw)
    source.write_text(contents, encoding='utf-8')
    session.open(source)
    assert session.path is None
    assert session.document.extras['custom_extension'] == {'value': 42}
    assert session.document.print_settings['proxy_project'] == raw
    assert session.save() != source
    assert source.read_text(encoding='utf-8') == contents


def test_recovery_creates_unlinked_copy_without_overwriting_original(tmp_path):
    session = DeckSession(tmp_path)
    session.document.deck.name = 'Original'
    session.document.extras['proxy_project_id'] = 'linked-project'
    path = session.save()
    original_id = session.document.deck.deck_id
    session.edit(lambda d: setattr(d.deck, 'name', 'Updated'))
    session.save()
    original_contents = path.read_bytes()
    session.recover(session.recovery_paths()[0])
    assert session.document.deck.name == 'Original (Recovered)'
    assert session.document.deck.deck_id != original_id
    assert 'proxy_project_id' not in session.document.extras
    assert session.path is None
    assert not session.history.can_undo
    assert session.save() != path
    assert path.read_bytes() == original_contents

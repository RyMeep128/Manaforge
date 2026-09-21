import json
import pytest
from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry, DeckCategory, DeckHistory
from mtg_editor.category_templates import COMMANDER, CategoryTemplates, TemplateStore, apply_template


def test_apply_preserves_assignments_and_supports_undo_roundtrip():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('custom', 'My strategy', 4), DeckCategory('ramp', 'rAMP', 7)]
    doc.deck.entries = [DeckEntry('a', 'Card', quantity=3, category_ids=['ramp'], tags=['Keep'],
                                  extras={'auto_categories': {'manual': True}})]
    before = doc.to_dict()
    history = DeckHistory(doc)
    history.execute(lambda d: apply_template(d, COMMANDER))
    assert len(doc.deck.categories) == 9
    assert doc.deck.entries[0].to_dict() == before['deck']['entries'][0]
    assert doc.deck.categories[0].sort_order == 4
    assert doc.deck.categories[1].category_id == 'ramp'
    applied = doc.to_dict()
    assert not history.execute(lambda d: apply_template(d, COMMANDER))
    assert DeckDocument.from_dict(applied).to_dict() == applied
    history.undo()
    assert doc.to_dict() == before
    history.redo()
    assert doc.to_dict() == applied


def test_saved_template_reusable_across_decks(tmp_path):
    path = tmp_path / 'category_templates.json'
    store = TemplateStore(path)
    store.save('My deck', [' Ramp ', 'ramp', 'Custom role', ''])
    assert TemplateStore(path).load() == {'My deck': ['Ramp', 'Custom role']}
    store.save('MY DECK', ['Tokens', 'Sacrifice'])
    doc = DeckDocument()
    apply_template(doc, store.load()['My deck'])
    assert [c.name for c in doc.deck.categories] == ['Tokens', 'Sacrifice']
    assert [c.sort_order for c in doc.deck.categories] == [0, 1]
    assert not list(tmp_path.glob('*.tmp'))


def test_bad_template_file_is_not_overwritten(tmp_path):
    path = tmp_path / 'category_templates.json'
    path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        TemplateStore(path).save('New', ['Ramp'])
    assert path.read_text(encoding='utf-8') == '{broken'
    path.write_text(json.dumps({'version': 2, 'templates': {}}), encoding='utf-8')
    with pytest.raises(ValueError, match='Unsupported'):
        TemplateStore(path).load()


def test_dialog_save_preview_cancel_and_window_apply(tmp_path, monkeypatch):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.categories = [DeckCategory('custom', 'Custom role')]
    before = window.document.to_dict()
    store = TemplateStore(tmp_path / 'category_templates.json')
    dialog = CategoryTemplates(window.document, store, window)
    assert dialog.selected_names() == list(COMMANDER)
    monkeypatch.setattr(W.QInputDialog, 'getText', lambda *a, **kw: ('My layout', True))
    dialog.save_current()
    assert dialog.selected_names() == ['Custom role']
    dialog.reject()
    assert window.document.to_dict() == before
    monkeypatch.setattr(CategoryTemplates, 'exec', lambda self: W.QDialog.DialogCode.Accepted)
    window.category_templates()
    assert len(window.document.deck.categories) == 9
    assert window.show_empty_categories.isChecked()
    assert window.grid.grouping == 'Category'
    window.undo()
    assert [c.name for c in window.document.deck.categories] == ['Custom role']
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.categorization import apply_categories, classify
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.role_editor import RoleEditor


def test_mixed_memberships_cancel_and_explicit_changes():
    app = W.QApplication.instance() or W.QApplication([])
    document = DeckDocument()
    document.deck.entries = [DeckEntry('a', 'One'), DeckEntry('b', 'Two')]
    apply_categories(document, {'a': classify({}, ['ramp', 'draw']),
                                'b': classify({}, ['draw'])})
    before = document.to_dict()
    dialog = RoleEditor(document, {'a', 'b'})
    assert dialog.items['auto:ramp'].checkState() == C.Qt.CheckState.PartiallyChecked
    assert dialog.items['auto:draw'].checkState() == C.Qt.CheckState.Checked
    assert dialog.choices() == {}
    dialog.items['auto:ramp'].setCheckState(C.Qt.CheckState.Checked)
    dialog.items['auto:draw'].setCheckState(C.Qt.CheckState.Unchecked)
    assert dialog.choices() == {'auto:ramp': True, 'auto:draw': False}
    dialog.items['auto:ramp'].setCheckState(C.Qt.CheckState.PartiallyChecked)
    assert dialog.choices() == {'auto:draw': False}
    dialog.reject()
    assert document.to_dict() == before
    dialog.deleteLater()
    app.processEvents()


def test_editor_accept_undo_redo_and_save(tmp_path, monkeypatch):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'Card')]
    apply_categories(window.document, {'a': classify({}, ['ramp', 'draw'])})
    window.changed()
    before = window.document.to_dict()

    def accept(dialog):
        dialog.items['auto:draw'].setCheckState(C.Qt.CheckState.Unchecked)
        return W.QDialog.DialogCode.Accepted

    monkeypatch.setattr(RoleEditor, 'exec', accept)
    window.edit_roles({'a'})
    assert window.document.deck.entries[0].category_ids == ['auto:ramp']
    edited = window.document.to_dict()
    window.undo()
    assert window.document.to_dict() == before
    window.redo()
    assert window.document.to_dict() == edited
    assert window.save()
    path = window.path
    window.new()
    window.open_path(path)
    assert window.document.deck.entries[0].category_ids == ['auto:ramp']
    assert window.document.deck.entries[0].extras['auto_categories']['manual']
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

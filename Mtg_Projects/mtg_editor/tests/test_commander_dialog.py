from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.commander_dialog import CommanderDialog


def test_preview_does_not_mutate_and_duplicate_selection_disabled():
    app = W.QApplication.instance() or W.QApplication([])
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card A'), DeckEntry('b', 'Card B')]
    before = doc.to_dict()
    dialog = CommanderDialog(doc, {})
    dialog.selectors[0].setCurrentIndex(1)
    assert dialog.apply_button.isEnabled()
    assert 'unsaved selection' in dialog.summary.text()
    assert 'unknown' in dialog.table.item(1, 1).text().lower()
    dialog.selectors[1].setCurrentIndex(1)
    assert not dialog.apply_button.isEnabled()
    dialog.reject()
    assert doc.to_dict() == before
    app.processEvents()


def test_window_commander_selection_is_undoable(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=SimpleNamespace(database=SimpleNamespace(legality_data=lambda ids: {})), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'Card')]
    window.run_task = lambda work, callback: callback(work())
    def accept(dialog):
        dialog.selectors[0].setCurrentIndex(1)
        return W.QDialog.DialogCode.Accepted
    monkeypatch.setattr(CommanderDialog, 'exec', accept)
    window.commander_checks()
    assert window.document.deck.commander_entry_ids == ['a']
    window.undo()
    assert window.document.deck.entries[0].section == 'mainboard'
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

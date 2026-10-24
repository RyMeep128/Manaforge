from PyQt6 import QtWidgets as W

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.playtest import PlaytestDialog


def test_dialog_mulligan_keep_draw_and_empty_settings():
    app = W.QApplication.instance() or W.QApplication([])
    document = DeckDocument()
    document.deck.entries = [DeckEntry('a', 'Card', quantity=10)]
    before = document.to_dict()
    dialog = PlaytestDialog(document)
    assert dialog.hand.count() == 7 and not dialog.draw_button.isEnabled()
    dialog.mulligan_button.click()
    dialog.keep_button.click()
    assert 'exactly 1' in dialog.message.text() and not dialog.sampler.kept
    dialog.hand.item(0).setSelected(True)
    dialog.keep_button.click()
    assert dialog.hand.count() == 6 and dialog.draw_button.isEnabled()
    dialog.draw_button.click()
    assert dialog.hand.count() == 7
    dialog.sections['mainboard'].setChecked(False)
    assert dialog.hand.count() == 0 and not dialog.keep_button.isEnabled()
    assert 'No cards' in dialog.message.text()
    dialog.notes.setPlainText('Discard these notes')
    dialog.reject()
    assert document.to_dict() == before
    dialog.deleteLater()
    app.processEvents()


def test_notes_settings_undo_and_save_roundtrip(tmp_path, monkeypatch):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'Card', quantity=10)]
    window.changed()
    before = window.document.to_dict()

    def accept(dialog):
        dialog.notes.setPlainText('Need more lands.\nTest another ten hands.')
        dialog.free.setChecked(True)
        dialog.sections['sideboard'].setChecked(True)
        return W.QDialog.DialogCode.Accepted

    monkeypatch.setattr(PlaytestDialog, 'exec', accept)
    window.playtest()
    edited = window.document.to_dict()
    assert edited['deck']['entries'] == before['deck']['entries']
    assert window.document.deck.playtest_notes.startswith('Need more lands.')
    window.undo()
    assert window.document.deck.to_dict() == before['deck']
    assert window.document.editor_preferences == edited['editor_preferences']
    window.redo()
    assert window.document.to_dict() == edited
    assert window.save()
    path = window.path
    window.new()
    window.open_path(path)
    dialog = PlaytestDialog(window.document)
    assert dialog.notes.toPlainText().startswith('Need more lands.')
    assert dialog.free.isChecked() and dialog.sections['sideboard'].isChecked()
    dialog.reject()
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

from PyQt6.QtWidgets import QApplication

from mtg_core.decks import DeckDocument
from mtg_editor.guidance import GuidanceDialog


def test_guidance_dialog_changes_are_drafts_until_saved():
    app = QApplication.instance() or QApplication([])
    document = DeckDocument()
    before = document.to_dict()
    dialog = GuidanceDialog(document, {})
    dialog.targets["lands"].setValue(31)
    dialog.suggestions.setCurrentRow(0)
    dialog.dismiss()
    assert dialog.settings.dismissed
    dialog.restore()
    assert not dialog.settings.dismissed
    dialog.reject()
    assert document.to_dict() == before
    assert dialog.settings.to_dict()["targets"]["lands"] == 31
    dialog.deleteLater()
    app.processEvents()

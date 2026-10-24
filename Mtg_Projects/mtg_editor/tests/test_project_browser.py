import json
import time
from PyQt6 import QtWidgets as W, QtTest
from mtg_core.decks import DeckDocument
from mtg_editor.project_browser import ProjectBrowser


def test_library_load_filter_open_and_new(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    doc = DeckDocument()
    doc.deck.name = 'My deck'
    path = tmp_path / 'deck.manaforge.json'
    path.write_text(json.dumps(doc.to_dict()))
    dialog = ProjectBrowser(tmp_path, tmp_path)
    deadline = time.monotonic() + 3
    while dialog.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        QtTest.QTest.qWait(5)
    assert dialog.worker is None and dialog.table.rowCount() == 1
    dialog.filter.setText('missing')
    assert dialog.table.isRowHidden(0)
    dialog.filter.clear()
    dialog.table.selectRow(0)
    dialog.open_selected()
    assert dialog.path == path.resolve()
    dialog.path = None
    dialog.create()
    assert dialog.new_deck and dialog.path is None
    app.processEvents()

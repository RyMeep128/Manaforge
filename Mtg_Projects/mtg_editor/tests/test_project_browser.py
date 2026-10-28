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


def test_delete_queues_library_removal_only_after_successful_trash(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import uuid
    from mtg_core.decks import DeckStore
    from mtg_core.library.client import LibraryConnections
    from mtg_core.library.publishing import PublicationJournal
    from mtg_editor.project_browser import ProjectDashboard
    from PyQt6 import QtCore as C
    app = W.QApplication.instance() or W.QApplication([])
    root = tmp_path / 'settings'
    monkeypatch.setattr('mtg_core.paths.data_root', lambda: root)
    journal = PublicationJournal(LibraryConnections(root))
    document = DeckDocument()
    path = tmp_path / 'master.manaforge.json'
    DeckStore().save(path, document)
    client = SimpleNamespace(server_id=str(uuid.uuid4()), account_id=str(uuid.uuid4()))
    client.publish_operation = lambda operation: {'deck_id': str(uuid.uuid4()), 'revision': 1}
    journal.send(client, client.server_id, document.deck.deck_id, deck=document.deck.to_dict(), color_identity=[])
    events = []
    browser = SimpleNamespace(roots=(tmp_path, tmp_path),
        deckDeleted=SimpleNamespace(emit=lambda path: events.append('deleted')),
        libraryDeletionQueued=SimpleNamespace(emit=lambda: events.append('queued')),
        refresh=lambda: None)
    monkeypatch.setattr(W.QMessageBox, 'question', lambda *args: W.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(W.QMessageBox, 'warning', lambda *args: None)
    monkeypatch.setattr(C.QFile, 'moveToTrash', lambda filename: False)
    ProjectDashboard.delete_selected_deck(browser, {'name': 'Master', 'path': str(path)})
    assert path.exists() and not journal.queued_deletions() and not events
    def trash(filename):
        from pathlib import Path
        Path(filename).unlink()
        return True
    monkeypatch.setattr(C.QFile, 'moveToTrash', trash)
    ProjectDashboard.delete_selected_deck(browser, {'name': 'Master', 'path': str(path)})
    assert not path.exists()
    assert len(journal.queued_deletions()) == 1
    assert events == ['deleted', 'queued']
    app.processEvents()

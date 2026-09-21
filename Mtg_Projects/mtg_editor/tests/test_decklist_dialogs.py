import time
from threading import Event
from types import SimpleNamespace
from PyQt6 import QtWidgets as W, QtTest
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.decklist_dialogs import ImportDecklist, ExportDecklist


def wait_for_worker(dialog, app):
    deadline = time.monotonic() + 3
    while dialog.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        QtTest.QTest.qWait(5)
    assert dialog.worker is None


def test_import_preview_invalidation_and_cancel(monkeypatch):
    from mtg_editor import decklist_dialogs
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(decklist_dialogs, 'resolve_decklist', lambda *a, **kw:
                        ([DeckEntry('a', 'Card', quantity=3)], {}, ['1 Missing: unavailable']))
    dialog = ImportDecklist(object())
    dialog.source.setPlainText('3 Card\n1 Missing')
    dialog.resolve()
    wait_for_worker(dialog, app)
    assert dialog.apply_button.isEnabled()
    assert dialog.preview.rowCount() == 1
    assert 'Missing' in dialog.messages.toPlainText()
    dialog.source.setPlainText('4 Card')
    assert not dialog.apply_button.isEnabled() and dialog.result is None
    dialog.reject()
    assert dialog.result is None


def test_cancel_waits_for_worker_without_applying(monkeypatch):
    from mtg_editor import decklist_dialogs
    app = W.QApplication.instance() or W.QApplication([])
    release = Event()
    def resolve(*args, **kwargs):
        release.wait(2)
        return ([DeckEntry('a', 'Card')], {}, [])
    monkeypatch.setattr(decklist_dialogs, 'resolve_decklist', resolve)
    dialog = ImportDecklist(object())
    dialog.source.setPlainText('1 Card')
    dialog.resolve()
    dialog.reject()
    assert dialog.worker is not None
    release.set()
    wait_for_worker(dialog, app)
    assert dialog.result is None and not dialog.apply_button.isEnabled()


def test_editor_import_is_one_undo_and_export_options(tmp_path, monkeypatch):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    def accept(dialog):
        dialog.result = ([DeckEntry('a', 'Card', quantity=2, set_code='abc', collector_number='1')], {}, [])
        return W.QDialog.DialogCode.Accepted
    monkeypatch.setattr(ImportDecklist, 'exec', accept)
    window.import_decklist()
    assert window.document.deck.entries[0].quantity == 2
    dialog = ExportDecklist(window.document)
    assert '(abc) 1' in dialog.preview.toPlainText()
    dialog.printings.setChecked(False)
    dialog.sections.setChecked(False)
    assert dialog.preview.toPlainText() == '2 Card\n'
    window.undo()
    assert not window.document.deck.entries
    window.redo()
    assert window.document.deck.entries[0].quantity == 2
    window.saved = window.document.to_dict()
    window.close()
    dialog.close()
    app.processEvents()


def test_public_url_import_preview_and_source_failure(monkeypatch):
    from mtg_editor import decklist_dialogs
    from mtg_core.decklists import DecklistEntry
    app = W.QApplication.instance() or W.QApplication([])
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return [DecklistEntry(1, 'Commander', section='commander')]
    monkeypatch.setattr(decklist_dialogs, 'fetch_public_deck', fetch)
    monkeypatch.setattr(decklist_dialogs, 'resolve_entries', lambda entries, *a, **kw:
        ([DeckEntry('a', entries[0].name, section=entries[0].section)], {}, []))
    dialog = ImportDecklist(object())
    dialog.input_mode.setCurrentIndex(1)
    dialog.url.setText('https://moxfield.com/decks/example')
    dialog.resolve()
    wait_for_worker(dialog, app)
    assert calls == ['https://moxfield.com/decks/example']
    assert dialog.apply_button.isEnabled()
    assert dialog.preview.item(0, 2).text() == 'commander'
    def unavailable(*args, **kwargs):
        raise ValueError('Deck is private or unavailable')
    monkeypatch.setattr(decklist_dialogs, 'fetch_public_deck', unavailable)
    dialog.url.setText('https://moxfield.com/decks/private')
    dialog.resolve()
    wait_for_worker(dialog, app)
    assert not dialog.apply_button.isEnabled() and dialog.result is None
    assert 'private' in dialog.messages.toPlainText()
    dialog.reject()

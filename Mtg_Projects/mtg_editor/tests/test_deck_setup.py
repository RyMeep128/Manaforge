"""Setup transaction and persistence regressions; exercised in CI."""
from copy import deepcopy

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.deck_setup import DeckSetupDialog
from mtg_editor.commander_discovery import DiscoveryController
from mtg_editor.gui import EditorWindow


def test_setup_cancel_and_commanderless_themes_roundtrip(tmp_path, monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(DiscoveryController, 'change_query', lambda *args: None)
    editor = EditorWindow(service=object(), root=tmp_path)
    document = DeckDocument()
    before = deepcopy(document.to_dict())
    dialog = DeckSetupDialog(editor, document, creating=True)
    dialog.format.setCurrentText('Modern')
    assert not dialog.tabs.isTabVisible(0)
    for i in range(dialog.themes.list.count()):
        item = dialog.themes.list.item(i)
        if item.data(C.Qt.ItemDataRole.UserRole) in ('artifacts', 'tokens'):
            item.setCheckState(C.Qt.CheckState.Checked)
    assert document.to_dict() == before
    dialog.apply_to(document)
    restored = DeckDocument.from_dict(document.to_dict())
    assert restored.deck.format == 'Modern'
    assert restored.deck.commander_entry_ids == []
    assert {t['slug'] for t in restored.editor_preferences['manual_themes']} == {'artifacts', 'tokens'}
    dialog.reject()
    editor.close()
    app.processEvents()


def test_settings_preserve_cards_manual_categories_and_unavailable_library(tmp_path, monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(DiscoveryController, 'change_query', lambda *args: None)
    editor = EditorWindow(service=object(), root=tmp_path)
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Favorite card', category_ids=['manual'],
                                  extras={'auto_categories': {'manual': True}})]
    association = {'id': 'offline', 'name': 'Friends', 'server_id': 'server'}
    doc.deck.extras['library_association'] = association
    before = deepcopy(doc.deck.entries[0].to_dict())
    dialog = DeckSetupDialog(editor, doc)
    assert dialog.library.currentData() == association
    dialog.apply_to(doc)
    assert doc.deck.entries[0].to_dict() == before
    assert doc.deck.extras['library_association'] == association
    dialog.reject()
    editor.close()
    app.processEvents()


def test_enter_search_never_creates_deck_and_steps_hide_later_choices(tmp_path, monkeypatch):
    from PyQt6 import QtTest
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(DiscoveryController, 'change_query', lambda *args: None)
    editor = EditorWindow(service=object(), root=tmp_path)
    dialog = DeckSetupDialog(editor, DeckDocument(), creating=True)
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    assert dialog.tabs.isHidden()
    dialog.next_step()
    assert dialog.stage == 1
    assert dialog.setup_pages.currentWidget() is dialog.commander_page
    dialog.show()
    dialog.search.setFocus()
    QtTest.QTest.keyClick(dialog.search, C.Qt.Key.Key_Return)
    assert not accepted and dialog.stage == 1
    dialog.next_step()
    assert dialog.stage == 2
    assert dialog.setup_pages.currentIndex() == 2
    dialog.reject()
    editor.close()
    app.processEvents()


def test_precon_keeps_commander_and_skips_commander_search(tmp_path, monkeypatch):
    from mtg_editor import precon_browser
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(DiscoveryController, 'change_query', lambda *args: None)
    editor = EditorWindow(service=object(), root=tmp_path)
    entry = DeckEntry('cmd', 'Original commander', section='commander', oracle_id='original', card_id='precon-art')

    class Browser:
        def __init__(self, *args):
            self.resolve_button = W.QPushButton()
            self.deck_name = W.QLineEdit('Test precon')
            self.record = dict(id='precon', name='Test precon', format='Commander',
                source_url='https://example.invalid/precon', release_date='2026-01-01',
                entries=[dict(count=1, name=entry.name, section='commander', set_code=None, collector_number=None)])
            self.result = ([entry], {}, [])
            self.cover_asset_id = None

        def exec(self):
            return W.QDialog.DialogCode.Accepted

    monkeypatch.setattr(precon_browser, 'PreconBrowser', Browser)
    dialog = DeckSetupDialog(editor, DeckDocument(), creating=True)
    dialog.start.setCurrentIndex(2)
    dialog.next_step()
    assert dialog.stage == 2
    assert [e.entry_id for e in dialog.selected] == ['cmd']
    result = deepcopy(dialog.draft)
    dialog.apply_to(result)
    assert result.deck.commander_entry_ids == ['cmd']
    assert len(result.deck.entries) == 1
    assert 'Original commander' in dialog.precon_text.text()
    dialog.show()
    app.processEvents()
    assert dialog.themes.isVisibleTo(dialog)
    assert dialog.themes.list.isVisibleTo(dialog)
    assert dialog.library.isVisibleTo(dialog)
    assert dialog.precon_summary.height() == 180
    assert dialog.themes.list.height() >= 80
    assert dialog.library.geometry().height() > 0
    import os
    from pathlib import Path
    from PyQt6 import QtGui as G
    output = os.environ.get('MANAFORGE_UI_SCREENSHOTS')
    if output:
        from mtg_ui.theme import application_stylesheet
        dialog.setStyleSheet(application_stylesheet())
        pixmap = G.QPixmap(100, 140)
        pixmap.fill(G.QColor('#365c68'))
        editor.thumbnails.cache[('precon-art', None)] = pixmap
        dialog.show()
        app.processEvents()
        destination = Path(output)
        destination.mkdir(parents=True, exist_ok=True)
        assert dialog.grab().save(str(destination / 'deck-setup-precon-finish.png'))
    dialog.previous_step()
    assert dialog.stage == 0
    dialog.reject()
    editor.close()
    app.processEvents()


def test_setup_visual_review_artifacts(tmp_path, monkeypatch):
    import os
    from pathlib import Path
    from mtg_ui.theme import application_stylesheet
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(DiscoveryController, 'change_query', lambda *args: None)
    editor = EditorWindow(service=object(), root=tmp_path)
    dialog = DeckSetupDialog(editor, DeckDocument(), creating=True)
    dialog.setStyleSheet(application_stylesheet())
    output = os.environ.get('MANAFORGE_UI_SCREENSHOTS')
    dialog.show()
    for stage in range(3):
        dialog.stage = stage
        dialog.update_stage()
        app.processEvents()
        if output:
            destination = Path(output)
            destination.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(destination / f'deck-setup-step-{stage + 1}.png'))
        if stage == 0:
            assert dialog.height() < 500
    dialog.reject()
    editor.close()
    app.processEvents()


def test_starting_and_precon_finish_do_not_start_commander_discovery(tmp_path, monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    searches = []
    monkeypatch.setattr(DiscoveryController, 'change_query', lambda *args: searches.append(args))
    editor = EditorWindow(service=object(), root=tmp_path)
    dialog = DeckSetupDialog(editor, DeckDocument(), creating=True)
    assert not searches
    assert dialog.themes.list.count() > 0
    dialog.start.setCurrentIndex(2)
    dialog.stage = 2
    dialog.update_stage()
    dialog.format_changed()
    assert not searches
    assert not dialog.controller.timer.isActive()
    dialog.stage = 1
    dialog.update_stage()
    assert searches
    dialog.reject()
    editor.close()
    app.processEvents()


def test_successful_saves_and_autosaves_queue_master_updates(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    calls = []
    editor.library_sync_handler = lambda deck, color: calls.append((deck['name'], color))
    editor.replace_document(DeckDocument())
    assert editor.save()
    assert len(calls) == 1
    editor.name.setText('Autosaved edit')
    editor.autosave.timeout.emit()
    assert calls[-1][0] == 'Autosaved edit'
    count = len(calls)
    assert editor.save(sync_library=False)
    assert len(calls) == count
    editor.library_sync_handler = None
    editor.close()
    app.processEvents()

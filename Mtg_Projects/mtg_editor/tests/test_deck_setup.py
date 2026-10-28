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
    assert dialog.tabs.isTabVisible(0)
    assert not dialog.tabs.isTabVisible(1)
    assert not dialog.tabs.isTabVisible(2)
    dialog.show()
    dialog.search.setFocus()
    QtTest.QTest.keyClick(dialog.search, C.Qt.Key.Key_Return)
    assert not accepted and dialog.stage == 1
    dialog.next_step()
    assert dialog.stage == 2
    assert not dialog.tabs.isTabVisible(0)
    assert dialog.tabs.isTabVisible(1) and dialog.tabs.isTabVisible(2)
    dialog.reject()
    editor.close()
    app.processEvents()

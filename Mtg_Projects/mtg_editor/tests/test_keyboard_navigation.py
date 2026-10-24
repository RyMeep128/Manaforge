"""Regression coverage for layered Escape and text-field shortcut isolation."""
from PyQt6 import QtCore as C, QtWidgets as W, QtTest
from mtg_editor.gui import EditorWindow
from mtg_core.decks import DeckEntry


def editor(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('existing', 'Existing card', quantity=1)]
    window.show()
    app.processEvents()
    return app, window


def test_empty_deck_search_defaults_to_ideas_even_after_another_tab(tmp_path):
    app, window = editor(tmp_path)
    window.document.deck.entries.clear()
    workspace = window.add_cards_workspace
    workspace.full_index = 2
    window.open_search()
    assert workspace.expanded
    assert window.add_card_tabs.currentWidget() is workspace.discovery
    window.add_card_tabs.setCurrentWidget(workspace.card_search)
    workspace.back()
    workspace.open()
    assert window.add_card_tabs.currentWidget() is workspace.discovery
    window.hide()
    window.deleteLater()
    app.processEvents()


def test_escape_closes_preview_then_quick_add_without_changing_deck(tmp_path):
    app, window = editor(tmp_path)
    before = window.document.to_dict()['deck']
    window.open_search()
    window.results.preview.show()
    QtTest.QTest.keyClick(window.query, C.Qt.Key.Key_Escape)
    assert not window.results.preview.isVisible()
    assert not window.search_panel.isHidden()
    QtTest.QTest.keyClick(window.query, C.Qt.Key.Key_Escape)
    assert window.search_panel.isHidden()
    QtTest.QTest.keyClick(window, C.Qt.Key.Key_Escape)
    assert window.isVisible()
    assert window.document.to_dict()['deck'] == before
    window.hide()
    window.deleteLater()
    app.processEvents()


def test_escape_from_discovery_returns_directly_to_deck(tmp_path):
    app, window = editor(tmp_path)
    window.open_search()
    window.open_add_cards()
    QtTest.QTest.keyClick(window, C.Qt.Key.Key_Escape)
    assert not window.add_cards_workspace.expanded
    assert window.search_panel.isHidden()
    assert window.workspace_stack.currentWidget() is window.splitter
    window.hide()
    window.deleteLater()
    app.processEvents()


def test_text_selection_and_dialog_escape_stay_in_their_context(tmp_path):
    app, window = editor(tmp_path)
    window.open_search()
    window.query.setText('lightning bolt')
    QtTest.QTest.keyClick(window.query, C.Qt.Key.Key_A, C.Qt.KeyboardModifier.ControlModifier)
    assert window.query.selectedText() == 'lightning bolt'
    dialog = W.QDialog(window)
    dialog.setModal(True)
    dialog.show()
    QtTest.QTest.keyClick(dialog, C.Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert not window.search_panel.isHidden()
    assert window.query.text() == 'lightning bolt'
    window.hide()
    window.deleteLater()
    app.processEvents()

from types import SimpleNamespace

from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckEntry
from mtg_editor.gui import EditorWindow


def test_plain_search_builds_local_query_and_updates_membership(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    panel = editor.add_cards_workspace.card_search
    panel.name.setText('Angel of Destiny')
    panel.color.setCurrentIndex(1)
    panel.kind.setCurrentText('Creature')
    panel.mana.setValue(5)
    assert panel.query() == 'name:"Angel of Destiny" c:w t:creature mv=5'
    panel.controller.cancel()
    result = SimpleNamespace(name='Angel of Destiny', card_id='angel', oracle_id='oracle',
                             set_code='set', collector_number='1', payload={})
    panel.completed(panel.query(), [result], '')
    panel.add('angel')
    assert panel.canvas.document.deck.entries[0].quantity == 1
    assert 'angel' in panel.canvas.in_deck_ids
    panel.membership.setCurrentIndex(1)
    assert not panel.canvas.document.deck.entries
    editor.undo()
    assert panel.canvas.document.deck.entries[0].quantity == 0
    assert panel.name.text() == 'Angel of Destiny'
    editor.close()
    app.processEvents()


def test_workspace_keeps_four_tabs_and_addition_state(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    workspace = editor.add_cards_workspace
    workspace.open()
    tabs = editor.add_card_tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        'Card Search', 'Syntax Search', 'Recommendations', 'Commanders']
    panel = workspace.card_search
    panel.rows = [DeckEntry('forest', 'Forest', card_id='forest')]
    panel.update_quantities()
    panel.add('forest')
    assert workspace.expanded and tabs.currentWidget() is panel
    assert panel.rows[0].quantity == 1
    workspace.back()
    workspace.open()
    assert tabs.currentWidget() is panel
    assert panel.rows[0].quantity == 1
    editor.close()
    app.processEvents()

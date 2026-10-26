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
    assert not panel.canvas.document.deck.entries
    panel.membership.setCurrentIndex(0)
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
        'Card Search', 'Syntax Search', 'Recommendations', 'Discover Deck Ideas']
    panel = workspace.card_search
    tabs.setCurrentWidget(panel)
    panel.rows = [DeckEntry('forest', 'Forest', card_id='forest')]
    panel.update_quantities()
    panel.add('forest')
    assert workspace.expanded and tabs.currentWidget() is panel
    assert not panel.canvas.document.deck.entries
    workspace.back()
    workspace.open()
    assert tabs.currentWidget() is panel
    assert not panel.canvas.document.deck.entries
    editor.close()
    app.processEvents()


def test_discovery_defaults_exclude_alternate_printings_in_other_sections(tmp_path):
    from mtg_core.sections import DeckSection
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    assert editor.syntax_membership.currentIndex() == 1
    assert editor.add_cards_workspace.card_search.membership.currentIndex() == 1
    assert editor.recommendation_panel.membership.currentIndex() == 1
    editor.document.deck.entries = [DeckEntry('owned', 'Forest', oracle_id='forest', section=DeckSection.CONSIDERING)]
    result = SimpleNamespace(name='Forest', card_id='alternate', oracle_id='forest',
                             set_code='set', collector_number='1', payload={})
    editor.show_results('', [result], '')
    assert not editor.search_document.deck.entries
    editor.syntax_membership.setCurrentIndex(0)
    assert editor.search_document.deck.entries[0].card_id == 'alternate'
    editor.syntax_membership.setCurrentIndex(1)
    editor.document.deck.entries.clear()
    editor.changed()
    assert editor.search_document.deck.entries[0].card_id == 'alternate'
    editor.close()
    app.processEvents()


def test_both_search_views_keep_the_same_facts_and_category_evidence(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    editor = EditorWindow(service=object(), root=tmp_path)
    panel = editor.add_cards_workspace.card_search
    panel.membership.setCurrentIndex(0)
    editor.syntax_membership.setCurrentIndex(0)
    payload = {'mana_cost': '{U}', 'color_identity': ['U'], 'legalities': {'commander': 'legal'},
               '_category_evidence': [{'name': 'Draw', 'reason': 'Evidence'}]}
    result = SimpleNamespace(card_id='print', name='Example', oracle_id='oracle',
                             set_code='set', collector_number='1', payload=payload)
    panel.completed(panel.query(), [result], '')
    editor.show_results(editor.effective_search_query(), [result], '')
    plain = panel.rows[0]
    syntax = editor.syntax_all_entries[0]
    assert plain.extras == syntax.extras
    assert plain is not syntax
    plain.extras['facts']['color_identity'].append('R')
    assert syntax.extras['facts']['color_identity'] == ['U']
    assert payload['color_identity'] == ['U']
    # Later pages retain the existing candidate instead of discarding UI state.
    panel.completed(panel.query(), [result], '')
    assert panel.rows[0] is plain
    editor.saved = editor.document.to_dict()
    editor.close()
    app.processEvents()

from types import SimpleNamespace
from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.insights import InsightsDialog


def test_scope_and_unknown_counts():
    app = W.QApplication.instance() or W.QApplication([])
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Unknown', quantity=3), DeckEntry('b', 'Side', section='sideboard')]
    dialog = InsightsDialog(doc, {})
    assert dialog.result['total'] == 3
    assert 'missing type' in dialog.warning.text()
    dialog.scope.setCurrentIndex(2)
    assert dialog.result['total'] == 4
    assert not dialog.tables['curve'].rowCount()
    dialog.close()
    app.processEvents()


def test_editor_insights_loads_local_data_without_changing_deck(tmp_path):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    service = SimpleNamespace(get_card=lambda **kw: dict(type_line='Creature', cmc=2, colors=['G'], mana_cost='{1}{G}'))
    window = EditorWindow(service=service, root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'Card', card_id='card', quantity=4)]
    before = window.document.to_dict()
    window.run_task = lambda work, callback: callback(work())
    window.deck_insights()
    assert window.insights_dialog.result['curve'] == {2: 4}
    assert window.document.to_dict() == before
    window.insights_dialog.close()
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

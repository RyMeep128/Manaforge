from PyQt6 import QtCore, QtWidgets
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.categorization import classify, apply_categories, is_manual
from mtg_editor.category_review import CategoryReview
from mtg_editor.organization import assign, remove_category


def test_manual_changes_and_deletion_are_protected():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card')]
    apply_categories(doc, {'a': classify({}, ['ramp'])})
    remove_category(doc, 'auto:ramp')
    assert is_manual(doc.deck.entries[0])
    apply_categories(doc, {'a': classify({}, ['ramp'])})
    assert doc.deck.entries[0].category_ids == []
    assign(doc, {'a'}, 'category', 'custom')
    assert is_manual(doc.deck.entries[0])


def test_review_cancel_and_deselect_do_not_mutate():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card'), DeckEntry('b', 'Manual', category_ids=['custom'])]
    before = doc.to_dict()
    dialog = CategoryReview(doc, {e.entry_id: classify({}, ['ramp']) for e in doc.deck.entries})
    assert list(dialog.selected_proposals()) == ['a']
    dialog.table.item(0, 0).setCheckState(QtCore.Qt.CheckState.Unchecked)
    assert dialog.selected_proposals() == {}
    dialog.reject()
    assert doc.to_dict() == before
    dialog.deleteLater()
    app.processEvents()


def test_search_add_categorizes_in_same_undo_transaction(tmp_path):
    from types import SimpleNamespace
    from mtg_editor.gui import EditorWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    assert window.group.currentText() == 'Category'
    assert window.grid.grouping == 'Category'
    result = SimpleNamespace(name='Example', card_id='a', oracle_id='o', set_code='abc',
        collector_number='1', payload={'type_line': 'Artifact', '_category_evidence': classify({}, ['ramp'])})
    window.show_results('', [result], '')
    window.add_result('a')
    assert window.document.deck.entries[0].category_ids == ['auto:ramp']
    window.undo()
    assert not window.document.deck.entries
    assert not window.document.deck.categories
    window.redo()
    assert window.document.deck.entries[0].category_ids == ['auto:ramp']
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()


def test_search_worker_enriches_results_locally_without_changing_payload():
    from types import SimpleNamespace
    from mtg_core.models import SearchCardResult
    from mtg_editor.gui import SearchWorker
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    original = SearchCardResult('card', 'oracle', 'Example', None, None, None, None, None,
                                {'type_line': 'Artifact'})
    from mtg_core.services import CardService
    class Service(CardService):
        def __init__(self):
            pass

        database = SimpleNamespace(categorization_data=lambda cards, oracles, **kwargs:
                                   {'tags': {'oracle': ['ramp']}})
        def search_cards(self, query, options):
            assert options['allow_remote'] is False
            return [original]
    worker = SearchWorker('example', Service())
    observed = []
    worker.completed.connect(lambda query, results, error: observed.append((results, error)))
    worker.run()
    assert observed[0][1] == ''
    assert observed[0][0][0].payload['_category_evidence'][0]['name'] == 'Ramp'
    assert '_category_evidence' not in original.payload


def test_show_empty_categories_preference_and_canvas(tmp_path):
    from mtg_editor.gui import EditorWindow
    from mtg_core.decks import DeckCategory
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.categories = [DeckCategory('empty', 'Old automatic category')]
    window.changed()
    assert not window.grid.headers
    window.show_empty_categories.setChecked(True)
    assert 'empty' in [h[0] for h in window.grid.headers]
    assert window.save()
    path = window.path
    window.new()
    window.open_path(path)
    assert window.show_empty_categories.isChecked()
    window.show_empty_categories.setChecked(False)
    assert not window.grid.headers
    assert window.document.deck.categories[0].category_id == 'empty'
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

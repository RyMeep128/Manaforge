from types import SimpleNamespace

from PyQt6 import QtWidgets, QtCore
from mtg_editor.gui import EditorWindow
from PyQt6 import QtGui
from mtg_core.decks import DeckEntry
import pytest


@pytest.mark.parametrize('mode', ['Grid', 'Stacks'])
def test_quantity_buttons_click_remove_and_undo(tmp_path, mode):
    from PyQt6.QtTest import QTest
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('one', 'Example', quantity=2)]
    window.view_mode.setCurrentText(mode)
    window.changed()
    window.show()
    app.processEvents()

    def click(delta):
        item = next(item for item in window.grid.items if item[0].entry_id == 'one')
        button = dict(window.grid.quantity_buttons(item[1]))[delta]
        point = button.center() - QtCore.QPoint(0, window.grid.verticalScrollBar().value())
        QTest.mouseClick(window.grid.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=point)

    click(1)
    assert window.document.deck.entries[0].quantity == 3
    click(-1)
    assert window.document.deck.entries[0].quantity == 2
    click(-1)
    click(-1)
    assert not window.document.deck.entries
    window.undo()
    assert window.document.deck.entries[0].quantity == 1
    window.close()
    app.processEvents()


def test_search_marks_alternate_printings_and_updates_after_undo(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    result = SimpleNamespace(name='Example', card_id='alternate', oracle_id='same',
                             set_code='set', collector_number='1')
    window.show_results('', [result], '')
    assert not window.results.in_deck_ids
    window.add_card(DeckEntry('original', 'Example', card_id='original', oracle_id='same'))
    assert window.results.in_deck_ids == {'alternate'}
    window.undo()
    assert not window.results.in_deck_ids
    window.redo()
    assert window.results.in_deck_ids == {'alternate'}
    window.close()
    app.processEvents()


def test_deck_filters_share_views_clear_selection_and_keep_last_valid_query(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [
        DeckEntry('a', 'Bird', extras={'facts': {'cmc': 2}}),
        DeckEntry('b', 'Dragon', extras={'facts': {'cmc': 6}})]
    window.changed()
    before = window.document.to_dict()
    window.grid.selected = {'b'}
    window.filter.setText('mv<=2')
    assert not window.table.isRowHidden(0)
    assert window.table.isRowHidden(1)
    assert not window.grid.selected
    assert {entry.entry_id for entry, _, _ in window.grid.items} == {'a'}
    window.filter.setText('mv:bad')
    assert window.grid.query == 'mv<=2'
    assert window.table.isRowHidden(1)
    window.filter.clear()
    assert not window.table.isRowHidden(1)
    assert window.document.to_dict() == before
    window.close()
    app.processEvents()


def test_readiness_filter_applies_to_both_views_and_expires_on_edit(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.entries = [DeckEntry('a', 'First'), DeckEntry('b', 'Second')]
    window.changed()
    window.grid.filtered_ids = {'b'}
    window.readiness_snapshot = window.document.to_dict()
    window.filter_changed()
    assert window.table.isRowHidden(0)
    assert not window.table.isRowHidden(1)
    assert {e.entry_id for e, _, _ in window.grid.items} == {'b'}
    window.change_quantity('b', 1)
    assert window.grid.filtered_ids is None
    assert not window.table.isRowHidden(0)
    window.close()
    app.processEvents()


def test_visual_grid_loads_cached_art_and_shares_table_selection(tmp_path):
    import time
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    image = QtGui.QImage(300, 420, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor('green'))
    image_path = tmp_path / 'card.png'
    image.save(str(image_path))
    class Service:
        def get_image_path(self, card_id):
            return str(image_path)
    window = EditorWindow(service=Service(), root=tmp_path)
    window.document.deck.entries.append(DeckEntry(entry_id='one', name='Test card', card_id='one'))
    window.changed()
    window.show()
    deadline = time.monotonic() + 3
    while ('one', None) not in window.thumbnails.cache and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.thumbnails.cache[('one', None)].isNull()
    assert window.views.currentWidget() is window.grid
    window.grid.selected = {'one'}
    window.change_quantity('one', 1)
    window.show_table()
    assert window.table.currentIndex().row() == 0
    assert window.document.deck.entries[0].quantity == 2
    window.close()
    app.processEvents()


def test_add_undo_redo_save_and_reopen(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    result = SimpleNamespace(name='Sol Ring', card_id='ring', oracle_id='oracle',
                             set_code='lea', collector_number='1')
    window.show_results('', [result], '')
    window.add_result('ring')
    window.add_result('ring')
    assert window.document.deck.entries[0].quantity == 2
    window.undo()
    assert window.document.deck.entries[0].quantity == 1
    window.redo()
    assert window.save()
    path = window.path
    window.new()
    window.open_path(path)
    assert window.document.deck.entries[0].quantity == 2
    assert window.document.to_dict() == window.saved
    window.close()
    app.processEvents()


def test_failed_save_keeps_dirty_document(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.name.setText('Unsaved')
    window.edit_metadata()
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr(window.store, 'save', fail)
    assert not window.save()
    assert window.document.to_dict() != window.saved
    assert '*' in window.windowTitle()
    window.saved = window.document.to_dict()
    window.close()
    app.processEvents()

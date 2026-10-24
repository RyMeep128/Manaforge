import pytest
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, QtTest
from mtg_core.decks import DeckCategory, DeckEntry
from mtg_core.sections import DeckSection
from mtg_editor.gui import EditorWindow


@pytest.fixture
def editor(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.document.deck.categories = [DeckCategory('draw', 'Draw'), DeckCategory('ramp', 'Ramp'),
                                        DeckCategory('empty', 'Empty')]
    window.document.deck.entries = [
        DeckEntry('commander', 'Leader', section=DeckSection.COMMANDER),
        DeckEntry('alpha', 'Alpha', quantity=3, card_id='alpha', category_ids=['draw', 'ramp'],
                  extras={'facts': {'mana_cost': '{1}{U}', 'type_line': 'Creature'}}),
        DeckEntry('beta', 'Beta', quantity=2, card_id='beta', category_ids=['ramp'],
                  extras={'facts': {'mana_cost': '{G}', 'type_line': 'Creature'}})]
    pixmap = G.QPixmap(240, 336)
    pixmap.fill(G.QColor('darkgreen'))
    for entry in window.document.deck.entries:
        window.thumbnails.cache[(entry.card_id, None)] = pixmap
        window.thumbnails.cache[(entry.card_id, None, 600)] = pixmap
    window.changed()
    window.resize(1600, 800)
    window.view_mode.setCurrentText('Text')
    window.show()
    app.processEvents()
    yield window
    window.close()
    app.processEvents()


def test_text_groups_count_primary_categories_collapse_and_filter(editor):
    rows = editor.text_view.rows
    assert editor.views.currentWidget() is editor.text_view
    headers = {key: (count, rect) for key, _, count, rect in rows.headers}
    assert headers['Commander'][0] == 1
    assert headers['draw'][0] == 3 and headers['ramp'][0] == 2
    assert 'empty' not in headers
    assert len({rect.x() for key, _, _, rect in rows.headers if key != 'Commander'}) == 2
    QtTest.QTest.mouseClick(rows.viewport(), C.Qt.MouseButton.LeftButton,
                           pos=headers['draw'][1].center())
    assert 'draw' in rows.collapsed
    assert 'alpha' not in {entry.entry_id for entry, _ in rows.items}
    assert editor.document.editor_preferences['text_collapsed'] == ['draw']
    editor.filter.setText('Beta')
    assert [entry.entry_id for entry, _ in rows.items] == ['beta']
    for grouping in ('Type', 'Mana Value', 'Color', 'Section'):
        editor.group.setCurrentText(grouping)
        assert [entry.entry_id for entry, _ in rows.items] == ['beta']


def test_text_quantity_bulk_selection_undo_and_printing_preview(editor):
    rows = editor.text_view.rows
    entry, rect = next(item for item in rows.items if item[0].entry_id == 'alpha')
    QtTest.QTest.mouseClick(rows.viewport(), C.Qt.MouseButton.LeftButton,
                           pos=dict(rows.quantity_buttons(rect))[1].center())
    assert editor.document.deck.entries[1].quantity == 4
    editor.undo()
    assert editor.document.deck.entries[1].quantity == 3
    alpha, beta = editor.document.deck.entries[1:]
    rows.select(alpha, C.Qt.KeyboardModifier.NoModifier)
    rows.select(beta, C.Qt.KeyboardModifier.ControlModifier)
    QtTest.QTest.keyClick(rows, C.Qt.Key.Key_Plus)
    assert [entry.quantity for entry in editor.document.deck.entries[1:]] == [4, 3]
    editor.undo()
    assert editor.grid.selected == {'alpha', 'beta'}
    editor.text_view.preview_entry(editor.document.deck.entries[1])
    assert editor.text_view.mana_cost(editor.document.deck.entries[1]) == '{1}{U}'
    assert editor.thumbnails.visible[id(editor.text_view)] == {('alpha', None, 600)}
    assert not editor.text_view.preview.pixmap().isNull()
    editor.text_view.preview_toggle.setChecked(False)
    assert editor.text_view.preview.isHidden()
    assert not editor.thumbnails.visible[id(editor.text_view)]


def test_text_view_scrolls_and_preference_survive_view_switches(editor):
    editor.document.deck.entries = [DeckEntry(str(index), f'Card {index:03}',
                                             extras={'facts': {'mana_cost': '{1}'}}) for index in range(100)]
    editor.changed()
    editor.resize(700, 600)
    W.QApplication.processEvents()
    assert editor.text_view.preview.isHidden()
    editor.text_view.rows.verticalScrollBar().setValue(350)
    editor.view_mode.setCurrentText('Grid')
    W.QApplication.processEvents()
    editor.grid.verticalScrollBar().setValue(120)
    editor.view_mode.setCurrentText('Stacks')
    W.QApplication.processEvents()
    editor.grid.verticalScrollBar().setValue(80)
    editor.view_mode.setCurrentText('Text')
    W.QApplication.processEvents()
    assert editor.text_view.rows.verticalScrollBar().value() == 350
    editor.view_mode.setCurrentText('Grid')
    W.QApplication.processEvents()
    assert editor.grid.verticalScrollBar().value() == 120
    editor.view_mode.setCurrentText('Text')
    W.QApplication.processEvents()
    assert editor.save()
    path = editor.path
    editor.new()
    editor.open_path(path)
    assert editor.view_mode.currentText() == 'Text'
    assert editor.views.currentWidget() is editor.text_view

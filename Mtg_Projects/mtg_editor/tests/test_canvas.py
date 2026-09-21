import time
from types import SimpleNamespace
import pytest
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, QtTest
from mtg_core.decks import DeckEntry, DeckCategory
from mtg_editor.gui import EditorWindow


@pytest.fixture
def window(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    window.view_mode.setCurrentText('Grid')
    pixmap = G.QPixmap(180, 252)
    pixmap.fill(G.QColor('darkgreen'))
    for i in range(12):
        entry = DeckEntry(str(i), f'Card {i:02}', card_id=str(i), sort_order=i,
                          extras={'facts': {'type_line': 'Creature', 'cmc': i % 4, 'colors': ['G']}})
        window.document.deck.entries.append(entry)
        window.thumbnails.cache[(str(i), None)] = pixmap
    window.changed()
    window.resize(1280, 720)
    window.show()
    app.processEvents()
    yield window
    window.close()
    app.processEvents()


def point(window, entry_id, *, title=False):
    rect = next(r for e, r, _ in window.grid.items if e.entry_id == entry_id)
    pos = rect.topLeft()+C.QPoint(70, 12) if title else rect.center()
    return pos-C.QPoint(0, window.grid.verticalScrollBar().value())


def test_ctrl_shift_selection_delete_and_undo(window):
    canvas = window.grid
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=point(window, '0'))
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton,
                           C.Qt.KeyboardModifier.ControlModifier, pos=point(window, '2'))
    assert canvas.selected == {'0', '2'}
    QtTest.QTest.mouseClick(canvas.viewport(), C.Qt.MouseButton.LeftButton,
                           C.Qt.KeyboardModifier.ShiftModifier, pos=point(window, '4'))
    assert canvas.selected == {'0', '2', '3', '4'}
    QtTest.QTest.keyClick(canvas, C.Qt.Key.Key_Delete)
    assert len(window.document.deck.entries) == 8
    window.undo()
    assert len(window.document.deck.entries) == 12


def test_stacks_hit_test_exposed_titles_hover_preview_and_size(window):
    window.view_mode.setCurrentText('Stacks')
    W.QApplication.processEvents()
    assert window.grid.hit(point(window, '1', title=True))[0].entry_id == '1'
    local = point(window, '1', title=True)
    # Explicit viewport event avoids dependence on another test's global cursor
    # position or active offscreen top-level window.
    event = G.QMouseEvent(C.QEvent.Type.MouseMove, C.QPointF(local),
                         C.QPointF(window.grid.viewport().mapToGlobal(local)),
                         C.Qt.MouseButton.NoButton, C.Qt.MouseButton.NoButton,
                         C.Qt.KeyboardModifier.NoModifier)
    W.QApplication.sendEvent(window.grid.viewport(), event)
    assert window.grid.hovered == '1'
    window.grid.show_preview()
    assert not window.grid.preview.pixmap().isNull()
    before = window.grid.items[0][1].width()
    window.zoom.setValue(240)
    assert window.grid.items[0][1].width() > before


def test_quantity_controls_and_artwork_double_click(window):
    requests = []
    window.grid.artworkRequested.disconnect()
    window.grid.artworkRequested.connect(requests.append)
    rect = window.grid.items[0][1]
    QtTest.QTest.mouseClick(window.grid.viewport(), C.Qt.MouseButton.LeftButton,
                           pos=C.QPoint(rect.right()-15, rect.bottom()-15))
    assert window.document.deck.entries[0].quantity == 2
    QtTest.QTest.mouseDClick(window.grid.viewport(), C.Qt.MouseButton.LeftButton, pos=point(window, '0'))
    assert requests == ['0']


def test_collapse_selection_scroll_preferences_survive_edits(window):
    window.grid.selected = {'1'}
    window.grid.verticalScrollBar().setValue(50)
    offset = window.grid.verticalScrollBar().value()
    window.change_quantity('1', 1)
    assert window.grid.selected == {'1'}
    assert window.grid.verticalScrollBar().value() == offset
    window.group.setCurrentText('Section')
    window.grid.collapsed.add('Excluded')
    window.preferences_changed()
    window.undo()
    assert window.grid.grouping == 'Section'
    assert 'Excluded' in window.grid.collapsed
    assert window.save()
    assert window.store.load(window.path).editor_preferences['group'] == 'Section'


def test_drag_feedback_rejects_derived_groups_and_accepts_section(window):
    window.group.setCurrentText('Type')
    canvas = window.grid
    canvas.selected = {'0'}
    class Event:
        accepted = False
        def position(self):
            return C.QPointF(canvas.headers[-1][3].center()-C.QPoint(0, canvas.verticalScrollBar().value()))
        def acceptProposedAction(self):
            self.accepted = True
        def ignore(self):
            self.accepted = False
        def source(self):
            return canvas
    event = Event()
    canvas.dragMoveEvent(event)
    assert not event.accepted
    window.group.setCurrentText('Section')
    canvas.dragMoveEvent(event)
    assert event.accepted
    canvas.dropEvent(event)
    assert window.document.deck.entries[0].section == 'sideboard'
    window.undo()
    assert window.document.deck.entries[0].section == 'mainboard'


def test_toolbar_wraps_without_offscreen_actions(window):
    window.resize(700, 600)
    W.QApplication.processEvents()
    for widget in window.header_actions:
        rect = C.QRect(widget.mapTo(window, C.QPoint()), widget.size())
        assert rect.right() < window.width()
        assert rect.bottom() < 150
    assert window.grid.height() > 300


def test_500_card_canvas_only_requests_visible_images_off_ui_thread(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    calls = []
    class Service:
        def get_image_path(self, card_id):
            calls.append((card_id, C.QThread.currentThread() == app.thread()))
            return None
    window = EditorWindow(service=Service(), root=tmp_path)
    window.document.deck.entries = [DeckEntry(str(i), f'Card {i:03}', card_id=str(i)) for i in range(500)]
    start = time.monotonic()
    window.changed()
    window.show()
    app.processEvents()
    assert time.monotonic()-start < 2
    assert len(window.thumbnails.pending) < 40
    window.grid.verticalScrollBar().setValue(window.grid.verticalScrollBar().maximum())
    app.processEvents()
    assert len(window.thumbnails.pending) < 40
    window.close()
    deadline = time.monotonic()+3
    while window.thumbnails.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not any(on_main for _, on_main in calls)
    assert len(calls) < 10
    window.close()
    app.processEvents()

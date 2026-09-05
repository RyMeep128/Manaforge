import json
import os
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
import pytest
import editor_widgets
import pdf
from models import ProjectState
from preview_interaction import MIME
from services import layout_service as layout

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def preview(monkeypatch):
    monkeypatch.setattr(editor_widgets.runtime_images, 'ensure_preview_entry', lambda *a: None)
    state = ProjectState.from_dict({'cards': {'wide': 1, 'a': 2},
        'oversized_enabled': True, 'oversized': {'wide': True}, 'backside_enabled': True})
    widget = editor_widgets.PrintPreview(state, {})
    widget.resize(1150, 950)
    widget.show()
    APP.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    APP.processEvents()


def center(overlay, row, column):
    return overlay.rectangle(row, column).center().toPoint()


def test_hover_select_both_halves_and_plus_click(preview, monkeypatch):
    overlay = preview._overlays[0]
    wide = next(p for p in preview._placements if p['span'] == 2)
    for column in (wide['column'], wide['column'] + 1):
        point = center(overlay, wide['row'], column)
        QtTest.QTest.mouseMove(overlay, point)
        assert overlay.item_at(overlay.hovered)['copy_id'] == wide['copy_id']
        QtTest.QTest.mouseClick(overlay, QtCore.Qt.MouseButton.LeftButton, pos=point)
        assert preview._selected_copy == wide['copy_id']
    calls = []
    monkeypatch.setattr(preview, 'add_at_slot', calls.append)
    point = center(overlay, 2, 2)
    QtTest.QTest.mouseClick(overlay, QtCore.Qt.MouseButton.LeftButton, pos=point)
    assert calls == [(0, 2, 2)]
    assert preview._state.manual_layout is None
    assert len(preview._overlays) * 2 == len(preview._pages)


def test_drag_validation_and_drop_preserve_grab_offset(preview):
    overlay = preview._overlays[0]
    wide = next(p for p in preview._placements if p['span'] == 2)
    mime = QtCore.QMimeData()
    mime.setData(MIME, json.dumps(dict(copy_id=wide['copy_id'], offset=1, preview=id(preview))).encode())
    preview._drag_span = 2
    invalid = QtGui.QDragEnterEvent(center(overlay, 1, 0), QtCore.Qt.DropAction.MoveAction,
        mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    overlay.dragEnterEvent(invalid)
    assert not overlay.drop_valid
    valid = QtGui.QDragMoveEvent(center(overlay, 1, 2), QtCore.Qt.DropAction.MoveAction,
        mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    overlay.dragMoveEvent(valid)
    assert overlay.drop_valid
    assert overlay.drop_destination == (0, 1, 1)
    drop = QtGui.QDropEvent(QtCore.QPointF(center(overlay, 1, 2)), QtCore.Qt.DropAction.MoveAction,
        mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    overlay.dropEvent(drop)
    APP.processEvents()
    placed = next(p for p in preview._placements if p['copy_id'] == wide['copy_id'])
    assert (placed['row'], placed['column']) == (1, 1)
    pages = pdf.distribute_cards_to_pages(preview._state, preview._columns, preview._rows)
    assert pdf.distribute_cards_to_grid(pages[0], True, preview._columns, preview._rows)[1][1][0] == 'wide'


def test_fit_zoom_page_navigation_reset_and_empty_project(preview):
    preview._set_zoom('Fit')
    preview._set_view_mode('Single Page')
    preview.add_page()
    APP.processEvents()
    assert preview._zoom_combo.currentText() == 'Fit'
    assert preview._view_mode == 'Single Page'
    assert preview._overlays[-1].page == 1
    assert preview._pages[preview._page_index] is preview._overlays[-1].parentWidget().parentWidget()
    preview._state.manual_layout = layout.record(preview._placements)
    preview.reset_layout()
    assert preview._state.manual_layout is None
    empty = editor_widgets.PrintPreview(ProjectState(), {})
    empty.show()
    APP.processEvents()
    assert len(empty._overlays) == 1
    assert empty._overlays[0].item_at((0, 0, 0)) is None
    empty.add_page()
    assert len(empty._overlays) == 2
    empty.close()
    empty.deleteLater()


def test_hover_page_navigation_timer(preview):
    preview.add_page()
    preview._set_page(0)
    preview._drag_active = True
    mime = QtCore.QMimeData()
    mime.setData(MIME, b'{}')
    event = QtGui.QDragEnterEvent(QtCore.QPoint(3, 3), QtCore.Qt.DropAction.MoveAction,
        mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    preview._next_button.dragEnterEvent(event)
    assert preview._next_button.timer.isActive()
    preview._next_button.timer.timeout.emit()
    assert preview._page_index == 1
    preview._next_button.dragLeaveEvent(QtGui.QDragLeaveEvent())
    assert not preview._next_button.timer.isActive()


def test_add_at_slot_reuses_dialog_route_and_places_only_new_copy(preview, monkeypatch):
    class Actions(QtWidgets.QWidget):
        def _add_single_card(self, *, on_added):
            preview._state.set_card_count('a', preview._state.get_card_count('a') + 1)
            on_added(SimpleNamespace(filename='a'))

    monkeypatch.setattr(editor_widgets, 'ActionsWidget', Actions)
    actions = Actions(preview)
    original = list(preview._placements)
    preview.add_at_slot((0, 2, 2))
    updated, _ = layout.resolve(preview._state, preview._columns, preview._rows)
    assert all(item in updated for item in original)
    new = next(p for p in updated if p not in original)
    assert (new['page'], new['row'], new['column'], new['name']) == (0, 2, 2, 'a')
    assert preview._state.get_card_count('a') == 3


def test_add_dialog_cancellation_does_not_capture_manual_layout(preview, monkeypatch):
    class Actions(QtWidgets.QWidget):
        def _add_single_card(self, *, on_added):
            pass  # Dialog rejected: no import or callback.

    monkeypatch.setattr(editor_widgets, 'ActionsWidget', Actions)
    actions = Actions(preview)
    before = preview._state.to_dict()
    preview.add_at_slot((0, 2, 2))
    assert preview._state.to_dict() == before


def test_wide_add_requires_adjacent_free_slot(preview, monkeypatch):
    class Actions(QtWidgets.QWidget):
        def _add_single_card(self, *, on_added):
            preview._state.set_card_count('wide', 2)
            on_added(SimpleNamespace(filename='wide'))

    monkeypatch.setattr(editor_widgets, 'ActionsWidget', Actions)
    actions = Actions(preview)
    with pytest.raises(ValueError, match='two adjacent'):
        preview.add_at_slot((0, 2, 2))
    assert preview._state.manual_layout is None


@pytest.mark.parametrize('zoom', ['Fit', '50%', '150%'])
@pytest.mark.parametrize('mode', ['Continuous', 'Single Page'])
def test_hit_regions_match_rendered_card_geometry(preview, zoom, mode):
    preview._set_zoom(zoom)
    preview._set_view_mode(mode)
    APP.processEvents()
    overlay = preview._overlays[0]
    grid = overlay.parentWidget()
    assert overlay.size() == grid.size()
    for item in preview._placements:
        if item['page'] != 0:
            continue
        artwork = grid.layout().itemAtPosition(item['row'], item['column']).widget()
        expected = overlay.rectangle(item['row'], item['column'], item['span']).toRect()
        assert abs(artwork.x() - expected.x()) <= 1
        assert abs(artwork.y() - expected.y()) <= 1
        assert abs(artwork.width() - expected.width()) <= 1
        assert abs(artwork.height() - expected.height()) <= 1


@pytest.mark.parametrize('bleed', ['0', '3', '6'])
@pytest.mark.parametrize('orientation', ['Portrait', 'Landscape'])
def test_sheet_geometry_matches_print_dimensions_with_bleed(preview, bleed, orientation):
    preview._state.bleed_edge = bleed
    preview._state.orient = orientation
    preview.refresh(preview._state, {})
    preview._zoom_combo.setCurrentText('Fit')
    APP.processEvents()
    page = preview._pages[0]
    overlay = preview._overlays[0]
    slot = overlay.rectangle(0, 0)
    scale = page.width() / page._page_width
    assert slot.width() == pytest.approx(page._card_width * scale, abs=1)
    assert slot.height() == pytest.approx(page._card_height * scale, abs=1)


def test_continuous_drag_scrolls_at_viewport_edge(preview, monkeypatch):
    preview.add_page()
    APP.processEvents()
    preview._set_view_mode('Continuous')
    preview.verticalScrollBar().setValue(0)
    cursor = preview.viewport().mapToGlobal(QtCore.QPoint(150, preview.viewport().height() - 5))
    monkeypatch.setattr(editor_widgets, 'QCursor', SimpleNamespace(pos=lambda: cursor))
    preview._scroll_drag()
    assert preview.verticalScrollBar().value() > 0
    previous = preview.verticalScrollBar().value()
    preview._view_mode = 'Single Page'
    preview._scroll_drag()
    assert preview.verticalScrollBar().value() == previous

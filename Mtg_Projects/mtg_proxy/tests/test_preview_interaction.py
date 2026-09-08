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


def test_empty_slot_menu_offers_unadded_related_token(preview, monkeypatch):
    token = SimpleNamespace(name='Sliver', card_id='token-id')
    suggestion = SimpleNamespace(
        candidate=token, source_name='Brood Sliver', component='token')
    monkeypatch.setattr(
        editor_widgets.deck_import_service, 'unadded_token_suggestions',
        lambda state: [suggestion])
    additions = []
    monkeypatch.setattr(
        preview, 'add_at_slot',
        lambda destination, selected_card=None:
        additions.append((destination, selected_card)))

    menu = preview.empty_slot_context_menu((0, 2, 2))
    related = next(action for action in menu.actions()
                   if action.text() == 'Add Related Token')
    related.menu().actions()[0].trigger()

    assert additions == [((0, 2, 2), token)]
    menu.deleteLater()


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


@pytest.mark.parametrize('offset', [0, 1])
def test_drag_oversized_onto_two_normal_cards_and_undo(preview, offset):
    items = sorted(preview._placements, key=lambda p: -p['span'])
    for item, pos in zip(items, [(0, 1, 0), (0, 0, 0), (0, 0, 1)]):
        item.update(zip(('page', 'row', 'column'), pos))
    preview._state.manual_layout = layout.record(items)
    preview.refresh_after_edit()
    before = preview._state.to_dict()
    overlay = preview._overlays[0]
    mime = QtCore.QMimeData()
    mime.setData(MIME, json.dumps(dict(copy_id=items[0]['copy_id'], offset=offset,
                                     preview=id(preview))).encode())
    point = center(overlay, 0, offset)
    event = QtGui.QDragEnterEvent(point, QtCore.Qt.DropAction.MoveAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    overlay.dragEnterEvent(event)
    assert overlay.drop_valid
    drop = QtGui.QDropEvent(QtCore.QPointF(point), QtCore.Qt.DropAction.MoveAction,
        mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    overlay.dropEvent(drop)
    APP.processEvents()
    assert drop.isAccepted()
    pages = pdf.distribute_cards_to_pages(preview._state, preview._columns, preview._rows)
    grid = pdf.distribute_cards_to_grid(pages[0], True, preview._columns, preview._rows)
    assert grid[0][0][0] == 'wide'
    assert grid[1][0][0] == grid[1][1][0] == 'a'
    after = preview._state.to_dict()
    preview.undo_layout()
    assert preview._state.to_dict() == before
    preview.redo_layout()
    assert preview._state.to_dict() == after


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


def test_layout_undo_redo_and_reset_restore_exact_state(preview):
    original = preview._state.to_dict()
    item = next(p for p in preview._placements if p['span'] == 1)
    preview.commit_layout(layout.move(preview._placements, item['copy_id'], (0, 2, 2),
                                      preview._columns, preview._rows))
    preview.refresh_after_edit()
    moved = preview._state.to_dict()
    assert preview._undo_button.isEnabled()
    preview.undo_layout()
    assert preview._state.to_dict() == original
    assert preview._redo_button.isEnabled()
    preview.redo_layout()
    assert preview._state.to_dict() == moved
    preview.reset_layout()
    assert preview._state.manual_layout is None
    preview.undo_layout()
    assert preview._state.to_dict() == moved


def test_undo_page_and_addition_and_external_changes(preview, monkeypatch):
    preview.add_page()
    preview.undo_layout()
    assert preview._extra_pages == 0
    preview.redo_layout()
    assert preview._extra_pages == 2

    class Actions(QtWidgets.QWidget):
        def _add_single_card(self, *, on_added):
            preview._state.set_card_count('a', 3)
            on_added(SimpleNamespace(filename='a'))

    monkeypatch.setattr(editor_widgets, 'ActionsWidget', Actions)
    actions = Actions(preview)
    preview.add_at_slot((1, 0, 0))
    preview.refresh_after_edit()
    added = preview._state.to_dict()
    preview.undo_layout()
    assert preview._state.get_card_count('a') == 2
    preview.redo_layout()
    assert preview._state.to_dict() == added
    preview._state.set_card_count('a', 8)
    preview.refresh_after_edit()
    preview.undo_layout()
    assert preview._state.get_card_count('a') == 8
    assert not preview._undo_button.isEnabled()
    assert not preview._redo_button.isEnabled()


def test_page_occupancy_captions_and_single_page_visibility(preview):
    assert preview._page_captions[0].text().startswith('Page 1: 4/9 filled')
    assert '(back)' in preview._page_captions[1].text()
    preview._view_combo.setCurrentText('Single Page')
    APP.processEvents()
    assert not preview._page_captions[0].isHidden()
    assert preview._page_captions[1].isHidden()
    preview._set_page(1)
    assert preview._page_captions[0].isHidden()
    assert not preview._page_captions[1].isHidden()


@pytest.mark.parametrize('choice,expected', [('Go Back', False), ('Print Anyway', True)])
def test_underfilled_warning_keeps_explicit_print_anyway(choice, expected):
    def answer():
        dialog = APP.activeModalWidget()
        assert isinstance(dialog, QtWidgets.QMessageBox)
        assert 'Page 4: 1/9 filled' in dialog.informativeText()
        assert dialog.defaultButton().text() == 'Go Back'
        next(button for button in dialog.buttons() if button.text() == choice).click()
    QtCore.QTimer.singleShot(0, answer)
    assert editor_widgets.confirm_underfilled_export(None, [dict(page=4, filled=1, capacity=9)]) is expected


def test_full_sheets_do_not_show_warning(monkeypatch):
    monkeypatch.setattr(editor_widgets, 'QMessageBox', lambda *args: pytest.fail('Unexpected warning'))
    assert editor_widgets.confirm_underfilled_export(None, [dict(page=1, filled=9, capacity=9)])


@pytest.mark.parametrize('proceed', [False, True])
def test_export_warning_gates_pdf_generation(monkeypatch, tmp_path, proceed):
    calls = []
    app = SimpleNamespace(show_home=lambda: None, _debug_mode=False,
                          warn_nonfatal=lambda *args: pytest.fail(str(args)))
    state = ProjectState.from_dict({'cards': {'one': 1}})
    actions = editor_widgets.ActionsWidget(app, state, {})
    monkeypatch.setattr(editor_widgets.QFileDialog, 'getSaveFileName',
                        lambda *args: (str(tmp_path / 'output.pdf'), ''))
    def confirm(parent, pages):
        assert pages == [dict(page=1, filled=1, capacity=9, cards=1)]
        calls.append('warning')
        return proceed
    monkeypatch.setattr(editor_widgets, 'confirm_underfilled_export', confirm)
    monkeypatch.setattr(editor_widgets, 'popup', lambda *args:
                        SimpleNamespace(show_during_work=lambda work: work()))
    monkeypatch.setattr(editor_widgets, 'make_popup_print_fn', lambda *args: lambda text: None)
    def generate(*args, **kwargs):
        calls.append('generate')
        return SimpleNamespace(pages=SimpleNamespace(save=lambda: calls.append('save')),
                               backside_pages=None, backside_pdf_path=None)
    monkeypatch.setattr(editor_widgets.pdf_service, 'generate_pdf', generate)
    monkeypatch.setattr(editor_widgets.subprocess, 'Popen', lambda *args, **kwargs: None)
    monkeypatch.setattr(editor_widgets.QMessageBox, 'information', lambda *args: None)
    actions._render_button.click()
    assert calls == (['warning', 'generate', 'save'] if proceed else ['warning'])
    actions.deleteLater()


def test_escape_cancels_underfilled_export():
    QtCore.QTimer.singleShot(0, lambda: APP.activeModalWidget().reject())
    assert not editor_widgets.confirm_underfilled_export(None, [dict(page=1, filled=1, capacity=9)])


def test_preview_keyboard_undo_redo(preview):
    item = next(p for p in preview._placements if p['span'] == 1)
    preview.commit_layout(layout.move(preview._placements, item['copy_id'], (0, 2, 2),
                                      preview._columns, preview._rows))
    preview.refresh_after_edit()
    moved = preview._state.to_dict()
    preview.activateWindow()
    preview._overlays[0].setFocus()
    APP.processEvents()
    QtTest.QTest.keyClick(preview._overlays[0], QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
    APP.processEvents()
    assert preview._state.manual_layout is None
    preview._overlays[0].setFocus()
    QtTest.QTest.keyClick(preview._overlays[0], QtCore.Qt.Key.Key_Y, QtCore.Qt.KeyboardModifier.ControlModifier)
    APP.processEvents()
    assert preview._state.to_dict() == moved


@pytest.mark.parametrize('manual', [False, True])
@pytest.mark.parametrize('operation,expected', [('increment', 3), ('typed', 5),
                                               ('selected_increment', 3), ('decrement', 1)])
def test_cards_tab_quantity_changes_reach_preview_and_saved_project(monkeypatch, manual, operation, expected):
    monkeypatch.setattr(editor_widgets.runtime_images, 'ensure_preview_entry', lambda *args: None)
    state = ProjectState.from_dict({'cards': {'a': 2, 'wide': 1},
        'oversized_enabled': True, 'oversized': {'wide': True}})
    images = {name: dict(data=editor_widgets.image.encode_cached_image_bytes(editor_widgets.fallback.data),
                         size=editor_widgets.fallback.size) for name in state.cards}
    grid = editor_widgets.CardGrid(state, images)
    cards = editor_widgets.CardScrollArea(state, images, grid)
    lazy = editor_widgets.LazyPrintPreview(state, images)
    tabs = editor_widgets.CardTabs(state, images, cards, lazy)
    tabs.setCurrentIndex(1)
    preview = lazy._preview
    original = next(p for p in preview._placements if p['name'] == 'a')
    if manual:
        preview.commit_layout(layout.move(preview._placements, original['copy_id'], (1, 0, 0),
                                          preview._columns, preview._rows))
        preview.refresh_after_edit()
    tabs.setCurrentIndex(0)
    card = grid._cards['a']
    if operation == 'typed':
        card._number_edit.setText('5')
        card._number_edit.editingFinished.emit()
    elif operation == 'selected_increment':
        card.set_selected(True)
        cards._selection_buttons[1].click()
    else:
        tooltip = 'Add one copy' if operation == 'increment' else 'Remove one copy'
        next(button for button in card.findChildren(QtWidgets.QPushButton)
             if button.toolTip() == tooltip).click()
    tabs.setCurrentIndex(1)
    assert state.get_card_count('a') == expected
    assert len([p for p in preview._placements if p['name'] == 'a']) == expected
    assert sum(p['span'] for p in preview._placements) == expected + 2
    if manual:
        kept = next(p for p in preview._placements if p['copy_id'] == original['copy_id'])
        assert (kept['page'], kept['row'], kept['column']) == (1, 0, 0)
    saved = ProjectState.from_dict(state.to_persisted_dict())
    assert saved.get_card_count('a') == expected
    assert len([p for p in layout.resolve(saved, preview._columns, preview._rows)[0]
                if p['name'] == 'a']) == expected
    tabs.deleteLater()
    APP.processEvents()


def test_preview_context_menu_has_only_artwork_and_oversized(preview):
    menu = preview.card_context_menu('a')
    assert [action.text() for action in menu.actions()] == ['Change artwork…', 'Print oversized']
    assert menu.actions()[1].isCheckable()
    assert not menu.actions()[1].isChecked()
    wide_menu = preview.card_context_menu('wide')
    assert wide_menu.actions()[1].isChecked()
    menu.deleteLater()
    wide_menu.deleteLater()


def test_right_click_either_oversized_half_targets_same_card(preview, monkeypatch):
    names = []
    empty_slots = []
    menu = SimpleNamespace(exec=lambda pos: None, deleteLater=lambda: None)
    monkeypatch.setattr(preview, 'card_context_menu', lambda name: names.append(name) or menu)
    monkeypatch.setattr(
        preview, 'empty_slot_context_menu',
        lambda slot: empty_slots.append(slot) or menu)
    overlay = preview._overlays[0]
    wide = next(p for p in preview._placements if p['name'] == 'wide')
    for column in (wide['column'], wide['column'] + 1):
        point = center(overlay, wide['row'], column)
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Reason.Mouse, point, overlay.mapToGlobal(point))
        overlay.contextMenuEvent(event)
        assert event.isAccepted()
    point = center(overlay, 2, 2)
    empty_event = QtGui.QContextMenuEvent(
        QtGui.QContextMenuEvent.Reason.Mouse, point)
    overlay.contextMenuEvent(empty_event)
    assert names == ['wide', 'wide']
    assert empty_slots == [(0, 2, 2)]
    assert empty_event.isAccepted()


@pytest.mark.parametrize('accepted,applied', [(False, False), (True, False), (True, True)])
def test_preview_artwork_reuses_picker_and_refreshes_only_when_applied(preview, monkeypatch, accepted, applied):
    calls = []
    def picker(parent, state, images, name):
        assert parent is preview and state is preview._state and images is preview._img_dict and name == 'a'
        return SimpleNamespace(exec=lambda: QtWidgets.QDialog.DialogCode.Accepted if accepted else QtWidgets.QDialog.DialogCode.Rejected,
                               was_applied=lambda: applied)
    monkeypatch.setattr(editor_widgets, 'HighResPickerDialog', picker)
    monkeypatch.setattr(preview, 'refresh_after_edit', lambda: calls.append('refresh'))
    monkeypatch.setattr(editor_widgets, 'autosave_managed_session', lambda: calls.append('save'))
    before = preview._state.to_dict()
    preview.card_context_menu('a').actions()[0].trigger()
    assert calls == (['refresh', 'save'] if accepted and applied else [])
    assert preview._state.to_dict() == before


def test_preview_oversized_toggle_reconciles_copies_and_supports_undo(preview):
    before = preview._state.to_dict()
    preview.card_context_menu('a').actions()[1].trigger()
    assert preview._state.oversized['a']
    assert preview._state.get_card_entry('a').oversized
    copies = [p for p in preview._placements if p['name'] == 'a']
    assert len(copies) == 2 and all(p['span'] == 2 for p in copies)
    occupied = set()
    for item in preview._placements:
        assert layout.fits(item, occupied, preview._columns, preview._rows)
        occupied.update(layout.cells(item))
    loaded = ProjectState.from_dict(preview._state.to_persisted_dict())
    assert loaded.oversized['a']
    preview.undo_layout()
    assert preview._state.to_dict() == before
    preview.redo_layout()
    assert preview._state.oversized['a']
    preview.card_context_menu('a').actions()[1].trigger()
    assert not preview._state.oversized.get('a')
    assert all(p['span'] == 1 for p in preview._placements if p['name'] == 'a')


def test_preview_can_enable_oversized_mode_and_rejects_impossible_size(preview, monkeypatch):
    preview._state.oversized_enabled = False
    preview.refresh_after_edit()
    preview.set_card_oversized('a', True)
    assert preview._state.oversized_enabled
    preview.undo_layout()
    assert not preview._state.oversized_enabled
    before = preview._state.to_dict()
    preview._columns = 1
    warnings = []
    monkeypatch.setattr(editor_widgets.QMessageBox, 'warning', lambda *args: warnings.append(args))
    preview.set_card_oversized('a', True)
    assert preview._state.to_dict() == before
    assert len(warnings) == 1

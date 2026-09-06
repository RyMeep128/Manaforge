import os
import threading
from copy import deepcopy
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtCore, QtWidgets, QtTest
import pytest
import editor_widgets as widgets
from background_tasks import popup
from models import ProjectState
from services.card_edit_service import set_oversized
from services import layout_service

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize('dismiss', ['reject', 'close', 'accept', 'escape'])
def test_progress_dialog_cannot_leave_worker_running(dismiss):
    dialog = popup(None, 'Audit test', False)
    release = threading.Event()
    observations = []
    def try_dismiss():
        if dismiss == 'escape':
            QtTest.QTest.keyClick(dialog, QtCore.Qt.Key.Key_Escape)
        else:
            getattr(dialog, dismiss)()
        observations.append(dialog.isVisible())
        release.set()
    QtCore.QTimer.singleShot(20, try_dismiss)
    dialog.show_during_work(lambda: release.wait(2))
    assert observations == [True]
    assert dialog._thread is None
    assert not dialog.isVisible()
    dialog.deleteLater()
    APP.processEvents()


def test_progress_worker_failure_is_propagated_after_completion():
    dialog = popup(None, 'Failure test', False)
    def fail():
        raise ValueError('test failure')
    with pytest.raises(ValueError, match='test failure'):
        dialog.show_during_work(fail)
    assert dialog._thread is None
    dialog.deleteLater()
    APP.processEvents()


def test_empty_grid_placeholders_do_not_accumulate():
    state = ProjectState()
    grid = widgets.CardGrid(state, {})
    initial = grid.layout().count()
    for _ in range(5):
        grid.refresh(state, {})
        assert grid.layout().count() == initial
    grid.deleteLater()
    APP.processEvents()


@pytest.fixture
def collection(monkeypatch):
    state = ProjectState.from_dict({'cards': {'a': 2, 'b': 1, 'c': 1}})
    images = {name: dict(data=widgets.fallback.data, size=widgets.fallback.size,
                        effective_dpi=300) for name in state.cards}
    monkeypatch.setattr(widgets.runtime_images, 'ensure_preview_entry', lambda s, imgs, name: imgs.get(name))
    grid = widgets.CardGrid(state, images)
    area = widgets.CardScrollArea(state, images, grid)
    area.show()
    APP.processEvents()
    yield state, images, grid, area
    area.deleteLater()
    APP.processEvents()


def test_deleted_selection_is_removed_and_not_restored(collection):
    state, images, grid, area = collection
    grid._cards['a'].set_selected(True)
    state.remove_card('a')
    area.refresh(state, images)
    assert grid._selected_names == set()
    assert 'selected' not in area._selection_label.text()
    state.set_card_count('a', 1)
    area.refresh(state, images)
    assert not grid._cards['a']._selected


def test_selected_size_actions_only_change_selected_cards(collection):
    state, images, grid, area = collection
    grid._cards['a'].set_selected(True)
    grid._cards['b'].set_selected(True)
    assert area._bulk_button.isVisible()
    area._bulk_button.menu().actions()[0].trigger()
    assert state.oversized_enabled
    assert state.oversized == {'a': True, 'b': True}
    assert state.cards == {'a': 2, 'b': 1, 'c': 1}
    assert grid._selected_names == {'a', 'b'}
    resolved, _ = layout_service.resolve(state, 3, 3)
    assert all(p['span'] == (1 if p['name'] == 'c' else 2) for p in resolved)
    loaded = ProjectState.from_dict(state.to_persisted_dict())
    assert loaded.oversized == state.oversized
    area._bulk_button.menu().actions()[1].trigger()
    assert state.oversized == {}


def test_bulk_size_failure_is_atomic():
    state = ProjectState.from_dict({'cards': {'a': 2, 'b': 1}, 'pagesize': 'A5', 'bleed_edge': '10'})
    before = deepcopy(state)
    with pytest.raises(ValueError):
        set_oversized(state, ['a', 'b'], True)
    assert state == before


def test_serialization_does_not_rewrite_live_legacy_maps():
    state = ProjectState.from_dict({'cards': {'a': 2}})
    state.cards['a'] = 7  # Serialization uses canonical entries without repairing live maps.
    before = deepcopy(state)
    assert state.to_dict()['cards'] == {'a': 2}
    state.to_persisted_dict()
    assert state == before

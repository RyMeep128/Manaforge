import os
import time
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtWidgets, QtGui
import editor_widgets
import runtime_images
import config
from models import ProjectState

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_500_card_cache_warmup_uses_one_read_and_write(monkeypatch):
    state = ProjectState.from_dict({'cards': {f'card{i}': 1 for i in range(500)}})
    reads, writes, builds = [], [], []
    monkeypatch.setattr(runtime_images, '_load_preview_cache', lambda s: reads.append(s) or {})
    monkeypatch.setattr(runtime_images, '_save_preview_cache', lambda s, data: writes.append(dict(data)))
    monkeypatch.setattr(runtime_images, '_preview_cache_key', lambda s, name: (name, 'fp', name))
    def build(s, name):
        builds.append(name)
        return {'_asset_key': name, '_fingerprint': 'fp'}
    monkeypatch.setattr(runtime_images, '_build_preview_entry', build)
    images = {}
    runtime_images.warm_preview_entries(state, images, list(state.cards))
    assert len(reads) == len(writes) == 1
    assert len(builds) == len(images) == len(writes[0]) == 500


def test_batch_reuses_missing_back_but_retries_next_operation(monkeypatch):
    state = ProjectState()
    builds = []
    monkeypatch.setattr(runtime_images, '_load_preview_cache', lambda s: {})
    monkeypatch.setattr(runtime_images, '_build_preview_entry', lambda s, name: builds.append(name))
    with runtime_images.preview_batch(state):
        for _ in range(500):
            assert runtime_images.ensure_preview_entry(state, {}, '__missing') is None
    assert builds == ['__missing']
    runtime_images.ensure_preview_entry(state, {}, '__missing')
    assert len(builds) == 2


def test_500_card_grid_reuses_unchanged_widgets(monkeypatch):
    state = ProjectState.from_dict({'cards': {f'card{i}': 1 for i in range(500)}})
    data, size = editor_widgets.fallback.data, editor_widgets.fallback.size
    images = {name: dict(data=data, size=size, effective_dpi=300) for name in state.cards}
    monkeypatch.setattr(runtime_images, 'ensure_preview_entry', lambda s, images, name: images.get(name))
    started = time.perf_counter()
    grid = editor_widgets.CardGrid(state, images)
    initial_time = time.perf_counter() - started
    original = dict(grid._cards)
    state.set_card_count('card0', 2)
    started = time.perf_counter()
    grid.refresh(state, images)
    edit_time = time.perf_counter() - started
    assert grid._cards['card0'] is not original['card0']
    assert grid._cards['card0']._number_edit.text() == '2'
    assert all(grid._cards[name] is widget for name, widget in original.items() if name != 'card0')
    print(f'500-card grid: initial {initial_time:.3f}s; one-card edit {edit_time:.3f}s')
    before_sort = dict(grid._cards)
    state.card_sort = 'Alphabetical (Z-A)'
    grid.refresh(state, images)
    assert all(grid._cards[name] is widget for name, widget in before_sort.items())
    # New art replaces its widget; deleted entries leave the grid.
    images['card1'] = dict(images['card1'])
    state.remove_card('card2')
    grid.refresh(state, images)
    assert grid._cards['card1'] is not before_sort['card1']
    assert 'card2' not in grid._cards
    grid.deleteLater()
    APP.processEvents()


def test_decoded_preview_cache_reuses_pixmaps_and_distinguishes_rotation(monkeypatch):
    QtGui.QPixmapCache.clear()
    monkeypatch.setattr(editor_widgets.CFG, 'PreviewImageCacheMemoryMB', 32)
    data, size = editor_widgets.fallback.data, editor_widgets.fallback.size
    first = editor_widgets.CardImage(data, size)
    second = editor_widgets.CardImage(data, size)
    rotated = editor_widgets.CardImage(data, size, rotation=180)
    assert first.pixmap().cacheKey() == second.pixmap().cacheKey()
    assert first.pixmap().cacheKey() != rotated.pixmap().cacheKey()
    assert QtGui.QPixmapCache.cacheLimit() == 32 * 1024
    for widget in (first, second, rotated):
        widget.deleteLater()
    APP.processEvents()


def test_preview_memory_setting_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'cwd', str(tmp_path))
    cfg = config.GlobalConfig()
    cfg.PreviewImageCacheMemoryMB = 512
    config.save_config(cfg)
    assert config.load_config().PreviewImageCacheMemoryMB == 512

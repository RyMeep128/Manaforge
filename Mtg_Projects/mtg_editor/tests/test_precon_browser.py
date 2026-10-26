import time
from PyQt6 import QtCore as C, QtWidgets as W, QtTest
from mtg_core.precons import normalize_catalog


class Thumbnails(C.QObject):
    updated = C.pyqtSignal()

    def get(self, *args):
        return None

    def set_visible(self, *args):
        pass


def test_browser_filters_rename_and_original_preview(monkeypatch):
    from mtg_editor import precon_browser
    app = W.QApplication.instance() or W.QApplication([])
    records = normalize_catalog([dict(name='Original precon', set_name='Example product', set_code='abc',
        release_date='2024-01-01', format='commander',
        cards=[dict(name='Main card', count=99, set_code='abc', number='42')],
        commander=[dict(name='Featured commander', count=1, set_code='abc', number='1')])])['decks']
    monkeypatch.setattr(precon_browser, 'load_catalog', lambda: records)
    class Service:
        def get_card(self, **kwargs):
            return dict(id='card', color_identity=['U'], name=kwargs['exact_name'])
    dialog = precon_browser.PreconBrowser(Service(), Thumbnails())
    deadline = time.monotonic() + 3
    while (dialog.catalog_worker is not None or dialog.metadata_worker is not None) and time.monotonic() < deadline:
        app.processEvents()
        QtTest.QTest.qWait(5)
    assert dialog.catalog_worker is None
    assert dialog.decks.count() == 1
    assert '99 Main card (abc) 42 [mainboard]' in dialog.source.toPlainText()
    assert dialog.deck_name.text() == 'Original precon'
    dialog.deck_name.setText('My upgrades')
    assert dialog.record['name'] == 'Original precon'
    dialog.search.setText('Featured commander 2024')
    assert dialog.decks.count() == 1
    dialog.color_buttons['R'].setChecked(True)
    assert dialog.decks.count() == 0 and not dialog.apply_button.isEnabled()
    dialog.clear_colors()
    dialog.color_buttons['U'].setChecked(True)
    assert dialog.decks.count() == 1
    dialog.color_buttons['R'].setChecked(True)
    assert dialog.decks.count() == 0  # Selected colors are combined, not treated as alternatives.
    dialog.clear_colors()
    assert dialog.decks.count() == 1
    dialog.search.setText('Not a product')
    assert dialog.record is None and not dialog.resolve_button.isEnabled()
    dialog.reject()


def test_catalog_load_does_not_look_up_cards(monkeypatch):
    from mtg_editor import precon_browser
    records = normalize_catalog([dict(name='Fast deck', set_name='Product', set_code='abc',
        release_date='2024-01-01', format='commander',
        cards=[dict(name='Card', count=100)])])['decks']
    monkeypatch.setattr(precon_browser, 'load_catalog', lambda: records)
    class Service:
        def get_card(self, **kwargs):
            raise AssertionError('Initial catalog loading must not look up cards')
    worker = precon_browser.CatalogWorker(Service(), None)
    worker.run()
    assert not worker.error
    assert len(worker.records) == 1
    assert worker.records[0]['metadata_ready'] is False

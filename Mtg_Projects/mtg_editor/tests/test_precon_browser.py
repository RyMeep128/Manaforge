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
    while dialog.catalog_worker is not None and time.monotonic() < deadline:
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
    dialog.color_filter.setCurrentIndex(dialog.color_filter.findData('R'))
    assert dialog.decks.count() == 0 and not dialog.apply_button.isEnabled()
    dialog.color_filter.setCurrentIndex(dialog.color_filter.findData('U'))
    assert dialog.decks.count() == 1
    dialog.search.setText('Not a product')
    assert dialog.record is None and not dialog.resolve_button.isEnabled()
    dialog.reject()

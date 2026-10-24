from types import SimpleNamespace

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_editor.commander_discovery import DiscoveryController, DiscoveryWorker
from mtg_editor.search import SearchCache


def test_discovery_worker_emits_snapshot_without_card_page_arguments():
    app = W.QApplication.instance() or W.QApplication([])
    calls, delivered = [], []
    snapshot = {'themes': [], 'results': [], 'more': False, 'status': 'cached'}

    def search(query, *, should_cancel=None):
        calls.append(query)
        return snapshot

    service = SimpleNamespace(search_editor_cards=search)
    worker = DiscoveryWorker('query', service, cache=SearchCache())
    worker.completed.connect(lambda query, result, error: delivered.append((query, result, error)))
    worker.run()
    assert delivered == [('query', snapshot, '')]
    assert calls == ['query']
    worker.run()
    assert calls == ['query']
    worker.cancel()
    worker.run()
    assert len(delivered) == 2
    worker.deleteLater()
    app.processEvents()


def test_discovery_controller_does_not_treat_snapshot_as_card_results():
    app = W.QApplication.instance() or W.QApplication([])
    snapshot = {'themes': [], 'results': [], 'more': False, 'status': 'cached'}
    controller = DiscoveryController(SimpleNamespace(search_editor_cards=lambda query, **kwargs: snapshot))
    delivered = []
    loop = C.QEventLoop()
    controller.resultsReady.connect(lambda query, result, error: (delivered.append((result, error)), loop.quit()))
    controller.search('query')
    timeout = C.QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    timeout.start(3000)
    loop.exec()
    timeout.stop()
    controller.shutdown()
    if controller.worker is not None:
        controller.worker.wait(3000)
    app.processEvents()
    assert delivered == [(snapshot, '')]
    controller.deleteLater()

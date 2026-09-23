from threading import Event
from time import monotonic
from types import SimpleNamespace

from PyQt6 import QtTest, QtWidgets as W

from mtg_editor.search import SearchCache, SearchWorker


def test_cache_expires_evicts_and_isolates_results():
    now = [0]
    cache = SearchCache(capacity=2, ttl=30, clock=lambda: now[0])
    results = [{'name': 'A'}]
    cache.put('A', results)
    results[0]['name'] = 'changed'
    copy = cache.get('A')
    copy[0]['name'] = 'also changed'
    assert cache.get('A') == [{'name': 'A'}]
    cache.put('B', [])
    cache.get('A')
    cache.put('C', [])
    assert cache.get('B') is None
    assert cache.get('C') == []
    now[0] = 30
    assert cache.get('A') is None


def test_worker_cache_refresh_errors_and_cancel():
    app = W.QApplication.instance() or W.QApplication([])
    calls = []

    def search(query, **kwargs):
        calls.append(query)
        if query == 'bad':
            raise ValueError('Invalid query')
        return []

    service = SimpleNamespace(search_editor_cards=search)
    cache = SearchCache()
    for query, refresh in [('ok', False), ('ok', False), ('ok', True), ('bad', False)]:
        worker = SearchWorker(query, service, cache=cache, refresh=refresh)
        observed = []
        worker.completed.connect(lambda *args: observed.append(args))
        worker.run()
        assert len(observed) == 1
    assert calls == ['ok', 'ok', 'bad']
    assert cache.get('bad') is None
    worker = SearchWorker('cancelled', service, cache=cache)
    worker.cancel()
    worker.run()
    assert 'cancelled' not in calls
    app.processEvents()


def wait_until(app, predicate):
    deadline = monotonic() + 3
    while not predicate() and monotonic() < deadline:
        app.processEvents()
        QtTest.QTest.qWait(5)
    assert predicate()


def test_query_replacement_clear_and_close_cancel_running_work(tmp_path):
    from mtg_editor.gui import EditorWindow
    app = W.QApplication.instance() or W.QApplication([])
    started = Event()
    calls = []

    def search(query, *, should_cancel):
        calls.append(query)
        if query == 'slow':
            started.set()
            deadline = monotonic() + 3
            while not should_cancel() and monotonic() < deadline:
                Event().wait(0.005)
            assert should_cancel()
        # Even a service returning stale data after cancellation must be ignored.
        return []

    window = EditorWindow(service=SimpleNamespace(search_editor_cards=search), root=tmp_path)
    window.query.setText('slow')
    window.search()
    wait_until(app, started.is_set)
    window.query.setText('new')
    window.search()
    wait_until(app, lambda: window.worker is None and calls == ['slow', 'new'])
    assert 'local matches' in window.search_status.text()
    started.clear()
    window.query.setText('slow')
    window.search()
    wait_until(app, started.is_set)
    window.query.clear()
    wait_until(app, lambda: window.worker is None)
    assert not window.search_timer.isActive()
    assert window.search_document.deck.entries == []
    started.clear()
    window.query.setText('slow')
    window.search()
    wait_until(app, started.is_set)
    window.close()
    wait_until(app, lambda: window.worker is None)
    assert not window.pending_search and not window.search_timer.isActive()
    window.close()
    app.processEvents()

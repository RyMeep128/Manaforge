"""Controller lifecycle coverage without constructing an EditorWindow."""
from time import monotonic
from types import SimpleNamespace

from PyQt6 import QtTest, QtWidgets

from mtg_editor.search import SearchController
from mtg_editor.tasks import EditorTaskRunner


def wait_until(app, predicate):
    deadline = monotonic() + 3
    while not predicate() and monotonic() < deadline:
        app.processEvents()
        QtTest.QTest.qWait(5)
    assert predicate()


def test_task_runner_rejects_overlap_and_recovers_from_callback_error():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    runner = EditorTaskRunner()
    errors, busy, settled, results = [], [], [], []
    runner.failed.connect(errors.append)
    runner.busyChanged.connect(busy.append)
    runner.settled.connect(lambda: settled.append(True))

    def fail(result):
        raise ValueError('Could not apply result')

    assert runner.start(lambda: 42, fail, context={'deck_id': 'example'})
    assert not runner.start(lambda: 99, results.append)
    wait_until(app, lambda: runner.task is None)
    assert errors == ['Could not apply result']
    assert busy == [True, False]
    assert settled == [True]
    assert runner.start(lambda: 7, results.append)
    wait_until(app, lambda: runner.task is None)
    assert results == [7]


def test_search_controller_refresh_debounce_and_shutdown():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    calls, results = [], []

    def search(query, **kwargs):
        calls.append(query)
        return []

    controller = SearchController(SimpleNamespace(search_editor_cards=search))
    controller.resultsReady.connect(lambda query, rows, error: results.append(query))
    for refresh in (False, False, True):
        controller.search('card', refresh=refresh)
        wait_until(app, lambda: controller.worker is None)
    assert calls == ['card', 'card']
    assert results == ['card'] * 3
    controller.change_query('pending')
    assert controller.timer.isActive()
    controller.shutdown()
    assert not controller.timer.isActive() and not controller.pending
    controller.search('ignored')
    assert controller.worker is None
    controller.resume()
    controller.search('resumed')
    wait_until(app, lambda: controller.worker is None)
    assert calls == ['card', 'card', 'resumed']

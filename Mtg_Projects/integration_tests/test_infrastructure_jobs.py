import time
from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.downloads import DownloadCancelled
from mtg_ui.jobs import JobQueue


def drain(app, condition):
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert condition()


class Receiver(C.QObject):
    def __init__(self):
        super().__init__()
        self.events = []

    @C.pyqtSlot(str, str, object)
    def receive(self, job_id, state, result):
        assert C.QThread.currentThread() == self.thread()
        self.events.append((job_id, state, result))


def test_jobs_queue_reports_failures_and_keeps_callbacks_on_gui_thread():
    app = W.QApplication.instance() or W.QApplication([])
    queue, receiver = JobQueue(), Receiver()
    queue.status.connect(receiver.receive)
    order = []

    def first(cancel, progress):
        assert C.QThread.currentThread() != receiver.thread()
        order.append(1)
        progress("downloaded")
        return "ready"

    def second(cancel, progress):
        order.append(2)
        raise ValueError("Corrupt archive")

    queue.submit(first)
    queue.submit(second)
    drain(app, lambda: not queue.busy)
    assert order == [1, 2]
    assert [e[1] for e in receiver.events].count("completed") == 1
    assert [e[1] for e in receiver.events].count("failed") == 1
    assert queue.shutdown()


def test_shutdown_cancels_active_and_pending_jobs_without_destroying_thread():
    app = W.QApplication.instance() or W.QApplication([])
    queue, receiver = JobQueue(), Receiver()
    queue.status.connect(receiver.receive)

    def cancellable(cancel, progress):
        cancel.wait(5)
        if cancel.is_set():
            raise DownloadCancelled()

    first = queue.submit(cancellable)
    app.processEvents()
    pending = queue.submit(lambda *args: "must not run")
    assert not queue.shutdown()
    drain(app, lambda: not queue.busy)
    assert queue.shutdown()
    assert {e[0] for e in receiver.events if e[1] == "cancelled"} == {first, pending}

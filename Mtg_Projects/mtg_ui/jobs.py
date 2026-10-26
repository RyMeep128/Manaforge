"""Sequential Qt queue. Work receives (cancel_event, report_progress).

Create/use on the GUI thread, connect signals to QObject slots, and keep the
owner alive until shutdown() returns True. Workers never manipulate widgets.
"""

from mtg_ui.loading import LoadingThread
from collections import deque
import threading
import time
import uuid

from PyQt6 import QtCore as C
from mtg_core.diagnostics import get_logger
from mtg_core.downloads import DownloadCancelled


class _Job(LoadingThread):
    progress = C.pyqtSignal(str, object)
    outcome = C.pyqtSignal(str, str, object)

    def __init__(self, job_id, work, parent):
        super().__init__(parent)
        self.job_id, self.work = job_id, work
        self.cancel_event = threading.Event()
        self._last_progress = 0.0
        self._last_phase = None
        self.operation = "Background operation"

    def report(self, value):
        if isinstance(value, dict):
            self.operation = value.get("operation", self.operation)
            phase = (
                value.get("operation"),
                value.get("phase"),
                value.get("stage"),
                value.get("task_state"),
            )
            current, total = value.get("current"), value.get("total")
        else:
            phase = getattr(value, "phase", None)
            current, total = (
                getattr(value, "downloaded", None),
                getattr(value, "total", None),
            )
        now = time.monotonic()
        if (
            phase != self._last_phase
            or now - self._last_progress >= 0.1
            or (total is not None and current == total)
        ):
            self.progress.emit(self.job_id, value)
            self._last_progress, self._last_phase = now, phase

    def run(self):
        from mtg_core.repair import record_operation

        try:
            if self.cancel_event.is_set():
                raise DownloadCancelled()
            result = self.work(self.cancel_event, self.report)
            record_operation(self.operation, "completed")
            self.outcome.emit(self.job_id, "completed", result)
        except DownloadCancelled:
            record_operation(self.operation, "cancelled")
            self.outcome.emit(self.job_id, "cancelled", None)
        except Exception as exc:
            record_operation(self.operation, "failed", str(exc))
            get_logger(__name__).error(
                "Background job failed id=%s type=%s", self.job_id, type(exc).__name__
            )
            self.outcome.emit(self.job_id, "failed", str(exc))


class JobQueue(C.QObject):
    progress = C.pyqtSignal(str, object)
    status = C.pyqtSignal(str, str, object)
    idle = C.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = deque()
        self._active = None
        self._closing = False
        self.latest_progress = None

    @property
    def busy(self):
        return self._active is not None or bool(self._pending)

    @property
    def current_id(self):
        return (
            self._active.job_id
            if self._active
            else self._pending[0][0]
            if self._pending
            else None
        )

    def submit(self, work):
        if self._closing:
            raise RuntimeError("Background queue is shutting down")
        job_id = uuid.uuid4().hex
        self._pending.append((job_id, work))
        self.status.emit(job_id, "queued", None)
        C.QTimer.singleShot(0, self._start_next)
        return job_id

    def cancel(self, job_id):
        if self._active and self._active.job_id == job_id:
            self._active.cancel_event.set()
        else:
            for entry in tuple(self._pending):
                if entry[0] == job_id:
                    self._pending.remove(entry)
                    self.status.emit(job_id, "cancelled", None)

    def shutdown(self):
        self._closing = True
        self.cancel_all()
        return not self.busy

    def cancel_all(self):
        """Cancel current work while allowing future jobs if window close is vetoed."""
        for job_id, _ in tuple(self._pending):
            self.cancel(job_id)
        if self._active:
            self._active.cancel_event.set()

    @C.pyqtSlot()
    def _start_next(self):
        if self._active or not self._pending or self._closing:
            return
        job_id, work = self._pending.popleft()
        self.latest_progress = None
        self._active = _Job(job_id, work, self)
        self._active.progress.connect(
            self._progress, C.Qt.ConnectionType.QueuedConnection
        )
        self._active.outcome.connect(
            self._outcome, C.Qt.ConnectionType.QueuedConnection
        )
        self._active.finished.connect(
            self._finished, C.Qt.ConnectionType.QueuedConnection
        )
        self.status.emit(job_id, "running", None)
        self._active.start()

    @C.pyqtSlot(str, object)
    def _progress(self, job_id, value):
        self.latest_progress = value
        self.progress.emit(job_id, value)

    @C.pyqtSlot(str, str, object)
    def _outcome(self, job_id, state, value):
        self.status.emit(job_id, state, value)

    @C.pyqtSlot()
    def _finished(self):
        self._active.deleteLater()
        self._active = None
        if self._pending and not self._closing:
            self._start_next()
        else:
            self.idle.emit()

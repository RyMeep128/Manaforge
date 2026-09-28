"""Background task execution and lifecycle for the editor."""
from PyQt6 import QtCore
from mtg_core.diagnostics import get_logger


class Task(QtCore.QThread):
    completed = QtCore.pyqtSignal(object, str)

    def __init__(self, work, parent=None, *, operation=None, context=None):
        super().__init__(parent)
        self.work = work
        self.operation = operation or getattr(work, '__qualname__', type(work).__name__)
        self.context = context or {}

    def run(self):
        try:
            self.completed.emit(self.work(), '')
        except Exception as exc:
            get_logger(__name__).exception('Background task failed operation=%s context=%s',
                                           self.operation, self.context)
            self.completed.emit(None, str(exc))


class EditorTaskRunner(QtCore.QObject):
    busyChanged = QtCore.pyqtSignal(bool)
    failed = QtCore.pyqtSignal(str)
    settled = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task = None
        self._callback = None

    def start(self, work, callback, *, context=None):
        if self.task is not None:
            return False
        operation = getattr(callback, '__qualname__', type(callback).__name__)
        self.task = Task(work, self, operation=operation, context=context)
        self._callback = callback
        self.task.completed.connect(self._completed)
        self.task.finished.connect(self._finished)
        self.busyChanged.emit(True)
        self.task.start()
        return True

    def _completed(self, result, error):
        if self.sender() is not self.task:
            return
        # Dialog callbacks can run nested event loops and deliver finished.
        task, callback = self.task, self._callback
        operation, context = task.operation, task.context
        self.busyChanged.emit(False)
        try:
            if error:
                self.failed.emit(error)
            else:
                callback(result)
        except (OSError, ValueError, TypeError) as exc:
            get_logger(__name__).exception(
                'Background result failed operation=%s context=%s',
                operation, context)
            self.failed.emit(str(exc))
        finally:
            self.settled.emit()

    def _finished(self):
        if self.sender() is not self.task:
            return
        self.task.deleteLater()
        self.task = None
        self._callback = None

"""Bounded recent results and cancellable local editor searches."""
from collections import OrderedDict
from copy import deepcopy
from mtg_core.diagnostics import get_logger
from threading import Event
from time import monotonic

from PyQt6 import QtCore
from mtg_core.search.cancellation import SearchCancelled, check_cancelled


class SearchCache:
    def __init__(self, capacity=20, ttl=30, clock=monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.entries = OrderedDict()

    def get(self, query):
        cached = self.entries.get(query)
        if cached is None:
            return None
        created, results = cached
        if self.clock() - created >= self.ttl:
            del self.entries[query]
            return None
        self.entries.move_to_end(query)
        return deepcopy(results)

    def put(self, query, results):
        self.entries[query] = (self.clock(), deepcopy(results))
        self.entries.move_to_end(query)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)


class SearchWorker(QtCore.QThread):
    completed = QtCore.pyqtSignal(str, object, str)

    def __init__(self, query, service, parent=None, *, cache=None, refresh=False):
        super().__init__(parent)
        self.query, self.service = query, service
        self.cache, self.refresh = cache, refresh
        self.cancelled = Event()

    def cancel(self):
        self.cancelled.set()

    def run(self):
        try:
            check_cancelled(self.cancelled.is_set)
            results = None if self.refresh or self.cache is None else self.cache.get(self.query)
            if results is None:
                results = self.service.search_editor_cards(self.query, should_cancel=self.cancelled.is_set)
                check_cancelled(self.cancelled.is_set)
                if self.cache is not None:
                    self.cache.put(self.query, results)
            check_cancelled(self.cancelled.is_set)
            self.completed.emit(self.query, results, '')
        except SearchCancelled:
            pass
        except Exception as exc:
            if not self.cancelled.is_set():
                get_logger(__name__).exception('Local card search failed query=%r', self.query)
                self.completed.emit(self.query, [], str(exc))


class SearchController(QtCore.QObject):
    """Own debouncing, one worker, cache, and obsolete-result suppression.

    Presentation subscribes to signals; workers never access widgets. A pending
    query starts only after the previous worker exits and its debounce expires.
    """
    resultsReady = QtCore.pyqtSignal(str, object, str)
    statusChanged = QtCore.pyqtSignal(str)
    busyChanged = QtCore.pyqtSignal(bool)
    cleared = QtCore.pyqtSignal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.cache = SearchCache()
        self.worker = None
        self.query = ''
        self.pending = self.refresh = self.closing = False
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.search)

    def change_query(self, query):
        self.cancel()
        self.query = query.strip()
        self.cleared.emit()
        if self.query and not self.closing:
            self.pending = True
            self.timer.start(350)
        else:
            self.statusChanged.emit('Search by name or Scryfall syntax')

    def cancel(self):
        self.timer.stop()
        self.pending = self.refresh = False
        if self.worker is not None:
            self.worker.cancel()
        self.busyChanged.emit(False)
        self.statusChanged.emit('Search cancelled')

    def search(self, query=None, *, refresh=False):
        self.timer.stop()
        if self.closing:
            return
        if query is not None:
            self.query = query.strip()
        self.refresh = self.refresh or refresh
        if self.worker is not None:
            self.worker.cancel()
            self.pending = True
            return
        self.pending = False
        if not self.query:
            self.refresh = False
            self.cleared.emit()
            self.statusChanged.emit('Search by name or Scryfall syntax')
            return
        self.statusChanged.emit('Searching local database...')
        self.busyChanged.emit(True)
        self.worker = SearchWorker(self.query, self.service, self,
                                   cache=self.cache, refresh=self.refresh)
        self.refresh = False
        self.worker.completed.connect(self._completed)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _completed(self, query, results, error):
        worker = self.sender()
        if (worker is self.worker and not worker.cancelled.is_set()
                and not self.closing and query == self.query):
            self.resultsReady.emit(query, results, error)

    def _finished(self):
        if self.sender() is not self.worker:
            return
        self.worker.deleteLater()
        self.worker = None
        self.busyChanged.emit(False)
        if self.pending and not self.closing and not self.timer.isActive():
            self.timer.start(0)

    def shutdown(self):
        self.closing = True
        self.cancel()

    def resume(self):
        """Allow new queries after the window rejects a close (e.g. failed save)."""
        self.closing = False

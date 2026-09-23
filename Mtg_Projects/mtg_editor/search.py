"""Bounded recent results and cancellable local editor searches."""
from collections import OrderedDict
from copy import deepcopy
import logging
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
                logging.getLogger(__name__).exception('Local card search failed query=%r', self.query)
                self.completed.emit(self.query, [], str(exc))

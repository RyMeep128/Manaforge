"""Bounded, seat-scoped artwork using the existing asynchronous image reader."""

from collections import OrderedDict
import time
from PyQt6 import QtCore as C, QtGui as G
from .artwork_cache import (
    PlayImageReader,
    RENDER_VERSION,
    CARD_RESOLUTION,
    INSPECTION_RESOLUTION,
)


class PlayArtwork(C.QObject):
    updated = C.pyqtSignal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.cache = OrderedDict()
        self.pending = OrderedDict()
        self.worker = None
        self.generation = 0
        self.worker_generation = -1
        self.allowed = set()
        self.stopping = False
        self.paused_until = 0
        self.next_timer = C.QTimer(self)
        self.next_timer.setSingleShot(True)
        self.next_timer.timeout.connect(self._next)

    @staticmethod
    def key(obj, *, detailed=False):
        if (
            obj.hidden
            or obj.face_down
            or not obj.card_identity
            or not obj.card_identity.printing_id
        ):
            return None
        face = int(
            bool(
                obj.characteristics
                and (obj.characteristics.transformed or obj.characteristics.flipped)
            )
        )
        key = (
            obj.card_identity.printing_id,
            None,
            INSPECTION_RESOLUTION if detailed else CARD_RESOLUTION,
            face,
        )
        return (
            key + (RENDER_VERSION,)
            if obj.zone == "battlefield" and not detailed
            else key
        )

    def show_objects(self, objects):
        self.allowed = {
            key
            for obj in objects
            for key in (self.key(obj), self.key(obj, detailed=True))
            if key
        }
        for key in tuple(self.pending):
            if key not in self.allowed:
                self.pending.pop(key)

    def get(self, obj, *, detailed=False):
        key = self.key(obj, detailed=detailed)
        if not key or key not in self.allowed:
            return None
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if not self.stopping and (self.worker is None or self.worker.key != key):
            self.pending[key] = None
            while len(self.pending) > 100:
                self.pending.popitem(last=False)
            self._next()
        return None

    def _next(self):
        if self.stopping or self.worker or not self.pending:
            return
        if time.monotonic() < self.paused_until:
            self.next_timer.start(
                max(1, int((self.paused_until - time.monotonic()) * 1000))
            )
            return
        key, _ = self.pending.popitem(last=False)
        self.worker_generation = self.generation
        self.worker = PlayImageReader(self.service, key, self)
        self.worker.loaded.connect(self._loaded, C.Qt.ConnectionType.QueuedConnection)
        self.worker.failed.connect(self._failed, C.Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(
            self._finished, C.Qt.ConnectionType.QueuedConnection
        )
        self.worker.start()

    @C.pyqtSlot(object, G.QImage)
    def _loaded(self, key, image):
        if self.worker_generation != self.generation or key not in self.allowed:
            return
        self.cache[key] = G.QPixmap.fromImage(image)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        self.updated.emit()

    @C.pyqtSlot(object, str, float)
    def _failed(self, key, error, delay):
        self.paused_until = max(self.paused_until, time.monotonic() + delay)

    @C.pyqtSlot()
    def _finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.paused_until = max(self.paused_until, time.monotonic() + 0.15)
        self._next()

    def conceal(self):
        self.generation += 1
        self.allowed.clear()
        self.pending.clear()
        self.cache.clear()
        self.next_timer.stop()

    def shutdown(self):
        self.stopping = True
        self.conceal()
        return self.worker is None

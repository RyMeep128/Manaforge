"""Virtual card painting with a bounded cache and one background image reader."""
from collections import OrderedDict
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path

from PyQt6 import QtCore, QtGui


class ImageReader(QtCore.QThread):
    loaded = QtCore.pyqtSignal(object, QtGui.QImage)
    failed = QtCore.pyqtSignal(object, str, float)

    def __init__(self, service, key, parent):
        super().__init__(parent)
        self.service, self.key = service, key

    def run(self):
        image = QtGui.QImage()
        try:
            card_id, asset_id = self.key
            if asset_id:
                data = self.service.get_image_bytes(asset_id)
                buffer = QtCore.QBuffer()
                buffer.setData(data or b'')
                buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
                reader = QtGui.QImageReader(buffer)
            else:
                path = self.service.get_image_path(card_id) if card_id else None
                if path and not Path(path).is_file():
                    path = None
                if not path and card_id and hasattr(self.service, 'ensure_image'):
                    path = self.service.ensure_image(card_id, allow_remote=True)
                reader = QtGui.QImageReader(str(path or ''))
            size = reader.size()
            if size.isValid():
                size.scale(300, 420, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
            image = reader.read()
        except Exception as exc:
            delay = 0
            cause = exc
            while cause:
                if getattr(cause, 'code', None) == 429:
                    raw = cause.headers.get('Retry-After', '60')
                    try:
                        delay = max(1, float(raw))
                    except ValueError:
                        try:
                            delay = max(1, (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError):
                            delay = 60
                cause = cause.__cause__
            self.failed.emit(self.key, str(exc), delay)
        self.loaded.emit(self.key, image)


class Thumbnails(QtCore.QObject):
    updated = QtCore.pyqtSignal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.cache = OrderedDict()
        self.pending = OrderedDict()
        self.worker = None
        self.stopping = False
        self.errors = {}
        self.paused_until = 0
        self.visible = {}
        self.next_timer = QtCore.QTimer(self)
        self.next_timer.setSingleShot(True)
        self.next_timer.timeout.connect(self.start_next)

    def set_visible(self, owner, keys):
        self.visible[owner] = set(keys)
        wanted = set().union(*self.visible.values())
        for key in list(self.pending):
            if key not in wanted:
                self.pending.pop(key, None)

    def retry(self, card_id, asset_id=None):
        key = (card_id, asset_id)
        self.cache.pop(key, None)
        self.errors.pop(key, None)
        self.updated.emit()

    def get(self, card_id, asset_id=None):
        key = (card_id, asset_id)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if not self.stopping and (self.worker is None or self.worker.key != key):
            self.pending[key] = None
            while len(self.pending) > 100:
                self.pending.popitem(last=False)
            self.start_next()
        return None

    def start_next(self):
        if self.stopping or self.worker is not None or not self.pending:
            return
        if time.monotonic() < self.paused_until:
            self.next_timer.start(max(1, int((self.paused_until-time.monotonic())*1000)))
            return
        key, _ = self.pending.popitem(last=True)
        self.worker = ImageReader(self.service, key, self)
        self.worker.loaded.connect(self.loaded)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def failed(self, key, error, delay):
        self.errors[key] = error
        self.paused_until = max(self.paused_until, time.monotonic() + delay)

    def loaded(self, key, image):
        self.cache[key] = QtGui.QPixmap.fromImage(image)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        self.updated.emit()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.paused_until = max(self.paused_until, time.monotonic() + .15)
        self.next_timer.start(150)

    def stop(self):
        self.stopping = True
        self.pending.clear()
        self.next_timer.stop()
        if self.worker is not None:
            self.worker.wait()


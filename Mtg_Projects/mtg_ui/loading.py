"""Application-wide loading indicator shared by threads and pool work."""
from functools import wraps

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W


class LoadingIndicator(W.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(C.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName('Loading')
        self.setToolTip('Loading…')
        self.resize(126, 36)
        self.angle = 0

    def paintEvent(self, event):
        painter = G.QPainter(self)
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        painter.setPen(C.Qt.PenStyle.NoPen)
        painter.setBrush(G.QColor('#202631'))
        painter.drawRoundedRect(self.rect(), 8, 8)
        pen = G.QPen(G.QColor('#55dfaa'), 3)
        pen.setCapStyle(C.Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(C.QRectF(10, 8, 20, 20), -self.angle * 16, 260 * 16)
        painter.setPen(G.QColor('#f5f5f5'))
        painter.drawText(C.QRect(40, 0, 82, 36), C.Qt.AlignmentFlag.AlignVCenter, 'Loading…')


class _Activity(C.QObject):
    def __init__(self, app):
        super().__init__(app)
        self.count = 0
        self.indicator = None
        self.timer = C.QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.refresh)

    @C.pyqtSlot()
    def begin(self):
        self.count += 1
        self.timer.start()
        self.refresh()

    @C.pyqtSlot()
    def end(self):
        self.count = max(0, self.count - 1)
        if not self.count:
            self.timer.stop()
            if self.indicator is not None:
                self.indicator.hide()

    def refresh(self):
        window = W.QApplication.activeModalWidget() or W.QApplication.activeWindow()
        # Background activity does not belong to a completed result/confirmation
        # message. A queued timer refresh must also never show idle activity.
        if not self.count or window is None or isinstance(window, W.QMessageBox):
            if self.indicator is not None:
                self.indicator.hide()
            return
        if self.indicator is None or self.indicator.parentWidget() is not window:
            if self.indicator is not None:
                self.indicator.deleteLater()
            self.indicator = LoadingIndicator(window)
            # The parent may close while other work continues.
            self.indicator.destroyed.connect(
                lambda _=None, indicator=self.indicator: self._indicator_destroyed(indicator))
        self.indicator.move(max(0, window.width() - self.indicator.width() - 16), 12)
        self.indicator.angle = (self.indicator.angle + 12) % 360
        self.indicator.show()
        self.indicator.raise_()
        self.indicator.update()

    def _indicator_destroyed(self, obj):
        if self.indicator is obj:
            self.indicator = None


def _activity():
    app = W.QApplication.instance()
    if not isinstance(app, W.QApplication):
        return None
    if not hasattr(app, '_loading_activity'):
        app._loading_activity = _Activity(app)
    return app._loading_activity


class LoadingThread(C.QThread):
    """Balance activity even when a worker fails or is cancelled."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        activity = _activity()
        if activity is not None:
            self.started.connect(activity.begin, C.Qt.ConnectionType.QueuedConnection)
            self.finished.connect(activity.end, C.Qt.ConnectionType.QueuedConnection)


class _PoolSignals(C.QObject):
    started = C.pyqtSignal()
    finished = C.pyqtSignal()


class LoadingRunnable(C.QRunnable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._activity_signals = _PoolSignals()
        activity = _activity()
        if activity is not None:
            self._activity_signals.started.connect(activity.begin, C.Qt.ConnectionType.QueuedConnection)
            self._activity_signals.finished.connect(activity.end, C.Qt.ConnectionType.QueuedConnection)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        run = cls.__dict__.get('run')
        if run is None:
            return

        @wraps(run)
        def tracked(self):
            self._activity_signals.started.emit()
            try:
                return run(self)
            finally:
                self._activity_signals.finished.emit()

        cls.run = tracked

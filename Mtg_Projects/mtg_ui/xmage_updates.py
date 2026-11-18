"""Shared optional engine updates, independent of the application installer."""
import threading
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_play import component_updates as service
from mtg_core.downloads import DownloadCancelled


def show_xmage_updates(parent=None):
    dialog = W.QDialog(parent)
    dialog.setWindowTitle("XMage Updates")
    dialog.resize(480, 280)
    layout = W.QVBoxLayout(dialog)
    layout.addWidget(XmageUpdatePanel(dialog))
    close = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    dialog.exec()


class EngineWorker(C.QThread):
    progress = C.pyqtSignal(object)
    outcome = C.pyqtSignal(object, str)

    def __init__(self, action, offer, parent):
        super().__init__(parent)
        self.action, self.offer = action, offer
        self.cancel = threading.Event()

    def run(self):
        try:
            if self.action == "check":
                result = service.check(cancel=self.cancel)
            elif self.action == "install":
                result = service.install(self.offer, cancel=self.cancel, progress=self.progress.emit)
            else:
                result = service.rollback(cancel=self.cancel, progress=self.progress.emit)
            self.outcome.emit(result, "")
        except DownloadCancelled:
            self.outcome.emit(None, "Cancelled. Retry to resume the download.")
        except Exception as error:
            self.outcome.emit(None, str(error))


class EngineUpdates(C.QObject):
    changed = C.pyqtSignal()

    def __init__(self, app):
        super().__init__(app)
        self.worker = None
        self.offer = None
        self.message = "XMage updates have not been checked."
        self.progress = None
        try:
            installed = service.installed_manifest()
            self.installed_version = installed["component_version"] if installed else "Not bundled in this source checkout"
        except (OSError, ValueError, KeyError) as error:
            self.installed_version = str(error)
        app.aboutToQuit.connect(self.shutdown)

    def shutdown(self):
        if self.worker:
            self.worker.cancel.set()
            self.worker.wait()

    def start(self, action):
        if self.worker:
            self.worker.cancel.set()
            self.message = "Cancelling XMage operation…"
            self.changed.emit()
            return
        self.progress = None
        self.worker = EngineWorker(action, self.offer, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.outcome.connect(self.on_outcome)
        self.worker.finished.connect(self.finished)
        self.message = {"check": "Checking XMage releases…", "install": "Downloading XMage…",
                        "rollback": "Verifying previous XMage engine…"}[action]
        self.worker.start()
        self.changed.emit()

    def on_progress(self, value):
        self.progress = value
        if isinstance(value, dict):
            self.message = value.get("phase", "Working…")
        else:
            self.message = f"Downloading XMage: {value.downloaded / 1024**2:.1f} MiB"
            if value.total:
                self.message += f" / {value.total / 1024**2:.1f} MiB"
            self.message += f" · {value.bytes_per_second / 1024**2:.1f} MiB/s"
        self.changed.emit()

    def on_outcome(self, value, error):
        action = self.worker.action
        if error:
            self.message = error
        elif action == "check":
            self.offer = value
            self.message = (f"Available: {value['component_version']} · {value['size'] / 1024**2:.1f} MiB"
                            if value else "XMage is up to date.")
        else:
            self.offer = None
            self.installed_version = value["component_version"]
            self.message = "XMage is ready for the next game."
        self.changed.emit()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.changed.emit()


class XmageUpdatePanel(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        app = W.QApplication.instance()
        if not hasattr(app, "_xmage_updates"):
            app._xmage_updates = EngineUpdates(app)
        self.updates = app._xmage_updates
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = W.QProgressBar()
        layout.addWidget(self.bar)
        self.check = W.QPushButton("Check for XMage Updates")
        self.check.clicked.connect(lambda: self.updates.start("check"))
        layout.addWidget(self.check)
        self.install = W.QPushButton("Update XMage")
        self.install.clicked.connect(lambda: self.updates.start("install"))
        layout.addWidget(self.install)
        self.revert = W.QPushButton("Revert to Previous Engine")
        self.revert.clicked.connect(lambda: self.updates.start("rollback"))
        layout.addWidget(self.revert)
        self.updates.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        updates = self.updates
        self.status.setText(f"XMage · Installed: {updates.installed_version}\n{updates.message}")
        busy = updates.worker is not None
        self.check.setText("Cancel XMage Operation" if busy else "Check for XMage Updates")
        self.install.setVisible(updates.offer is not None)
        self.install.setEnabled(not busy)
        self.revert.setEnabled(not busy and (service.runtime.component_root() / "active.json").is_file())
        self.bar.setVisible(busy)
        p = updates.progress
        if p is not None and not isinstance(p, dict) and p.total:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(100 * p.downloaded / p.total))
        else:
            self.bar.setRange(0, 0)

"""Shared application-release checking, transfer progress, and installer handoff."""
import time
import threading
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_proxy.constants import APP_VERSION
from mtg_print import update_service
from mtg_print import application_install


class InstallWorker(C.QThread):
    progress = C.pyqtSignal(object)
    completed = C.pyqtSignal(object, str)

    def __init__(self, result=None, initialize=None, parent=None):
        super().__init__(parent)
        self.result, self.initialize = result, initialize
        self.cancel = threading.Event()

    def run(self):
        try:
            if self.initialize is not None:
                value = application_install.finish_startup(APP_VERSION, cancel=self.cancel,
                    report=lambda value: None, initialize=self.initialize)
            else:
                value = application_install.prepare(self.result, cancel=self.cancel,
                                                     progress=self.progress.emit)
            self.completed.emit(value, '')
        except Exception as exc:
            self.completed.emit(None, str(exc))


class ReleaseWorker(C.QThread):
    checked = C.pyqtSignal(object, str)

    def run(self):
        try:
            result = update_service.check_for_update(APP_VERSION, cancelled_fn=self.isInterruptionRequested)
        except Exception as exc:
            self.checked.emit(None, str(exc))
        else:
            self.checked.emit(result, '')


class ApplicationUpdates(C.QObject):
    changed = C.pyqtSignal()

    def __init__(self, app):
        super().__init__(app)
        self.worker = None
        self.result = None
        self.error = ''
        self.manual = False
        self.install_worker = None
        self.install_value = None
        self.install_error = ''
        self.phase = ''
        self.detail = ''
        self.download_progress = None
        self.settings = C.QSettings('Manaforge', 'ApplicationUpdates')
        self.last_attempt = 0
        app.aboutToQuit.connect(self.wait_for_worker)

    @property
    def checking(self):
        return self.worker is not None

    def wait_for_worker(self):
        if self.install_worker is not None:
            self.install_worker.cancel.set()
            self.install_worker.wait()
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()

    def check(self, manual=True):
        if self.install_worker is not None:
            return
        if self.checking:
            self.manual = self.manual or manual
            return
        now = time.time()
        if not manual:
            from mtg_print.config import CFG
            if not CFG.UpdateCheckOnStartup or not CFG.OnlineMode:
                return
            try:
                last = float(self.settings.value('lastAttempt', 0))
            except (TypeError, ValueError):
                last = 0
            if (self.settings.value('lastAttemptVersion', '') == APP_VERSION
                    and 0 <= now - last < 6 * 60 * 60):
                return
        elif now - self.last_attempt < 30 and self.result is not None and not self.error:
            self.present_result(manual=True)
            return
        self.last_attempt = now
        self.settings.setValue('lastAttempt', now)
        self.settings.setValue('lastAttemptVersion', APP_VERSION)
        self.manual = manual
        self.error = ''
        self.worker = ReleaseWorker(self)
        self.worker.checked.connect(self.completed)
        self.worker.finished.connect(self.settled)
        self.changed.emit()
        self.worker.start()

    def completed(self, result, error):
        self.result, self.error = result, error

    def settled(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.changed.emit()
        self.present_result(manual=self.manual)

    def present_result(self, *, manual):
        if self.error:
            if manual:
                W.QMessageBox.warning(None, 'Update Check Failed', self.error + '\n\nPlease retry Check for Updates.')
            return
        if self.result and self.result.update_available:
            version = self.result.latest_version
            if manual or self.settings.value('notifiedVersion', '') != version:
                self.settings.setValue('notifiedVersion', version)
                self.show_download()
        elif manual and self.result is not None:
            W.QMessageBox.information(None, 'No Updates Found',
                f"You're up to date.\n\nCurrent version: {APP_VERSION}")

    def activate(self):
        if self.install_worker is not None:
            self.install_worker.cancel.set()
            self.detail = 'Canceling update download…'
            self.changed.emit()
        elif self.checking:
            self.check(manual=True)
        elif self.result and self.result.update_available and not self.error:
            self.show_download()
        else:
            self.check()

    def show_download(self):
        result = self.result
        if not result or not result.asset_url:
            return
        dialog = W.QMessageBox(W.QMessageBox.Icon.Information, 'Update Available',
            f'Installed version: {APP_VERSION}\nAvailable version: {result.latest_version}\n\n'
            'Download and verify the installer, then close Manaforge and install the update. '
            'Your existing data stays in its configured location. Portable folders are preserved.')
        if result.asset_name != 'Manaforge-Setup.exe' or not result.checksum_url:
            dialog.setText(dialog.text() + '\n\nThis legacy release has no verified installer. Check again after an installer release is available.')
            dialog.addButton(W.QMessageBox.StandardButton.Close)
            dialog.exec()
            return
        download = dialog.addButton('Download & Install', W.QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(W.QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() is download:
            self.start_install_worker(InstallWorker(result, parent=self))

    def verify_startup(self, initialize):
        # Capture the previous installed version before successful cleanup removes
        # the updater receipt. This also covers upgrades from before What's New.
        try:
            record = application_install.read_record() or {}
            self.previous_startup_version = record.get('old_version')
        except (OSError, ValueError):
            self.previous_startup_version = None
        self.start_install_worker(InstallWorker(initialize=initialize, parent=self))

    def start_install_worker(self, worker):
        if self.install_worker is not None:
            return
        self.install_worker = worker
        self.install_value, self.install_error = None, ''
        self.error = ''
        self.download_progress = None
        self.phase = 'Verifying startup' if worker.initialize else 'Downloading'
        self.detail = self.phase + '…'
        worker.progress.connect(self.transfer_progress)
        worker.completed.connect(self.install_completed)
        worker.finished.connect(self.install_settled)
        self.changed.emit()
        worker.start()

    def transfer_progress(self, progress):
        self.download_progress = progress
        percent = f'{100 * progress.downloaded / progress.total:.0f}% · ' if progress.total else ''
        total = f' / {progress.total / 1024**2:.1f} MiB' if progress.total else ' MiB'
        speed = f' · {progress.bytes_per_second / 1024**2:.1f} MiB/s' if progress.bytes_per_second > 0 else ''
        self.detail = f'{progress.phase.title()} · {percent}{progress.downloaded / 1024**2:.1f}{total}{speed}'
        self.changed.emit()

    def install_completed(self, value, error):
        self.install_value, self.install_error = value, error

    def install_settled(self):
        worker, self.install_worker = self.install_worker, None
        startup = worker.initialize is not None
        worker.deleteLater()
        self.phase = ''
        self.error = self.install_error
        if startup:
            self.detail = self.install_value or self.error
            if not self.error:
                from .whats_new import whats_new
                whats_new().startup(W.QApplication.activeWindow(),
                    previous=getattr(self, 'previous_startup_version', None))
        elif self.error:
            self.detail = self.error + ' Click to retry.'
        elif self.install_value:
            # Honor each window's unsaved-work and background-job close guards.
            app = W.QApplication.instance()
            app.setQuitOnLastWindowClosed(False)
            app.closeAllWindows()
            if any(window.isVisible() for window in app.topLevelWidgets()):
                self.error = 'Installation postponed. Save your work, then retry the update.'
                self.detail = self.error
                app.setQuitOnLastWindowClosed(True)
            else:
                try:
                    self.phase = 'Installing / Restarting'
                    self.detail = 'Installer ready. Preparing the new version…'
                    application_install.launch(self.install_value)
                except Exception as exc:
                    self.phase = ''
                    self.error = str(exc)
                    self.detail = self.error
                    # Restore the hidden main windows if installer launch fails.
                    for window in app.topLevelWidgets():
                        if isinstance(window, W.QMainWindow):
                            window.show()
                    app.setQuitOnLastWindowClosed(True)
                else:
                    app.quit()
        self.changed.emit()

    def button_text(self):
        if self.phase:
            if self.phase == 'Downloading' and self.download_progress and self.download_progress.total:
                p = self.download_progress
                return f'{p.phase.title()} {100 * p.downloaded / p.total:.0f}% (Cancel)'
            return self.phase + ('… (Cancel)' if self.phase == 'Downloading' else '…')
        if self.error:
            return 'Update Error — Retry'
        if self.checking:
            return 'Checking for Updates...'
        if self.result:
            return 'Update Available' if self.result.update_available else 'Up to Date'
        return 'Check for Updates'


def application_updates():
    app = W.QApplication.instance()
    if not hasattr(app, '_application_updates'):
        app._application_updates = ApplicationUpdates(app)
    return app._application_updates


class ApplicationUpdatePanel(W.QWidget):
    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self.updates = application_updates()
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        self.status.setVisible(not compact)
        self.button = W.QPushButton()
        self.button.clicked.connect(self.updates.activate)
        self.progress = W.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.status)
        layout.addWidget(self.button)
        layout.addWidget(self.progress)
        self.updates.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        updates = self.updates
        available = updates.result and updates.result.update_available and not updates.error
        self.button.setText(updates.button_text())
        self.button.setEnabled(not updates.checking and updates.phase != 'Verifying startup')
        color, hover = ('#B45309', '#92400e') if available else ('#28734f', '#32875f')
        self.button.setStyleSheet(
            f'QPushButton {{background:{color};color:white;border:1px solid {color};'
            'border-radius:6px;padding:8px 16px;}'
            f'QPushButton:hover {{background:{hover};}}'
            'QPushButton:disabled {background:#34483e;color:#d3dfd7;}'
            'QPushButton:focus {border:2px solid white;}')
        self.progress.setVisible(updates.checking or bool(updates.phase))
        p = updates.download_progress
        if updates.phase == 'Downloading' and p and p.total:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(100 * p.downloaded / p.total))
        else:
            self.progress.setRange(0, 0)
        status = f'Installed version: {APP_VERSION}'
        if updates.checking:
            status += ' \u00b7 Checking published releases\u2026'
        elif updates.error:
            status += '\nUpdate check failed: ' + updates.error + ' Retry below.'
        elif updates.result:
            status += f' \u00b7 Latest downloadable version: {updates.result.latest_version}'
            status += ' \u00b7 Update available' if available else ' \u00b7 Up to date'
        else:
            status += ' \u00b7 Updates have not been checked'
        if updates.detail:
            status += '\n' + updates.detail
        self.status.setText(status)
        self.button.setToolTip(status)
        self.button.setAccessibleDescription(status)


class ApplicationUpdateAction(G.QAction):
    """Use the toolbar's own button geometry for the navigation update control."""

    def __init__(self, toolbar):
        super().__init__(toolbar)
        self.updates = application_updates()
        toolbar.addAction(self)
        self.button = toolbar.widgetForAction(self)
        self.toolbar = toolbar
        self.triggered.connect(self.updates.activate)
        self.updates.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        updates = self.updates
        available = updates.result and updates.result.update_available and not updates.error
        self.setText(updates.button_text())
        self.setEnabled(not updates.checking and updates.phase != 'Verifying startup')
        color, hover = ('#B45309', '#92400e') if available else ('#28734f', '#32875f')
        # Override colors only: size, padding, borders and font come from the
        # same toolbar/theme rules as Home and the other navigation actions.
        self.button.setStyleSheet(
            f'QToolButton {{background-color:{color};color:white;}}'
            f'QToolButton:hover {{background-color:{hover};}}'
            'QToolButton:disabled {background-color:#34483e;color:#d3dfd7;}')
        status = f'Installed version: {APP_VERSION}'
        if updates.detail:
            status += '\n' + updates.detail
        if updates.error:
            status += '\nUpdate check failed: ' + updates.error + ' Click to retry.'
        elif updates.result:
            status += f' | Latest downloadable version: {updates.result.latest_version}'
        self.setStatusTip(status)
        window = self.toolbar.window()
        if updates.detail and isinstance(window, W.QMainWindow):
            window.statusBar().showMessage(updates.detail)
        self.button.setAccessibleDescription(status)

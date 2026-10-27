"""Shared application-release state; the portable ZIP workflow leaves installs intact."""
import time
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_proxy.constants import APP_VERSION
from mtg_print import update_service


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
        self.settings = C.QSettings('Manaforge', 'ApplicationUpdates')
        self.last_attempt = 0
        app.aboutToQuit.connect(self.wait_for_worker)

    @property
    def checking(self):
        return self.worker is not None

    def wait_for_worker(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()

    def check(self, manual=True):
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
        if self.checking:
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
            'Download the Windows ZIP using your browser. Download progress appears in the browser. '
            'Wait for the download to finish, then extract the entire ZIP into a NEW folder. '
            'Close Manaforge and run the executable in the new folder. Keep the old folder until '
            'the new version launches successfully; reopen it if installation fails. '
            'Your existing data stays in its configured location.\n\n'
            'The running application remains on its installed version until you launch the new copy.')
        download = dialog.addButton('Download update', W.QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(W.QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() is download:
            if not G.QDesktopServices.openUrl(C.QUrl(result.asset_url)):
                W.QMessageBox.warning(None, 'Download Could Not Start',
                    'Open this URL in your browser to retry:\n' + result.asset_url)


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
        self.button.setText('Checking for Updates...' if updates.checking else
                            'Update Available' if available else 'Check for Updates')
        self.button.setEnabled(not updates.checking)
        color, hover = ('#B45309', '#92400e') if available else ('#28734f', '#32875f')
        self.button.setStyleSheet(
            f'QPushButton {{background:{color};color:white;border:1px solid {color};'
            'border-radius:6px;padding:8px 16px;}'
            f'QPushButton:hover {{background:{hover};}}'
            'QPushButton:disabled {background:#34483e;color:#d3dfd7;}'
            'QPushButton:focus {border:2px solid white;}')
        self.progress.setVisible(updates.checking)
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
        self.triggered.connect(self.updates.activate)
        self.updates.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        updates = self.updates
        available = updates.result and updates.result.update_available and not updates.error
        self.setText('Checking for Updates...' if updates.checking else
                     'Update Available' if available else 'Check for Updates')
        self.setEnabled(not updates.checking)
        color, hover = ('#B45309', '#92400e') if available else ('#28734f', '#32875f')
        # Override colors only: size, padding, borders and font come from the
        # same toolbar/theme rules as Home and the other navigation actions.
        self.button.setStyleSheet(
            f'QToolButton {{background-color:{color};color:white;}}'
            f'QToolButton:hover {{background-color:{hover};}}'
            'QToolButton:disabled {background-color:#34483e;color:#d3dfd7;}')
        status = f'Installed version: {APP_VERSION}'
        if updates.error:
            status += '\nUpdate check failed: ' + updates.error + ' Click to retry.'
        elif updates.result:
            status += f' | Latest downloadable version: {updates.result.latest_version}'
        self.setStatusTip(status)
        self.button.setAccessibleDescription(status)

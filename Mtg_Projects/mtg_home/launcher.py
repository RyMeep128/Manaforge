"""One homepage, reusable in-process tools, and an independent Print Studio."""
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from PyQt6 import QtCore as C, QtNetwork as N, QtWidgets as W
from mtg_core.diagnostics import get_logger
from mtg_core.paths import data_root
from mtg_ui.theme import application_stylesheet
from mtg_ui.tooltips import disable_hover_tooltips
from .modules import MODULES
from .navigation import add_home_action, print_studio_command, request_home


class ModuleController(C.QObject):
    def __init__(self, home, service=None, factories=None):
        super().__init__(home)
        self.home, self._service = home, service
        self.windows = {}
        self.factories = factories or {}
        self.printer = None
        self.printer_log = None
        self.poll = C.QTimer(self)
        self.poll.setInterval(500)
        self.poll.timeout.connect(self.printer_finished)
        home.moduleRequested.connect(self.open_module)
        home.settingsRequested.connect(self.settings)

    @property
    def service(self):
        if self._service is None:
            from mtg_core import get_default_card_service
            self._service = get_default_card_service()
        return self._service

    def show_home(self):
        self.home.showNormal()
        self.home.raise_()
        self.home.activateWindow()

    def open_module(self, key):
        module = next((item for item in MODULES if item.key == key), None)
        if module is None or not module.available:
            return
        try:
            if module.action == 'printer':
                self.open_printer()
                return
            window = self.windows.get(key)
            if window is not None:
                if getattr(window, 'closing', False):
                    self.home.statusBar().showMessage('The tool is finishing its previous session. Please wait.', 4000)
                    return
            else:
                factory = self.factories.get(key)
                if factory:
                    window = factory()
                elif module.action == 'editor':
                    from mtg_editor.gui import EditorWindow
                    window = EditorWindow(service=self.service)
                    add_home_action(window, self.show_home)
                elif module.action == 'rules':
                    from .rules_workspace import RulesWorkspace
                    window = RulesWorkspace(self.service, self.show_home)
                else:
                    return
                window.setAttribute(C.Qt.WidgetAttribute.WA_DeleteOnClose)
                self.windows[key] = window
                window.destroyed.connect(lambda obj=None, module_key=key: self.windows.pop(module_key, None))
            window.showNormal()
            window.raise_()
            window.activateWindow()
        except Exception as exc:
            get_logger(__name__).exception('Module startup failed module=%s', key)
            W.QMessageBox.warning(self.home, 'Could not open ' + module.title, str(exc))

    def open_printer(self):
        address = os.environ.get('MANAFORGE_HOME_SOCKET', '') + '-print'
        if request_home(address):
            return
        if self.printer is not None and self.printer.poll() is None:
            self.home.statusBar().showMessage('Print Studio is already open. Switch to its window to continue.', 5000)
            return
        command, directory = print_studio_command()
        if not getattr(sys, 'frozen', False) and not Path(command[1]).is_file():
            raise FileNotFoundError('The Print Studio entry point could not be found: ' + command[1])
        logs = data_root() / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        self.printer_log = logs / 'print-studio-launch.log'
        environment = os.environ.copy()
        environment['MANAFORGE_PRINTER_SOCKET'] = address
        products = Path(__file__).resolve().parents[1]
        paths = [str(products), str(products / 'mtg_core'), environment.get('PYTHONPATH', '')]
        environment['PYTHONPATH'] = os.pathsep.join(path for path in paths if path)
        with self.printer_log.open('wb') as output:
            self.printer = subprocess.Popen(command, cwd=str(directory), env=environment,
                stdout=output, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.poll.start()
        self.home.statusBar().showMessage('Opening Print Studio…', 4000)

    def printer_finished(self):
        if self.printer is None or self.printer.poll() is None:
            return
        code = self.printer.returncode
        self.poll.stop()
        self.printer = None
        if code:
            details = ''
            try:
                with self.printer_log.open('rb') as log:
                    log.seek(0, 2)
                    log.seek(max(0, log.tell()-3000))
                    details = log.read().decode('utf-8', errors='replace')
            except OSError:
                pass
            W.QMessageBox.warning(self.home, 'Print Studio closed unexpectedly',
                                 f'Exit code {code}.\n\n{details}\n\nLog: {self.printer_log}')

    def settings(self, key):
        try:
            if key == 'printing':
                from mtg_ui.printing_preferences import edit_printing_preferences
                edit_printing_preferences(self.home, self.service)
            elif key == 'artwork':
                from mtg_ui.artwork_preferences import edit_artwork_preferences
                edit_artwork_preferences(self.home, self.service)
        except Exception as exc:
            get_logger(__name__).exception('Homepage settings failed kind=%s', key)
            W.QMessageBox.warning(self.home, 'Could not open settings', str(exc))


def main():
    app = W.QApplication.instance() or W.QApplication(sys.argv)
    app.setApplicationName('Manaforge')
    app.setStyle('Fusion')
    app.setStyleSheet(application_stylesheet())
    disable_hover_tooltips()
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    address = 'manaforge-home-' + sha256(str(root.resolve()).encode()).hexdigest()[:20]
    lock = C.QLockFile(str(root / 'manaforge-home.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if not request_home(address):
            W.QMessageBox.information(None, 'Manaforge', 'Manaforge is already starting or running. Switch to its homepage window.')
        return 0
    server = N.QLocalServer()
    N.QLocalServer.removeServer(address)  # This process owns the matching lock.
    if not server.listen(address):
        W.QMessageBox.warning(None, 'Manaforge startup failed', server.errorString())
        return 1
    os.environ['MANAFORGE_HOME_SOCKET'] = address
    from .home import HomeWindow
    home = HomeWindow()
    controller = ModuleController(home)
    def activate():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            controller.show_home()
            socket.disconnectFromServer()
            socket.deleteLater()
    server.newConnection.connect(activate)
    home.show()
    result = app.exec()
    server.close()
    lock.unlock()
    return result

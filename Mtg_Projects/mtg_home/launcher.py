"""One application window with persistent, lazily created module workspaces."""
from hashlib import sha256
import os
from pathlib import Path
import sys
from PyQt6 import QtCore as C, QtNetwork as N, QtWidgets as W
from mtg_core.diagnostics import get_logger
from mtg_core.paths import data_root
from mtg_ui.theme import application_stylesheet
from mtg_ui.tooltips import disable_hover_tooltips
from .modules import MODULES
from .navigation import request_home


class ModuleController(C.QObject):
    def __init__(self, home, service=None, factories=None):
        super().__init__(home)
        self.home, self._service = home, service
        self.windows = {}
        from mtg_ui.jobs import JobQueue
        self.jobs = JobQueue(self)
        self._installation_engine = None
        self._automatic_update = None
        self.jobs.progress.connect(self.data_progress)
        self.jobs.status.connect(self.data_status)
        self.factories = factories or {}
        home.shutdown_guard = self.shutdown
        home.moduleRequested.connect(self.open_module)
        home.settingsRequested.connect(self.settings)

    @property
    def service(self):
        if self._service is None:
            from mtg_core import get_default_card_service
            self._service = get_default_card_service()
        return self._service

    def show_home(self):
        self.home.show_workspace('home')
        if self.home.isMinimized():
            self.home.setWindowState(self.home.windowState() & ~C.Qt.WindowState.WindowMinimized)
        self.home.show()
        self.home.raise_()
        self.home.activateWindow()

    def open_module(self, key):
        if key == 'home':
            self.show_home()
            return
        module = next((item for item in MODULES if item.key == key), None)
        if module is None or not module.available:
            return
        try:
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
                    window.print_project_handler = self.open_print_project
                elif module.action == 'printer':
                    from .printing import create_print_workspace
                    window = create_print_workspace(self.home)
                elif module.action == 'rules':
                    from .rules_workspace import RulesWorkspace
                    window = RulesWorkspace(self.service, self.show_home)
                else:
                    return
                self.home.add_workspace(key, window)
                self.windows[key] = window
            self.home.show_workspace(key)
        except Exception as exc:
            self.home.navigation[self.home.current_workspace].setChecked(True)
            get_logger(__name__).exception('Module startup failed module=%s', key)
            W.QMessageBox.warning(self.home, 'Could not open ' + module.title, str(exc))

    def open_print_project(self, project):
        self.open_module('print')
        printer = self.windows.get('print')
        if printer is None:
            raise OSError('Print Studio could not be opened.')
        printer.open_managed_project(project['id'])

    def shutdown(self):
        if self.jobs.busy:
            self.jobs.cancel_all()
            self.home.statusBar().showMessage('Cancelling background downloads before closing...')
            C.QTimer.singleShot(250, self.home.close)
            return False
        editor = self.windows.get('editor')
        if editor is not None and hasattr(editor, 'session'):
            busy = (editor.worker is not None or editor.task is not None or editor.thumbnails.worker is not None
                    or editor.recommendation_panel.worker is not None
                    or editor.add_cards_workspace.discovery.controller.worker is not None
                    or editor.add_cards_workspace.card_search.controller.worker is not None
                    or editor.text_view.worker is not None
                    or editor.dashboard.worker is not None)
            if busy:
                self.home.statusBar().showMessage('Finishing background work before closing...')
                C.QTimer.singleShot(250, self.home.close)
                return False
            if editor.session.dirty and not editor.save():
                return False
        rules = self.windows.get('rules')
        if rules is not None and getattr(rules, 'busy', False):
            self.home.statusBar().showMessage('Finishing the rules update before closing...')
            C.QTimer.singleShot(250, self.home.close)
            return False
        printer = self.windows.get('print')
        if printer is not None and hasattr(printer, 'prepare_to_close'):
            if not printer.prepare_to_close():
                self.home.show_workspace('print')
                return False
            printer.setProperty('manaforgePreparedToClose', True)
        # Close the editor first: its asynchronous shutdown can defer the exit.
        ordered = [self.windows[key] for key in ('editor', 'print', 'rules') if key in self.windows]
        for window in ordered:
            window.setProperty('manaforgeQuitting', True)
            if not window.close():
                if getattr(window, 'closing', False):
                    C.QTimer.singleShot(250, self.home.close)
                return False
        context = getattr(printer, '_manaforge_context', None)
        if context is not None:
            context.save()
            app = W.QApplication.instance()
            if getattr(app, '_manaforge_print_context', None) is context:
                del app._manaforge_print_context
        return True

    def settings(self, key):
        try:
            if key == 'printing':
                from mtg_ui.printing_preferences import edit_printing_preferences
                edit_printing_preferences(self.home, self.service)
            elif key == 'artwork':
                from mtg_ui.artwork_preferences import edit_artwork_preferences
                edit_artwork_preferences(self.home, self.service)
            elif key == 'data':
                from mtg_ui.data_management import DataManagementDialog
                DataManagementDialog(self.home,engine=self.installation_engine,jobs=self.jobs).exec()
        except Exception as exc:
            get_logger(__name__).exception('Homepage settings failed kind=%s', key)
            W.QMessageBox.warning(self.home, 'Could not open settings', str(exc))

    @property
    def installation_engine(self):
        if self._installation_engine is None:
            from mtg_core.installation import InstallationEngine
            self._installation_engine = InstallationEngine(service=self._service)
        return self._installation_engine

    def check_data_updates(self):
        from mtg_print.config import CFG
        if self.jobs.busy or not CFG.OnlineMode:
            return
        engine=self.installation_engine
        if engine.needs_update():
            self._automatic_update=self.jobs.submit(lambda cancel,report:engine.run(cancel=cancel,report=report))
            self.home.statusBar().showMessage('Checking library updates in the background…')

    @C.pyqtSlot(str,object)
    def data_progress(self,job_id,value):
        if isinstance(value,dict):
            self.home.statusBar().showMessage(value.get('operation','Updating data…'))

    @C.pyqtSlot(str,str,object)
    def data_status(self,job_id,state,value):
        if state=='failed':
            self.home.statusBar().showMessage('Data update could not finish. Existing data is available. Open Settings → Data Management to retry.',15000)
        elif state=='completed':
            self.home.statusBar().showMessage('Data operation completed.',5000)
            if self._service is not None and hasattr(self._service,'_printings_refreshed'):
                self._service._printings_refreshed.clear()
            editor=self.windows.get('editor')
            if editor is not None and hasattr(editor,'recommendation_panel'):
                editor.thumbnails.cache.clear()
                editor.recommendation_panel.request_refresh()


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
    from mtg_ui.data_management import run_initial_setup
    if not run_initial_setup():
        server.close()
        lock.unlock()
        return 0
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
    update_timer=C.QTimer(controller)
    update_timer.timeout.connect(controller.check_data_updates)
    update_timer.start(6*60*60*1000)
    C.QTimer.singleShot(1000,controller.check_data_updates)
    result = app.exec()
    server.close()
    lock.unlock()
    return result

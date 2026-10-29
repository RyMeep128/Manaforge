"""Homepage and routing regressions; no real module subprocesses or downloads."""
import sys
from pathlib import Path
from PyQt6 import QtCore as C, QtWidgets as W, QtTest
import pytest

from mtg_home.home import HomeWindow
from mtg_home.launcher import ModuleController
from mtg_home.modules import MODULES
from mtg_home.navigation import print_studio_command


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def test_artwork_audit_failures_do_not_open_automatic_update_prompt(app, monkeypatch):
    home = HomeWindow()
    controller = ModuleController(home, service=object())
    prompts = []
    monkeypatch.setattr('mtg_ui.feedback.report_problem', lambda *args: prompts.append(args))
    controller._automatic_update = 'automatic-update'
    controller.data_status('artwork-audit', 'failed', OverflowError('volume ID'))
    assert not prompts
    controller.data_status('automatic-update', 'failed', OSError('offline'))
    assert len(prompts) == 1
    home.shutdown_guard = None
    home.close()


def test_home_registry_disabled_play_keyboard_and_responsive_layout(app, monkeypatch):
    monkeypatch.setenv('MANAFORGE_ENABLE_LOCAL_PLAY', '0')
    home = HomeWindow()
    activated = []
    home.moduleRequested.connect(activated.append)
    assert len(MODULES) == 5
    assert home.tiles['library'].isEnabled()
    assert not home.tiles['play'].isEnabled()
    home.tiles['play'].click()
    assert not activated
    home.show()
    home.tiles['editor'].setFocus()
    QtTest.QTest.keyClick(home.tiles['editor'], C.Qt.Key.Key_Return)
    assert activated == ['editor']
    home.resize(600, 650)
    app.processEvents()
    assert home._columns == 1
    home.resize(1100, 800)
    app.processEvents()
    assert home._columns == 2
    home.close()


def test_controller_reuses_workspaces_inside_the_same_window(app, monkeypatch):
    monkeypatch.setenv('MANAFORGE_ENABLE_LOCAL_PLAY', '0')
    home = HomeWindow()
    created = []
    def factory():
        window = W.QMainWindow()
        created.append(window)
        return window
    controller = ModuleController(home, service=object(), factories={'editor': factory, 'rules': factory})
    home.show()
    controller.open_module('editor')
    controller.open_module('editor')
    controller.open_module('rules')
    controller.open_module('play')
    assert len(created) == 2
    assert home.isVisible()
    assert all(not window.isWindow() and window.window() is home for window in created)
    editor = controller.windows['editor']
    editor.setProperty('retainedState', 'my deck')
    controller.show_home()
    assert home.pages.currentWidget() is home.home_page
    controller.open_module('editor')
    assert controller.windows['editor'] is editor
    assert editor.property('retainedState') == 'my deck'
    assert len(created) == 2
    home.close()


def test_editor_publication_routes_to_existing_browse_workspace_without_uploading(app):
    from types import SimpleNamespace
    home = HomeWindow()
    calls = []
    def factory():
        window = W.QMainWindow()
        window.publishing = SimpleNamespace(prepare=lambda deck, color: calls.append((deck, color)))
        return window
    controller = ModuleController(home, service=object(), factories={'library': factory})
    controller.publish_deck({'name': 'Snapshot'}, 'U')
    controller.publish_deck({'name': 'Second snapshot'}, 'R')
    assert len(controller.windows) == 1
    assert calls == [({'name': 'Snapshot'}, 'U'), ({'name': 'Second snapshot'}, 'R')]
    assert home.current_workspace == 'library'
    home.close()


def test_print_command_reuses_environment_and_ignores_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    command, directory = print_studio_command('deck.json')
    assert Path(command[0]).parent == Path(sys.executable).parent
    assert Path(command[1]).is_absolute() and Path(command[1]).is_file()
    assert directory.name == 'mtg_proxy'
    assert command[-2:] == ['--open-project', 'deck.json']
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    command, directory = print_studio_command('deck.json')
    assert command == [sys.executable, '--print-studio', '--open-project', 'deck.json']


def test_printer_reuses_an_embedded_workspace_without_spawning(app, monkeypatch):
    import subprocess
    def no_process(*args, **kwargs):
        pytest.fail('Unified navigation must not start another process')
    monkeypatch.setattr(subprocess, 'Popen', no_process)
    created = []
    class Printer(W.QMainWindow):
        def open_managed_project(self, key):
            self.project_key = key
    def factory():
        printer = Printer()
        created.append(printer)
        return printer
    home = HomeWindow()
    controller = ModuleController(home, service=object(), factories={'print': factory})
    home.show()
    controller.open_module('print')
    controller.show_home()
    controller.open_print_project({'id': 'deck-print'})
    assert len(created) == 1
    assert created[0].window() is home and not created[0].isWindow()
    assert created[0].project_key == 'deck-print'
    home.close()


def test_print_context_reuses_qapplication_and_finds_embedded_boundary(app):
    from main_window import PrintApplicationContext
    from mtg_ui.workspaces import print_application, print_workspace
    context = PrintApplicationContext()
    root = W.QMainWindow()
    workspace = W.QMainWindow(root)
    workspace.setWindowFlags(C.Qt.WindowType.Widget)
    workspace.setProperty('manaforgeEmbedded', True)
    workspace.setProperty('printWorkspace', True)
    child = W.QWidget(workspace)
    context.set_window(workspace)
    app._manaforge_print_context = context
    try:
        assert W.QApplication.instance() is app
        assert print_application() is context
        assert print_workspace(child) is workspace
        assert child.window() is root
    finally:
        del app._manaforge_print_context
        root.close()



def test_module_failure_keeps_home_open(app, monkeypatch):
    def fail():
        raise RuntimeError('startup fixture')
    messages = []
    monkeypatch.setattr(W.QMessageBox, 'warning', lambda *args: messages.append(args))
    home = HomeWindow()
    home.show()
    controller = ModuleController(home, service=object(), factories={'editor': fail})
    controller.open_module('editor')
    assert messages and 'startup fixture' in messages[0][-1]
    assert home.isVisible()
    home.close()


def test_failed_print_save_keeps_the_shared_application_open(app):
    class Printer(W.QMainWindow):
        ready = False

        def prepare_to_close(self):
            return self.ready
    home = HomeWindow()
    controller = ModuleController(home, service=object(), factories={'print': Printer})
    home.show()
    controller.open_module('print')
    assert not home.close()
    assert home.isVisible()
    controller.windows['print'].ready = True
    assert home.close()


def test_embedded_rules_close_returns_home_without_discarding_workspace(app, monkeypatch):
    from mtg_ui.rules_reference import RulesBrowser
    from mtg_home.rules_workspace import RulesWorkspace
    class Service:
        def rules_index(self):
            return {'metadata': None, 'sections': [], 'keywords': []}
    def synchronous(self, work, callback):
        self.token += 1
        callback(self.token, work(), '')
    monkeypatch.setattr(RulesBrowser, 'submit', synchronous)
    returned = []
    workspace = RulesWorkspace(Service(), lambda: returned.append(True))
    workspace.setProperty('manaforgeEmbedded', True)
    workspace.reject()
    assert returned == [True] and not workspace._closed
    workspace.setProperty('manaforgeQuitting', True)
    workspace.reject()
    assert workspace._closed


def test_created_deck_upload_uses_selected_library_and_existing_publisher(app):
    from types import SimpleNamespace
    home = HomeWindow()
    calls = []
    def factory():
        window = W.QMainWindow()
        def prepare(deck, color):
            calls.append(('prepare', deck['name'], color))
            return True
        window.publishing = SimpleNamespace(
            prepare=prepare,
            use_connection=lambda key: calls.append(('destination', key)),
            publish_button=SimpleNamespace(isEnabled=lambda: True),
            publish=lambda: calls.append(('upload',)))
        return window
    controller = ModuleController(home, service=object(), factories={'library': factory})
    controller.publish_deck({'name': 'New deck', 'library_association': {'id': 'friends'}}, 'U', upload=True)
    assert calls == [('prepare', 'New deck', 'U'), ('destination', 'friends'), ('upload',)]
    home.close()


def test_copy_routes_immediately_to_editor_and_preserves_saved_file_on_cancel(app, tmp_path):
    home = HomeWindow()
    calls = []
    path = tmp_path / 'copy.manaforge.json'
    path.write_text('{}')
    def factory():
        window = W.QMainWindow()
        window.open_path = lambda selected: calls.append(selected)  # Models an editor declining to replace its dirty deck.
        return window
    controller = ModuleController(home, service=object(), factories={'editor': factory})
    controller.open_copied_deck(path)
    assert home.current_workspace == 'editor'
    assert calls == [path]
    assert path.exists()
    home.close()

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


def test_home_registry_disabled_play_keyboard_and_responsive_layout(app):
    home = HomeWindow()
    activated = []
    home.moduleRequested.connect(activated.append)
    assert len(MODULES) == 4
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


def test_controller_reuses_editor_and_rules_without_closing_home(app):
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
    assert all(window.isVisible() for window in created)
    for window in list(controller.windows.values()):
        window.close()
    C.QCoreApplication.sendPostedEvents(None, C.QEvent.Type.DeferredDelete)
    assert not controller.windows
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


def test_printer_is_started_once_and_uses_existing_data_environment(app, monkeypatch, tmp_path):
    import mtg_home.launcher as launcher
    monkeypatch.setenv('PRINT_PROXY_PREP_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(launcher, 'request_home', lambda address: False)
    calls = []
    class Process:
        def poll(self):
            return None
    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        return Process()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    home = HomeWindow()
    controller = ModuleController(home, service=object())
    controller.open_module('print')
    controller.open_module('print')
    assert len(calls) == 1
    assert calls[0][1]['env']['PRINT_PROXY_PREP_DATA_DIR'] == str(tmp_path)
    assert calls[0][1]['env']['MANAFORGE_PRINTER_SOCKET'].endswith('-print')
    assert Path(calls[0][1]['cwd']).name == 'mtg_proxy'
    controller.poll.stop()
    home.close()


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

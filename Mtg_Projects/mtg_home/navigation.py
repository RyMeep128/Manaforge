"""Shared Home action and printer command for source and packaged entry points."""
import os
from pathlib import Path
import sys
from PyQt6 import QtNetwork as N, QtWidgets as W


def request_home(address=None):
    address = address or os.environ.get('MANAFORGE_HOME_SOCKET')
    if not address:
        return False
    socket = N.QLocalSocket()
    socket.connectToServer(address)
    if not socket.waitForConnected(250):
        return False
    socket.write(b'home')
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    return True


def add_home_action(window, callback=None):
    def home():
        if callback is not None:
            callback()
        elif not request_home():
            W.QMessageBox.information(window, 'Manaforge Home', 'Open Launch Manaforge to return to the homepage. Your current project will remain open.')
    action = window.menuBar().addAction('Home')
    action.setShortcut('Ctrl+Shift+H')
    action.triggered.connect(home)
    return action


def print_studio_command(project_path=None):
    if getattr(sys, 'frozen', False):
        command, directory = [sys.executable, '--print-studio'], Path(sys.executable).resolve().parent
    else:
        directory = Path(__file__).resolve().parents[1] / 'mtg_proxy'
        python = Path(sys.executable)
        if python.name.casefold() == 'pythonw.exe' and python.with_name('python.exe').exists():
            python = python.with_name('python.exe')
        command = [str(python), str(directory / 'main.py')]
    if project_path:
        command.extend(['--open-project', str(project_path)])
    return command, directory


def register_print_window(window, app):
    """Enable Home and refocusing only for launcher-managed printer windows."""
    if not os.environ.get('MANAFORGE_HOME_SOCKET'):
        return
    add_home_action(window)
    from PyQt6 import QtNetwork as N
    server = N.QLocalServer(app)
    address = os.environ.get('MANAFORGE_PRINTER_SOCKET')
    if not address or not server.listen(address):
        server.deleteLater()
        return
    def activate():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            window.showNormal()
            window.raise_()
            window.activateWindow()
            socket.disconnectFromServer()
            socket.deleteLater()
    server.newConnection.connect(activate)
    app._manaforge_navigation_server = server

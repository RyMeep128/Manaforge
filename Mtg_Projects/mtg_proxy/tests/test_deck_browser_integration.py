from pathlib import Path
from types import SimpleNamespace
from PyQt6 import QtWidgets as W, QtCore as C


def test_proxy_dashboard_opens_shared_browser_and_editor(monkeypatch, tmp_path):
    import editor_widgets
    from mtg_editor import project_browser, gui
    app = W.QApplication.instance() or W.QApplication([])
    path = tmp_path / 'deck.manaforge.json'
    observed = []
    class Browser:
        def __init__(self, *args):
            self.path = path
        def exec(self):
            return W.QDialog.DialogCode.Accepted
    class Editor(W.QWidget):
        def open_path(self, target):
            observed.append(target)
    monkeypatch.setattr(project_browser, 'ProjectBrowser', Browser)
    monkeypatch.setattr(gui, 'EditorWindow', Editor)
    application = SimpleNamespace(check_for_updates=lambda **kw: None, open_blank_editor=lambda: None, resume_draft=lambda: None)
    dashboard = editor_widgets.ProjectDashboardPage(application)
    dashboard.open_deck_library()
    assert observed == [path] and len(dashboard._deck_windows) == 1
    dashboard._deck_windows[0].close()
    C.QCoreApplication.sendPostedEvents(None, C.QEvent.Type.DeferredDelete)
    assert not dashboard._deck_windows
    dashboard.close()
    app.processEvents()

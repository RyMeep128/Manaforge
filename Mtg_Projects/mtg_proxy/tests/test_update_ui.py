from services.update_service import UpdateCheckResult
import main_window


def test_update_check_is_available_on_projects_and_editor():
    from types import SimpleNamespace
    from PyQt6 import QtWidgets
    from editor_widgets import ProjectDashboardPage
    from models import ProjectState

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    calls = []
    application = SimpleNamespace(
        check_for_updates=lambda manual: calls.append(manual),
        open_blank_editor=lambda: None,
        show_home=lambda: None,
    )
    dashboard = ProjectDashboardPage(application)
    button = next(button for button in dashboard.findChildren(QtWidgets.QPushButton)
                  if button.text() == 'Check for updates')
    button.click()
    editor = main_window.AppShellWindow._build_editor_page(
        SimpleNamespace(_application=application), ProjectState(), {})
    more = next(button for button in editor.findChildren(QtWidgets.QToolButton)
                if button.text() == 'More')
    action = next(action for action in more.menu().actions()
                  if action.text() == 'Check for updates…')
    action.trigger()
    assert calls == [True, True]
    dashboard.deleteLater()
    editor.deleteLater()
    app.processEvents()


class _FakeWindow:
    def __init__(self):
        self.calls = []

    def check_for_updates(self, manual=True):
        self.calls.append(manual)


def test_startup_update_check_respects_setting(monkeypatch):
    window = _FakeWindow()
    monkeypatch.setattr(main_window.CFG, "UpdateCheckOnStartup", True)

    main_window.AppShellWindow.check_for_updates_on_startup(window)

    assert window.calls == [False]

    monkeypatch.setattr(main_window.CFG, "UpdateCheckOnStartup", False)
    main_window.AppShellWindow.check_for_updates_on_startup(window)

    assert window.calls == [False]


def test_manual_update_failure_warns(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    main_window.AppShellWindow._handle_update_check_finished(
        object(), None, "network down", True
    )

    assert warnings == [("Update Check Failed", "Could not check for updates.\n\nnetwork down")]


def test_startup_update_failure_stays_quiet(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    main_window.AppShellWindow._handle_update_check_finished(
        object(), None, "network down", False
    )

    assert warnings == []


def test_manual_no_update_shows_up_to_date(monkeypatch):
    infos = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "information",
        lambda _parent, title, message: infos.append((title, message)),
    )

    result = UpdateCheckResult(
        current_version="0.1.0",
        latest_version="0.1.0",
        update_available=False,
        release_url="https://github.test/release",
    )
    main_window.AppShellWindow._handle_update_check_finished(object(), result, "", True)

    assert infos == [("No Updates Found", "You're up to date.\n\nCurrent version: 0.1.0")]


def test_update_found_dialog_includes_versions_and_release_url(monkeypatch):
    infos = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "information",
        lambda _parent, title, message: infos.append((title, message)),
    )

    result = UpdateCheckResult(
        current_version="0.1.0",
        latest_version="0.1.1",
        update_available=True,
        release_url="https://github.test/release",
        asset_name="PrintProxyPrep-0.1.1-win.zip",
        asset_url="https://github.test/download.zip",
    )
    main_window.AppShellWindow._handle_update_check_finished(object(), result, "", True)

    title, message = infos[0]
    assert title == "Update Available"
    assert "Current version: 0.1.0" in message
    assert "Latest version: 0.1.1" in message
    assert "https://github.test/release" in message
    assert "https://github.test/download.zip" in message


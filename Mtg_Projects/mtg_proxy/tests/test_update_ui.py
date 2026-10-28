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
        resume_draft=lambda: None,
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
    menu_labels = [action.text() for action in more.menu().actions()]
    assert any(label.startswith('Export sheets or cards') for label in menu_labels)
    assert any(label.startswith('Apply print preset') for label in menu_labels)
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
    from types import SimpleNamespace
    from mtg_ui import whats_new
    monkeypatch.setattr(whats_new, 'whats_new', lambda: SimpleNamespace(startup=lambda parent: None))
    window = _FakeWindow()
    monkeypatch.setattr(main_window.CFG, "UpdateCheckOnStartup", True)

    main_window.AppShellWindow.check_for_updates_on_startup(window)

    assert window.calls == [False]

    monkeypatch.setattr(main_window.CFG, "UpdateCheckOnStartup", False)
    main_window.AppShellWindow.check_for_updates_on_startup(window)

    assert window.calls == [False]


def test_panels_share_state_and_show_check_error(monkeypatch):
    from PyQt6 import QtWidgets
    from mtg_ui import application_updates as ui
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ui.ApplicationUpdates(app)
    monkeypatch.setattr(ui, 'application_updates', lambda: controller)
    first, second = ui.ApplicationUpdatePanel(), ui.ApplicationUpdatePanel()
    assert first.button.text() == 'Check for Updates'
    assert '#28734f' in first.button.styleSheet()
    controller.result = UpdateCheckResult('0.3.29-alpha.1', '0.3.30-alpha.1', True,
                                         'https://github.test/release',
                                         'Manaforge-Windows.zip', 'https://github.test/app.zip')
    controller.changed.emit()
    assert first.button.text() == second.button.text() == 'Update Available'
    assert '#B45309' in first.button.styleSheet()
    controller.error = 'network down'
    controller.result = None
    controller.changed.emit()
    assert 'network down' in first.status.text()
    assert 'Up to date' not in first.status.text()
    assert first.button.isEnabled()
    first.deleteLater()
    second.deleteLater()
    controller.deleteLater()
    app.processEvents()


def test_manual_and_automatic_checks_do_not_duplicate_worker(monkeypatch):
    from PyQt6 import QtWidgets
    from mtg_ui import application_updates as ui
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ui.ApplicationUpdates(app)
    controller.worker = object()
    controller.check(manual=False)
    controller.check(manual=True)
    assert controller.manual
    controller.worker = None
    controller.deleteLater()
    app.processEvents()


def test_cached_manual_check_still_shows_result(monkeypatch):
    from PyQt6 import QtWidgets
    from mtg_ui import application_updates as ui
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ui.ApplicationUpdates(app)
    controller.result = UpdateCheckResult('0.3.37-alpha.1', '0.3.37-alpha.1', False, '')
    controller.last_attempt = ui.time.time()
    messages = []
    monkeypatch.setattr(ui.W.QMessageBox, 'information',
                        lambda parent, title, message: messages.append((title, message)))
    controller.activate()
    assert controller.worker is None
    assert messages[0][0] == 'No Updates Found'
    assert "You're up to date" in messages[0][1]
    controller.deleteLater()
    app.processEvents()


def test_navigation_update_uses_native_toolbar_action(monkeypatch):
    from PyQt6 import QtWidgets
    from mtg_ui import application_updates as ui
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ui.ApplicationUpdates(app)
    monkeypatch.setattr(ui, 'application_updates', lambda: controller)
    calls = []
    monkeypatch.setattr(controller, 'activate', lambda: calls.append(True))
    toolbar = QtWidgets.QToolBar()
    home = toolbar.addAction('Home')
    action = ui.ApplicationUpdateAction(toolbar)
    assert type(toolbar.widgetForAction(home)) is type(action.button)
    assert 'padding' not in action.button.styleSheet()
    assert 'min-height' not in action.button.styleSheet()
    action.button.click()
    assert calls == [True]
    toolbar.deleteLater()
    controller.deleteLater()
    app.processEvents()


def test_download_progress_and_cancel_are_shared(monkeypatch):
    from types import SimpleNamespace
    import threading
    from PyQt6 import QtWidgets
    from mtg_core.downloads import DownloadProgress
    from mtg_ui import application_updates as ui
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    controller = ui.ApplicationUpdates(app)
    monkeypatch.setattr(ui, 'application_updates', lambda: controller)
    first, second = ui.ApplicationUpdatePanel(), ui.ApplicationUpdatePanel()
    cancel = threading.Event()
    controller.install_worker = SimpleNamespace(cancel=cancel)
    controller.phase = 'Downloading'
    controller.transfer_progress(DownloadProgress(1024**2, 2 * 1024**2, 1024**2))
    assert first.progress.value() == second.progress.value() == 50
    assert '50%' in first.button.text()
    assert 'MiB/s' in first.status.text()
    first.button.click()
    assert cancel.is_set()
    controller.install_worker = None
    first.deleteLater()
    second.deleteLater()
    controller.deleteLater()
    app.processEvents()

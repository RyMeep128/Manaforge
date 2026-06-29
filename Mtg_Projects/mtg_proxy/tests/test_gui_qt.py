import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import editor_widgets
import gui_qt
from models import ProjectState
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget


_QT_APP = None


def _qt_app():
    global _QT_APP
    app = QApplication.instance()
    if app is None:
        _QT_APP = QApplication([])
        return _QT_APP
    return app


class _FakeApplication:
    def __init__(self, json_path):
        self._json_path = json_path
        self.warnings = []

    def json_path(self):
        return self._json_path

    def set_json_path(self, json_path):
        self._json_path = json_path

    def warn_nonfatal(self, title, message):
        self.warnings.append((title, message))


def test_load_project_file_updates_active_json_path_on_success(monkeypatch):
    app = _FakeApplication("old.json")

    monkeypatch.setattr(
        gui_qt.project_service,
        "load_project",
        lambda pd, id_, path, print_fn, warn_fn=None: True,
    )

    loaded = gui_qt.load_project_file(
        app, {}, {}, "new.json", lambda _message: None
    )

    assert loaded is True
    assert app.json_path() == "new.json"


def test_load_project_file_keeps_active_json_path_on_failure(monkeypatch):
    app = _FakeApplication("old.json")

    monkeypatch.setattr(
        gui_qt.project_service,
        "load_project",
        lambda pd, id_, path, print_fn, warn_fn=None: False,
    )

    loaded = gui_qt.load_project_file(
        app, {}, {}, "broken.json", lambda _message: None
    )

    assert loaded is False
    assert app.json_path() == "old.json"


def test_remove_card_from_project_state_cleans_up_related_metadata():
    print_dict = {
        "cards": {"card-a.png": 2, "card-b.png": 1},
        "backsides": {"card-a.png": "__back.png"},
        "backside_short_edge": {"card-a.png": True},
        "oversized": {"card-a.png": True},
        "high_res_front_overrides": {"card-a.png": {"dpi": 600}},
    }

    gui_qt.remove_card_from_project_state(print_dict, "card-a.png")

    assert print_dict["cards"] == {"card-b.png": 1}
    assert print_dict["backsides"] == {}
    assert print_dict["backside_short_edge"] == {}
    assert print_dict["oversized"] == {}
    assert print_dict["high_res_front_overrides"] == {}


def test_remove_card_from_project_state_accepts_project_state():
    state = ProjectState.from_dict(
        {
            "cards": {"card-a.png": 2, "card-b.png": 1},
            "backsides": {"card-a.png": "__back.png"},
            "backside_short_edge": {"card-a.png": True},
            "oversized": {"card-a.png": True},
            "high_res_front_overrides": {"card-a.png": {"dpi": 600}},
        }
    )

    gui_qt.remove_card_from_project_state(state, "card-a.png")

    assert state.cards == {"card-b.png": 1}
    assert state.backsides == {}
    assert state.backside_short_edge == {}
    assert state.oversized == {}
    assert state.high_res_front_overrides_dict() == {}


def test_delete_project_with_confirmation_only_runs_after_confirmation(monkeypatch):
    class _FakeDashboardApp:
        def __init__(self):
            self.warnings = []

        def warn_nonfatal(self, title, message):
            self.warnings.append((title, message))

    app = _FakeDashboardApp()
    refreshed = []
    monkeypatch.setattr(
        gui_qt.project_library,
        "get_project",
        lambda project_id: {"id": project_id, "display_name": "Alpha"},
    )

    deleted = []
    monkeypatch.setattr(
        gui_qt.project_library,
        "remove_project",
        lambda project_id: deleted.append(project_id) or True,
    )

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    gui_qt.delete_project_with_confirmation(
        None, app, "project-1", lambda: refreshed.append(True)
    )
    assert deleted == []
    assert refreshed == []

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    gui_qt.delete_project_with_confirmation(
        None, app, "project-1", lambda: refreshed.append(True)
    )
    assert deleted == ["project-1"]
    assert refreshed == [True]


def test_lazy_print_preview_builds_only_when_preview_tab_is_selected(monkeypatch):
    _qt_app()
    constructed = []
    refreshed = []

    class _FakePrintPreview(QWidget):
        def __init__(self, print_dict, img_dict):
            super().__init__()
            constructed.append((print_dict, img_dict))

        def refresh(self, print_dict, img_dict):
            refreshed.append((print_dict, img_dict))

    monkeypatch.setattr(editor_widgets, "PrintPreview", _FakePrintPreview)

    state = ProjectState()
    img_dict = {}
    scroll_area = QWidget()
    preview_tab = editor_widgets.LazyPrintPreview(state, img_dict)
    tabs = editor_widgets.CardTabs(state, img_dict, scroll_area, preview_tab)

    assert constructed == []
    assert preview_tab.is_loaded() is False

    tabs.setCurrentIndex(1)

    assert len(constructed) == 1
    assert preview_tab.is_loaded() is True

    tabs.refresh_preview(state, img_dict)

    assert len(constructed) == 1
    assert len(refreshed) == 1


def test_lazy_print_preview_cancelled_oversized_warning_stops_loading(monkeypatch):
    _qt_app()
    constructed = []
    confirm_calls = []

    class _FakePrintPreview(QWidget):
        def __init__(self, print_dict, img_dict):
            super().__init__()
            constructed.append((print_dict, img_dict))

    monkeypatch.setattr(editor_widgets, "PrintPreview", _FakePrintPreview)
    monkeypatch.setattr(
        editor_widgets,
        "confirm_oversized_landscape_if_needed",
        lambda *args, **kwargs: confirm_calls.append((args, kwargs)) or False,
    )

    state = ProjectState.from_dict(
        {
            "orient": "Portrait",
            "cards": {"oversized-a.png": 1},
            "oversized_enabled": True,
            "oversized": {"oversized-a.png": True},
        }
    )
    img_dict = {}
    scroll_area = QWidget()
    preview_tab = editor_widgets.LazyPrintPreview(state, img_dict)
    tabs = editor_widgets.CardTabs(state, img_dict, scroll_area, preview_tab)

    tabs.setCurrentIndex(1)

    assert len(confirm_calls) == 1
    assert constructed == []
    assert preview_tab.is_loaded() is False


def test_oversized_warning_switches_to_landscape_and_refreshes(monkeypatch):
    class _FakeMessageBox:
        class Icon:
            Warning = object()

        class ButtonRole:
            AcceptRole = object()
            ActionRole = object()

        class StandardButton:
            Cancel = object()

        def __init__(self, parent):
            self.parent = parent
            self._clicked_button = None
            self._switch_button = None

        def setIcon(self, icon):
            self.icon = icon

        def setWindowTitle(self, title):
            self.title = title

        def setText(self, text):
            self.text = text

        def setInformativeText(self, text):
            self.informative_text = text

        def addButton(self, text, role=None):
            if text == "Switch to Landscape":
                self._switch_button = text
            return text

        def setDefaultButton(self, button):
            self.default_button = button

        def exec(self):
            self._clicked_button = self._switch_button

        def clickedButton(self):
            return self._clicked_button

    class _FakeWindow:
        def __init__(self):
            self.refreshed_widgets = []
            self.refreshed_previews = []

        def refresh_widgets(self, state):
            self.refreshed_widgets.append(state.orient)

        def refresh_preview(self, state, img_dict):
            self.refreshed_previews.append((state.orient, img_dict))

    class _FakeParent:
        def __init__(self, window):
            self._window = window

        def window(self):
            return self._window

    monkeypatch.setattr(editor_widgets, "QMessageBox", _FakeMessageBox)

    window = _FakeWindow()
    state = ProjectState.from_dict(
        {
            "orient": "Portrait",
            "cards": {"oversized-a.png": 1},
            "oversized_enabled": True,
            "oversized": {"oversized-a.png": True},
        }
    )
    img_dict = {}

    result = editor_widgets.confirm_oversized_landscape_if_needed(
        _FakeParent(window),
        state,
        img_dict,
    )

    assert result is True
    assert state.orient == "Landscape"
    assert window.refreshed_widgets == ["Landscape"]
    assert window.refreshed_previews == [("Landscape", img_dict)]


def test_save_pdf_cancelled_oversized_warning_stops_before_file_dialog(monkeypatch):
    _qt_app()
    confirm_calls = []

    class _FakeActionsApplication(_FakeApplication):
        _debug_mode = False

        def show_home(self):
            pass

        def import_and_open_project(self, json_path):
            pass

        def save_active_project(self, state):
            return None

    monkeypatch.setattr(
        editor_widgets,
        "confirm_oversized_landscape_if_needed",
        lambda *args, **kwargs: confirm_calls.append((args, kwargs)) or False,
    )
    monkeypatch.setattr(
        editor_widgets.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("file dialog opened")),
    )

    state = ProjectState.from_dict(
        {
            "orient": "Portrait",
            "cards": {"oversized-a.png": 1},
            "oversized_enabled": True,
            "oversized": {"oversized-a.png": True},
        }
    )
    widget = editor_widgets.ActionsWidget(_FakeActionsApplication("project.json"), state, {})

    widget._render_button.click()

    assert len(confirm_calls) == 1

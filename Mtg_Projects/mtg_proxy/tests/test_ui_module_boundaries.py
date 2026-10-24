import dialogs
import editor_widgets
from mtg_ui import print_dialogs


def test_dialogs_exports_real_helpers():
    assert callable(dialogs.load_project_file)
    assert callable(dialogs.delete_project_with_confirmation)
    assert callable(dialogs.remove_card_from_project_state)
    assert dialogs is print_dialogs
    assert dialogs.AddCardDialog is print_dialogs.AddCardDialog
    assert dialogs.HighResPickerDialog is print_dialogs.HighResPickerDialog


def test_editor_widgets_exports_real_widgets():
    assert editor_widgets.EditorPage.__module__ == "editor_widgets"
    assert editor_widgets.ProjectDashboardPage.__module__ == "editor_widgets"
    assert editor_widgets.OptionsWidget.__module__ == "editor_widgets"


def test_editor_widgets_autosave_helper_uses_managed_session_hook(monkeypatch):
    class _FakeApplication:
        def __init__(self):
            self.autosave_calls = 0

        def autosave_managed_session(self):
            self.autosave_calls += 1

    app = _FakeApplication()
    monkeypatch.setattr(editor_widgets.QApplication, "instance", lambda: app)

    editor_widgets.autosave_managed_session()

    assert app.autosave_calls == 1
